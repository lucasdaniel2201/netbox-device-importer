"""Plano de importacao: planilha validada -> o que vai acontecer no NetBox.

O plano e calculado **antes** de enviar qualquer coisa. Dois motivos:

- a API nao tem "criar ou atualizar" (a idempotencia e GET -> PATCH ou POST);
- na 4.3.6 um erro em lote nao diz qual item falhou, entao nao da para descobrir
  depois - tem que validar antes.

A resolucao das referencias (site, papel, fabricante, device-type) sai do proprio
snapshot da descoberta, sem gastar chamada extra so para conferir se existe. O que
nao existe vira uma `Reference` a criar - e o usuario aprova antes.

Nada aqui fala com o NetBox: e so planejamento (e por isso e testavel offline).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app import config, provision
from app.spreadsheet import ROLE_KEY, SITE_KEY, normalize_for_match

DEFAULT_ROLE = "Camera"
DEFAULT_STATUS = "active"

# Quando (e so quando) falta permissao para interface/IP. No NetBox o IP so se
# vincula a um device POR UMA INTERFACE; sem interface nao ha como pendurar o IP
# nem definir o primary_ip4.
NETWORK_DEFERRED_NOTE = (
    "Interface (MAC) e IP nao foram criados: falta permissao de escrita em "
    "dcim.interface / ipam.ip-address. Sem interface o NetBox nao vincula um IP ao device."
)


def slugify(value: str) -> str:
    """Slug no padrao do NetBox: minusculo, ASCII, com hifens."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "sem-nome"


def build_comments(firmware: str, nvr: str) -> str:
    """Comments do device: e onde firmware e NVR ficam (custom fields: 403)."""
    linhas = []
    if firmware:
        linhas.append(f"Firmware: {firmware}")
    if nvr:
        linhas.append(f"NVR: {nvr}")
    if linhas:
        linhas.append("Origem: planilha de cameras (importador NetBox).")
    return "\n".join(linhas)


@dataclass
class Reference:
    """Referencia que **falta** no NetBox e precisa ser criada antes do device."""

    kind: str  # manufacturer | device_type
    key: str
    label: str
    payload: dict[str, Any]
    manufacturer_name: str = ""

    @property
    def endpoint(self) -> str:
        return provision.REFERENCE_WRITE_ENDPOINTS[self.kind]


def clean_custom_fields(values: dict[str, Any] | None) -> dict[str, Any]:
    """Descarta custom fields vazios.

    Enviar `""` (ou `[]`) num campo obrigatorio tambem da 400, entao o vazio sai de
    vez - assim o erro do NetBox aponta o campo que realmente ficou de fora.
    """
    limpos: dict[str, Any] = {}
    for name, value in (values or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, tuple)) and not value:
            continue
        limpos[str(name)] = value
    return limpos


def network_enabled(snapshot: dict[str, Any]) -> bool:
    """Da para criar interface e IP? Depende das permissoes do token."""
    return all(
        "POST" in provision.endpoint_actions(snapshot, key)
        for key in ("interface", "ip_address")
    )


# Tipo declarado pelo NetBox -> como o valor e editado e enviado.
DECLARED_KINDS: dict[str, str] = {
    "boolean": "bool",
    "multiselect": "list",
    "multiobject": "list",
    "integer": "int",
}


def custom_field_defs(
    snapshot: dict[str, Any], object_type: str = "dcim.device"
) -> dict[str, dict[str, Any]]:
    """Definicoes dos custom fields do objeto: nome -> {label, type, required}.

    Com a permissao de `extras.customfield` (que agora existe) isso vem exato, em
    vez de deduzido por amostragem - da para exigir de verdade o que e obrigatorio.
    """
    definicoes: dict[str, dict[str, Any]] = {}
    for campo in snapshot.get("custom_fields", []):
        if object_type not in (campo.get("object_types") or []):
            continue
        nome = campo.get("name")
        if nome:
            definicoes[str(nome)] = {
                "label": campo.get("label") or str(nome),
                "type": str(campo.get("type") or ""),
                "required": bool(campo.get("required")),
            }
    return definicoes


def custom_field_kind(sample: Any, declared_type: str = "") -> str:
    """Como editar/enviar o campo.

    O tipo declarado manda; sem ele (quando a listagem de custom fields nao esta
    liberada), deduzimos do exemplo lido de um device real.
    """
    if declared_type in DECLARED_KINDS:
        return DECLARED_KINDS[declared_type]
    if declared_type:
        return "text"
    if isinstance(sample, bool):
        return "bool"
    if isinstance(sample, (list, tuple)):
        return "list"
    return "text"


def parse_custom_value(kind: str, raw: Any) -> Any:
    """Converte o que o usuario digitou no valor que o NetBox espera.

    Lista vira **lista de verdade**: mandar a string "[]" (ou "['a']") faz o NetBox
    recusar com "Escolha ... e invalida para o conjunto de escolhas ...".
    """
    if kind == "list":
        if isinstance(raw, (list, tuple)):
            itens = [str(item).strip() for item in raw if str(item).strip()]
            return itens or None

        texto = str(raw or "").strip()
        if not texto:
            return None
        if texto.startswith("["):
            # Aceita o formato que o proprio NetBox devolve (ex.: "['a', 'b']").
            try:
                parsed = json.loads(texto.replace("'", '"'))
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                itens = [str(item).strip() for item in parsed if str(item).strip()]
                return itens or None
        itens = [part.strip() for part in re.split(r"[;,]", texto) if part.strip()]
        return itens or None

    texto = str(raw or "").strip()
    if not texto:
        return None
    if kind == "bool":
        lowered = texto.casefold()
        if lowered in ("1", "true", "sim", "yes", "s", "sim (true)"):
            return True
        if lowered in ("0", "false", "nao", "no", "n", "nao (false)"):
            return False
        # Desconhecido: omitir em vez de chutar. Gravar um booleano errado em
        # silencio e pior do que o NetBox recusar o device.
        return None
    if kind == "int":
        try:
            return int(texto)
        except ValueError:
            return None
    return texto


def custom_field_sample(snapshot: dict[str, Any], object_type: str) -> dict[str, Any]:
    """Exemplo de custom fields daquele tipo de objeto (para pre-preencher).

    Cada tipo tem os seus: `dcim.device` pede `Validavel`, `ipam.ipaddress` pede
    `add_to_zabbix` - e um obrigatorio vazio recusa o POST.
    """
    amostras = snapshot.get("custom_fields_sample") or {}
    if not isinstance(amostras, dict):
        return {}
    valores = amostras.get(object_type)
    return valores if isinstance(valores, dict) else {}


@dataclass
class PlanOptions:
    role: str = DEFAULT_ROLE
    status: str = DEFAULT_STATUS
    # None = usa os padroes do deployment (app/config.CUSTOM_FIELDS). Um dict vazio
    # significa "nao enviar nada" - util em teste.
    custom_fields: dict[str, Any] | None = None
    ip_custom_fields: dict[str, Any] | None = None
    interface_name: str = provision.DEFAULT_INTERFACE_NAME


@dataclass
class DevicePlan:
    row_number: int
    name: str
    site: str
    vendor: str
    model: str
    firmware: str
    nvr: str
    mac: str
    ip: str
    description: str
    comments: str
    status: str = DEFAULT_STATUS
    custom_fields: dict[str, Any] = field(default_factory=dict)
    ip_custom_fields: dict[str, Any] = field(default_factory=dict)
    include_network: bool = False
    interface_name: str = ""
    site_id: int | None = None
    role_id: int | None = None
    device_type_id: int | None = None
    issues: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        resolvido = self.site_id is not None and self.role_id is not None
        return not self.issues and resolvido and self.device_type_id is not None

    @property
    def device_type_label(self) -> str:
        return f"{self.vendor} {self.model}".strip()

    def payload(self) -> dict[str, Any]:
        """Corpo do POST/PATCH do device (so faz sentido quando `ready`)."""
        body: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "role": self.role_id,
            "site": self.site_id,
            "device_type": self.device_type_id,
        }
        if self.description:
            body["description"] = self.description
        if self.comments:
            body["comments"] = self.comments
        if self.custom_fields:
            body["custom_fields"] = dict(self.custom_fields)
        return body


def resolve_custom_fields(
    snapshot: dict[str, Any], object_type: str, configured: dict[str, Any] | None = None
) -> dict[str, Any]:
    """O que mandar em custom_fields para aquele tipo de objeto.

    Ordem: o que estiver declarado (app/config.py) e, para os campos **obrigatorios**
    que ninguem declarou, o valor observado num objeto existente.

    O fallback da amostra existe porque a API nao expoe as opcoes dos campos `select`
    (`choices` vem vazio): um valor lido de um objeto real e, por definicao, valido -
    chutar um valor "obvio" da 400 ("Escolha X e invalida para o conjunto de escolhas").
    """
    valores = dict(
        configured if configured is not None else config.CUSTOM_FIELDS.get(object_type, {})
    )
    for nome, definicao in custom_field_defs(snapshot, object_type).items():
        if not definicao.get("required") or nome in valores:
            continue
        observado = custom_field_sample(snapshot, object_type).get(nome)
        if observado not in (None, "", []):
            valores[nome] = observado
    return clean_custom_fields(valores)


def missing_required_custom_fields(
    snapshot: dict[str, Any], object_type: str, provided: dict[str, Any]
) -> list[str]:
    """Campos obrigatorios daquele objeto que o app NAO vai enviar.

    Substitui a conferencia que existia na tela: sem o valor o POST da 400, entao e
    melhor avisar antes de importar do que descobrir no meio.
    """
    return [
        nome
        for nome, definicao in custom_field_defs(snapshot, object_type).items()
        if definicao.get("required") and nome not in provided
    ]


@dataclass
class ImportPlan:
    options: PlanOptions
    devices: list[DevicePlan] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    # O que sera enviado em custom_fields (para o resumo e o relatorio).
    custom_fields_used: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Campos obrigatorios do NetBox que ninguem esta mandando.
    missing_required: list[str] = field(default_factory=list)

    @property
    def ready_devices(self) -> list[DevicePlan]:
        return [device for device in self.devices if device.ready]

    @property
    def blocked_devices(self) -> list[DevicePlan]:
        return [device for device in self.devices if not device.ready]

    @property
    def can_import(self) -> bool:
        """So libera quando nada esta bloqueado, nao falta referencia nem campo."""
        return (
            not self.blocked_devices
            and not self.references
            and not self.missing_required
        )


def _index_by_label(snapshot: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {
        normalize_for_match(item.get("label")): item
        for item in snapshot.get("objects", {}).get(key, [])
        if item.get("label")
    }


def device_type_key(manufacturer: str, model: str) -> str:
    return f"{normalize_for_match(manufacturer)}|{normalize_for_match(model)}"


def find_object_id(snapshot: dict[str, Any], key: str, label: str) -> int | None:
    """Id de um objeto descoberto pelo rotulo (ex.: fabricante pelo nome)."""
    item = _index_by_label(snapshot, key).get(normalize_for_match(label))
    return item.get("id") if item else None


def _device_type_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        device_type_key(item.get("manufacturer", ""), item.get("label", "")): item
        for item in snapshot.get("objects", {}).get("device_types", [])
        if item.get("label")
    }


def build_plan(
    sheet: Any, snapshot: dict[str, Any], options: PlanOptions | None = None
) -> ImportPlan:
    """Monta o plano a partir da planilha validada e do snapshot do NetBox."""
    options = options or PlanOptions()
    sites = _index_by_label(snapshot, "sites")
    roles = _index_by_label(snapshot, "device_roles")
    manufacturers = _index_by_label(snapshot, "manufacturers")
    device_types = _device_type_index(snapshot)

    custom_fields = resolve_custom_fields(snapshot, "dcim.device", options.custom_fields)
    ip_custom_fields = resolve_custom_fields(snapshot, "ipam.ipaddress", options.ip_custom_fields)
    com_rede = network_enabled(snapshot)

    # Sem a tela de campos personalizados, este e o alarme: se o NetBox exigir um
    # campo que o app nao manda, avisa agora em vez de falhar com 400 no POST.
    faltando = [
        f"dcim.device.{nome}"
        for nome in missing_required_custom_fields(snapshot, "dcim.device", custom_fields)
    ]
    if com_rede:
        faltando += [
            f"ipam.ipaddress.{nome}"
            for nome in missing_required_custom_fields(
                snapshot, "ipam.ipaddress", ip_custom_fields
            )
        ]

    references: dict[tuple[str, str], Reference] = {}
    devices: list[DevicePlan] = []

    for row in sheet.rows:
        cells = row.cells
        vendor = (cells.get("Vendor") or "").strip()
        model = (cells.get("Model") or "").strip()
        issues = list(row.issues)
        site_label = (cells.get(SITE_KEY) or "").strip()
        firmware = (cells.get("Firmware") or "").strip()
        nvr = (cells.get("Server") or "").strip()
        # Papel: a coluna da planilha manda; sem ela, vale o escolhido na tela.
        papel_texto = (cells.get(ROLE_KEY) or "").strip() or options.role
        papel = roles.get(normalize_for_match(papel_texto))
        pending: list[str] = []

        site = sites.get(normalize_for_match(site_label)) if site_label else None
        if site is None and not any(item.startswith("Site") for item in issues):
            issues.append(
                f"Site '{site_label}' nao esta no NetBox." if site_label else "Site vazio."
            )
        if papel is None:
            issues.append(f"Papel '{papel_texto}' nao existe no NetBox.")

        manufacturer = manufacturers.get(normalize_for_match(vendor)) if vendor else None
        if vendor and manufacturer is None:
            pending.append(f"fabricante '{vendor}'")
            references.setdefault(
                ("manufacturer", normalize_for_match(vendor)),
                Reference(
                    kind="manufacturer",
                    key=normalize_for_match(vendor),
                    label=vendor,
                    payload={"name": vendor, "slug": slugify(vendor)},
                ),
            )

        device_type = None
        if vendor and model:
            chave = device_type_key(vendor, model)
            device_type = device_types.get(chave)
            if device_type is None:
                pending.append(f"device-type '{vendor} {model}'")
                references.setdefault(
                    ("device_type", chave),
                    Reference(
                        kind="device_type",
                        key=chave,
                        label=f"{vendor} {model}",
                        payload={"model": model, "slug": slugify(f"{vendor} {model}")},
                        manufacturer_name=vendor,
                    ),
                )
        else:
            issues.append("Fabricante e modelo sao necessarios para o device-type.")

        devices.append(
            DevicePlan(
                row_number=row.row_number,
                name=row.name_normalized,
                site=site_label,
                vendor=vendor,
                model=model,
                firmware=firmware,
                nvr=nvr,
                mac=(cells.get("MAC address") or "").strip(),
                ip=(cells.get("IP") or "").strip(),
                description=(cells.get("Description") or "").strip(),
                comments=build_comments(firmware, nvr),
                status=options.status,
                custom_fields=dict(custom_fields),
                ip_custom_fields=dict(ip_custom_fields),
                include_network=com_rede,
                interface_name=options.interface_name if com_rede else "",
                site_id=site.get("id") if site else None,
                role_id=papel.get("id") if papel else None,
                device_type_id=device_type.get("id") if device_type else None,
                issues=issues,
                pending=pending,
            )
        )

    return ImportPlan(
        options=options,
        devices=devices,
        references=list(references.values()),
        deferred=[] if com_rede else [NETWORK_DEFERRED_NOTE],
        custom_fields_used={
            "dcim.device": dict(custom_fields),
            **({"ipam.ipaddress": dict(ip_custom_fields)} if com_rede else {}),
        },
        missing_required=faltando,
    )
