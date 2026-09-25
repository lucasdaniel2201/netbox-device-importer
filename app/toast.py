"""Notificacoes (toasts) nao invasivas no canto superior direito.

Boas praticas aplicadas:
- posicionadas abaixo do cabecalho, sem cobri-lo (offset informado pela janela);
- sinalizam o tipo por icone E cor (nao dependem apenas de cor);
- empilham em vez de se sobrescreverem (varias acoes seguidas nao se perdem);
- auto-fechamento pausa quando o mouse esta sobre o aviso (tempo para ler);
- sempre trazem botao de fechar;
- duracao proporcional a gravidade (erro fica mais tempo que informacao);
- animacao curta de entrada/saida, sem chamar atencao demais.
"""

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
    # check U+2713, multiplicacao U+00D7, exclamação e "i". Evitar simbolos fora
    # da fonte (ex.: U+2715), que caem em fallback e renderizam deformados.
    "success": {"accent": theme.SUCCESS, "icon": "\u2713", "duration": 4000},
    "error": {"accent": theme.ERROR, "icon": "\u00d7", "duration": 9000},
    "warning": {"accent": theme.WARNING, "icon": "!", "duration": 6000},
    "info": {"accent": theme.INFO, "icon": "i", "duration": 4000},
}

TOAST_WIDTH = 360
TOAST_MIN_HEIGHT = 46
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
        self._color = QColor(theme.TEXT_FAINT)
        self._hover = QColor(theme.TEXT)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

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
        # Desenha as duas diagonais do "X".
        painter.drawLine(QLineF(rect.topLeft(), rect.bottomRight()))
        painter.drawLine(QLineF(rect.topRight(), rect.bottomLeft()))
        painter.end()


class ToastItem(QFrame):
    """Um aviso individual, com barra de destaque, icone, texto e fechar."""

    dismissed = Signal(object)

    def __init__(self, message: str, kind: str, duration_ms: int | None, parent=None) -> None:
        super().__init__(parent)
        style = KIND_STYLES.get(kind, KIND_STYLES["info"])
        self._duration = style["duration"] if duration_ms is None else duration_ms
        self._anim: QPropertyAnimation | None = None

        self.setObjectName("toastCard")
        self.setFixedWidth(TOAST_WIDTH)
        self.setMinimumHeight(TOAST_MIN_HEIGHT)
        self.setStyleSheet(
            f"QFrame#toastCard {{ background: {theme.CARD}; border: 1px solid {theme.BORDER};"
            " border-radius: 10px; }"
            "QFrame#toastAccent { border-top-left-radius: 10px;"
            " border-bottom-left-radius: 10px; }"
            f"QLabel#toastText {{ color: {theme.TEXT}; font-size: 12px;"
            " background: transparent; }"
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(shadow)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 10, 8, 10)
        row.setSpacing(10)

        accent = QFrame()
        accent.setObjectName("toastAccent")
        accent.setFixedWidth(5)
        accent.setStyleSheet(
            f"background: {style['accent']};"
            " border-top-left-radius: 10px; border-bottom-left-radius: 10px;"
        )
        row.addWidget(accent)

        icon = QLabel(style["icon"])
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {style['accent']}; color: #ffffff; border-radius: 11px;"
            " font-size: 12px; font-weight: 700;"
        )
        row.addWidget(icon)

        text = QLabel(message)
        text.setObjectName("toastText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(text, stretch=1)

        close = CloseButton()
        close.clicked.connect(self.dismiss)
        row.addWidget(close, alignment=Qt.AlignmentFlag.AlignTop)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._start_timer()

    # ------------------------------------------------------------------ tempo
    def _start_timer(self) -> None:
        if self._duration and self._duration > 0:
            self._timer.start(self._duration)

    def enterEvent(self, event) -> None:  # noqa: N802
        # Pausa o auto-fechamento enquanto o mouse estiver sobre o aviso.
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
        """Coloca o aviso deslocado e anima ate a posicao final."""
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


class ToastManager(QWidget):
    """Coluna de avisos no canto superior direito da janela."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedWidth(TOAST_WIDTH)
        self._items: list[ToastItem] = []
        self._top_offset = 96
        parent.installEventFilter(self)
        # Mostra a si mesmo: garante funcionamento mesmo se for criado depois que
        # o widget pai ja foi exibido.
        self.show()

    def set_top_offset(self, offset: int) -> None:
        """Desloca a coluna para nao cobrir o cabecalho da pagina atual."""
        self._top_offset = offset
        self._reposition()

    def notify(self, message: str, kind: str = "info", duration_ms: int | None = None) -> None:
        item = ToastItem(message, kind, duration_ms, self)
        item.dismissed.connect(self._on_dismissed)
        self._items.append(item)

        while len(self._items) > MAX_VISIBLE:
            self._items.pop(0).close_now()

        item.adjustSize()
        item.show()
        self.raise_()
        # Posicoes definidas na hora (empilhamento previsivel); so a entrada anima.
        self._relayout()
        item.slide_in_from_right()

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
