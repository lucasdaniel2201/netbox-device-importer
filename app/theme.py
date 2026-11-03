"""Tema do aplicativo: paleta ativa, QSS e troca de tema em tempo de execucao.

Este modulo e a porta de entrada da camada visual. Os tokens vivem em
`app/ui/tokens.py` e a folha de estilos em `app/ui/styles.py`; aqui ficam o estado
global (qual tema esta ativo) e as funcoes que aplicam o tema ao `QApplication`.

Compatibilidade: `TEXT`, `TEXT_MUTED`, `CARD`, `ERROR` e companhia continuam
existindo como as cores do tema escuro. Codigo antigo que importa `theme.TEXT` nao
quebra, mas codigo novo deve usar `theme.palette()` - e o que respeita o tema claro.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

from app.ui.styles import build_qss
from app.ui.tokens import DARK, DEFAULT_MODE, PALETTES, Palette

_current: Palette = PALETTES[DEFAULT_MODE]


def palette() -> Palette:
    """Paleta ativa (a que a interface esta usando agora)."""
    return _current


def current_mode() -> str:
    return _current.mode


def set_mode(mode: str) -> Palette:
    """Troca o tema ativo. Retorna a paleta resultante."""
    global _current
    _current = PALETTES.get(mode, PALETTES[DEFAULT_MODE])
    return _current


def toggle_mode() -> Palette:
    return set_mode("light" if _current.is_dark else "dark")


def style_sheet(font_family: str, mode: str | None = None) -> str:
    """QSS completo para a fonte e o tema pedidos (padrao: o ativo)."""
    p = PALETTES[mode] if mode in PALETTES else _current
    return build_qss(p, font_family)


def build_palette(mode: str | None = None) -> QPalette:
    """QPalette do Qt para o tema (usada por widgets que nao leem QSS, como tooltips)."""
    p = PALETTES[mode] if mode in PALETTES else _current
    q = QPalette()
    q.setColor(QPalette.ColorRole.Window, QColor(p.bg))
    q.setColor(QPalette.ColorRole.WindowText, QColor(p.text))
    q.setColor(QPalette.ColorRole.Base, QColor(p.surface))
    q.setColor(QPalette.ColorRole.AlternateBase, QColor(p.surface_alt))
    q.setColor(QPalette.ColorRole.Text, QColor(p.text))
    q.setColor(QPalette.ColorRole.PlaceholderText, QColor(p.text_faint))
    q.setColor(QPalette.ColorRole.Button, QColor(p.surface))
    q.setColor(QPalette.ColorRole.ButtonText, QColor(p.text))
    q.setColor(QPalette.ColorRole.ToolTipBase, QColor(p.surface_hi))
    q.setColor(QPalette.ColorRole.ToolTipText, QColor(p.text))
    q.setColor(QPalette.ColorRole.Highlight, QColor(p.accent))
    q.setColor(QPalette.ColorRole.HighlightedText, QColor(p.on_accent))
    q.setColor(QPalette.ColorRole.Link, QColor(p.accent))
    q.setColor(QPalette.ColorRole.BrightText, QColor(p.text))
    q.setColor(QPalette.ColorRole.Mid, QColor(p.border))
    q.setColor(QPalette.ColorRole.Midlight, QColor(p.surface_hi))
    q.setColor(QPalette.ColorRole.Dark, QColor(p.bg))
    q.setColor(QPalette.ColorRole.Shadow, QColor(p.shadow))
    q.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(p.disabled_text))
    q.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(p.disabled_text)
    )
    return q


def build_dark_palette() -> QPalette:
    """Nome historico de `build_palette('dark')` (usado por app/main.py e tools)."""
    return build_palette("dark")


def apply_to(root) -> Palette:
    """Avisa `apply_theme` em `root` e nos filhos.

    Necessario para widgets criados DEPOIS de `apply(app, ...)`: sem isso, um
    icone desenhado dentro de uma pagina nova ficaria sem pixmap (aconteceu com
    os icones das regras na pagina de importacao).
    """
    p = _current
    widgets = [root]
    if isinstance(root, QWidget):
        widgets.extend(root.findChildren(QWidget))
    for widget in widgets:
        hook = getattr(widget, "apply_theme", None)
        if callable(hook):
            try:
                hook(p)
            except RuntimeError:
                continue
    return p


def apply(app, font_family: str, mode: str | None = None) -> Palette:
    """Aplica paleta, QSS e avisa os widgets que pintam por conta propria.

    Widgets com `apply_theme(palette)` (botoes com icone desenhado, spinner,
    delegados) sao atualizados aqui - sem isso, trocar de tema deixaria icones com
    a cor do tema anterior.
    """
    if mode is not None:
        set_mode(mode)
    p = _current
    app.setPalette(build_palette(p.mode))
    app.setStyleSheet(style_sheet(font_family, p.mode))

    for widget in app.allWidgets():
        hook = getattr(widget, "apply_theme", None)
        if callable(hook):
            try:
                hook(p)
            except RuntimeError:
                # Widget C++ ja destruido: nada a repintar.
                continue
    return p


# ------------------------------------------------------------------ aliases
# Cores do tema escuro para o codigo legado. Prefira `theme.palette()`.
SWAMP = DARK.bg
PAGE_BG = DARK.bg
CARD = DARK.surface
SURFACE_HI = DARK.surface_hi
ALT_ROW = DARK.surface_alt
DISABLED_BG = DARK.surface_alt
BORDER = DARK.border
BORDER_STRONG = DARK.border_strong
GRID = DARK.grid
TEXT = DARK.text
TEXT_MUTED = DARK.text_muted
TEXT_FAINT = DARK.text_faint
DISABLED_TEXT = DARK.disabled_text
TURQUOISE = DARK.accent
TURQUOISE_HI = DARK.accent_hover
TURQUOISE_DK = DARK.accent_pressed
NAVY_800 = DARK.bg_elevated
SUCCESS = DARK.success
ERROR = DARK.danger
WARNING = DARK.warning
INFO = DARK.info
BUTTON_DISABLED_BG = DARK.surface_hi
