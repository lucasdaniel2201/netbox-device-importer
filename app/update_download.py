"""Download do instalador de atualizacao em thread propria.

Diferente da checagem automatica (`app/update_check.py`), esta etapa so roda
depois de um clique explicito do usuario. Por isso a falha NAO e silenciosa:
se ele pediu para baixar e algo deu errado, a causa precisa aparecer na tela.

O arquivo tem ~57 MB, entao e baixado em streaming - nunca inteiro na memoria -
e gravado numa pasta temporaria. Como este e o unico ponto do app que baixa E
executa um binario, a URL passa por uma validacao de confianca antes de qualquer
byte sair: so aceitamos HTTPS em hosts do GitHub.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QObject, Qt, Signal, Slot

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.updater import TIMEOUT_S  # noqa: E402

CHUNK_SIZE = 64 * 1024
DOWNLOAD_DIR_NAME = "ImportadorNetBox-updates"

# Fronteira de confianca: o asset do GitHub pode vir de github.com/api.github.com
# e, depois do redirect, de objects.githubusercontent.com (ou outro subdominio de
# githubusercontent.com). Qualquer outro host e recusado ANTES do requests.get.
GITHUB_HOSTS_EXATOS = {"github.com", "api.github.com"}
GITHUB_USER_CONTENT_HOST = "githubusercontent.com"


def _host_do_github(host: str) -> bool:
    host = host.lower()
    if host in GITHUB_HOSTS_EXATOS:
        return True
    return host == GITHUB_USER_CONTENT_HOST or host.endswith("." + GITHUB_USER_CONTENT_HOST)


def validar_url_download(url: str) -> None:
    """Recusa URL que nao seja HTTPS de um host do GitHub.

    Levanta ValueError com mensagem clara porque a janela transforma isso num
    toast de erro: e acao do usuario, nao checagem silenciosa.
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        # Ex.: porta nao numerica. Mantem a mensagem no padrao das demais
        # recusas, em portugues, em vez de vazar o texto interno do urlparse.
        raise ValueError(f"URL de download invalida: {exc}") from exc
    if parsed.scheme != "https":
        raise ValueError("URL de download recusada: o endereco precisa ser HTTPS.")
    host = parsed.hostname
    if not host or not _host_do_github(host):
        raise ValueError(
            f"URL de download recusada: host '{host or 'desconhecido'}' nao e do GitHub."
        )


def abrir_instalador(caminho: str | Path) -> None:
    """Abre o Setup.exe para o Inno Setup fazer o upgrade por cima.

    Separada em funcao para os testes espionarem: `os.startfile` so existe no
    Windows, entao em outro sistema o erro e explicito em vez de quebrar o import.
    """
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise RuntimeError("Abrir o instalador automaticamente so e possivel no Windows.")
    startfile(str(caminho))


class UpdateDownloadWorker(QObject):
    """Baixa o instalador, emite progresso e abre ao terminar."""

    # Disparado pela UI (main thread); o slot roda na thread do download.
    request_download = Signal(str)
    progress = Signal(int, int)  # bytes baixados, total (0 quando desconhecido)
    finished = Signal(str)       # caminho do Setup.exe baixado e aberto
    failed = Signal(str)         # mensagem de erro para o usuario

    def __init__(self) -> None:
        super().__init__()
        self._cancel = False
        # QueuedConnection explicito pelo mesmo motivo do UpdateCheckWorker: a
        # conexao automatica foi decidida antes do moveToThread e, sem isso, o
        # download rodaria na thread da interface (congelando a janela).
        self.request_download.connect(self.download, Qt.ConnectionType.QueuedConnection)

    @Slot(str)
    def download(self, url: str) -> None:
        try:
            validar_url_download(url)
        except ValueError as exc:
            self.failed.emit(str(exc))
            return

        try:
            caminho = self._baixar(url)
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        try:
            abrir_instalador(caminho)
        except Exception as exc:
            # O download em si deu certo: mantemos o arquivo no disco para o
            # usuario conseguir executar manualmente se a abertura automatica falhar.
            self.failed.emit(f"Download concluido, mas nao foi possivel abrir o instalador: {exc}")
            return

        self.finished.emit(str(caminho))

    def _baixar(self, url: str) -> Path:
        # timeout vale para cada leitura do stream (nao para os 57 MB inteiros):
        # se a rede parar de responder, o erro aparece em TIMEOUT_S segundos.
        resposta = requests.get(url, stream=True, timeout=TIMEOUT_S)
        destino: Path | None = None
        try:
            resposta.raise_for_status()
            # `requests` segue o redirect do asset para objects.githubusercontent.com.
            # Valida o destino FINAL antes de consumir o corpo: se um redirect
            # inesperado apontar para fora do GitHub, nenhum byte do binario e lido.
            validar_url_download(resposta.url)
            total = int(resposta.headers.get("Content-Length") or 0)
            destino = self._destino(url)
            baixados = 0
            with open(destino, "wb") as arquivo:
                for bloco in resposta.iter_content(chunk_size=CHUNK_SIZE):
                    if self._cancel:
                        raise RuntimeError("Download cancelado.")
                    if not bloco:
                        continue
                    arquivo.write(bloco)
                    baixados += len(bloco)
                    self.progress.emit(baixados, total)
            return destino
        except Exception:
            # Nao deixar instalador pela metade na pasta temporaria: se falhou,
            # o arquivo nao serve para o Inno Setup e so atrapalharia um retry.
            if destino is not None:
                destino.unlink(missing_ok=True)
            raise
        finally:
            resposta.close()

    @staticmethod
    def _destino(url: str) -> Path:
        nome = Path(urlparse(url).path).name or "ImportadorCamerasSetup.exe"
        pasta = Path(tempfile.gettempdir()) / DOWNLOAD_DIR_NAME
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta / nome

    @Slot()
    def cancel(self) -> None:
        """Marca o download para parar no proximo bloco (encerramento da janela)."""
        self._cancel = True
