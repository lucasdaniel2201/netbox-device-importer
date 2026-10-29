"""Leitura, validacao e geracao do modelo de planilha de **links IP**.

Um "link" aqui e o enlace de internet de um site: o bloco publico entregue pelo
provedor (normalmente /30 ou /31), o bloco da rede local e o endereco do roteador
dentro do bloco publico. E o que a planilha real do projeto ja traz em colunas
separadas.

No NetBox isso vira tres objetos:

- `ipam.prefix` do bloco publico (escopo: site);
- `ipam.prefix` do bloco LAN (escopo: site);
- `ipam.ip-address` do endereco do link, vinculado a interface WAN do device.

A planilha so descreve; quem monta o plano e resolve o que falta e `app/link_plan.py`.
Nada aqui fala com o NetBox.
"""

from __future__ import annotations

import ipaddress
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.spreadsheet import (  # noqa: E402
    # Reexportado de proposito: a aba de listas e a mesma nos dois modelos, e o
    # teste da planilha de links confere o nome pelo modulo dela.
    DROPDOWN_ROWS as DROPDOWN_ROWS,
    LIST_SHEET_TITLE as LIST_SHEET_TITLE,
    ColumnSpec,
    add_dropdown,
    map_headers,
    new_data_sheet,
    normalize_for_match,
    read_raw_table,
    row_to_cells,
    write_list_sheet,
)

DATA_SHEET_TITLE = "Links IP"

SITE_KEY = "Site"
DEVICE_KEY = "Device"
VENDOR_KEY = "Vendor"
MODEL_KEY = "Model"
DEVICE_ROLE_KEY = "Device role"
INTERFACE_KEY = "Interface"
PUBLIC_KEY = "Public block"
LAN_KEY = "Lan block"
IP_KEY = "Link IP"
ROLE_KEY = "Prefix role"
ZABBIX_KEY = "Zabbix"
DESCRIPTION_KEY = "Description"
PROVIDER_KEY = "Provider"

# Valores aceitos no campo obrigatorio `add_to_zabbix` do NetBox desta instancia.
ZABBIX_VALUES = ("0", "1")

COLUMN_SPECS: tuple[ColumnSpec, ...] = (
    ColumnSpec(
        key=SITE_KEY,
        label="Site",
        aliases=("Site", "Local", "Unidade", "Delegacia"),
        sample="SITE EXEMPLO - Matriz",
        hint="Site do NetBox (obrigatorio). O bloco publico e o LAN ficam com este escopo.",
        required_value=True,
        fixed=True,
    ),
    ColumnSpec(
        key=DEVICE_KEY,
        label="Device",
        aliases=("Device", "Dispositivo", "Host"),
        sample="SITE EXEMPLO - Matriz",
        hint="Nome do device (roteador) que JA existe no NetBox. O app nao cria device aqui.",
        required_value=True,
        fixed=True,
    ),
    ColumnSpec(
        key=VENDOR_KEY,
        label="Fabricante",
        aliases=("Fabricante", "Vendor", "Marca"),
        sample="MikroTik",
        hint="Fabricante do roteador. So e usado quando o device ainda nao existe.",
    ),
    ColumnSpec(
        key=MODEL_KEY,
        label="Modelo",
        aliases=("Modelo", "Model", "Equipamento"),
        sample="RB760iGS",
        hint="Modelo do roteador (o 'Equipamento' da planilha). Usado para criar o device.",
    ),
    ColumnSpec(
        key=DEVICE_ROLE_KEY,
        label="Papel do device",
        aliases=("Papel do device", "Papel device", "Funcao do device"),
        sample="Roteador",
        hint="Papel (role) do device criado. Em branco = Roteador.",
    ),
    ColumnSpec(
        key=PUBLIC_KEY,
        label="Bloco público",
        aliases=(
            "Bloco publico",
            "Bloco de IP público",
            # Como a planilha real chama a coluna em uma das abas.
            "IP público",
            "WAN",
            "Prefixo público",
        ),
        sample="203.0.113.240/30",
        hint="Bloco entregue pelo provedor, em CIDR (ex.: 203.0.113.240/30). Vira um prefixo.",
        required_value=True,
        fixed=True,
    ),
    ColumnSpec(
        key=INTERFACE_KEY,
        label="Interface",
        aliases=("Interface", "Porta", "Interface WAN"),
        sample="wan1",
        hint="Interface do device onde o IP do link e vinculado. Em branco = wan1.",
    ),
    ColumnSpec(
        key=IP_KEY,
        label="IP do link",
        aliases=("IP do link", "IP", "IP WAN", "Endereço do link"),
        sample="203.0.113.241/30",
        hint=(
            "Endereco do roteador dentro do bloco publico. Em branco = o app deduz o "
            "primeiro endereco utilizavel (e avisa no plano)."
        ),
    ),
    ColumnSpec(
        key=LAN_KEY,
        label="Bloco LAN",
        aliases=("Bloco LAN", "Bloco lan", "LAN", "Rede local"),
        sample="10.10.48.0/24",
        hint="Bloco da rede local do site, em CIDR. Em branco = nao cria prefixo de LAN.",
    ),
    ColumnSpec(
        key=ROLE_KEY,
        label="Papel do prefixo",
        aliases=("Papel do prefixo", "Papel", "Role", "Função do prefixo"),
        sample="",
        hint="Papel (role) de IPAM para os prefixos. Em branco = sem papel.",
    ),
    ColumnSpec(
        key=ZABBIX_KEY,
        label="Adicionar ao Zabbix",
        aliases=("Adicionar ao Zabbix", "Zabbix", "add_to_zabbix"),
        sample="0",
        hint=(
            "Valor do campo obrigatorio add_to_zabbix (0 = nao, 1 = sim). "
            "Em branco = usa o valor observado num IP existente."
        ),
    ),
    ColumnSpec(
        key=DESCRIPTION_KEY,
        label="Descrição",
        aliases=("Descrição", "Descricao", "Link"),
        sample="PROVEDOR - SITE EXEMPLO",
        hint="Descricao do link: vai para os prefixos e para o IP.",
    ),
    ColumnSpec(
        key=PROVIDER_KEY,
        label="Fornecedor / chamado",
        aliases=("Fornecedor / chamado", "Fornecedor", "Chamado", "Des. parceiro"),
        sample="PROVEDOR - chamado 12345",
        hint="Provedor e numero do chamado. Vai para os comments do prefixo publico.",
    ),
)

COLUMNS_BY_KEY = {spec.key: spec for spec in COLUMN_SPECS}
TARGET_FIELDS = [spec.key for spec in COLUMN_SPECS]
FIXED_COLUMNS = [spec.key for spec in COLUMN_SPECS if spec.fixed]
REQUIRED_VALUES = [spec.key for spec in COLUMN_SPECS if spec.required_value]
DEFAULT_INTERFACE = "wan1"


def parse_network(value: str, rotulo: str = "bloco") -> ipaddress.IPv4Network:
    """CIDR do NetBox: IPv4, tolerante a host com mascara (`...241/30` -> `...240/30`).

    Mascara e obrigatoria: um endereco solto viraria um /32 no NetBox em silencio -
    num bloco de link, /32 quase sempre e engano de digitacao.
    """
    texto = (value or "").strip()
    if texto and "/" not in texto:
        raise ValueError(
            f"{rotulo.capitalize()} sem mascara: '{texto}'. Informe o CIDR (ex.: 203.0.113.240/30)."
        )
    try:
        rede = ipaddress.ip_network(texto, strict=False)
    except ValueError as exc:
        raise ValueError(f"{rotulo.capitalize()} com CIDR invalido: '{texto}'.") from exc
    if rede.version != 4:
        raise ValueError(f"{rotulo.capitalize()} so aceita IPv4: '{texto}'.")
    return rede


def parse_host_address(value: str, rede: ipaddress.IPv4Network) -> ipaddress.IPv4Address:
    """Endereco de host dentro do bloco (aceita com ou sem mascara)."""
    texto = (value or "").strip()
    parte = texto.split("/")[0]
    try:
        endereco = ipaddress.IPv4Address(parte)
    except ValueError as exc:
        raise ValueError(f"IP do link invalido: '{texto}'.") from exc
    if endereco not in rede:
        raise ValueError(f"IP do link {endereco} nao pertence ao bloco {rede}.")
    return endereco


def default_link_ip(rede: ipaddress.IPv4Network) -> ipaddress.IPv4Address:
    """Endereco do link quando a planilha nao traz um.

    - `/32`: o proprio endereco (bloco de um host so);
    - `/31`: o **segundo** endereco, que e o lado do cliente na convencao RFC 3021;
    - demais: o primeiro endereco utilizavel (rede + 1).
    """
    if rede.prefixlen == 32:
        return rede.network_address
    if rede.prefixlen == 31:
        return rede.network_address + 1
    return rede.network_address + 1


def usable_host_address(rede: ipaddress.IPv4Network, endereco: ipaddress.IPv4Address) -> bool:
    """Endereco pode ser atribuido? (rede e broadcast de /30 ou maior nao podem)"""
    if rede.prefixlen >= 31:
        return True
    return endereco != rede.network_address and endereco != rede.broadcast_address


@dataclass
class LinkRow:
    """Uma linha da planilha de links apos leitura, normalizacao e validacao."""

    row_number: int
    cells: dict[str, str]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Endereco do roteador que veio na propria coluna do bloco (planilhas reais
    # trazem `198.51.100.45/31` em vez de `198.51.100.44/31`).
    block_host: str = ""

    @property
    def valid(self) -> bool:
        return not self.issues

    @property
    def site(self) -> str:
        return self.cells.get(SITE_KEY, "")

    @property
    def device(self) -> str:
        return self.cells.get(DEVICE_KEY, "")


@dataclass
class LinkSheet:
    filename: str
    rows: list[LinkRow]
    columns_found: list[str] = field(default_factory=list)
    file_warnings: list[str] = field(default_factory=list)
    skipped_empty: int = 0

    @property
    def valid_rows(self) -> list[LinkRow]:
        return [row for row in self.rows if row.valid]

    @property
    def rows_with_errors(self) -> list[LinkRow]:
        return [row for row in self.rows if not row.valid]


def _normalize_cells(cells: dict[str, str]) -> tuple[list[str], str]:
    """Normaliza blocos e IP para a forma que o NetBox devolve.

    Devolve (avisos, endereco_do_roteador_achado_no_bloco). O segundo existe porque
    a planilha real costuma trazer **o endereco do roteador** na coluna do
    bloco: `198.51.100.45/31` e `10.10.66.10/24`, nao a rede. Deduzir o IP nesse
    caso daria outro endereco - entao a coluna do bloco tambem e fonte do IP do link.
    """
    avisos: list[str] = []
    endereco_no_bloco = ""
    for key, rotulo in ((PUBLIC_KEY, "bloco público"), (LAN_KEY, "bloco LAN")):
        valor = cells.get(key, "").strip()
        if not valor:
            continue
        rede = parse_network(valor, rotulo)
        cells[key] = str(rede)
        endereco = valor.split("/")[0].strip()
        if endereco != str(rede.network_address):
            if key == PUBLIC_KEY:
                endereco_no_bloco = endereco
                avisos.append(
                    f"Bloco público '{valor}' traz o endereço do roteador; a rede é "
                    f"'{rede}' e o endereço será usado como IP do link."
                )
            else:
                avisos.append(
                    f"{rotulo.capitalize()} ajustado de '{valor}' para a rede '{rede}'."
                )

    rede_texto = cells.get(PUBLIC_KEY, "")
    ip_texto = cells.get(IP_KEY, "").strip()
    if rede_texto and ip_texto:
        rede = ipaddress.ip_network(rede_texto)
        endereco = parse_host_address(ip_texto, rede)
        cells[IP_KEY] = f"{endereco}/{rede.prefixlen}"
        if "/" not in ip_texto:
            avisos.append(
                f"IP do link sem mascara: assumida a do bloco (/{rede.prefixlen})."
            )
    return avisos, endereco_no_bloco


def _validate_row(
    row_number: int,
    cells: dict[str, str],
    sites: dict[str, str],
    prefix_roles: dict[str, str],
    duplicates: dict[str, list[int]],
) -> LinkRow:
    resultado = LinkRow(row_number=row_number, cells=cells)

    site = cells.get(SITE_KEY, "").strip()
    if not site:
        resultado.issues.append("Site vazio (escolha na lista suspensa do modelo).")
    elif sites and normalize_for_match(site) not in sites:
        resultado.issues.append(
            f"Site '{site}' nao existe no NetBox (use a lista suspensa do modelo)."
        )

    if not cells.get(DEVICE_KEY, "").strip():
        resultado.issues.append("Device vazio: o IP do link precisa de um device existente.")

    for chave, rotulo in ((PUBLIC_KEY, "bloco público"), (LAN_KEY, "bloco LAN")):
        valor = cells.get(chave, "").strip()
        if not valor:
            continue
        try:
            parse_network(valor, rotulo)
        except ValueError as exc:
            resultado.issues.append(str(exc))

    rede_texto = cells.get(PUBLIC_KEY, "").strip()
    if not rede_texto:
        resultado.issues.append("Bloco público vazio (e o prefixo do link).")

    rede = None
    if rede_texto:
        try:
            rede = parse_network(rede_texto, "bloco público")
        except ValueError:
            rede = None

    if rede is not None:
        ip_texto = cells.get(IP_KEY, "").strip()
        if ip_texto:
            try:
                endereco = parse_host_address(ip_texto, rede)
            except ValueError as exc:
                resultado.issues.append(str(exc))
            else:
                if not usable_host_address(rede, endereco):
                    resultado.issues.append(
                        f"IP do link {endereco} e endereco de rede/broadcast de {rede}."
                    )

    papel = cells.get(ROLE_KEY, "").strip()
    if papel and prefix_roles and normalize_for_match(papel) not in prefix_roles:
        resultado.issues.append(
            f"Papel de prefixo '{papel}' nao existe no IPAM do NetBox."
        )

    zabbix = cells.get(ZABBIX_KEY, "").strip()
    if zabbix and zabbix not in ZABBIX_VALUES:
        resultado.issues.append(
            f"'Adicionar ao Zabbix' aceita {' ou '.join(ZABBIX_VALUES)} (recebido '{zabbix}')."
        )

    _mark_duplicates(resultado, cells, duplicates)
    return resultado


def _mark_duplicates(
    resultado: LinkRow, cells: dict[str, str], duplicates: dict[str, list[int]]
) -> None:
    """Bloco público, bloco LAN e IP repetidos em outra linha sao erro nas duas."""
    for chave, rotulo, severidade in (
        (PUBLIC_KEY, "Bloco público", resultado.issues),
        (IP_KEY, "IP do link", resultado.issues),
        # O mesmo /24 pode atender dois links do mesmo site (dois provedores). Na
        # planilha real isso acontece; aqui vale avisar, nao bloquear.
        (LAN_KEY, "Bloco LAN", resultado.warnings),
    ):
        valor = cells.get(chave, "").strip()
        if not valor:
            continue
        outras = [
            linha
            for linha in duplicates.get(f"{chave}:{normalize_for_match(valor)}", [])
            if linha != resultado.row_number
        ]
        if outras:
            severidade.append(
                f"{rotulo} repetido com a(s) linha(s): "
                + ", ".join(str(linha) for linha in outras)
            )


def _index(values: list[str] | None) -> dict[str, str]:
    return {normalize_for_match(value): value for value in (values or []) if value}


def read_file(
    path: Path,
    sites: list[str] | None = None,
    prefix_roles: list[str] | None = None,
) -> LinkSheet:
    """Le a planilha de links (.xlsx ou .csv).

    `sites` e `prefix_roles` (opcionais) validam as colunas contra o NetBox.
    """
    header_cells, table_rows, file_warnings = read_raw_table(path)
    index_by_target, missing = map_headers(header_cells, COLUMN_SPECS, TARGET_FIELDS)

    faltando = [COLUMNS_BY_KEY[key].label for key in FIXED_COLUMNS if key in missing]
    if faltando:
        raise ValueError(
            "Coluna(s) obrigatoria(s) do modelo de links nao encontrada(s): "
            + ", ".join(faltando)
            + ". Confira o cabecalho ou baixe o modelo de exemplo."
        )

    cells_por_linha: list[tuple[int, dict[str, str]]] = []
    ignoradas = 0
    for row_number, values in enumerate(table_rows, start=2):
        cells = row_to_cells(values, index_by_target, TARGET_FIELDS)
        if not any(cells.get(key, "").strip() for key in (SITE_KEY, DEVICE_KEY, PUBLIC_KEY)):
            ignoradas += 1
            continue
        cells_por_linha.append((row_number, cells))

    # Normaliza antes de comparar: "203.0.113.241/30" e "203.0.113.240/30" sao o
    # mesmo bloco, e a duplicidade tem que pegar isso.
    normalizadas: list[tuple[int, dict[str, str], list[str], list[str], str]] = []
    for row_number, cells in cells_por_linha:
        try:
            avisos, endereco_no_bloco = _normalize_cells(cells)
        except ValueError as exc:
            normalizadas.append((row_number, cells, [], [str(exc)], ""))
            continue
        normalizadas.append((row_number, cells, avisos, [], endereco_no_bloco))

    duplicates: dict[str, list[int]] = {}
    for row_number, cells, _avisos, _erros, _endereco in normalizadas:
        for chave in (PUBLIC_KEY, LAN_KEY, IP_KEY):
            valor = cells.get(chave, "").strip()
            if valor:
                duplicates.setdefault(
                    f"{chave}:{normalize_for_match(valor)}", []
                ).append(row_number)

    known_sites = _index(sites)
    known_roles = _index(prefix_roles)

    rows: list[LinkRow] = []
    for row_number, cells, avisos, erros, endereco_no_bloco in normalizadas:
        linha = _validate_row(row_number, cells, known_sites, known_roles, duplicates)
        linha.issues[:0] = erros
        linha.warnings[:0] = avisos
        linha.block_host = endereco_no_bloco
        rows.append(linha)

    return LinkSheet(
        filename=path.name,
        rows=rows,
        columns_found=[key for key in TARGET_FIELDS if key in index_by_target],
        file_warnings=file_warnings,
        skipped_empty=ignoradas,
    )


def write_example_template(
    path: Path,
    sites: list[str] | None = None,
    prefix_roles: list[str] | None = None,
    devices: list[str] | None = None,
) -> None:
    """Gera o modelo de links, com listas suspensas de Site, Papel e Device.

    Device entra como lista suspensa pelo mesmo motivo que Site: e uma referencia do
    NetBox. Sao milhares de nomes, mas a lista fica numa aba filtrável e a celula
    aceita digitar para pular ao item.
    """
    known_sites = sorted({site for site in (sites or []) if site})
    known_roles = sorted({role for role in (prefix_roles or []) if role})
    known_devices = sorted({device for device in (devices or []) if device})

    # O papel so entra na amostra quando for um papel de link: herdar "Reservado"
    # (o primeiro da lista) marcaria os blocos com o papel errado.
    papel_amostra = next(
        (
            role
            for role in known_roles
            if any(chave in normalize_for_match(role) for chave in ("link", "wan", "internet"))
        ),
        "",
    )

    sample = []
    for spec in COLUMN_SPECS:
        if spec.key == SITE_KEY and known_sites:
            sample.append(known_sites[0])
        elif spec.key == ROLE_KEY:
            sample.append(papel_amostra)
        else:
            sample.append(spec.sample)

    workbook, sheet = new_data_sheet(DATA_SHEET_TITLE, list(COLUMN_SPECS), sample)

    if known_sites or known_roles or known_devices:
        write_list_sheet(
            workbook,
            [
                ("Sites", known_sites),
                ("Papeis de prefixo", known_roles),
                ("Devices", known_devices),
            ],
        )
        selected = list(TARGET_FIELDS)
        add_dropdown(
            sheet,
            selected,
            SITE_KEY,
            "A",
            known_sites,
            "Site invalido",
            "Escolha um site que exista no NetBox (use a seta da celula).",
        )
        add_dropdown(
            sheet,
            selected,
            ROLE_KEY,
            "B",
            known_roles,
            "Papel invalido",
            "Escolha um papel de prefixo que exista no NetBox (use a seta da celula).",
        )
        add_dropdown(
            sheet,
            selected,
            DEVICE_KEY,
            "C",
            known_devices,
            "Device invalido",
            "Escolha um device que exista no NetBox (o importador de links nao cria device).",
        )

    workbook.save(path)
    workbook.close()
