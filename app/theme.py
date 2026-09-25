"""Paleta e tema visual do app: tema escuro na identidade do NetBox.

Cores da marca NetBox Labs:
- Bright Turquoise `#00F2D4` (acento principal)
- Turquoise Blue `#4AEADC` (acento claro)
- Swamp `#001423` (navy profundo, fundo do app)

Nota de acessibilidade: o texto sobre o turquesa e **escuro** (Swamp). Branco
sobre `#00F2D4` tem contraste 1.43:1 (reprova em WCAG) e o navy tem 14.65:1
(AAA) - por isso os botoes primarios usam texto navy.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# ------------------------------------------------------------------- paleta
SWAMP = "#001423"          # navy profundo (marca)
PAGE_BG = "#001423"        # fundo das paginas
CARD = "#01202F"           # cartoes e campos
SURFACE_HI = "#033247"     # superficie elevada (headers, hover)
ALT_ROW = "#04222E"        # linhas alternadas
DISABLED_BG = "#0A2B39"    # fundo de controles desabilitados
BORDER = "#0E4152"
BORDER_STRONG = "#1C6076"
GRID = "#0B3644"

TEXT = "#E6F4F6"
TEXT_MUTED = "#9DBAC3"
TEXT_FAINT = "#6C8A94"
DISABLED_TEXT = "#5A7681"

TURQUOISE = "#00F2D4"      # acento principal
TURQUOISE_HI = "#4AEADC"   # acento claro (hover)
TURQUOISE_DK = "#00C4AC"   # acento escuro (pressed/foco)
NAVY_800 = "#033247"       # fim do gradiente das faixas

# Cores semanticas (avisos/toasts), harmonizadas com o tema.
SUCCESS = "#3FD6A4"
ERROR = "#FF6B5E"
WARNING = "#F0B429"
INFO = "#5AA9E8"

# Preenchimento das variacoes de estado dos botoes primarios.
BUTTON_DISABLED_BG = DISABLED_BG

_TOKENS = {
    "SWAMP": SWAMP,
    "PAGE_BG": PAGE_BG,
    "CARD": CARD,
    "SURFACE_HI": SURFACE_HI,
    "ALT_ROW": ALT_ROW,
    "DISABLED_BG": DISABLED_BG,
    "BORDER": BORDER,
    "BORDER_STRONG": BORDER_STRONG,
    "GRID": GRID,
    "TEXT": TEXT,
    "TEXT_MUTED": TEXT_MUTED,
    "TEXT_FAINT": TEXT_FAINT,
    "DISABLED_TEXT": DISABLED_TEXT,
    "TURQUOISE": TURQUOISE,
    "TURQUOISE_HI": TURQUOISE_HI,
    "TURQUOISE_DK": TURQUOISE_DK,
    "NAVY_800": NAVY_800,
    "SUCCESS": SUCCESS,
    "ERROR": ERROR,
    "WARNING": WARNING,
    "INFO": INFO,
    "BUTTON_DISABLED_BG": BUTTON_DISABLED_BG,
}

STYLE_TEMPLATE = """
* {
    font-family: "__UI_FONT__", "Segoe UI", "Inter", sans-serif;
}
QWidget {
    color: __TEXT__;
    font-size: 13px;
}
QMainWindow, QStackedWidget, QDialog {
    background: __SWAMP__;
}
QLabel {
    background: transparent;
    color: __TEXT__;
}
QFrame#brandBanner {
    /* Gradiente sutil do navy para um tom mais azulado: da profundidade sem ruido. */
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 __SWAMP__, stop:1 __NAVY_800__);
    border: none;
    border-bottom: 2px solid __TURQUOISE__;
}
QLabel#brandTitle {
    color: __TEXT__;
    font-size: 21px;
    font-weight: 700;
    letter-spacing: -0.2px;
}
QLabel#brandSubtitle {
    color: rgba(230, 244, 246, 0.72);
    font-size: 11px;
    letter-spacing: 0.3px;
}
QLabel#brandSession {
    color: __TURQUOISE__;
    font-size: 13px;
    font-weight: 600;
}
QLabel#loginFooter {
    color: __TEXT_FAINT__;
    font-size: 11px;
    letter-spacing: 0.2px;
}
QWidget#loadingPage {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 __SWAMP__, stop:1 __NAVY_800__);
}
QLabel#loadingTitle {
    color: __TEXT__;
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.2px;
}
QLabel#loadingServer {
    color: __TURQUOISE__;
    font-size: 12px;
    letter-spacing: 0.3px;
}
QLabel#loadingHint {
    color: rgba(230, 244, 246, 0.60);
    font-size: 11px;
}
QLabel#savedToken {
    color: __TEXT_MUTED__;
    font-size: 11px;
}
QLabel#serverLabel {
    color: __TEXT__;
    font-weight: 600;
    font-size: 12px;
}
QFrame#card {
    background: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 14px;
}
QLabel#cardTitle {
    font-size: 20px;
    font-weight: 700;
    color: __TEXT__;
    letter-spacing: -0.2px;
}
QLabel#cardSubtitle {
    color: __TEXT_MUTED__;
    font-size: 12px;
}
QLabel#fieldLabel {
    color: __TEXT__;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.2px;
}
QPushButton {
    background: __CARD__;
    border: 1px solid __BORDER_STRONG__;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 600;
    color: __TEXT__;
    outline: none;
}
QPushButton:hover {
    background: __SURFACE_HI__;
    border-color: __TURQUOISE_DK__;
}
QPushButton:focus {
    border: 2px solid __TURQUOISE__;
}
QPushButton:disabled {
    background: __DISABLED_BG__;
    color: __DISABLED_TEXT__;
    border-color: __BORDER__;
}
QPushButton#primaryButton {
    background: __TURQUOISE__;
    border: none;
    color: __SWAMP__;
    font-weight: 700;
}
QPushButton#primaryButton:hover {
    background: __TURQUOISE_HI__;
}
QPushButton#primaryButton:pressed {
    background: __TURQUOISE_DK__;
}
QPushButton#primaryButton:focus {
    border: 2px solid #E6F4F6;
}
QPushButton#primaryButton:disabled {
    background: __BUTTON_DISABLED_BG__;
    color: __DISABLED_TEXT__;
    border: 1px solid __BORDER__;
}
QPushButton#bannerButton {
    background: rgba(230, 244, 246, 0.10);
    border: 1px solid rgba(230, 244, 246, 0.35);
    border-radius: 6px;
    color: __TEXT__;
    padding: 6px 12px;
    font-weight: 600;
    letter-spacing: 0.2px;
}
QPushButton#bannerButton:hover {
    background: rgba(0, 242, 212, 0.16);
    border-color: __TURQUOISE__;
    color: __TEXT__;
}
QPushButton#bannerButton:disabled {
    background: rgba(230, 244, 246, 0.05);
    color: rgba(230, 244, 246, 0.45);
    border-color: rgba(230, 244, 246, 0.18);
}
QPushButton#flatButton {
    background: transparent;
    border: none;
    color: __TEXT_MUTED__;
    padding: 4px 6px;
    font-weight: 600;
}
QPushButton#flatButton:hover {
    color: __TURQUOISE__;
}
QGroupBox {
    background: __CARD__;
    border: 1px solid __BORDER__;
    border-radius: 10px;
    /* A faixa do titulo precisa ser mais alta que o texto (senao ele corta a borda). */
    margin-top: 26px;
    padding: 10px 12px 12px 12px;
    font-weight: 600;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 4px 6px 0 6px;
    color: __TEXT__;
    letter-spacing: 0.2px;
}
QLineEdit, QSpinBox, QComboBox {
    background: __CARD__;
    color: __TEXT__;
    border: 1px solid __BORDER_STRONG__;
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: __TURQUOISE__;
    selection-color: __SWAMP__;
    outline: none;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 2px solid __TURQUOISE__;
    padding: 6px 8px;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: __SURFACE_HI__;
    color: __TEXT__;
    border: 1px solid __BORDER_STRONG__;
    selection-background-color: __TURQUOISE__;
    selection-color: __SWAMP__;
    outline: none;
}
QCheckBox {
    color: __TEXT__;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid __BORDER_STRONG__;
    border-radius: 4px;
    background: __CARD__;
}
QCheckBox::indicator:hover {
    border-color: __TURQUOISE_DK__;
}
QCheckBox::indicator:checked {
    background: __TURQUOISE__;
    border-color: __TURQUOISE__;
}
QRadioButton {
    color: __TEXT__;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid __BORDER_STRONG__;
    border-radius: 9px;
    background: __CARD__;
}
QRadioButton::indicator:hover {
    border-color: __TURQUOISE_DK__;
}
QRadioButton::indicator:checked {
    background: __TURQUOISE__;
    border-color: __TURQUOISE__;
}
QToolButton {
    background: __CARD__;
    color: __TEXT__;
    border: 1px solid __BORDER_STRONG__;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
    outline: none;
}
QToolButton:hover {
    background: __SURFACE_HI__;
}
QToolButton:checked {
    background: __TURQUOISE__;
    color: __SWAMP__;
}
QToolButton:focus {
    border: 2px solid __TURQUOISE__;
}
QToolTip {
    background: __SURFACE_HI__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    padding: 5px 7px;
}
QTableWidget, QTreeWidget {
    background: __CARD__;
    color: __TEXT__;
    alternate-background-color: __ALT_ROW__;
    border: 1px solid __BORDER__;
    border-radius: 10px;
    gridline-color: __GRID__;
    selection-background-color: __TURQUOISE__;
    selection-color: __SWAMP__;
    outline: none;
}
QTableWidget:focus, QTreeWidget:focus {
    border: 1px solid __TURQUOISE_DK__;
}
/* Sem "color" no item: assim o setForeground por linha (campos obrigatorios) vale. */
QTableWidget::item, QTreeWidget::item {
    padding: 5px;
}
QTableWidget::item:selected, QTreeWidget::item:selected {
    background: __TURQUOISE__;
    color: __SWAMP__;
}
QHeaderView::section {
    background: __SURFACE_HI__;
    border: none;
    border-bottom: 1px solid __BORDER__;
    padding: 7px;
    font-weight: 700;
    color: __TEXT__;
}
QTableCornerButton::section {
    background: __SURFACE_HI__;
    border: none;
    border-bottom: 1px solid __BORDER__;
    border-right: 1px solid __BORDER__;
}
QProgressBar {
    background: __DISABLED_BG__;
    border: none;
    border-radius: 7px;
    text-align: center;
    min-height: 20px;
    color: __TEXT__;
}
QProgressBar::chunk {
    background: __TURQUOISE__;
    border-radius: 7px;
}
QScrollArea {
    background: __SWAMP__;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: __SWAMP__;
}
QAbstractScrollArea::corner {
    background: __SURFACE_HI__;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: __BORDER_STRONG__;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: __TURQUOISE_DK__;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: __BORDER_STRONG__;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: __TURQUOISE_DK__;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0px;
    height: 0px;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QMenu {
    background: __CARD__;
    color: __TEXT__;
    border: 1px solid __BORDER_STRONG__;
}
QMenu::item {
    background: transparent;
    padding: 6px 22px 6px 12px;
}
QMenu::item:selected {
    background: __SURFACE_HI__;
}
QMenu::separator {
    height: 1px;
    background: __BORDER__;
    margin: 5px 8px;
}
QMessageBox {
    background: __CARD__;
}
QMessageBox QLabel {
    color: __TEXT__;
}
QMessageBox QPushButton {
    background: __CARD__;
    color: __TEXT__;
    border: 1px solid __BORDER_STRONG__;
    border-radius: 7px;
    padding: 6px 14px;
    font-weight: 600;
}
QMessageBox QPushButton:hover {
    background: __SURFACE_HI__;
}
QMessageBox QPushButton:disabled {
    background: __DISABLED_BG__;
    color: __DISABLED_TEXT__;
    border-color: __BORDER__;
}
"""


def style_sheet(font_family: str) -> str:
    """QSS com a fonte da UI e as cores da paleta aplicadas."""
    css = STYLE_TEMPLATE.replace("__UI_FONT__", font_family)
    for name, value in _TOKENS.items():
        css = css.replace(f"__{name}__", value)
    return css


def build_dark_palette() -> QPalette:
    """Paleta escura fixa do NetBox: nao depende do tema (claro/escuro) do Windows."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(SWAMP))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(ALT_ROW))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_FAINT))
    palette.setColor(QPalette.ColorRole.Button, QColor(CARD))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE_HI))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(TURQUOISE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(SWAMP))
    palette.setColor(QPalette.ColorRole.Link, QColor(TURQUOISE))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Mid, QColor(NAVY_800))
    palette.setColor(QPalette.ColorRole.Midlight, QColor(SURFACE_HI))
    palette.setColor(QPalette.ColorRole.Dark, QColor(SWAMP))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#000A10"))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(DISABLED_TEXT)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(DISABLED_TEXT)
    )
    return palette
