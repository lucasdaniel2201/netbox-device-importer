"""Utilitario de desenvolvimento: gera screenshots reais do app sem abrir janela.

Roda a interface com `QT_QPA_PLATFORM=offscreen`, reproduzindo a configuracao do
`app/main.py` (tema Fusion, fontes da marca, paleta escura e folha de estilos),
e salva PNGs prontos para o README em `docs/screenshots/`.

Como rodar:

    python tools/screenshots.py

E um utilitario de desenvolvimento, nao um teste: ele instancia a `MainWindow`
de verdade, mas com a checagem de atualizacoes e o armazenamento de token
substituidos para o resultado ser deterministico e offline. Os PNGs sao
sobrescritos a cada execucao.

Atencao: `import app.main` instala um `sys.excepthook` global (efeito colateral
do modulo, usado para exibir erros mesmo rodando sem console). Aqui isso e
aceitavel e inofensivo para o proposito do script.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

# Precisa vir ANTES de qualquer import do PySide6: o Qt decide a plataforma de
# janela na inicializacao, e o offscreen garante que nada apareca na tela.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

# A ordem importa: `app.main` importa `app.main_window`, entao nao ha efeito
# colateral adicional alem do excepthook mencionado no docstring.
import app.main as main_mod  # noqa: E402
import app.main_window as main_window  # noqa: E402
from app import credentials, update_check  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.updater import Release  # noqa: E402

# Endereco ficticio para os screenshots: a tela de login/carregamento exibe o
# NETBOX_URL configurado, e o README nao pode expor hostname/IP real de cliente.
FICTITIOUS_NETBOX_URL = "https://netbox.exemplo.local"

OUT_DIR = ROOT / "docs" / "screenshots"


def settle(app: QApplication, seconds: float = 0.4) -> None:
    """Processa eventos por alguns instantes para layout e animacoes assentarem.

    O `window.grab()` de uma janela recem-exibida pode sair em branco; chamar
    `processEvents()` em loop (em vez de uma unica vez) deixa o Qt desenhar,
    rodar o spinner e concluir a animacao de entrada do toast.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def snapshot_sintetico() -> dict:
    """Snapshot de ambiente 100% ficticio, no formato que a MainWindow espera.

    O formato segue `tests/test_session.py` (funcao `snapshot`), mas com dados
    plausiveis e inventados: nenhum hostname, IP ou nome de cliente real.
    """
    return {
        "base_url": FICTITIOUS_NETBOX_URL,
        "token_scheme": "Token",
        "tls_verified": True,
        "tls_blocked": False,
        "status": {"netbox-version": "4.3.6"},
        "api_version": "4.3",
        "current_user": {
            "username": "analista.exemplo",
            "is_superuser": False,
            "is_staff": False,
        },
        "objects": {
            "sites": [
                {"id": 1, "label": "Matriz Centro"},
                {"id": 2, "label": "Filial Norte"},
                {"id": 3, "label": "Filial Sul"},
                {"id": 4, "label": "CD Logistica"},
            ],
            "locations": [
                {"id": 11, "label": "Predio A", "site": "Matriz Centro"},
                {"id": 12, "label": "Predio B", "site": "Matriz Centro"},
            ],
            "regions": [
                {"id": 21, "label": "Sudeste"},
                {"id": 22, "label": "Sul"},
            ],
            "site_groups": [
                {"id": 31, "label": "Operacao"},
                {"id": 32, "label": "Administrativo"},
            ],
            "racks": [
                {"id": 41, "label": "RACK-01", "site": "Matriz Centro"},
                {"id": 42, "label": "RACK-02", "site": "Filial Norte"},
                {"id": 43, "label": "RACK-03", "site": "CD Logistica"},
            ],
            "device_roles": [
                {"id": 51, "label": "Camera"},
                {"id": 52, "label": "DVR"},
            ],
            "manufacturers": [
                {"id": 61, "label": "Hikvision"},
                {"id": 62, "label": "Dahua"},
            ],
            "device_types": [
                {"id": 71, "label": "DS-2CD2143", "manufacturer": "Hikvision"},
                {"id": 72, "label": "IPC-HDW2431", "manufacturer": "Dahua"},
            ],
            "tags": [
                {"id": 81, "label": "monitorado"},
                {"id": 82, "label": "externo"},
                {"id": 83, "label": "interno"},
            ],
            "tenants": [
                {"id": 91, "label": "Exemplo Ltda"},
            ],
        },
        "counts": {
            "devices": 4,
            "interfaces": 12,
            "ip_addresses": 4,
            "prefixes": 2,
            "journal_entries": 0,
        },
        "schema": {},
        "capabilities": {
            "device": ["GET", "POST", "PUT", "PATCH"],
            "device_type": ["GET", "POST"],
            "manufacturer": ["GET", "POST"],
            "device_role": ["GET"],
            "site": ["GET"],
            "location": ["GET"],
            "tenant": ["GET"],
            "interface": ["GET"],
            "ip_address": ["GET", "POST"],
            "tag": ["GET"],
        },
        "custom_fields": [
            {
                "id": 101,
                "name": "Departamento",
                "label": "Departamento",
                "type": "text",
                "required": False,
                "object_types": ["dcim.device", "dcim.site"],
                "choices": [],
            },
            {
                "id": 102,
                "name": "Criticidade",
                "label": "Criticidade",
                "type": "select",
                "required": True,
                "object_types": ["dcim.device"],
                "choices": ["Baixa", "Media", "Alta"],
            },
            {
                "id": 103,
                "name": "Aprovisionado_por",
                "label": "Aprovisionado por",
                "type": "text",
                "required": False,
                "object_types": ["dcim.device"],
                "choices": [],
            },
        ],
        "content_types": {},
        "errors": [],
    }


def capture(window: MainWindow, filename: str, app: QApplication) -> None:
    """Exibe a janela, aguarda o layout e salva o PNG em docs/screenshots/."""
    window.resize(1240, 900)
    window.show()
    settle(app, 0.5)

    pixmap = window.grab()
    destino = OUT_DIR / filename
    if not pixmap.save(str(destino), "PNG"):
        raise RuntimeError(f"Nao consegui gravar o screenshot: {destino}")

    print(f"Gerado: {destino} ({pixmap.width()}x{pixmap.height()})")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # Mesma configuracao do app/main.py: Fusion, fonte da marca, paleta e QSS.
    app.setApplicationName("Importador de Cameras NetBox")
    app.setStyle("Fusion")
    family = main_mod.load_brand_fonts()
    app.setFont(QFont(family, 10))
    app.setPalette(main_mod.theme.build_dark_palette())
    app.setStyleSheet(main_mod.theme.style_sheet(family))

    icon = main_mod.app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    window: MainWindow | None = None
    with tempfile.TemporaryDirectory() as tmp:
        token_file = Path(tmp) / "token.dat"

        # Token apontando para um caminho inexistente: a MainWindow abre sempre
        # na tela de login, sem interferencia de credenciais guardadas na maquina.
        token_patch = mock.patch.object(credentials, "token_path", lambda: token_file)
        # A checagem de atualizacoes faria HTTP real para api.github.com; aqui
        # vira um no-op para o script ser offline e deterministico.
        update_patch = mock.patch.object(
            update_check.UpdateCheckWorker, "check", lambda _worker: None
        )
        # Substitui so o rotulo exibido na tela (login/carregamento) por um
        # endereco ficticio, para nao expor o servidor real no README.
        url_patch = mock.patch.object(
            main_window, "NETBOX_URL", FICTITIOUS_NETBOX_URL
        )

        try:
            with token_patch, update_patch, url_patch:
                window = MainWindow()
                window.resize(1240, 900)

                # 1) Login: estado inicial, sem token guardado.
                capture(window, "login.png", app)

                # 2) Carregamento: usa _go_loading() e deixa o spinner desenhar.
                window._go_loading()
                settle(app, 0.6)
                capture(window, "carregando.png", app)

                # 3) Ambiente NetBox: para o carregamento e povoa com dados ficticios.
                window._stop_loading()
                window._go_env()
                window._populate(snapshot_sintetico())
                settle(app, 0.6)
                capture(window, "ambiente.png", app)

                # 4) Aviso de atualizacao: volta ao login e dispara o aviso pelo
                # caminho REAL do app (`_on_update_available`), e nao por um toast
                # generico - assim o botao de baixar o instalador aparece na
                # imagem exatamente como aparece para o usuario.
                window._go_login()
                settle(app, 0.3)
                window._on_update_available(
                    Release(
                        versao="1.0.1",
                        page_url=(
                            "https://github.com/lucasdaniel2201/netbox-device-importer"
                            "/releases/tag/v1.0.1"
                        ),
                        setup_url=(
                            "https://github.com/lucasdaniel2201/netbox-device-importer"
                            "/releases/download/v1.0.1/ImportadorCamerasSetup-1.0.1.exe"
                        ),
                    )
                )
                settle(app, 0.6)
                capture(window, "atualizacao.png", app)
        finally:
            if window is not None:
                window.close()
                app.processEvents()

    return 0


if __name__ == "__main__":
    sys.exit(main())
