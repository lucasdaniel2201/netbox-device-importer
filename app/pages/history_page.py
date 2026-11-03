"""Historico de operacoes: o que ja foi importado, com prova em disco.

Le os relatorios JSON que o proprio app grava em `reports/`. Nada aqui e simulado:
se a pasta estiver vazia, isso e dito com clareza. Duplo clique abre o relatorio no
programa padrao do sistema.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QWidget

from app import reports
from app.history import Run, list_runs
from app.ui import icons
from app.ui.components import (
    Card,
    Divider,
    ScrollPage,
    SectionHeader,
    ghost_button,
    secondary_button,
)
from app.ui.table import Cell, DataTable, Row


class HistoryPage(ScrollPage):
    open_folder = Signal()
    open_report = Signal(str)
    refresh_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(max_width=1100, parent=parent)
        self._runs: list[Run] = []

        cartao = Card()
        cabecalho = SectionHeader(
            "Histórico de operações",
            "Cada importação grava log, JSON e CSV. O JSON guarda o X-Request-ID de cada escrita.",
        )
        self.folder_button = secondary_button("Abrir pasta", "folder")
        self.folder_button.clicked.connect(self.open_folder.emit)
        self.refresh_button = ghost_button("Atualizar lista")
        self.refresh_button.clicked.connect(self.refresh_clicked.emit)
        cabecalho.actions.addWidget(self.refresh_button)
        cabecalho.actions.addWidget(self.folder_button)
        cartao.body.addWidget(cabecalho)
        cartao.body.addWidget(Divider())

        self.table = DataTable(
            ["Quando", "Tipo", "Linhas", "Criados", "Atualizados", "Erros", "Situação"],
            status_column=6,
            search_placeholder="Buscar por tipo ou data",
            ascending=False,
            compact_columns=(2, 3, 4, 5, 6),
        )
        self.table.table.setMinimumHeight(220)
        self.table.set_empty_message(
            "Nenhuma importação registrada nesta máquina.", icon_name="history"
        )
        self.table.table.itemDoubleClicked.connect(self._on_double_click)
        self.table.table.itemSelectionChanged.connect(self._on_selection)
        cartao.body.addWidget(self.table)

        self.detail = QLabel("Selecione uma execução para ver o caminho do relatório.")
        self.detail.setProperty("faint", "true")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cartao.body.addWidget(self.detail)
        self.body.addWidget(cartao)

        self.body.addStretch(1)
        self.set_runs([])

    # ------------------------------------------------------------------ dados
    def load(self) -> None:
        self.set_runs(list_runs())

    def set_runs(self, runs: list[Run]) -> None:
        self._runs = list(runs)
        linhas = [
            Row.of(
                Cell(run.display_time, sort_key=run.timestamp),
                run.kind_label,
                Cell(str(run.total), sort_key=run.total, align="right"),
                Cell(str(run.created), sort_key=run.created, align="right"),
                Cell(str(run.updated), sort_key=run.updated, align="right"),
                Cell(str(run.errors), sort_key=run.errors, align="right"),
                Cell(run.status_label, kind=run.status_kind, tip=run.result_label),
                payload=run,
            )
            for run in runs
        ]
        self.table.set_rows(linhas)
        self.table.fit_height(max_rows=8)
        if runs:
            self.detail.setText(
                "Selecione uma execução para ver o caminho do relatório. "
                "Duplo clique abre o JSON."
            )
        else:
            self.detail.setText(
                f"Nenhum relatório em {reports.reports_dir()}. "
                "O primeiro aparece aqui ao terminar uma importação."
            )

    def _on_selection(self) -> None:
        run = self.table.selected_payload()
        if not isinstance(run, Run):
            return
        self.detail.setText(f"{run.path}   ·   duplo clique abre o relatório JSON")

    def _on_double_click(self, _item) -> None:
        run = self.table.selected_payload()
        if isinstance(run, Run):
            self.open_report.emit(str(run.path))

    # ------------------------------------------------------------------- tema
    def apply_theme(self, palette) -> None:
        self.table.apply_theme(palette)
        self.folder_button.setIcon(icons.icon("folder", palette.text_muted, 16))
