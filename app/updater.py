"""Verificacao de atualizacoes via Github Releases."""

from __future__ import annotations

from dataclasses import dataclass

import requests

GITHUB_OWNER = "lucasdaniel2201"
GITHUB_REPO = "netbox-device-importer"
TIMEOUT_S = 5.0


@dataclass(frozen=True)
class Release:
    versao: str             # tag_name sem o "v" na frente
    page_url: str           # html_url
    setup_url: str | None   # browser_download_url do "*Setup*.exe"


def parse_version(texto: str) -> tuple[int, ...]:
    """'v1.10.0' -> (1, 10, 0). Aceita com e sem 'v'.

    O formato aceito e so numeros separados por ponto. Um sufixo tipo '-rc1'
    levantaria ValueError no int() - e como quem chama a checagem engole a
    excecao de proposito, uma tag fora desse padrao deixaria o app quieto para
    sempre. A versao publicada neste projeto segue o padrao (ver app/version.py).
    """
    sem_v = texto.removeprefix("v")
    pedacos = sem_v.split(".")
    numeros = []
    for pedaco in pedacos:
        numeros.append(int(pedaco))
    return tuple(numeros)


def ha_atualizacao(atual: str, remota: str) -> bool:
    """True somente se 'remota' for MAIS NOVA que 'atual'."""
    return parse_version(remota) > parse_version(atual)


def buscar_ultima_release() -> Release:
    """Consulta a ultima release no Github e devolve um Release."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    resposta = requests.get(url, timeout=TIMEOUT_S)
    resposta.raise_for_status()
    dados = resposta.json()
    versao = dados["tag_name"].removeprefix("v")
    page_url = dados["html_url"]
    setup_url = None
    for asset in dados["assets"]:
        nome = asset["name"]
        if nome.startswith("ImportadorCamerasSetup-") and nome.endswith(".exe"):
            setup_url = asset["browser_download_url"]
            break

    return Release(versao=versao, page_url=page_url, setup_url=setup_url)
