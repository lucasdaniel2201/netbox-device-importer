"""Transicoes sutis, sem chamar mais atencao que o conteudo."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


def fade_in(widget: QWidget, duration: int = 150) -> None:
    """Aparece suavemente. O efeito e removido ao fim para nao pesar no desenho."""
    if widget is None:
        return
    efeito = QGraphicsOpacityEffect(widget)
    efeito.setOpacity(0.0)
    widget.setGraphicsEffect(efeito)

    animacao = QPropertyAnimation(efeito, b"opacity", widget)
    animacao.setDuration(duration)
    animacao.setStartValue(0.0)
    animacao.setEndValue(1.0)
    animacao.setEasingCurve(QEasingCurve.Type.OutCubic)

    def limpar() -> None:
        widget.setGraphicsEffect(None)

    animacao.finished.connect(limpar)
    widget._fade_animation = animacao  # type: ignore[attr-defined]
    animacao.start()
