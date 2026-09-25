"""Ponto de entrada do app: python -m app.main (ou pythonw -m app.main)."""

import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import theme  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.paths import resource_path, writable_base  # noqa: E402

FONTS_DIR = resource_path("app", "assets", "fonts")
ICON_PNG = resource_path("app", "assets", "app_icon.png")

# Fonte da interface. "Inter" e empacotada em app/assets/fonts; se por algum motivo
# nao carregar, cai para fontes do sistema.
UI_FONT_FAMILY = "Segoe UI"


def error_log_path():
    """Log de erros: ao lado do .exe quando empacotado; na raiz em desenvolvimento."""
    return writable_base() / "app_error.log"


ERROR_LOG = error_log_path()


def load_brand_fonts() -> str:
    """Registra as fontes Inter empacotadas. Retorna a familia a usar na UI."""
    global UI_FONT_FAMILY
    if not FONTS_DIR.is_dir():
        return UI_FONT_FAMILY

    loaded_families: list[str] = []
    for font_file in sorted(FONTS_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        if font_id >= 0:
            loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))

    if "Inter" in loaded_families:
        UI_FONT_FAMILY = "Inter"
        return UI_FONT_FAMILY

    # variavel (Inter Variable) tambem serve
    for family in loaded_families:
        if family.lower().startswith("inter"):
            UI_FONT_FAMILY = family
            return UI_FONT_FAMILY

    return UI_FONT_FAMILY


def app_icon() -> QIcon:
    """Icone do app (assets/app_icon.png), com fallback silencioso."""
    return QIcon(str(ICON_PNG)) if ICON_PNG.exists() else QIcon()


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """Garante que erros aparecam mesmo rodando sem console (pythonw)."""
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        ERROR_LOG.write_text(details, encoding="utf-8")
    except Exception:
        pass
    try:
        QMessageBox.critical(
            None,
            "Erro inesperado",
            f"Ocorreu um erro inesperado. Detalhes salvos em:\n{ERROR_LOG}\n\n{exc_value}",
        )
    except Exception:
        pass


sys.excepthook = _excepthook


def main() -> int:
    app = QApplication(sys.argv)
    # Nao usar setApplicationDisplayName: o Qt anexa esse nome ao titulo de cada
    # janela, gerando titulos duplicados (ex.: "... - NetBox - Importador de Cameras").
    app.setApplicationName("Importador de Cameras NetBox")
    app.setStyle("Fusion")

    family = load_brand_fonts()
    app.setFont(QFont(family, 10))
    app.setPalette(theme.build_dark_palette())
    app.setStyleSheet(theme.style_sheet(family))

    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
