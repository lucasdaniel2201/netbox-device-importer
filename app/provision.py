"""Descoberta do ambiente NetBox e (depois) resolucao de referencias.

Fase 0 do projeto: antes de mapear a planilha, precisamos ver a realidade da
instancia - quais sites, roles, device-types, tags e custom fields existem e,
principalmente, **quais campos** cada endpoint aceita e **quais acoes o token
pode executar**. O schema autoritativo vem do OPTIONS de cada endpoint (nao da
documentacao publica, que e de outra versao).

Formatos que a instancia devolve (confirmado na 4.3.6): o DRF lista os campos
DIRETO sob a acao (`actions.POST.<campo>`), sem um envelope `properties`.

Tudo aqui e somente leitura.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.netbox_client import NetBoxClient, NetBoxConnectionError, NetBoxTLSError

# Objetos de referencia: conjuntos pequenos, listamos todos.
REFERENCE_ENDPOINTS: dict[str, str] = {
    "sites": "/api/dcim/sites/",
    "locations": "/api/dcim/locations/",
    "regions": "/api/dcim/regions/",
    "site_groups": "/api/dcim/site-groups/",
    "racks": "/api/dcim/racks/",
    "device_roles": "/api/dcim/device-roles/",
    "manufacturers": "/api/dcim/manufacturers/",
    "device_types": "/api/dcim/device-types/",
    "tags": "/api/extras/tags/",
    "tenants": "/api/tenancy/tenants/",
}

# Objetos potencialmente grandes: so a contagem interessa.
COUNT_ENDPOINTS: dict[str, str] = {
    "devices": "/api/dcim/devices/",
    "interfaces": "/api/dcim/interfaces/",
    "ip_addresses": "/api/ipam/ip-addresses/",
    "prefixes": "/api/ipam/prefixes/",
    "journal_entries": "/api/extras/journal-entries/",
}

# Endpoints cujo OPTIONS define o mapeamento (campos, obrigatorios, opcoes) e,
# de quebra, o que o token pode escrever em cada um.
SCHEMA_ENDPOINTS: dict[str, str] = {
    "device": "/api/dcim/devices/",
    "device_type": "/api/dcim/device-types/",
    "manufacturer": "/api/dcim/manufacturers/",
    "device_role": "/api/dcim/device-roles/",
    "site": "/api/dcim/sites/",
    "location": "/api/dcim/locations/",
    "tenant": "/api/tenancy/tenants/",
    "interface": "/api/dcim/interfaces/",
    "ip_address": "/api/ipam/ip-addresses/",
    "tag": "/api/extras/tags/",
}

# O caminho dos content types mudou de nome em algumas versoes; tentamos os dois.
CONTENT_TYPES_ENDPOINTS: tuple[str, ...] = (
    "/api/extras/content-types/",
    "/api/extras/object-types/",
)
CUSTOM_FIELDS_ENDPOINT = "/api/extras/custom-fields/"

# Endpoints de escrita usados pela importacao.
DEVICE_ENDPOINT = "/api/dcim/devices/"
INTERFACE_ENDPOINT = "/api/dcim/interfaces/"
IP_ADDRESS_ENDPOINT = "/api/ipam/ip-addresses/"
REFERENCE_WRITE_ENDPOINTS: dict[str, str] = {
    "manufacturer": "/api/dcim/manufacturers/",
    "device_type": "/api/dcim/device-types/",
    "device_role": "/api/dcim/device-roles/",
    "site": "/api/dcim/sites/",
}

# Tipo da interface criada para a camera (choice do NetBox: 1000BASE-T).
DEFAULT_INTERFACE_NAME = "eth0"
DEFAULT_INTERFACE_TYPE = "1000base-t"

# Campos do device comparados para decidir entre "ja existe" e "atualizar".
COMPARE_FIELDS: tuple[str, ...] = (
    "name",
    "status",
    "description",
    "comments",
    "site",
    "role",
    "device_type",
)


def summarize_object(obj: dict[str, Any]) -> dict[str, Any]:
    """Resumo enxuto de um objeto de referencia (id + rotulo + contexto)."""
    label = (
        obj.get("name")
        or obj.get("model")
        or obj.get("address")
        or obj.get("slug")
        or ""
    )
    summary: dict[str, Any] = {"id": obj.get("id"), "label": str(label)}
    if obj.get("slug"):
        summary["slug"] = obj["slug"]
    for related in ("manufacturer", "site", "region", "role", "tenant"):
        value = obj.get(related)
        if isinstance(value, dict) and value.get("name"):
            summary[related] = value["name"]
    return summary


def _content_type_map(client: NetBoxClient) -> dict[int, str]:
    """id do content type -> "app_label.model" (para resolver os custom fields)."""
    last_error: Exception | None = None
    for path in CONTENT_TYPES_ENDPOINTS:
        try:
            items = client.fetch_all(path)
        except Exception as exc:  # endpoint ausente nesta versao
            last_error = exc
            continue
        mapping: dict[int, str] = {}
        for item in items:
            app_label = item.get("app_label")
            model = item.get("model")
            if item.get("id") is not None and app_label and model:
                mapping[item["id"]] = f"{app_label}.{model}"
        if mapping:
            return mapping
    if last_error is not None:
        raise last_error
    return {}


def _custom_fields(client: NetBoxClient, content_types: dict[int, str]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for field in client.fetch_all(CUSTOM_FIELDS_ENDPOINT):
        field_type = field.get("type")
        if isinstance(field_type, dict):
            field_type = field_type.get("value")
        fields.append(
            {
                "id": field.get("id"),
                "name": field.get("name"),
                "label": field.get("label"),
                "type": field_type,
                "required": field.get("required"),
                "object_types": [
                    content_types.get(type_id, str(type_id))
                    for type_id in (field.get("object_types") or [])
                ],
                "choices": field.get("choices") or [],
            }
        )
    return fields


def _field_spec(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    choices = spec.get("choices") or []
    return {
        "type": spec.get("type"),
        "label": spec.get("label", name),
        "required": bool(spec.get("required", False)),
        "read_only": bool(spec.get("read_only", spec.get("readOnly", False))),
        "max_length": spec.get("max_length"),
        "choices": [
            choice.get("value") if isinstance(choice, dict) else choice
            for choice in choices
        ],
    }


def extract_fields(options_payload: Any, action: str = "POST") -> dict[str, dict[str, Any]]:
    """Campos gravaveis do OPTIONS de um endpoint (por padrao, os do POST).

    E a resposta para "quais campos existem no NetBox": vem da propria instancia,
    entao vale para a versao instalada. Aceita os dois formatos do DRF - os
    campos direto sob a acao (formato da 4.3.6) ou dentro de `properties`.
    """
    actions = (options_payload or {}).get("actions") or {}
    source = actions.get(action) or {}
    nested = source.get("properties")
    if isinstance(nested, dict):
        source = nested

    fields: dict[str, dict[str, Any]] = {}
    for name, spec in source.items():
        if not isinstance(spec, dict) or "type" not in spec:
            continue
        fields[name] = _field_spec(name, spec)
    return fields


def endpoint_actions(snapshot: dict[str, Any], name: str) -> list[str]:
    """Acoes permitidas num endpoint, segundo o OPTIONS (ex.: ['PUT', 'POST']).

    Lista vazia significa que o token nao tem permissao nenhuma ali - foi o que
    aconteceu com `interface` nesta instancia.
    """
    payload = (snapshot.get("schema") or {}).get(name) or {}
    return sorted((payload.get("actions") or {}).keys())


def has_environment(snapshot: dict[str, Any]) -> bool:
    """True se **alguma coisa** foi lida com sucesso.

    Se nada foi lido, nao faz sentido dizer "conectado": foi o caso do certificado
    autoassinado, em que todas as chamadas falharam e a tela aparecia vazia.
    """
    if snapshot.get("status"):
        return True
    if any(snapshot.get("objects", {}).values()):
        return True
    if snapshot.get("counts") or snapshot.get("schema"):
        return True
    return False


def looks_like_tls_failure(snapshot: dict[str, Any]) -> bool:
    """True se a falha foi de certificado TLS nao validado.

    Usa a marca estrutural que a descoberta grava; o teste por texto e so rede de
    seguranca (ex.: um snapshot antigo, com a mensagem crua do requests).
    """
    if snapshot.get("tls_blocked"):
        return True
    markers = (
        "certificate verify failed",
        "certificate_verify_failed",
        "self-signed certificate",
    )
    for erro in snapshot.get("errors", []):
        texto = str(erro).lower()
        if any(marker in texto for marker in markers):
            return True
    return False


def needs_tls_retry(snapshot: dict[str, Any], verify_tls: bool) -> bool:
    """Vale tentar de novo aceitando certificado autoassinado?

    So quando o usuario pediu verificacao (verify_tls), nada foi lido e o motivo
    foi o certificado.
    """
    return bool(verify_tls) and not has_environment(snapshot) and looks_like_tls_failure(snapshot)


def discover(client: NetBoxClient) -> dict[str, Any]:
    """Fotografia do ambiente: versao, objetos de referencia, campos e contagens.

    Cada secao e tolerante a falha: um endpoint indisponivel vira uma entrada em
    `errors` em vez de derrubar a descoberta inteira.
    """
    snapshot: dict[str, Any] = {
        "base_url": client.base_url,
        "token_scheme": getattr(client, "token_scheme", ""),
        "tls_verified": bool(getattr(client, "verify_tls", True)),
        "tls_blocked": False,
        "status": {},
        "current_user": {},
        "objects": {},
        "counts": {},
        "custom_fields": [],
        "custom_fields_sample": {},
        "content_types": {},
        "schema": {},
        "capabilities": {},
        "errors": [],
    }

    def record_error(section: str, exc: Exception) -> None:
        # Marca estrutural: nao dependemos de procurar texto na mensagem (que nos
        # mesmos traduzimos) para saber que o certificado foi o problema.
        if isinstance(exc, NetBoxTLSError):
            snapshot["tls_blocked"] = True
        snapshot["errors"].append(f"{section}: {exc}")

    try:
        snapshot["status"] = client.status()
    except (NetBoxConnectionError, NetBoxTLSError) as exc:
        record_error("status", exc)
        # Servidor inalcancavel (ou certificado barrando): nao vale tentar os outros
        # ~26 endpoints - cada um esperaria o timeout e a tela de carregamento ficaria
        # minutos rodando. Quem chama decide o que fazer (ex.: repetir sem verificar TLS).
        return snapshot
    except Exception as exc:
        record_error("status", exc)

    # Diz logo no inicio de quem e o token - as permissoes sao do dono dele.
    snapshot["current_user"] = current_user(client)

    snapshot["api_version"] = getattr(client, "api_version", "")

    for key, path in REFERENCE_ENDPOINTS.items():
        try:
            params = {"brief": 1} if key == "device_types" else None
            objects = client.fetch_all(path, params=params)
            snapshot["objects"][key] = [summarize_object(item) for item in objects]
        except Exception as exc:
            record_error(key, exc)
            snapshot["objects"].setdefault(key, [])

    for key, path in COUNT_ENDPOINTS.items():
        try:
            snapshot["counts"][key] = client.count(path)
        except Exception as exc:
            record_error(key, exc)

    try:
        content_types = _content_type_map(client)
        snapshot["content_types"] = content_types
    except Exception as exc:
        record_error("content_types", exc)
        content_types = {}

    try:
        snapshot["custom_fields"] = _custom_fields(client, content_types)
    except Exception as exc:
        record_error("custom_fields", exc)

    # Exemplo de custom field por tipo de objeto (pre-preenche os obrigatorios).
    snapshot["custom_fields_sample"] = sample_custom_fields(client)

    for key, path in SCHEMA_ENDPOINTS.items():
        try:
            snapshot["schema"][key] = client.options(path)
        except Exception as exc:
            record_error(f"schema.{key}", exc)

    snapshot["capabilities"] = {
        key: endpoint_actions(snapshot, key) for key in snapshot["schema"]
    }

    return snapshot


def fields_for(snapshot: dict[str, Any], name: str = "device") -> dict[str, dict[str, Any]]:
    """Campos gravaveis de um endpoint ja descoberto (ex.: 'device')."""
    return extract_fields(snapshot.get("schema", {}).get(name))


def reference_labels(snapshot: dict[str, Any], key: str) -> list[str]:
    """Rotulos de um conjunto descoberto (ex.: nomes dos manufacturers)."""
    return [str(item.get("label", "")) for item in snapshot.get("objects", {}).get(key, [])]


def site_tenants(snapshot: dict[str, Any]) -> list[tuple[str, int]]:
    """Tenants presentes nos sites descobertos: [(tenant, quantidade)]."""
    counts: dict[str, int] = {}
    for site in snapshot.get("objects", {}).get("sites", []):
        tenant = str(site.get("tenant") or "")
        counts[tenant] = counts.get(tenant, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))


def site_names(snapshot: dict[str, Any], tenant: str | None = None) -> list[str]:
    """Nomes dos sites (opcionalmente de um tenant), em ordem alfabetica.

    E a lista que alimenta a lista suspensa (dropdown) da coluna Site do modelo.
    """
    names: list[str] = []
    for site in snapshot.get("objects", {}).get("sites", []):
        if tenant and str(site.get("tenant") or "") != tenant:
            continue
        label = site.get("label")
        if label:
            names.append(str(label))
    return sorted(set(names))


def create_reference(client: NetBoxClient, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Cria uma referencia (fabricante, device-type, papel ou site)."""
    return client.create(REFERENCE_WRITE_ENDPOINTS[kind], payload)


ME_ENDPOINT = "/api/users/me/"


def current_user(client: NetBoxClient) -> dict[str, Any]:
    """Quem e o dono do token (`/api/users/me/`).

    Importante porque as permissoes sao SEMPRE do dono do token, nao de quem esta
    logado na interface: um superusuario que use um token de outro usuario continua
    limitado ao que aquele usuario pode. Sem isso, um 403 vira adivinhacao.
    """
    try:
        data = client.request("GET", ME_ENDPOINT)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "username": data.get("username", ""),
        "is_superuser": bool(data.get("is_superuser", False)),
        "is_staff": bool(data.get("is_staff", False)),
    }


def custom_field_samples(
    client: NetBoxClient, endpoint: str = DEVICE_ENDPOINT, sample_size: int = 5
) -> dict[str, Any]:
    """Nomes dos campos personalizados + um valor de exemplo, lidos de objetos reais.

    Descobre os custom fields sem depender de permissao extra: o OPTIONS nao
    enumera os campos, mas a resposta de um objeto existente traz todas as chaves
    de `custom_fields` (com null nas vazias).

    E o que da um valor **valido** para campos obrigatorios cujas escolhas a API nao
    expoe (ex.: `add_to_zabbix` num IP, `Validavel` num device).
    """
    samples: dict[str, Any] = {}
    try:
        data = client.request("GET", endpoint, params={"limit": sample_size})
    except Exception:
        return samples

    results = data.get("results", []) if isinstance(data, dict) else data
    for obj in results or []:
        campos = obj.get("custom_fields")
        if not isinstance(campos, dict):
            continue
        for name, value in campos.items():
            if name not in samples or (samples[name] is None and value is not None):
                samples[name] = value
    return samples


# De onde tirar exemplo de custom field: cada tipo de objeto tem os seus campos, e
# um campo obrigatorio num deles (ex.: add_to_zabbix num IP) trava o POST.
SAMPLE_ENDPOINTS: dict[str, str] = {
    "dcim.device": DEVICE_ENDPOINT,
    "ipam.ipaddress": IP_ADDRESS_ENDPOINT,
}


def sample_custom_fields(client: NetBoxClient) -> dict[str, dict[str, Any]]:
    """Exemplo de custom fields por tipo de objeto."""
    return {
        object_type: custom_field_samples(client, endpoint)
        for object_type, endpoint in SAMPLE_ENDPOINTS.items()
    }


def refresh_reference_objects(
    client: NetBoxClient,
    snapshot: dict[str, Any],
    keys: tuple[str, ...] = ("manufacturers", "device_types"),
) -> None:
    """Reler os objetos de referencia no snapshot (depois de criar algum)."""
    objects = snapshot.setdefault("objects", {})
    for key in keys:
        params = {"brief": 1} if key == "device_types" else None
        items = client.fetch_all(REFERENCE_ENDPOINTS[key], params=params)
        objects[key] = [summarize_object(item) for item in items]


def _plain(value: Any) -> Any:
    """Valor comparavel: no NetBox `status` vem como objeto aninhado."""
    if isinstance(value, dict):
        if "value" in value:
            return value["value"]
        return value.get("id", value.get("name"))
    return value


def device_matches(existing: dict[str, Any], payload: dict[str, Any]) -> bool:
    """O device existente ja esta igual ao payload? (evita PATCH desnecessario)"""
    for field_name in COMPARE_FIELDS:
        if field_name not in payload:
            continue
        if str(_plain(existing.get(field_name))) != str(payload[field_name]):
            return False
    return True


def upsert_device(
    client: NetBoxClient,
    payload: dict[str, Any],
    changelog_message: str = "",
) -> tuple[str, int | None, str]:
    """Cria ou atualiza o device pela chave `name` (idempotencia).

    Retorna (status, id, request_id), com status em created | updated | exists.
    """
    body = dict(payload)
    if changelog_message:
        body["changelog_message"] = changelog_message

    existing = client.get_or_none(DEVICE_ENDPOINT, name=payload.get("name", ""))
    if existing is None:
        created = client.create(DEVICE_ENDPOINT, body)
        return "created", created.get("id"), client.last_request_id
    if device_matches(existing, payload):
        return "exists", existing.get("id"), client.last_request_id
    updated = client.update(DEVICE_ENDPOINT, existing["id"], body)
    return "updated", updated.get("id", existing.get("id")), client.last_request_id


def upsert_interface(
    client: NetBoxClient,
    device_id: int,
    name: str = DEFAULT_INTERFACE_NAME,
    mac_address: str = "",
    interface_type: str = DEFAULT_INTERFACE_TYPE,
) -> tuple[str, int | None]:
    """Garante a interface da camera no device.

    Se o device ja tem interface, **reaproveita a primeira** em vez de criar outra:
    o device-type pode ter criado interfaces por template (e ha o plugin
    netbox_interface_synchronization instalado nesta instancia).
    """
    existentes = client.fetch_all(INTERFACE_ENDPOINT, params={"device_id": device_id})

    if existentes:
        alvo = existentes[0]
        interface_id = alvo.get("id")
        if not mac_address or _same_mac(alvo.get("mac_address"), mac_address):
            return "exists", interface_id
        client.update(INTERFACE_ENDPOINT, interface_id, {"mac_address": mac_address})
        return "updated", interface_id

    payload: dict[str, Any] = {
        "device": device_id,
        "name": name,
        "type": interface_type,
        "enabled": True,
    }
    if mac_address:
        payload["mac_address"] = mac_address
    criada = client.create(INTERFACE_ENDPOINT, payload)
    return "created", criada.get("id")


def upsert_ip_address(
    client: NetBoxClient,
    address: str,
    interface_id: int,
    ip_status: str = "active",
    custom_fields: dict[str, Any] | None = None,
    description: str = "",
) -> tuple[str, int | None]:
    """Cria/atualiza o IP e o vincula a interface do device.

    O vinculo exige `assigned_object_type` + `assigned_object_id` (relacao generica).

    `custom_fields` e obrigatorio na pratica nesta instancia: `ipam.ipaddress` tem o
    campo `add_to_zabbix` como **obrigatorio** - sem ele o POST leva 400.
    """
    if "/" not in address:
        address = f"{address}/32"
    campos = {
        name: value
        for name, value in (custom_fields or {}).items()
        if value not in (None, "", [])
    }

    payload: dict[str, Any] = {
        "address": address,
        "status": ip_status,
        "assigned_object_type": "dcim.interface",
        "assigned_object_id": interface_id,
    }
    if campos:
        payload["custom_fields"] = campos
    if description:
        payload["description"] = description

    existente = client.get_or_none(IP_ADDRESS_ENDPOINT, address=address)
    if existente is None:
        criado = client.create(IP_ADDRESS_ENDPOINT, payload)
        return "created", criado.get("id")
    if _ip_matches(existente, interface_id, ip_status, campos, description):
        return "exists", existente.get("id")
    atualizado = client.update(IP_ADDRESS_ENDPOINT, existente["id"], payload)
    return "updated", atualizado.get("id", existente.get("id"))


def set_primary_ip4(client: NetBoxClient, device_id: int, ip_id: int) -> None:
    """Marca o IP como primario do device (so aceito se estiver na interface dele)."""
    client.update(DEVICE_ENDPOINT, device_id, {"primary_ip4": ip_id})


def _same_mac(atual: Any, nova: str) -> bool:
    def limpar(valor: Any) -> str:
        return re.sub(r"[^0-9a-f]", "", str(valor or "").lower())

    limpa = limpar(atual)
    return bool(limpa) and limpa == limpar(nova)


def _ip_matches(
    existente: dict[str, Any],
    interface_id: int,
    ip_status: str,
    custom_fields: dict[str, Any] | None = None,
    description: str = "",
) -> bool:
    status = existente.get("status")
    if isinstance(status, dict):
        status = status.get("value")
    if str(status) != ip_status:
        return False
    objeto = existente.get("assigned_object") or {}
    if not isinstance(objeto, dict) or objeto.get("id") != interface_id:
        return False

    atuais = existente.get("custom_fields") or {}
    for nome, valor in (custom_fields or {}).items():
        if atuais.get(nome) != valor:
            return False
    if description:
        atual = str(existente.get("description") or "")
        if atual != description:
            return False
    return True


def save_snapshot(snapshot: dict[str, Any], path: str | Path) -> Path:
    """Grava a fotografia em JSON (base para decidir o mapeamento)."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return destination


def netbox_version(snapshot: dict[str, Any]) -> str:
    """Versao do NetBox relatada pelo /api/status/."""
    status = snapshot.get("status") or {}
    return str(status.get("netbox-version") or status.get("netbox_version") or "")
