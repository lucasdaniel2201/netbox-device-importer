"""Conjunto de icones desenhados com QPainter.

Um unico estilo para o app inteiro: traco de 1,7 px, pontas arredondadas, grade de
24x24, sem preenchimento (exceto pontos). Nada de glifos de fonte nem de misturar
bibliotecas: o glifo fora da fonte empacotada ja renderizou deformado neste
projeto, e um icone desenhado e nitido em qualquer escala e em qualquer tema.

`icon()` devolve um QIcon com cores distintas para o estado normal e o selecionado
(usado pelos itens da barra lateral), e `pixmap()` entrega o desenho puro.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

STROKE = 1.7
GRID = 24.0


def _device_ratio() -> float:
    tela = QGuiApplication.primaryScreen()
    try:
        return max(1.0, float(tela.devicePixelRatio())) if tela else 1.0
    except (AttributeError, RuntimeError):
        return 1.0


def _rounded(p: QPainter, x: float, y: float, w: float, h: float, r: float = 2.0) -> None:
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def _chevron(p: QPainter, x: float, y: float, direction: str = "right") -> None:
    if direction == "right":
        p.drawPolyline([QPointF(x, y), QPointF(x + 6, y + 6), QPointF(x, y + 12)])
    elif direction == "down":
        p.drawPolyline([QPointF(x, y), QPointF(x + 6, y + 6), QPointF(x + 12, y)])


def _draw(name: str, p: QPainter) -> None:
    """Desenha um icone na grade 24x24 (o painter ja esta configurado)."""
    if name == "dashboard":
        for x, y in ((3.5, 3.5), (13.5, 3.5), (3.5, 13.5), (13.5, 13.5)):
            _rounded(p, x, y, 7, 7, 2)
    elif name == "import":
        p.drawLine(QPointF(12, 3.5), QPointF(12, 14))
        p.drawPolyline([QPointF(8, 10.5), QPointF(12, 14.5), QPointF(16, 10.5)])
        p.drawPolyline([QPointF(4, 16), QPointF(4, 20), QPointF(20, 20), QPointF(20, 16)])
    elif name == "link":
        # Dois elos entrelacados: a leitura de "vinculo" sem depender de detalhe fino.
        p.drawEllipse(QRectF(3.5, 7.5, 10.5, 10.5))
        p.drawEllipse(QRectF(10, 7.5, 10.5, 10.5))
    elif name == "history":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        p.drawPolyline([QPointF(12, 7.5), QPointF(12, 12), QPointF(15.5, 14)])
    elif name == "settings":
        for y, knob in ((6.5, 9.0), (12.0, 15.0), (17.5, 8.0)):
            p.drawLine(QPointF(4, y), QPointF(20, y))
            p.setBrush(QColor(p.pen().color()))
            p.drawEllipse(QRectF(knob - 2.2, y - 2.2, 4.4, 4.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "refresh":
        p.drawArc(QRectF(4, 4, 16, 16), 45 * 16, 285 * 16)
        p.drawPolyline([QPointF(17.5, 3.5), QPointF(18.2, 8.4), QPointF(13.4, 7.5)])
    elif name == "logout":
        p.drawPolyline([QPointF(10, 4), QPointF(5, 4), QPointF(5, 20), QPointF(10, 20)])
        p.drawLine(QPointF(9, 12), QPointF(20, 12))
        p.drawPolyline([QPointF(16, 8), QPointF(20, 12), QPointF(16, 16)])
    elif name == "download":
        p.drawLine(QPointF(12, 3.5), QPointF(12, 15))
        p.drawPolyline([QPointF(7.5, 10.5), QPointF(12, 15), QPointF(16.5, 10.5)])
        p.drawLine(QPointF(4.5, 20), QPointF(19.5, 20))
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 6.5)
        path.lineTo(9.5, 6.5)
        path.lineTo(11.5, 9)
        path.lineTo(21, 9)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "file":
        path = QPainterPath()
        path.moveTo(6, 3.5)
        path.lineTo(14, 3.5)
        path.lineTo(18.5, 8)
        path.lineTo(18.5, 20.5)
        path.lineTo(6, 20.5)
        path.closeSubpath()
        p.drawPath(path)
        p.drawPolyline([QPointF(14, 3.5), QPointF(14, 8), QPointF(18.5, 8)])
    elif name == "check":
        p.drawPolyline([QPointF(5, 12.5), QPointF(10, 17.5), QPointF(19, 7)])
    elif name == "alert":
        path = QPainterPath()
        path.moveTo(12, 3.5)
        path.lineTo(21.5, 20)
        path.lineTo(2.5, 20)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(12, 9), QPointF(12, 14))
        p.setBrush(QColor(p.pen().color()))
        p.drawEllipse(QRectF(11.1, 16.2, 1.8, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "x":
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "info":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        p.drawLine(QPointF(12, 11), QPointF(12, 17))
        p.setBrush(QColor(p.pen().color()))
        p.drawEllipse(QRectF(11.1, 7.2, 1.8, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "search":
        p.drawEllipse(QRectF(4, 4, 12, 12))
        p.drawLine(QPointF(15, 15), QPointF(20, 20))
    elif name == "eye":
        path = QPainterPath()
        path.moveTo(2.5, 12)
        path.cubicTo(6, 6.5, 18, 6.5, 21.5, 12)
        path.cubicTo(18, 17.5, 6, 17.5, 2.5, 12)
        p.drawPath(path)
        p.drawEllipse(QRectF(9, 9, 6, 6))
    elif name == "eye_off":
        path = QPainterPath()
        path.moveTo(2.5, 12)
        path.cubicTo(6, 6.5, 18, 6.5, 21.5, 12)
        path.cubicTo(18, 17.5, 6, 17.5, 2.5, 12)
        p.drawPath(path)
        p.drawEllipse(QRectF(9, 9, 6, 6))
        p.drawLine(QPointF(4, 20), QPointF(20, 4))
    elif name == "sun":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        for angulo in range(0, 360, 45):
            rad = math.radians(angulo)
            p.drawLine(
                QPointF(12 + 6.6 * math.cos(rad), 12 + 6.6 * math.sin(rad)),
                QPointF(12 + 9.2 * math.cos(rad), 12 + 9.2 * math.sin(rad)),
            )
    elif name == "moon":
        cheia = QPainterPath()
        cheia.addEllipse(QRectF(5, 2.5, 16, 16))
        recorte = QPainterPath()
        recorte.addEllipse(QRectF(10, 0.5, 16, 16))
        p.drawPath(cheia.subtracted(recorte))
    elif name == "server":
        _rounded(p, 3.5, 4.5, 17, 6.5, 2)
        _rounded(p, 3.5, 13, 17, 6.5, 2)
        p.setBrush(QColor(p.pen().color()))
        p.drawEllipse(QRectF(7, 7.1, 1.6, 1.6))
        p.drawEllipse(QRectF(7, 15.6, 1.6, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "shield":
        path = QPainterPath()
        path.moveTo(12, 3)
        path.lineTo(20, 6)
        path.lineTo(20, 12)
        path.cubicTo(20, 17, 16.5, 20, 12, 21.5)
        path.cubicTo(7.5, 20, 4, 17, 4, 12)
        path.lineTo(4, 6)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "external":
        p.drawPolyline([QPointF(13, 4), QPointF(20, 4), QPointF(20, 11)])
        p.drawLine(QPointF(20, 4), QPointF(11, 13))
        p.drawPolyline([QPointF(18, 14), QPointF(18, 20), QPointF(4, 20), QPointF(4, 6), QPointF(10, 6)])
    elif name == "chevron_right":
        _chevron(p, 9, 6)
    elif name == "chevron_down":
        _chevron(p, 6, 9, "down")
    elif name == "arrow_right":
        p.drawLine(QPointF(4, 12), QPointF(20, 12))
        p.drawPolyline([QPointF(15, 7), QPointF(20, 12), QPointF(15, 17)])
    elif name == "arrow_left":
        p.drawLine(QPointF(4, 12), QPointF(20, 12))
        p.drawPolyline([QPointF(9, 7), QPointF(4, 12), QPointF(9, 17)])
    elif name == "plus":
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == "trash":
        p.drawLine(QPointF(4, 7), QPointF(20, 7))
        p.drawPolyline([QPointF(9, 7), QPointF(9, 4), QPointF(15, 4), QPointF(15, 7)])
        p.drawPolyline(
            [QPointF(6, 7), QPointF(6.8, 20), QPointF(17.2, 20), QPointF(18, 7)]
        )
    elif name == "database":
        p.drawEllipse(QRectF(4, 3.5, 16, 5.5))
        p.drawLine(QPointF(4, 6.2), QPointF(4, 17.8))
        p.drawLine(QPointF(20, 6.2), QPointF(20, 17.8))
        p.drawArc(QRectF(4, 15, 16, 5.5), 180 * 16, 180 * 16)
        p.drawArc(QRectF(4, 9.5, 16, 5.5), 180 * 16, -180 * 16)
    else:
        # Icone desconhecido: um marcador discreto e previsivel.
        p.drawEllipse(QRectF(9, 9, 6, 6))


def pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    """QPixmap do icone na cor pedida, ja preparado para telas HiDPI."""
    ratio = _device_ratio()
    lado = max(1, int(round(size * ratio)))
    canvas = QPixmap(lado, lado)
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(lado / GRID, lado / GRID)

    # A escala do painter ja converte o traco: 1,7 e a espessura na grade 24x24.
    caneta = QPen(QColor(color), STROKE)
    caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
    caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(caneta)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _draw(name, painter)
    painter.end()
    return canvas


def icon(
    name: str,
    color: str,
    size: int = 20,
    checked_color: str | None = None,
    disabled_color: str | None = None,
) -> QIcon:
    """QIcon com estados normal/selecionado/desabilitado.

    O estado selecionado e o que faz o item ativo da barra lateral mudar de cor
    sem precisar de um widget desenhado a mao.
    """
    resultado = QIcon()
    resultado.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    if checked_color:
        resultado.addPixmap(pixmap(name, checked_color, size), QIcon.Mode.Normal, QIcon.State.On)
    if disabled_color:
        resultado.addPixmap(
            pixmap(name, disabled_color, size), QIcon.Mode.Disabled, QIcon.State.Off
        )
        resultado.addPixmap(
            pixmap(name, disabled_color, size), QIcon.Mode.Disabled, QIcon.State.On
        )
    return resultado
