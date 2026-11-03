"""Tabela de dados do app: busca, ordenacao e etiquetas de estado.

Construida sobre `QTableWidget` de proposito: as telas atuais ja usam esse widget e
troca-lo por `QTableView` + modelo nao traria ganho para o volume real (dezenas a
poucos milhares de linhas). O que faltava era a camada de experiencia em volta:
busca, contagem, ordenacao previsivel e uma coluna de situacao legivel de longe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import theme as theme_mod
from app.ui import icons
from app.ui.components import SearchField
from app.ui.tokens import GAP_SM


@dataclass
class Cell:
    """Uma celula: texto, estado (vira pilula) e dica de contexto."""

    text: str = ""
    kind: str | None = None
    tip: str | None = None
    sort_key: object | None = None
    bold: bool = False
    align: str | None = None


@dataclass
class Row:
    cells: list[Cell] = field(default_factory=list)
    payload: object | None = None

    @classmethod
    def of(cls, *cells: Cell | str, payload: object | None = None) -> Row:
        return cls([c if isinstance(c, Cell) else Cell(str(c)) for c in cells], payload)


class PillDelegate(QStyledItemDelegate):
    """Desenha a situacao como etiqueta arredondada, com cor e texto.

    Cor sozinha nao comunica: a pilula tem o texto do estado dentro dela, entao
    continua legivel para quem nao distingue verde de vermelho.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        estilo = opt.widget.style() if opt.widget else QApplication.style()
        estilo.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        texto = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if not texto:
            return
        kind = index.data(Qt.ItemDataRole.UserRole) or "neutral"
        p = theme_mod.palette()
        cor = QColor(p.kind_color(kind))
        fundo = QColor(p.kind_soft(kind))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fonte = QFont(opt.font)
        fonte.setPointSizeF(max(8.0, opt.font.pointSizeF() - 1.0))
        fonte.setBold(True)
        painter.setFont(fonte)
        medidas = painter.fontMetrics()
        largura = min(medidas.horizontalAdvance(texto) + 20, option.rect.width() - 12)
        altura = 22
        caixa = QRectF(
            option.rect.left() + 6,
            option.rect.center().y() - altura / 2,
            max(28, largura),
            altura,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fundo)
        painter.drawRoundedRect(caixa, 11, 11)

        caneta = painter.pen()
        caneta.setColor(cor)
        caneta.setWidthF(1.0)
        painter.setPen(caneta)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(caixa.adjusted(0.5, 0.5, -0.5, -0.5), 10.5, 10.5)

        painter.setPen(cor)
        painter.drawText(
            caixa.adjusted(9, 0, -9, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            medidas.elidedText(texto, Qt.TextElideMode.ElideRight, int(caixa.width() - 18)),
        )
        painter.restore()


class DataTable(QWidget):
    """Tabela com barra de busca, contagem e ordenacao por coluna."""

    def __init__(
        self,
        columns: list[str],
        status_column: int | None = None,
        search_placeholder: str = "Buscar...",
        ascending: bool = True,
        compact_columns: tuple[int, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._status_column = status_column
        self._rows: list[Row] = []
        self._sort_column = 0
        self._sort_ascending = ascending

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP_SM)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.setSpacing(GAP_SM)
        self.search = SearchField(search_placeholder)
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._apply_filter)
        topo.addWidget(self.search)
        topo.addStretch(1)

        self.counter = QLabel("")
        self.counter.setProperty("faint", "true")
        topo.addWidget(self.counter)
        layout.addLayout(topo)

        self.table = QTableWidget(0, len(self._columns))
        self.table.setHorizontalHeaderLabels(self._columns)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        ordem_inicial = (
            Qt.SortOrder.AscendingOrder if ascending else Qt.SortOrder.DescendingOrder
        )
        header.setSortIndicator(0, ordem_inicial)
        for coluna in range(len(self._columns)):
            header.setSectionResizeMode(coluna, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for coluna_compacta in compact_columns:
            header.setSectionResizeMode(
                coluna_compacta, QHeaderView.ResizeMode.ResizeToContents
            )

        if status_column is not None:
            self.table.setItemDelegateForColumn(status_column, PillDelegate(self.table))

        layout.addWidget(self.table, stretch=1)

        self.empty = QWidget()
        vazio = QVBoxLayout(self.empty)
        vazio.setContentsMargins(0, 24, 0, 24)
        vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vazio.addWidget(self.empty_icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.empty_label = QLabel("Nada para mostrar.")
        self.empty_label.setObjectName("EmptyText")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vazio.addWidget(self.empty_label)
        self.empty.hide()
        layout.addWidget(self.empty)

        self._empty_icon = "file"
        self.apply_theme(theme_mod.palette())

    # ------------------------------------------------------------------ dados
    def set_rows(self, rows: list[Row]) -> None:
        self._rows = list(rows)
        self._render()

    def rows(self) -> list[Row]:
        return list(self._rows)

    def selected_payload(self):
        """Payload da linha selecionada (None sem selecao)."""
        linha = self.table.currentRow()
        if linha < 0:
            return None
        item = self.table.item(linha, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole + 1)

    def clear(self) -> None:
        self._rows = []
        self._render()

    def fit_height(
        self,
        max_rows: int = 8,
        row_height: int = 42,
        min_height: int = 190,
        max_height: int = 430,
    ) -> None:
        """Ajusta a altura ao numero de linhas: tabela de 3 linhas nao vira vazio."""
        linhas = max(1, min(self.table.rowCount(), max_rows))
        altura = 42 + row_height * linhas
        self.table.setFixedHeight(max(min_height, min(max_height, altura)))

    def set_empty_message(self, text: str, icon_name: str = "file") -> None:
        self.empty_label.setText(text)
        self._empty_icon = icon_name
        self.apply_theme(theme_mod.palette())

    def _render(self) -> None:
        ordenadas = sorted(
            self._rows,
            key=lambda row: self._sort_key(row, self._sort_column),
            reverse=not self._sort_ascending,
        )
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(ordenadas))
        for indice, row in enumerate(ordenadas):
            for coluna in range(min(len(row.cells), len(self._columns))):
                cell = row.cells[coluna]
                item = QTableWidgetItem(cell.text)
                if cell.tip:
                    item.setToolTip(cell.tip)
                if coluna == 0 and row.payload is not None:
                    item.setData(Qt.ItemDataRole.UserRole + 1, row.payload)
                if cell.kind and coluna == self._status_column:
                    item.setData(Qt.ItemDataRole.UserRole, cell.kind)
                    item.setToolTip(cell.tip or cell.text)
                if cell.bold:
                    fonte = item.font()
                    fonte.setBold(True)
                    item.setFont(fonte)
                if cell.align == "right":
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(indice, coluna, item)
        self.table.setUpdatesEnabled(True)
        self._apply_filter()

    @staticmethod
    def _sort_key(row: Row, column: int):
        if column >= len(row.cells):
            return ""
        cell = row.cells[column]
        if cell.sort_key is not None:
            return cell.sort_key
        return cell.text.casefold()

    def _on_header_clicked(self, column: int) -> None:
        if column == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        ordem = (
            Qt.SortOrder.AscendingOrder
            if self._sort_ascending
            else Qt.SortOrder.DescendingOrder
        )
        self.table.horizontalHeader().setSortIndicator(column, ordem)
        self._render()

    def _apply_filter(self) -> None:
        termo = self.search.text().strip().casefold()
        visiveis = 0
        for linha in range(self.table.rowCount()):
            combina = True
            if termo:
                textos = []
                for coluna in range(self.table.columnCount()):
                    item = self.table.item(linha, coluna)
                    if item is not None:
                        textos.append(item.text())
                combina = termo in " ".join(textos).casefold()
            self.table.setRowHidden(linha, not combina)
            visiveis += 1 if combina else 0

        total = self.table.rowCount()
        if not total:
            # O estado vazio ja diz que nao ha nada; "0 linhas" ao lado seria ruido.
            self.counter.setText("")
        elif termo:
            self.counter.setText(f"{visiveis} de {total} linhas")
        else:
            plural = "linha" if total == 1 else "linhas"
            self.counter.setText(f"{total} {plural}")

        tem_conteudo = total > 0
        self.table.setVisible(tem_conteudo)
        self.empty.setVisible(not tem_conteudo)

    # ------------------------------------------------------------------ tema
    def apply_theme(self, palette) -> None:
        self.empty_icon.setPixmap(icons.pixmap(self._empty_icon, palette.text_faint, 30))
        self.table.viewport().update()
