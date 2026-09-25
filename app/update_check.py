"""Checagem de atualizacoes em thread propria.

Segue o padrao do `SessionWorker` (`app/session.py`): um `QObject` movido para uma
`QThread`, comunicando por sinais. Roda no inicio do app, antes do login, e nao
depende da sessao do NetBox.

Falha aqui e silenciosa de proposito: sem internet e o caso normal do analista em
campo, nao e erro para mostrar na tela.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.updater import buscar_ultima_release, ha_atualizacao  # noqa: E402
from app.version import __version__  # noqa: E402


class UpdateCheckWorker(QObject):
    """Consulta a ultima release e avisa se houver versao mais nova."""

    # Disparado pela UI (main thread); o slot roda na thread da checagem
    request_check = Signal()
    # Emitido SO quando ha atualizacao, com o Release encontrado.
    available = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        # QueuedConnection explicito, e nao a conexao automatica: o worker troca de
        # thread no moveToThread, e a conexao automatica foi decidida quando ele
        # ainda estava na thread principal (virou direta). Se alguem emitir
        # request_check da interface, a conexao direta rodaria o slot - e o
        # requests.get junto - na thread da interface, congelando a janela.
        self.request_check.connect(self.check, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def check(self) -> None:
        try:
            release = buscar_ultima_release()
        except Exception:
            # Sem internet, repo fora do ar ou sem Release publicada: nao ha o que
            # avisar. Se a checagem passar a falhar sempre, olhar aqui primeiro.
            return
        if ha_atualizacao(__version__, release.versao):
            self.available.emit(release)
