"""Componentes reutilizaveis do design system.

Todos falam a mesma lingua visual e leem as cores da paleta ativa: nenhum deles
escreve uma cor literal. Quando um componente desenha por conta propria (icones,
indicadores), ele implementa `apply_theme(palette)` para acompanhar a troca de
tema sem recriar a tela.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import theme as theme_mod
from app.ui import icons
from app.ui.tokens import (
    GAP_LG,
    GAP_MD,
    GAP_SM,
    SIDEBAR_WIDTH,
)


def repolish(widget: QWidget) -> None:
    """Reaplica o QSS depois de mudar uma propriedade dinamica (kind/state)."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class Card(QFrame):
    """Superficie com borda sutil. O conteudo vai em `body`."""

    def __init__(self, parent: QWidget | None = None, padding: int = GAP_LG) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(GAP_MD)


class SectionHeader(QWidget):
    """Titulo e subtitulo de uma secao, com espaco para acoes a direita."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP_MD)

        coluna = QVBoxLayout()
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        coluna.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("CardSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        coluna.addWidget(self.subtitle_label)
        row.addLayout(coluna, stretch=1)

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(GAP_SM)
        row.addLayout(self.actions)
        # As acoes ficam no topo: alinhadas ao centro, elas invadem o subtitulo
        # quando o texto quebra em duas linhas.
        row.setAlignment(self.actions, Qt.AlignmentFlag.AlignTop)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)


class Badge(QLabel):
    """Etiqueta curta de estado. A cor vem do significado, nao do gosto."""

    def __init__(self, text: str = "", kind: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.setProperty("kind", kind)
        repolish(self)

    def set_state(self, text: str, kind: str) -> None:
        self.setText(text)
        self.set_kind(kind)


class StatTile(QFrame):
    """Numero grande com rotulo. Usado no painel para leitura rapida."""

    def __init__(
        self,
        label: str,
        value: str = "—",
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StatTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GAP_LG, GAP_MD, GAP_LG, GAP_MD)
        layout.setSpacing(2)

        self.label = QLabel(label.upper())
        self.label.setObjectName("StatLabel")
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        self.hint = QLabel(hint)
        self.hint.setObjectName("StatHint")
        self.hint.setVisible(bool(hint))

        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def set_value(self, value) -> None:
        self.value.setText("—" if value is None else str(value))

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.setVisible(bool(text))


class IconButton(QToolButton):
    """Botao quadrado so com icone desenhado."""

    def __init__(
        self,
        name: str,
        tooltip: str = "",
        size: int = 18,
        box: int = 34,
        color_key: str = "text_muted",
        checked_color_key: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._size = size
        self._color_key = color_key
        self._checked_color_key = checked_color_key
        self.setObjectName("iconButton")
        self.setFixedSize(box, box)
        self.setIconSize(QSize(size, size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self.apply_theme(theme_mod.palette())

    def apply_theme(self, palette) -> None:
        normal = getattr(palette, self._color_key, palette.text_muted)
        checked = (
            getattr(palette, self._checked_color_key, palette.accent)
            if self._checked_color_key
            else None
        )
        self.setIcon(
            icons.icon(
                self._name,
                normal,
                self._size,
                checked_color=checked,
                disabled_color=palette.disabled_text,
            )
        )


class SearchField(QLineEdit):
    """Campo de busca com a lupa como acao interna."""

    def __init__(self, placeholder: str = "Buscar...", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SearchInput")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(260)
        self._action = self.addAction(
            icons.icon("search", "#8A9BB0", 15), QLineEdit.ActionPosition.LeadingPosition
        )

    def apply_theme(self, palette) -> None:
        self._action.setIcon(icons.icon("search", palette.text_faint, 15))


class ThinProgress(QProgressBar):
    """Barra fina sem texto: o rotulo fica ao lado, legivel em qualquer largura."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(8)
        self.setRange(0, 0)


class Banner(QFrame):
    """Faixa de contexto (aviso, erro, informacao) com titulo e texto."""

    def __init__(
        self,
        kind: str = "info",
        title: str = "",
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        self._icon_name = {"info": "info", "success": "check", "warning": "alert", "danger": "x"}
        row = QHBoxLayout(self)
        row.setContentsMargins(GAP_MD, GAP_MD, GAP_MD, GAP_MD)
        row.setSpacing(GAP_MD)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        row.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignTop)

        coluna = QVBoxLayout()
        coluna.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("BannerTitle")
        self.text_label = QLabel(text)
        self.text_label.setObjectName("BannerText")
        self.text_label.setWordWrap(True)
        coluna.addWidget(self.title_label)
        coluna.addWidget(self.text_label)
        row.addLayout(coluna, stretch=1)

        self.set_kind(kind)
        self.title_label.setVisible(bool(title))
        self.text_label.setVisible(bool(text))
        self.apply_theme(theme_mod.palette())

    def set_kind(self, kind: str) -> None:
        self.setProperty("kind", kind)
        self._kind = kind
        repolish(self)

    def set_content(self, title: str, text: str, kind: str | None = None) -> None:
        if kind:
            self.set_kind(kind)
        self.title_label.setText(title)
        self.title_label.setVisible(bool(title))
        self.text_label.setText(text)
        self.text_label.setVisible(bool(text))
        self.apply_theme(theme_mod.palette())

    def apply_theme(self, palette) -> None:
        cor = palette.kind_color(self._kind)
        nome = self._icon_name.get(self._kind, "info")
        self.icon_label.setPixmap(icons.pixmap(nome, cor, 18))


class EmptyState(QWidget):
    """Estado vazio explicito: o que falta e qual e o proximo passo."""

    def __init__(
        self,
        title: str,
        text: str,
        icon_name: str = "file",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GAP_LG, 32, GAP_LG, 32)
        layout.setSpacing(GAP_SM)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(34, 34)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.title = QLabel(title)
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.text = QLabel(text)
        self.text.setObjectName("EmptyText")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setWordWrap(True)
        layout.addWidget(self.text)

        self.actions = QHBoxLayout()
        self.actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.actions.setSpacing(GAP_SM)
        layout.addLayout(self.actions)

        self._icon_name = icon_name
        self.apply_theme(theme_mod.palette())

    def apply_theme(self, palette) -> None:
        self.icon_label.setPixmap(icons.pixmap(self._icon_name, palette.text_faint, 32))


class Stepper(QWidget):
    """Indicador de etapas: numero, rotulo e a linha que liga cada passo.

    Um estado ativo por vez, com o gatilho visivelmente marcado - o passo atual
    recebe a cor de acento e os concluidos ficam com o "check".
    """

    def __init__(self, steps: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dots: list[QLabel] = []
        self._labels: list[QLabel] = []
        self._lines: list[QFrame] = []

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP_SM)

        for index, texto in enumerate(steps):
            if index:
                linha = QFrame()
                linha.setObjectName("StepLine")
                linha.setFixedHeight(1)
                linha.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self._lines.append(linha)
                row.addWidget(linha, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)

            dot = QLabel(str(index + 1))
            dot.setObjectName("StepDot")
            dot.setFixedSize(26, 26)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dots.append(dot)
            row.addWidget(dot)

            label = QLabel(texto)
            label.setObjectName("StepLabel")
            self._labels.append(label)
            row.addWidget(label)

        self.set_step(0)

    def set_step(self, current: int) -> None:
        for index, (dot, label) in enumerate(zip(self._dots, self._labels, strict=True)):
            if index < current:
                estado, texto = "done", "✓"
            elif index == current:
                estado, texto = "current", str(index + 1)
            else:
                estado, texto = "upcoming", str(index + 1)
            dot.setText(texto)
            dot.setProperty("state", estado)
            label.setProperty("state", estado)
            repolish(dot)
            repolish(label)
        for index, linha in enumerate(self._lines):
            linha.setProperty("done", "true" if index < current else "false")
            repolish(linha)


class ScrollPage(QWidget):
    """Pagina rolavel com coluna central de largura maxima confortavel."""

    def __init__(self, parent: QWidget | None = None, max_width: int = 1180) -> None:
        super().__init__(parent)
        self.setObjectName("PageArea")

        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        externo.addWidget(self.scroll)

        conteudo = QWidget()
        conteudo.setObjectName("PageArea")
        self.centro = QHBoxLayout(conteudo)
        self.centro.setContentsMargins(GAP_LG, GAP_LG, GAP_LG, GAP_LG)
        self.centro.addStretch(1)

        self.column = QWidget()
        self.column.setMaximumWidth(max_width)
        self.column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.body = QVBoxLayout(self.column)
        self.body.setContentsMargins(GAP_LG, GAP_SM, GAP_LG, GAP_LG)
        self.body.setSpacing(GAP_LG)

        self.centro.addWidget(self.column, stretch=60)
        self.centro.addStretch(1)
        self.scroll.setWidget(conteudo)


class IconTextButton(QPushButton):
    """Botao com icone que acompanha o tema.

    O icone nao pode ser pintado uma vez com uma cor fixa: no tema escuro o texto
    sobre o acento e navy, no claro e branco. Aqui a cor e resolvida a cada troca.
    """

    _COLOR_KEYS = {
        "primary": "on_accent",
        "secondary": "text_muted",
        "ghost": "text_muted",
        "danger": "danger",
    }

    def __init__(
        self,
        text: str,
        icon_name: str | None = None,
        kind: str = "secondary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._icon_name = icon_name
        self._kind = kind
        self.icon_size = 16
        if icon_name:
            self.setIconSize(QSize(self.icon_size, self.icon_size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_theme(theme_mod.palette())

    def set_icon(self, name: str | None) -> None:
        self._icon_name = name
        self.apply_theme(theme_mod.palette())

    def apply_theme(self, palette) -> None:
        if not self._icon_name:
            return
        chave = self._COLOR_KEYS.get(self._kind, "text_muted")
        cor = getattr(palette, chave, palette.text_muted)
        self.setIcon(
            icons.icon(self._icon_name, cor, self.icon_size, disabled_color=palette.disabled_text)
        )


def primary_button(text: str, icon_name: str | None = None) -> IconTextButton:
    botao = IconTextButton(text, icon_name, "primary")
    botao.setObjectName("primaryButton")
    botao.setMinimumHeight(36)
    return botao


def secondary_button(text: str, icon_name: str | None = None) -> IconTextButton:
    botao = IconTextButton(text, icon_name, "secondary")
    botao.setMinimumHeight(36)
    return botao


def ghost_button(text: str, icon_name: str | None = None) -> IconTextButton:
    botao = IconTextButton(text, icon_name, "ghost")
    botao.setObjectName("ghostButton")
    return botao


def danger_button(text: str, icon_name: str | None = None) -> IconTextButton:
    botao = IconTextButton(text, icon_name, "danger")
    botao.setObjectName("dangerButton")
    return botao


def field_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("FieldLabel")
    return label


def muted(text: str, faint: bool = False) -> QLabel:
    """Texto secundario (a cor vem do QSS via propriedade, entao segue o tema)."""
    label = QLabel(text)
    label.setProperty("faint" if faint else "muted", "true")
    label.setWordWrap(True)
    return label


def spacer(width: int = 0, height: int = 0) -> QWidget:
    item = QWidget()
    item.setFixedSize(width, height)
    return item


def sidebar_width() -> int:
    return SIDEBAR_WIDTH
