"""Peças compartilhadas pelos dialogos de importação.

Os dois fluxos (câmeras e links) têm as mesmas etapas e a mesma linguagem: escolher
a origem, revisar o plano, acompanhar o envio e ler o resumo. O que muda é o
conteúdo de cada etapa. Manter o esqueleto aqui evita que as duas telas divirjam.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app import theme as theme_mod
from app.ui import icons
from app.ui.components import (
    Banner,
    Card,
    Divider,
    SectionHeader,
    StatTile,
    Stepper,
    ghost_button,
    muted,
    secondary_button,
)
from app.ui.table import DataTable, Row
from app.ui.tokens import GAP_LG, GAP_MD, GAP_SM

SHEET_SUFFIXES = (".xlsx", ".csv")


class DropArea(QFrame):
    """Área de origem: clique ou arraste o arquivo para cá."""

    file_dropped = Signal(str)
    clicked = Signal()

    def __init__(
        self,
        title: str,
        text: str,
        button_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(GAP_LG, GAP_LG, GAP_LG, GAP_LG)
        layout.setSpacing(GAP_SM)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(34, 34)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.title = QLabel(title)
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.title)

        self.text = QLabel(text)
        self.text.setObjectName("EmptyText")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setWordWrap(True)
        self.text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.text)

        self.button = secondary_button(button_text, "folder")
        self.button.clicked.connect(self.clicked.emit)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.apply_theme(theme_mod.palette())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith(SHEET_SUFFIXES):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            caminho = url.toLocalFile()
            if caminho.lower().endswith(SHEET_SUFFIXES):
                self.file_dropped.emit(caminho)
                event.acceptProposedAction()
                return

    def apply_theme(self, palette) -> None:
        self.icon_label.setPixmap(icons.pixmap("import", palette.accent, 32))
        self.button.setIcon(icons.icon("folder", palette.text_muted, 16))


class ChecklistCard(Card):
    """Requisitos do arquivo, em cartao: o que precisa ter antes de importar."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        items: list[tuple[str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items = items
        self._icon_labels: list[QLabel] = []

        self.body.addWidget(SectionHeader(title, subtitle))
        self.body.addWidget(Divider())
        for _tipo, texto in items:
            linha = QHBoxLayout()
            linha.setSpacing(GAP_SM)
            icone = QLabel()
            icone.setFixedSize(16, 16)
            self._icon_labels.append(icone)
            linha.addWidget(icone, alignment=Qt.AlignmentFlag.AlignTop)
            descricao = muted(texto)
            linha.addWidget(descricao, stretch=1)
            self.body.addLayout(linha)
        self.body.addStretch(1)
        self.apply_theme(theme_mod.palette())

    def apply_theme(self, palette) -> None:
        for icone, (tipo, _texto) in zip(self._icon_labels, self._items, strict=True):
            nome = "info" if tipo == "info" else "check"
            icone.setPixmap(icons.pixmap(nome, palette.kind_color(tipo), 16))


class DialogHeader(QWidget):
    """Título, explicação e etapas do diálogo."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        steps: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP_SM)

        titulo = QLabel(title)
        titulo.setObjectName("PageTitle")
        layout.addWidget(titulo)

        explicacao = muted(subtitle)
        layout.addWidget(explicacao)

        self.stepper = Stepper(steps)
        layout.addSpacing(GAP_SM)
        layout.addWidget(self.stepper)
        layout.addSpacing(GAP_SM)
        layout.addWidget(Divider())

    def set_step(self, index: int) -> None:
        self.stepper.set_step(index)


class SummaryPanel(QWidget):
    """Resumo de uma execução: números, avisos, erros e o relatório em disco."""

    open_folder = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP_MD)

        self.banner = Banner("success", "", "")
        layout.addWidget(self.banner)

        grid = QGridLayout()
        grid.setHorizontalSpacing(GAP_MD)
        grid.setVerticalSpacing(GAP_MD)
        self.tiles: dict[str, StatTile] = {}
        for indice, (chave, rotulo) in enumerate(
            (
                ("created", "Criados"),
                ("updated", "Atualizados"),
                ("exists", "Sem mudança"),
                ("errors", "Erros"),
            )
        ):
            tile = StatTile(rotulo, "0")
            self.tiles[chave] = tile
            grid.addWidget(tile, 0, indice)
            grid.setColumnStretch(indice, 1)
        layout.addLayout(grid)

        self.notes = QLabel("")
        self.notes.setProperty("muted", "true")
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)

        self.samples = QLabel("")
        self.samples.setProperty("faint", "true")
        self.samples.setWordWrap(True)
        self.samples.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.samples)

        self.details = DataTable(
            ["Linha", "Item", "Resultado"],
            status_column=2,
            search_placeholder="Filtrar linhas...",
            compact_columns=(2,),
        )
        self.details.search.hide()
        self.details.set_empty_message("Nenhuma linha processada.", icon_name="file")
        self.details.hide()
        layout.addWidget(self.details, stretch=1)

        rodape = QHBoxLayout()
        rodape.setSpacing(GAP_SM)
        self.report_label = QLabel("")
        self.report_label.setProperty("faint", "true")
        self.report_label.setWordWrap(True)
        self.report_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rodape.addWidget(self.report_label, stretch=1)

        self.folder_button = ghost_button("Abrir pasta dos relatórios")
        self.folder_button.setIconSize(QSize(16, 16))
        self.folder_button.clicked.connect(self.open_folder.emit)
        rodape.addWidget(self.folder_button)
        layout.addLayout(rodape)

    def set_summary(self, summary: dict, extra: list[str] | None = None) -> None:
        for chave, tile in self.tiles.items():
            tile.set_value(summary.get(chave, 0))

        erros = int(summary.get("errors") or 0)
        avisos = int(summary.get("warnings") or 0)
        cancelado = bool(summary.get("canceled"))
        processados = int(summary.get("processed") or 0)
        total = int(summary.get("total") or 0)

        if cancelado:
            self.banner.set_content(
                "Execução cancelada",
                f"{processados} de {total} linhas processadas antes do cancelamento.",
                "warning",
            )
        elif erros:
            self.banner.set_content(
                "Concluída com erros",
                f"{erros} linha(s) não foram gravadas. O motivo está nos primeiros erros "
                "abaixo e no relatório.",
                "danger",
            )
        elif avisos:
            self.banner.set_content(
                "Concluída com avisos",
                f"{avisos} linha(s) foram gravadas com alguma etapa pendente. Nada foi "
                "desfeito — veja os avisos abaixo.",
                "warning",
            )
        else:
            self.banner.set_content(
                "Importação concluída",
                f"{processados} linha(s) processadas sem erro.",
                "success",
            )

        notas = [f"{processados} de {total} linhas processadas."]
        if avisos:
            notas.append(f"{avisos} linha(s) com aviso.")
        for nota in extra or []:
            notas.append(nota)
        self.notes.setText("  ·  ".join(notas))

        linhas = []
        for item in (summary.get("error_samples") or [])[:3]:
            linhas.append(f"Erro — {item.get('name')}: {item.get('message')}")
        for item in (summary.get("warning_samples") or [])[:2]:
            linhas.append(f"Aviso — {item.get('name')}: {item.get('message')}")
        self.samples.setText("\n".join(linhas))
        self.samples.setVisible(bool(linhas))
        self.details.hide()

        caminhos = summary.get("report_paths") or {}
        json_path = caminhos.get("json") or ""
        if json_path:
            self.report_label.setText(f"Relatório JSON: {json_path}")
        else:
            self.report_label.setText("")
        self.folder_button.setVisible(bool(json_path))

    def set_details(self, rows: list[Row]) -> None:
        """Tabela por linha do resumo. Substitui as amostras de erro quando ha dados."""
        self.details.set_rows(rows)
        self.details.fit_height(max_rows=8, max_height=430, min_height=190)
        visivel = bool(rows)
        self.details.setVisible(visivel)
        if visivel:
            self.samples.hide()

    def report_dir(self) -> str:
        """Pasta do relatório atual (vazia quando não há caminho)."""
        texto = self.report_label.text()
        if ": " not in texto:
            return ""
        return str(Path(texto.split(": ", 1)[1]).parent)

    def apply_theme(self, palette) -> None:
        self.banner.apply_theme(palette)
        self.folder_button.setIcon(icons.icon("folder", palette.text_muted, 16))
