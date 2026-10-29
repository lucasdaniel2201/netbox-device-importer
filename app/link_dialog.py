"""Dialogo de importacao de links IP: planilha, plano e envio.

Mesmo desenho do dialogo de cameras, com uma diferenca de escopo: aqui **nao** se
cria device nem referencia. O link vai para um device que ja existe, entao o que a
planilha pode pedir e conferir sao os blocos, o IP e o site - e nao ha botao de
"criar o que esta faltando".

O plano e mostrado inteiro antes do envio: bloco público, LAN e IP com a indicacao
de "pronto" ou do erro linha a linha.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app import link_plan, link_sheet, provision, theme

SHEET_FILTER = "Planilhas (*.xlsx *.csv);;Excel (*.xlsx);;CSV (*.csv)"
PLAN_COLUMNS = ("Linha", "Site", "Device", "Bloco público", "IP do link", "Situação")


class LinkImportDialog(QDialog):
    def __init__(self, parent, snapshot: dict, session) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar links IP para o NetBox")
        self.setModal(True)
        self.resize(1120, 680)

        self._snapshot = snapshot
        self._session = session
        self._sheet = None
        self._plan = None
        self._busy = False

        self._build_ui()
        self._connect_session()
        self._refresh_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.sheet_button = QPushButton("Escolher planilha de links")
        self.sheet_button.clicked.connect(self._on_choose_sheet)
        top.addWidget(self.sheet_button)

        self.sheet_label = QLabel("Nenhuma planilha carregada.")
        self.sheet_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.sheet_label.setWordWrap(True)
        top.addWidget(self.sheet_label, stretch=1)
        layout.addLayout(top)

        self.plan_table = QTableWidget(0, len(PLAN_COLUMNS))
        self.plan_table.setHorizontalHeaderLabels(list(PLAN_COLUMNS))
        self.plan_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plan_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plan_table.setAlternatingRowColors(True)
        self.plan_table.verticalHeader().setVisible(False)
        header = self.plan_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for coluna in range(1, len(PLAN_COLUMNS)):
            header.setSectionResizeMode(coluna, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.plan_table, stretch=1)

        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        layout.addWidget(self.plan_label)

        bottom = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        bottom.addWidget(self.progress_bar, stretch=1)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._on_cancel)
        bottom.addWidget(self.cancel_button)

        self.import_button = QPushButton("Importar links")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setMinimumHeight(34)
        self.import_button.clicked.connect(self._on_import)
        bottom.addWidget(self.import_button)

        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.reject)
        bottom.addWidget(self.close_button)
        layout.addLayout(bottom)

    def _connect_session(self) -> None:
        self._session.links_progress.connect(self._on_progress)
        self._session.links_done.connect(self._on_import_done)
        self._session.links_failed.connect(self._on_import_failed)

    def _disconnect_session(self) -> None:
        for signal, slot in (
            (self._session.links_progress, self._on_progress),
            (self._session.links_done, self._on_import_done),
            (self._session.links_failed, self._on_import_failed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    # -------------------------------------------------------------- estado
    def _refresh_ui(self) -> None:
        plan = self._plan
        self.plan_table.clearContents()

        if plan is None:
            self.plan_table.setRowCount(0)
            self.plan_label.setText("Carregue uma planilha de links para ver o plano.")
            self.plan_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
            self.import_button.setEnabled(False)
            self.import_button.setText("Importar links")
            return

        self._fill_table(plan)

        prontos = len(plan.ready_rows)
        com_erro = len(plan.blocked_rows)
        deduzidos = sum(1 for row in plan.ready_rows if row.link_ip_deduced)
        partes = [f"{prontos} link(s) prontos", f"{plan.prefix_count} prefixo(s)"]
        if plan.devices_to_create:
            partes.append(f"{plan.devices_to_create} device(s) a criar")
        if com_erro:
            partes.append(f"{com_erro} com erro")
        if deduzidos:
            partes.append(f"{deduzidos} com IP deduzido")
        if plan.missing_required:
            partes.append("campo(s) do NetBox sem valor: " + ", ".join(plan.missing_required))
        self.plan_label.setText(" | ".join(partes))

        if com_erro or plan.missing_required:
            cor = theme.ERROR
        else:
            cor = theme.SUCCESS
        self.plan_label.setStyleSheet(f"color: {cor}; font-weight: 600;")

        if self._busy:
            rotulo, habilitado = "Importando...", False
        elif plan.missing_required:
            rotulo, habilitado = "Configure o campo no app (config.py)", False
        elif com_erro:
            rotulo, habilitado = "Corrija as pendencias na planilha", False
        elif prontos:
            rotulo, habilitado = f"Importar {prontos} link(s)", True
        else:
            rotulo, habilitado = "Importar links", False
        self.import_button.setText(rotulo)
        self.import_button.setEnabled(habilitado)

    def _fill_table(self, plan) -> None:
        self.plan_table.setRowCount(len(plan.rows))
        for index, row in enumerate(plan.rows):
            if row.issues:
                situacao, cor = "ERRO: " + " | ".join(row.issues), theme.ERROR
            elif row.pending:
                situacao, cor = "vai criar: " + ", ".join(row.pending), theme.WARNING
            elif row.warnings:
                situacao, cor = "aviso: " + " | ".join(row.warnings), theme.WARNING
            else:
                situacao, cor = "pronto", theme.SUCCESS
            valores = [
                str(row.row_number),
                row.site,
                row.device,
                row.public_block,
                row.link_ip,
                situacao,
            ]
            for column, text in enumerate(valores):
                item = QTableWidgetItem(text)
                if column == len(valores) - 1:
                    item.setForeground(QColor(cor))
                self.plan_table.setItem(index, column, item)

    def _rebuild_plan(self) -> None:
        if self._sheet is None:
            self._plan = None
            self._refresh_ui()
            return
        self._plan = link_plan.build_plan(self._sheet, self._snapshot)
        self._refresh_ui()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(busy)
        self.sheet_button.setEnabled(not busy)
        self.close_button.setEnabled(not busy)
        if not busy:
            self.progress_bar.setValue(0)
        self._refresh_ui()

    # ----------------------------------------------------- acoes do usuario
    def _on_choose_sheet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher planilha de links", str(Path.home()), SHEET_FILTER
        )
        if not path:
            return
        try:
            sheet = link_sheet.read_file(
                Path(path),
                sites=provision.site_names(self._snapshot),
                prefix_roles=provision.reference_labels(self._snapshot, "prefix_roles"),
            )
        except Exception as exc:
            self._sheet = None
            self._plan = None
            self.sheet_label.setText("Nenhuma planilha carregada.")
            self._refresh_ui()
            QMessageBox.warning(self, "Planilha de links invalida", str(exc))
            return

        self._sheet = sheet
        self.sheet_label.setText(
            f"{Path(path).name} - {len(sheet.valid_rows)} linhas validas "
            f"({len(sheet.rows_with_errors)} com erro)"
        )
        self._rebuild_plan()

    def _on_import(self) -> None:
        plan = self._plan
        if plan is None or not plan.can_import:
            return
        self._set_busy(True)
        self.progress_bar.setRange(0, len(plan.ready_rows))
        self.progress_bar.setValue(0)
        self._session.request_import_links.emit(plan)

    def _on_cancel(self) -> None:
        self._session.request_cancel.emit()
        self.cancel_button.setEnabled(False)

    # --------------------------------------------------- callbacks da sessao
    def _on_progress(self, index: int, total: int, name: str, status: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index)
        self.progress_bar.setFormat(f"{index}/{total} | {name} | {status}")

    def _on_import_done(self, summary: dict) -> None:
        self._set_busy(False)
        texto = (
            f"{summary['created']} criados, {summary['updated']} atualizados, "
            f"{summary['exists']} sem mudanca, {summary['errors']} erros"
        )
        if summary.get("prefixes"):
            texto += f". Prefixos envolvidos: {summary['prefixes']}"
        if summary.get("devices_created"):
            texto += f". Devices criados: {summary['devices_created']}"
        if summary.get("deduced_ips"):
            texto += f". IPs deduzidos: {summary['deduced_ips']}"
        if summary.get("warnings"):
            texto += f". {summary['warnings']} linha(s) com aviso"
        texto += "."

        amostras = summary.get("error_samples") or []
        if amostras:
            texto += "\n\nPrimeiros erros:"
            for item in amostras:
                texto += f"\n- {item['name']}: {item['message']}"
        for item in summary.get("warning_samples") or []:
            texto += f"\n\nAviso ({item['name']}): {item['message']}"

        caminhos = summary.get("report_paths", {})
        if caminhos:
            texto += f"\n\nRelatorio: {caminhos.get('json', '')}"
        QMessageBox.information(self, "Importacao de links concluida", texto)

    def _on_import_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Falha na importacao de links", message)

    # --------------------------------------------------------------- fechar
    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy:
            resposta = QMessageBox.question(
                self,
                "Importacao em andamento",
                "Ha uma importacao rodando. Cancelar e fechar?",
            )
            if resposta != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._session.request_cancel.emit()
        self._disconnect_session()
        super().closeEvent(event)

    def reject(self) -> None:
        if self._busy:
            return
        self._disconnect_session()
        super().reject()
