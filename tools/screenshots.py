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

from openpyxl import load_workbook  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

# A ordem importa: `app.main` importa `app.main_window`, entao nao ha efeito
# colateral adicional alem do excepthook mencionado no docstring.
import app.main as main_mod  # noqa: E402
from app import credentials, preferences, reports, theme, update_check  # noqa: E402
from app.import_dialog import ImportDialog  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.spreadsheet import write_example_template  # noqa: E402
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


def capture(
    window: MainWindow,
    filename: str,
    app: QApplication,
    size: tuple[int, int] | None = (1240, 900),
) -> None:
    """Exibe a janela, aguarda o layout e salva o PNG em docs/screenshots/."""
    if size is not None:
        window.resize(*size)
    window.show()
    settle(app, 0.5)

    pixmap = window.grab()
    destino = OUT_DIR / filename
    if not pixmap.save(str(destino), "PNG"):
        raise RuntimeError(f"Nao consegui gravar o screenshot: {destino}")

    print(f"Gerado: {destino} ({pixmap.width()}x{pixmap.height()})")


def snapshot_para_captura() -> dict:
    """Snapshot do ambiente de exemplo, pronto para as telas.

    Parte do snapshot ficticio e ajusta duas coisas que mudariam a imagem: o
    custom field obrigatorio que o app nao preenche (apareceria como bloqueio) e
    as permissoes de escrita de interface/IP (apareceriam como leitura parcial).
    """
    snap = snapshot_sintetico()
    for campo in snap["custom_fields"]:
        if campo["name"] == "Criticidade":
            campo["required"] = False
    snap["capabilities"]["interface"] = ["GET", "POST", "PATCH"]
    snap["capabilities"]["ip_address"] = ["GET", "POST", "PATCH"]
    snap["schema"] = {
        chave: {"actions": {acao: {} for acao in acoes}}
        for chave, acoes in snap["capabilities"].items()
    }
    return snap


def planilha_de_exemplo(path: Path, snap: dict) -> None:
    """Gera um .xlsx valido e preenche linhas plausiveis (ficticias)."""
    sites = [item["label"] for item in snap["objects"]["sites"]]
    roles = [item["label"] for item in snap["objects"]["device_roles"]]
    write_example_template(path, sites=sites, roles=roles)

    linhas = [
        ["CAM-RECEPCAO-01", "Matriz Centro", "Camera", "10.10.10.11", "Hikvision",
         "DS-2CD2143", "V5.7.55", "AA-BB-CC-DD-EE-01", "", "Recepção"],
        ["CAM-RECEPCAO-02", "Matriz Centro", "Camera", "10.10.10.12", "Hikvision",
         "DS-2CD2143", "V5.7.55", "AA-BB-CC-DD-EE-02", "", "Recepção lateral"],
        ["CAM-PATIO-01", "Matriz Centro", "Camera", "10.10.10.20", "Dahua",
         "IPC-HDW2431", "V2.8", "AA-BB-CC-DD-EE-03", "", "Pátio"],
        ["CAM-ESTOQUE-01", "CD Logistica", "Camera", "10.30.0.11", "Intelbras",
         "VIP 1230 B", "", "", "", "Estoque"],
        ["SW-FILIAL-NORTE", "Filial Norte", "DVR", "", "Hikvision", "DS-2CD2143",
         "", "", "", "Switch do rack"],
    ]
    workbook = load_workbook(path)
    sheet = workbook["Cameras"]
    for indice, linha in enumerate(linhas, start=2):
        for coluna, valor in enumerate(linha, start=1):
            sheet.cell(row=indice, column=coluna, value=valor)
    workbook.save(path)
    workbook.close()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # Mesma configuracao do app/main.py: Fusion, fonte da marca e tema aplicado
    # pelo proprio app (paleta + QSS + icones).
    app.setApplicationName("Importador NetBox")
    app.setStyle("Fusion")
    family = main_mod.load_brand_fonts()
    app.setFont(QFont(family, 10))
    theme.apply(app, family, "dark")

    icon = main_mod.app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    window: MainWindow | None = None
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        token_file = tmp / "token.dat"
        reports_dir = tmp / "reports"
        reports_dir.mkdir()
        sheet_path = tmp / "modelo-preenchido.xlsx"
        snap = snapshot_para_captura()
        planilha_de_exemplo(sheet_path, snap)

        # Token apontando para um caminho inexistente: a MainWindow abre sempre
        # na tela de login, sem interferencia de credenciais guardadas na maquina.
        token_patch = mock.patch.object(credentials, "token_path", lambda: token_file)
        # A checagem de atualizacoes faria HTTP real para api.github.com; aqui
        # vira um no-op para o script ser offline e deterministico.
        update_patch = mock.patch.object(
            update_check.UpdateCheckWorker, "check", lambda _worker: None
        )
        # Historico vazio: o README nao pode parecer ter importacoes reais.
        reports_patch = mock.patch.object(reports, "reports_dir", lambda: reports_dir)
        # O tema claro e uma preferencia: nao pode FICAR salva na maquina de quem
        # gera as imagens. Redireciona para um arquivo temporario.
        preferences_patch = mock.patch.object(
            preferences, "preferences_path", lambda: tmp / "preferences.json"
        )
        # Endereco ficticio: o README nao pode expor o servidor real do cliente.
        # Cada tela importa o nome no proprio modulo, entao o patch e por modulo.
        url_patches = [
            mock.patch("app.pages.login_page.NETBOX_URL", FICTITIOUS_NETBOX_URL),
            mock.patch("app.pages.loading_page.NETBOX_URL", FICTITIOUS_NETBOX_URL),
            mock.patch("app.pages.settings_page.NETBOX_URL", FICTITIOUS_NETBOX_URL),
        ]

        try:
            with (
                token_patch,
                update_patch,
                reports_patch,
                preferences_patch,
                url_patches[0],
                url_patches[1],
                url_patches[2],
            ):
                window = MainWindow()
                window.resize(1280, 880)

                # 1) Login: estado inicial, sem token guardado.
                capture(window, "login.png", app)

                # 2) Carregando: o spinner precisa estar rodando para desenhar.
                window._go_loading()
                settle(app, 0.6)
                capture(window, "carregando.png", app)

                # 3) Ambiente: para o carregamento e povoa com dados ficticios.
                window._stop_loading()
                window._go_env()
                window._populate(snap)
                settle(app, 0.6)
                capture(window, "painel.png", app)

                for indice, arquivo in (
                    (1, "importacao.png"),
                    (2, "links.png"),
                    (4, "configuracoes.png"),
                ):
                    window._shell.set_page(indice, animate=False)
                    if indice == 4:
                        window._shell.settings_page._toggle_tree()
                    settle(app, 0.4)
                    capture(window, arquivo, app)

                # 4) Dialogo de importacao, com um plano real montado a partir de
                # uma planilha de exemplo (nada de tabela inventada na imagem).
                dialog = ImportDialog(window, snap, window._session)
                dialog.resize(1160, 780)
                dialog.show()
                settle(app, 0.3)
                dialog._load_sheet(str(sheet_path))
                settle(app, 0.5)
                capture(dialog, "dialogo-revisao.png", app, size=None)
                dialog.reject()

                # 5) Tema claro: mesma tela, outra paleta.
                window._on_theme_selected("light")
                window._shell.set_page(0, animate=False)
                settle(app, 0.6)
                capture(window, "painel-claro.png", app)
                window._on_theme_selected("dark")

                # 6) Aviso de atualizacao: pelo caminho REAL do app, para o botao
                # aparecer exatamente como aparece para o usuario.
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
