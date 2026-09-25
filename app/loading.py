"""Spinner da tela de carregamento, desenhado com QPainter.

Sem asset externo (nada de GIF/SVG empacotado) e sem glifo de fonte: e a licao que
ja pagamos no projeto antigo - simbolo fora da fonte empacotada renderiza deformado.
Desenhar tambem deixa a animacao nitida em qualquer escala.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app import theme

TICK_MS = 16  # ~60 quadros por segundo
GRAUS_POR_TICK = 4.2  # uma volta a cada ~1,4 s


class Spinner(QWidget):
    """Anel girando: trilha clara + arco solido com pontas arredondadas."""

    def __init__(self, parent=None, diameter: int = 68, stroke: int = 5) -> None:
        super().__init__(parent)
        self._stroke = stroke
        self.setFixedSize(diameter, diameter)
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.advance)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self.update()

    def stop(self) -> None:
        self._timer.stop()

    def is_running(self) -> bool:
        return self._timer.isActive()

    @property
    def angle(self) -> float:
        return self._angle

    def advance(self) -> None:
        """Um passo da animacao (o timer chama; o teste chama direto)."""
        self._angle = (self._angle + GRAUS_POR_TICK) % 360.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margem = self._stroke / 2 + 1
        caixa = QRectF(margem, margem, self.width() - 2 * margem, self.height() - 2 * margem)

        trilha = QPen(QColor(255, 255, 255, 46), self._stroke)
        trilha.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(trilha)
        painter.drawEllipse(caixa)

        # O arco abre e fecha de leve: parece "respirar" em vez de um pedaco rigido.
        abertura = 220 + 60 * math.sin(math.radians(self._angle * 2))
        arco = QPen(QColor(theme.TURQUOISE), self._stroke)
        arco.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arco)
        painter.drawArc(caixa, int(-self._angle * 16), int(-abertura * 16))
        painter.end()
