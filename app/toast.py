"""Notificacoes (toasts) nao invasivas no canto superior direito.

Boas praticas aplicadas:
- posicionadas abaixo do cabecalho, sem cobri-lo (offset informado pela janela);
- sinalizam o tipo por icone E cor (nao dependem apenas de cor);
- empilham em vez de se sobrescreverem;
- auto-fechamento pausa quando o mouse esta sobre o aviso;
- sempre trazem botao de fechar;
- duracao proporcional a gravidade (erro fica mais tempo que informacao);
- animacao curta de entrada/saida, sem chamar atencao demais;
- acompanham o tema ativo (inclusive se ele mudar com o aviso aberto).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QLineF,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app import theme

KIND_STYLES = {
    # Icones escolhidos entre os glifos que EXISTEM na fonte Inter (empacotada):
    # check U+2713, multiplicacao U+00D7, exclamacao e "i". Evitar simbolos fora
    # da fonte (ex.: U+2715), que caem em fallback e renderizam deformados.
    "success": {"accent": "#3DD68C", "icon": "\u2713", "duration": 4000},
    "error": {"accent": "#F87171", "icon": "\u00d7", "duration": 9000},
    "warning": {"accent": "#F2B84B", "icon": "!", "duration": 6000},
    "info": {"accent": "#5B9DFF", "icon": "i", "duration": 4000},
}

TOAST_WIDTH = 380
TOAST_MIN_HEIGHT = 48
MARGIN = 16
SPACING = 8
MAX_VISIBLE = 4
SLIDE = 24


class CloseButton(QPushButton):
    """Botao de fechar com o "X" desenhado via QPainter.

    Desenhar evita depender de glifos da fonte: U+2715 nao existe na Inter e
    caia em fallback, renderizando deformado.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Fechar")
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        p = theme.palette()
        self._color = QColor(p.text_faint)
        self._hover = QColor(p.text)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._hover if self.underMouse() else self._color
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        margin = 6
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.drawLine(QLineF(rect.topLeft(), rect.bottomRight()))
        painter.drawLine(QLineF(rect.topRight(), rect.bottomLeft()))
        painter.end()

    def apply_theme(self, palette) -> None:
        self._color = QColor(palette.text_faint)
        self._hover = QColor(palette.text)
        self.update()


class ToastItem(QFrame):
    """Um aviso individual, com barra de destaque, icone, texto e fechar."""

    dismissed = Signal(object)

    def __init__(
        self,
        message: str,
        kind: str,
        duration_ms: int | None,
        parent=None,
        action_label: str | None = None,
        action_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        style = KIND_STYLES.get(kind, KIND_STYLES["info"])
        self._kind = kind if kind in KIND_STYLES else "info"
        self._duration = style["duration"] if duration_ms is None else duration_ms
        self._anim: QPropertyAnimation | None = None
        self._action_callback = action_callback
        self.action_button: QPushButton | None = None

        self.setObjectName("toastCard")
        self.setFixedWidth(TOAST_WIDTH)
        self.setMinimumHeight(TOAST_MIN_HEIGHT)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(24)
        self._shadow.setOffset(0, 6)
        self.setGraphicsEffect(self._shadow)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 11, 10, 11)
        row.setSpacing(10)

        self._accent = QFrame()
        self._accent.setObjectName("toastAccent")
        self._accent.setFixedWidth(4)
        row.addWidget(self._accent)

        self._icon = QLabel(style["icon"])
        self._icon.setFixedSize(22, 22)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._icon)

        self._text = QLabel(message)
        self._text.setObjectName("toastText")
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self._text, stretch=1)

        if action_label is not None:
            action = QPushButton(action_label)
            action.setObjectName("primaryButton")
            action.setCursor(Qt.CursorShape.PointingHandCursor)
            action.clicked.connect(self._on_action_clicked)
            self.action_button = action
            row.addWidget(action, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._close = CloseButton()
        self._close.clicked.connect(self.dismiss)
        row.addWidget(self._close, alignment=Qt.AlignmentFlag.AlignTop)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

        self.apply_theme(theme.palette())
        self._start_timer()

    # ------------------------------------------------------------------ tempo
    def _start_timer(self) -> None:
        if self._duration and self._duration > 0:
            self._timer.start(self._duration)

    def _on_action_clicked(self) -> None:
        if self._action_callback is not None:
            self._action_callback()

    def set_action_label(self, text: str) -> None:
        """Atualiza o rotulo do botao de acao (ex.: progresso do download)."""
        if self.action_button is not None:
            self.action_button.setText(text)

    def set_action_enabled(self, enabled: bool) -> None:
        """Habilita/desabilita o botao de acao sem tocar no botao de fechar."""
        if self.action_button is not None:
            self.action_button.setEnabled(enabled)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._start_timer()
        super().leaveEvent(event)

    # -------------------------------------------------------------- animacao
    def animate_to(self, target: QPoint, animate: bool = True) -> None:
        if self._anim is not None:
            self._anim.stop()
        if not animate or self.pos() == target:
            self.move(target)
            return
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(150)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(target)
        self._anim = anim
        anim.start()

    def slide_in_from_right(self) -> None:
        final = self.pos()
        self.move(final.x() + SLIDE, final.y())
        self.animate_to(final)

    def dismiss(self) -> None:
        self._timer.stop()
        if self._anim is not None:
            self._anim.stop()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(130)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(QPoint(self.x() + SLIDE, self.y()))
        self._anim = anim
        anim.finished.connect(lambda: self.dismissed.emit(self))
        anim.start()

    def close_now(self) -> None:
        self.dismissed.emit(self)

    # ------------------------------------------------------------------- tema
    def apply_theme(self, palette) -> None:
        p = palette
        accent = p.kind_color(self._kind)
        self._shadow.setColor(QColor(0, 0, 0, 110 if p.is_dark else 45))
        self.setStyleSheet(
            f"QFrame#toastCard {{ background: {p.surface};"
            f" border: 1px solid {p.border}; border-radius: 12px; }}"
            "QFrame#toastAccent { border-top-left-radius: 12px;"
            " border-bottom-left-radius: 12px; }"
            f"QLabel#toastText {{ color: {p.text}; font-size: 12px;"
            " background: transparent; }"
        )
        self._accent.setStyleSheet(
            f"background: {accent};"
            " border-top-left-radius: 12px; border-bottom-left-radius: 12px;"
        )
        self._icon.setStyleSheet(
            f"background: {accent}; color: {p.on_accent}; border-radius: 11px;"
            " font-size: 12px; font-weight: 700;"
        )
        self._close.apply_theme(p)
        self.update()


class ToastManager(QWidget):
    """Coluna de avisos no canto superior direito da janela."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedWidth(TOAST_WIDTH)
        self._items: list[ToastItem] = []
        self._top_offset = 96
        parent.installEventFilter(self)
        self.show()

    def set_top_offset(self, offset: int) -> None:
        """Desloca a coluna para nao cobrir o cabecalho da pagina atual."""
        self._top_offset = offset
        self._reposition()

    def notify(
        self,
        message: str,
        kind: str = "info",
        duration_ms: int | None = None,
        action_label: str | None = None,
        action_callback: Callable[[], None] | None = None,
    ) -> ToastItem:
        item = ToastItem(
            message,
            kind,
            duration_ms,
            self,
            action_label=action_label,
            action_callback=action_callback,
        )
        item.dismissed.connect(self._on_dismissed)
        self._items.append(item)

        while len(self._items) > MAX_VISIBLE:
            self._items.pop(0).close_now()

        item.adjustSize()
        item.show()
        self.raise_()
        self._relayout()
        item.slide_in_from_right()
        return item

    def apply_theme(self, palette) -> None:
        for item in self._items:
            item.apply_theme(palette)

    def _on_dismissed(self, item: ToastItem) -> None:
        if item in self._items:
            self._items.remove(item)
        item.hide()
        item.deleteLater()
        self._relayout()

    def _relayout(self) -> None:
        y = 0
        for item in self._items:
            item.adjustSize()
            item.move(0, y)
            y += item.height() + SPACING

        self.setFixedHeight(max(0, y - SPACING))
        self._reposition()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = max(MARGIN, parent.width() - TOAST_WIDTH - MARGIN)
        self.move(x, self._top_offset)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(watched, event)
