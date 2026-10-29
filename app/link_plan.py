"""Plano de links IP: planilha validada -> o que vai acontecer no NetBox.

Mesma ideia do plano de cameras: calcular antes de enviar, porque a API nao tem
"criar ou atualizar" e um erro em lote nao diz qual item falhou. Aqui cada linha
vira ate tres objetos no IPAM:

- prefixo do bloco publico (escopo: site);
- prefixo do bloco LAN (escopo: site), quando a planilha traz;
- IP address do link, vinculado a interface WAN de um device que ja existe.

O device **nao** e criado por este modulo: quem cria device e a importacao de
cameras. O nome dele so pode ser conferido na hora da escrita (o snapshot guarda
contagem de devices, nao a lista de 5 mil nomes), entao nome inexistente vira erro
daquela linha durante a importacao - sem impedir as outras.

Nada aqui fala com o NetBox: e so planejamento (e por isso e testavel offline).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any

from app import import_plan, provision
from app.link_sheet import (
    DEFAULT_INTERFACE,
    DESCRIPTION_KEY,
    DEVICE_KEY,
    DEVICE_ROLE_KEY,
    INTERFACE_KEY,
    IP_KEY,
    LAN_KEY,
    MODEL_KEY,
    PROVIDER_KEY,
    PUBLIC_KEY,
    ROLE_KEY,
    SITE_KEY,
    VENDOR_KEY,
    ZABBIX_KEY,
    LinkSheet,
    default_link_ip,
    parse_host_address,
    parse_network,
    usable_host_address,
)
from app.spreadsheet import normalize_for_match

PREFIX_STATUS = "active"
ZABBIX_FIELD = "add_to_zabbix"
DEFAULT_DEVICE_ROLE = "Roteador"


@dataclass
class LinkPlanRow:
    row_number: int
    site: str
    device: str
    interface: str
    public_block: str
    lan_block: str
    link_ip: str
    role_label: str
    description: str
    provider: str
    vendor: str = ""
    model: str = ""
    device_role: str = ""
    link_ip_deduced: bool = False
    site_id: int | None = None
    role_id: int | None = None
    device_role_id: int | None = None
    manufacturer_id: int | None = None
    device_type_id: int | None = None
    device_exists: bool = False
    device_custom_fields: dict[str, Any] = field(default_factory=dict)
    ip_custom_fields: dict[str, Any] = field(default_factory=dict)
    prefix_custom_fields: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # O que sera criado antes do link (fabricante, device-type, o proprio device).
    pending: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.issues and self.site_id is not None

    @property
    def base_description(self) -> str:
        return self.description or self.site

    def public_prefix_payload(self, scope_field: str = "scope_type") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prefix": self.public_block,
            "status": PREFIX_STATUS,
            "description": self.base_description,
        }
        if self.site_id is not None:
            payload.update(_scope(self.site_id, scope_field))
        if self.role_id is not None:
            payload["role"] = self.role_id
        if self.provider:
            payload["comments"] = self.provider
        if self.prefix_custom_fields:
            payload["custom_fields"] = dict(self.prefix_custom_fields)
        return payload

    def lan_prefix_payload(self, scope_field: str = "scope_type") -> dict[str, Any] | None:
        if not self.lan_block:
            return None
        payload: dict[str, Any] = {
            "prefix": self.lan_block,
            "status": PREFIX_STATUS,
            "description": f"{self.base_description} (LAN)",
        }
        if self.site_id is not None:
            payload.update(_scope(self.site_id, scope_field))
        if self.role_id is not None:
            payload["role"] = self.role_id
        if self.prefix_custom_fields:
            payload["custom_fields"] = dict(self.prefix_custom_fields)
        return payload

    def ip_description(self) -> str:
        return self.base_description

    def device_payload(self, device_type_id: int | None = None) -> dict[str, Any]:
        """Corpo do POST do device criado junto com o link.

        So e usado quando o device da linha nao existe no site. O device nasce com
        o site da linha, o papel escolhido e o device-type do fabricante/modelo.
        """
        body: dict[str, Any] = {
            "name": self.device,
            "site": self.site_id,
            "role": self.device_role_id,
            "device_type": device_type_id or self.device_type_id,
            "status": PREFIX_STATUS,
            "description": self.base_description,
        }
        if self.device_custom_fields:
            body["custom_fields"] = dict(self.device_custom_fields)
        return body


def _scope(site_id: int, scope_field: str) -> dict[str, Any]:
    """Vinculo do prefixo com o site.

    No NetBox 4.3 o campo `site` do prefixo virou o escopo generico
    (`scope_type`/`scope_id`); o app pergunta ao OPTIONS qual dos dois a instancia
    usa e manda o formato certo.
    """
    if scope_field == "site":
        return {"site": site_id}
    return {"scope_type": "dcim.site", "scope_id": site_id}


@dataclass
class LinkPlan:
    rows: list[LinkPlanRow] = field(default_factory=list)
    # Campos obrigatorios do NetBox que ninguem esta mandando.
    missing_required: list[str] = field(default_factory=list)
    custom_fields_used: dict[str, dict[str, Any]] = field(default_factory=dict)
    scope_field: str = "scope_type"

    @property
    def ready_rows(self) -> list[LinkPlanRow]:
        return [row for row in self.rows if row.ready]

    @property
    def blocked_rows(self) -> list[LinkPlanRow]:
        return [row for row in self.rows if not row.ready]

    @property
    def can_import(self) -> bool:
        return bool(self.rows) and not self.blocked_rows and not self.missing_required

    @property
    def devices_to_create(self) -> int:
        """Quantos devices serao criados junto com os links."""
        return sum(1 for row in self.ready_rows if not row.device_exists)

    @property
    def prefix_count(self) -> int:
        """Quantos prefixos distintos as linhas prontas vao criar/atualizar."""
        prefixos = set()
        for row in self.ready_rows:
            prefixos.add(row.public_block)
            if row.lan_block:
                prefixos.add(row.lan_block)
        return len(prefixos)


def _device_type_id(snapshot: dict[str, Any], vendor: str, model: str) -> int | None:
    """Id do device-type de (fabricante, modelo), se ele existir."""
    chave = import_plan.device_type_key(vendor, model)
    for item in snapshot.get("objects", {}).get("device_types", []):
        if import_plan.device_type_key(item.get("manufacturer", ""), item.get("label", "")) == chave:
            return item.get("id")
    return None


def _prefix_role_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        normalize_for_match(item.get("label")): item
        for item in snapshot.get("objects", {}).get("prefix_roles", [])
        if item.get("label")
    }


def _device_index(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Nome normalizado -> devices com aquele nome (o nome nao e unico)."""
    indice: dict[str, list[dict[str, Any]]] = {}
    for item in snapshot.get("objects", {}).get("devices", []):
        if item.get("label"):
            indice.setdefault(normalize_for_match(item["label"]), []).append(item)
    return indice


def _device_role_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        normalize_for_match(item.get("label")): item
        for item in snapshot.get("objects", {}).get("device_roles", [])
        if item.get("label")
    }


def _site_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        normalize_for_match(item.get("label")): item
        for item in snapshot.get("objects", {}).get("sites", [])
        if item.get("label")
    }


def _resolve_link_ip(
    public_block: str, link_ip: str, block_host: str = ""
) -> tuple[str, bool, list[str]]:
    """IP do link com mascara do bloco.

    Tres origens, em ordem de confianca:

    1. a coluna **IP do link**, quando preenchida (manda sempre);
    2. o endereco que veio na propria coluna do bloco - planilhas reais trazem
       `198.51.100.45/31`, e esse endereco e o do roteador, nao a rede;
    3. deducao do bloco, que **avisa** porque e palpite.
    """
    rede = ipaddress.ip_network(public_block)
    avisos: list[str] = []

    if link_ip.strip():
        endereco = parse_host_address(link_ip, rede)
        if block_host and str(endereco) != block_host:
            avisos.append(
                f"IP do link {endereco} difere do endereco da coluna do bloco "
                f"({block_host}); vale a coluna 'IP do link'."
            )
        return f"{endereco}/{rede.prefixlen}", False, avisos

    if block_host:
        endereco = parse_host_address(block_host, rede)
        if not usable_host_address(rede, endereco):
            avisos.append(
                f"'{block_host}' e rede/broadcast de {rede}; deduzindo o IP do link."
            )
        else:
            avisos.append(
                f"IP do link veio do proprio bloco: {endereco}/{rede.prefixlen}."
            )
            return f"{endereco}/{rede.prefixlen}", False, avisos

    endereco = default_link_ip(rede)
    return (
        f"{endereco}/{rede.prefixlen}",
        True,
        [
            f"IP do link deduzido do bloco: {endereco}/{rede.prefixlen} "
            "(confira se e o endereco do roteador)."
        ],
    )


def _collect_values(destino: dict[str, list[Any]], valores: dict[str, Any]) -> None:
    """Acumula os valores distintos enviados (para o resumo e o relatorio)."""
    for nome, valor in valores.items():
        lista = destino.setdefault(nome, [])
        if valor not in lista:
            lista.append(valor)


def _collapse_values(destino: dict[str, list[Any]]) -> dict[str, Any]:
    """Um valor -> ele mesmo; varios -> lista (a tela mostra os dois)."""
    return {
        nome: (valores[0] if len(valores) == 1 else list(valores))
        for nome, valores in destino.items()
    }


def build_plan(sheet: LinkSheet, snapshot: dict[str, Any]) -> LinkPlan:
    """Monta o plano a partir da planilha de links validada e do snapshot."""
    sites = _site_index(snapshot)
    roles = _prefix_role_index(snapshot)
    devices = _device_index(snapshot)
    device_roles = _device_role_index(snapshot)
    device_custom_fields = import_plan.resolve_custom_fields(snapshot, "dcim.device")
    ip_custom_fields = import_plan.resolve_custom_fields(snapshot, "ipam.ipaddress")
    prefix_custom_fields = import_plan.resolve_custom_fields(snapshot, "ipam.prefix")

    plan = LinkPlan(
        custom_fields_used={"ipam.ipaddress": {}, "ipam.prefix": dict(prefix_custom_fields)},
        scope_field=provision.prefix_scope_field(snapshot),
    )
    usados_ip: dict[str, list[Any]] = {}

    for row in sheet.rows:
        cells = row.cells
        site_label = (cells.get(SITE_KEY) or "").strip()
        role_label = (cells.get(ROLE_KEY) or "").strip()
        site = sites.get(normalize_for_match(site_label)) if site_label else None
        papel = roles.get(normalize_for_match(role_label)) if role_label else None

        issues = list(row.issues)
        warnings = list(row.warnings)
        if site is None and site_label and not any("Site" in item for item in issues):
            issues.append(f"Site '{site_label}' nao esta no NetBox.")

        device_label = (cells.get(DEVICE_KEY) or "").strip()
        vendor = (cells.get(VENDOR_KEY) or "").strip()
        model = (cells.get(MODEL_KEY) or "").strip()
        device_role_label = (cells.get(DEVICE_ROLE_KEY) or "").strip() or DEFAULT_DEVICE_ROLE
        papel_device = device_roles.get(normalize_for_match(device_role_label))
        pending: list[str] = []
        manufacturer_id: int | None = None
        device_type_id: int | None = None

        site_id = site.get("id") if site else None
        encontrados = devices.get(normalize_for_match(device_label), []) if device_label else []
        no_site = [
            item for item in encontrados if site_id is not None and item.get("site_id") == site_id
        ]
        device_exists = bool(no_site)

        # A descoberta pode nao trazer devices (token sem permissao de dcim.device):
        # nesse caso quem resolve e a importacao, e o plano nao acusa nada.
        if device_label and devices and not device_exists:
            if not vendor or not model:
                issues.append(
                    f"Device '{device_label}' nao existe no site e, sem Fabricante e "
                    "Modelo, nao da para cria-lo."
                )
            elif papel_device is None:
                issues.append(
                    f"Papel de device '{device_role_label}' nao existe no NetBox."
                )
            else:
                if encontrados:
                    warnings.append(
                        f"Device '{device_label}' existe em outro site; sera criado no "
                        "site desta linha."
                    )
                manufacturer_id = import_plan.find_object_id(snapshot, "manufacturers", vendor)
                device_type_id = _device_type_id(snapshot, vendor, model)
                if manufacturer_id is None:
                    pending.append(f"fabricante '{vendor}'")
                if device_type_id is None:
                    pending.append(f"device-type '{vendor} {model}'")
                pending.append(f"device '{device_label}'")
                for nome in import_plan.missing_required_custom_fields(
                    snapshot, "dcim.device", device_custom_fields
                ):
                    issues.append(f"Campo obrigatorio sem valor: dcim.device.{nome}")
        elif device_exists:
            if len(encontrados) > 1:
                warnings.append(
                    f"Device '{device_label}' existe {len(encontrados)} vezes no NetBox; "
                    "resolvido pelo site da linha."
                )
            exato = next(
                (item["label"] for item in no_site if item.get("label") != device_label), None
            )
            if exato:
                warnings.append(
                    f"Device escrito como '{device_label}'; no NetBox e '{exato}'."
                )
        if role_label and papel is None and not any("Papel" in item for item in issues):
            issues.append(f"Papel de prefixo '{role_label}' nao esta no NetBox.")

        public_block = (cells.get(PUBLIC_KEY) or "").strip()
        link_ip, deduzido, aviso_ip = "", False, []
        if public_block:
            try:
                rede = parse_network(public_block, "bloco público")
                public_block = str(rede)
                link_ip, deduzido, aviso_ip = _resolve_link_ip(
                    public_block, cells.get(IP_KEY, ""), row.block_host
                )
            except ValueError as exc:
                issues.append(str(exc))
        warnings.extend(aviso_ip)

        lan_block = (cells.get(LAN_KEY) or "").strip()
        if lan_block:
            try:
                lan_block = str(parse_network(lan_block, "bloco LAN"))
            except ValueError as exc:
                issues.append(str(exc))

        campos_ip = dict(ip_custom_fields)
        zabbix = (cells.get(ZABBIX_KEY) or "").strip()
        if zabbix:
            campos_ip[ZABBIX_FIELD] = zabbix
        # O gate e por linha: a coluna da planilha pode ser o que satisfaz o campo
        # obrigatorio, entao conferir so o valor padrao bloquearia a importacao a toa.
        for nome in import_plan.missing_required_custom_fields(
            snapshot, "ipam.ipaddress", campos_ip
        ):
            issues.append(f"Campo obrigatorio sem valor: ipam.ipaddress.{nome}")
        for nome in import_plan.missing_required_custom_fields(
            snapshot, "ipam.prefix", prefix_custom_fields
        ):
            issues.append(f"Campo obrigatorio sem valor: ipam.prefix.{nome}")

        _collect_values(usados_ip, campos_ip)
        plan.rows.append(
            LinkPlanRow(
                row_number=row.row_number,
                site=site_label,
                device=(cells.get(DEVICE_KEY) or "").strip(),
                interface=(cells.get(INTERFACE_KEY) or "").strip() or DEFAULT_INTERFACE,
                public_block=public_block,
                lan_block=lan_block,
                link_ip=link_ip,
                link_ip_deduced=deduzido,
                vendor=vendor,
                model=model,
                device_role=device_role_label,
                device_role_id=papel_device.get("id") if papel_device else None,
                manufacturer_id=manufacturer_id,
                device_type_id=device_type_id,
                device_exists=device_exists,
                device_custom_fields=dict(device_custom_fields),
                pending=pending,
                role_label=role_label,
                description=(cells.get(DESCRIPTION_KEY) or "").strip(),
                provider=(cells.get(PROVIDER_KEY) or "").strip(),
                site_id=site.get("id") if site else None,
                role_id=papel.get("id") if papel else None,
                ip_custom_fields=campos_ip,
                prefix_custom_fields=dict(prefix_custom_fields),
                issues=issues,
                warnings=warnings,
            )
        )

    plan.custom_fields_used["ipam.ipaddress"] = _collapse_values(usados_ip)
    return plan
