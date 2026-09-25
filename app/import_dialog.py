"""Dialogo de importacao: escolher a planilha, conferir o plano e enviar.

Fica separado da janela principal porque o fluxo tem regras proprias:

- o plano e mostrado ANTES de qualquer envio (a API nao tem "criar ou atualizar");
- referencias que faltam sao criadas so com confirmacao explicita;
- enquanto houver pendencia, o botao de importar fica bloqueado.

O snapshot e o mesmo dicionario da janela principal (e da thread da sessao), entao
quando o worker cria uma referencia e rele os objetos, o plano ja resolve sem
precisar recarregar nada.
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

from app import import_plan, provision, theme
from app.spreadsheet import read_file

SHEET_FILTER = "Planilhas (*.xlsx *.csv);;Excel (*.xlsx);;CSV (*.csv)"
PLAN_COLUMNS = ("Linha", "Nome", "Site", "Tipo", "Situacao")


def describe_custom_fields(usados: dict) -> str:
    """Texto curto do que sera enviado em custom_fields (nao deixar isso invisivel)."""
    partes = []
    for object_type, campos in usados.items():
        if not campos:
            continue
        itens = ", ".join(f"{nome}={valor}" for nome, valor in sorted(campos.items()))
        partes.append(f"{object_type}: {itens}")
    return " | ".join(partes)


class ImportDialog(QDialog):
    def __init__(self, parent, snapshot: dict, session) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar câmeras para o NetBox")
        self.setModal(True)
        self.resize(1020, 660)

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
        self.sheet_button = QPushButton("Escolher planilha preenchida")
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
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

        self.provision_button = QPushButton("Criar o que está faltando")
        self.provision_button.clicked.connect(self._on_provision)
        bottom.addWidget(self.provision_button)

        self.import_button = QPushButton("Importar câmeras")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setMinimumHeight(34)
        self.import_button.clicked.connect(self._on_import)
        bottom.addWidget(self.import_button)

        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.reject)
        bottom.addWidget(self.close_button)
        layout.addLayout(bottom)

    def _connect_session(self) -> None:
        self._session.progress.connect(self._on_progress)
        self._session.import_done.connect(self._on_import_done)
        self._session.import_failed.connect(self._on_import_failed)
        self._session.provision_done.connect(self._on_provision_done)
        self._session.provision_failed.connect(self._on_provision_failed)

    def _disconnect_session(self) -> None:
        for signal, slot in (
            (self._session.progress, self._on_progress),
            (self._session.import_done, self._on_import_done),
            (self._session.import_failed, self._on_import_failed),
            (self._session.provision_done, self._on_provision_done),
            (self._session.provision_failed, self._on_provision_failed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    # -------------------------------------------------------------- estado
    def _all_sites(self) -> list[str]:
        """Todos os sites do NetBox: a planilha traz o site por linha."""
        return provision.site_names(self._snapshot)

    def _refresh_ui(self) -> None:
        plan = self._plan
        self.plan_table.clearContents()

        if plan is None:
            self.plan_table.setRowCount(0)
            self.plan_label.setText("Carregue uma planilha para ver o plano.")
            self.plan_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
            self.provision_button.setEnabled(False)
            self.provision_button.setText("Criar o que está faltando")
            self.import_button.setEnabled(False)
            self.import_button.setText("Importar câmeras")
            return

        self._fill_table(plan)

        prontos = len(plan.ready_devices)
        bloqueados = len(plan.blocked_devices)
        faltando = len(plan.references)
        com_erro = sum(1 for device in plan.devices if device.issues)
        aguardando = bloqueados - com_erro
        sem_campo = plan.missing_required

        partes = [f"{prontos} prontos para importar"]
        if com_erro:
            partes.append(f"{com_erro} com erro")
        if aguardando:
            partes.append(f"{aguardando} aguardando referencia")
        if faltando:
            partes.append(f"{faltando} referencia(s) a criar")
        if sem_campo:
            partes.append("campo(s) do NetBox sem valor: " + ", ".join(sem_campo))
        texto = " | ".join(partes)
        if plan.deferred:
            texto += f"\n{plan.deferred[0]}"
        # Os valores fixos de custom field aparecem aqui: nao podem ser invisiveis.
        campos = describe_custom_fields(plan.custom_fields_used)
        if campos:
            texto += f"\nCampos personalizados enviados -> {campos}"
        self.plan_label.setText(texto)

        if com_erro or sem_campo:
            cor = theme.ERROR
        elif bloqueados or faltando:
            cor = theme.WARNING
        else:
            cor = theme.SUCCESS
        self.plan_label.setStyleSheet(f"color: {cor}; font-weight: 600;")

        self.provision_button.setText(f"Criar o que está faltando ({faltando})")
        self.provision_button.setEnabled(bool(faltando) and not self._busy)

        if self._busy:
            rotulo, habilitado = "Importando...", False
        elif faltando:
            rotulo, habilitado = "Provisione as referencias primeiro", False
        elif sem_campo:
            rotulo, habilitado = "Configure o campo no app (config.py)", False
        elif bloqueados:
            rotulo, habilitado = "Corrija as pendencias na planilha", False
        elif prontos:
            rotulo, habilitado = f"Importar {prontos} câmeras", True
        else:
            rotulo, habilitado = "Importar câmeras", False
        self.import_button.setText(rotulo)
        self.import_button.setEnabled(habilitado)

    def _fill_table(self, plan) -> None:
        self.plan_table.setRowCount(len(plan.devices))
        for index, device in enumerate(plan.devices):
            if device.issues:
                situacao, cor = "ERRO: " + " | ".join(device.issues), theme.ERROR
            elif device.pending:
                situacao, cor = "pendente: criar " + ", ".join(device.pending), theme.WARNING
            else:
                situacao, cor = "pronto", theme.SUCCESS
            valores = [
                str(device.row_number),
                device.name,
                device.site,
                device.device_type_label,
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
        # Sem a tela de campos personalizados: os valores vem de app/config.py.
        self._plan = import_plan.build_plan(self._sheet, self._snapshot)
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
            self, "Escolher planilha", str(Path.home()), SHEET_FILTER
        )
        if not path:
            return
        try:
            sheet = read_file(
                Path(path),
                sites=self._all_sites(),
                roles=provision.reference_labels(self._snapshot, "device_roles"),
            )
        except Exception as exc:
            self._sheet = None
            self._plan = None
            self.sheet_label.setText("Nenhuma planilha carregada.")
            self._refresh_ui()
            QMessageBox.warning(self, "Planilha invalida", str(exc))
            return

        self._sheet = sheet
        self.sheet_label.setText(
            f"{Path(path).name} - {len(sheet.valid_rows)} linhas validas "
            f"({len(sheet.rows_with_errors)} com erro)"
        )
        self._rebuild_plan()

    def _on_provision(self) -> None:
        plan = self._plan
        if plan is None or not plan.references:
            return
        lista = "\n".join(f"  - {ref.kind}: {ref.label}" for ref in plan.references)
        resposta = QMessageBox.question(
            self,
            "Criar referencias no NetBox",
            "Vou criar estes objetos antes de importar:\n\n"
            f"{lista}\n\nConfirma?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        self._session.request_provision.emit(plan.references)

    def _on_import(self) -> None:
        plan = self._plan
        if plan is None or not plan.can_import:
            return
        self._set_busy(True)
        self.progress_bar.setRange(0, len(plan.ready_devices))
        self.progress_bar.setValue(0)
        self._session.request_import.emit(plan)

    def _on_cancel(self) -> None:
        self._session.request_cancel.emit()
        self.cancel_button.setEnabled(False)

    # --------------------------------------------------- callbacks da sessao
    def _on_progress(self, index: int, total: int, name: str, status: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index)
        self.progress_bar.setFormat(f"{index}/{total} | {name} | {status}")

    def _on_provision_done(self, payload: dict) -> None:
        self._set_busy(False)
        criados = payload.get("created", [])
        self._rebuild_plan()
        if criados:
            nomes = ", ".join(item["label"] for item in criados)
            QMessageBox.information(
                self, "Referencias criadas", f"Criado no NetBox: {nomes}"
            )

    def _on_provision_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Falha ao criar referencia", message)

    def _on_import_done(self, summary: dict) -> None:
        self._set_busy(False)
        paths = summary.get("report_paths", {})
        texto = (
            f"{summary['created']} criados, {summary['updated']} atualizados, "
            f"{summary['exists']} sem mudanca, {summary['errors']} erros"
        )
        if summary.get("warnings"):
            texto += f", {summary['warnings']} com aviso"
        texto += "."
        # Mostrar o comeco dos erros aqui: sem isso o usuario so descobre abrindo o JSON.
        amostras = summary.get("error_samples") or []
        if amostras:
            texto += "\n\nPrimeiros erros:"
            for item in amostras:
                texto += f"\n- {item['name']}: {item['message']}"
        for item in summary.get("warning_samples") or []:
            texto += f"\n\nAviso ({item['name']}): {item['message']}"
        # O que ficou de fora precisa aparecer aqui: foi o usuario que teve de
        # perguntar por que o IP nao foi criado, porque isso so existia no JSON.
        for nota in summary.get("deferred") or []:
            texto += f"\n\nAtencao: {nota}"
        if paths:
            texto += f"\n\nRelatorio: {paths.get('json', '')}"
        QMessageBox.information(self, "Importacao concluida", texto)

    def _on_import_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Falha na importacao", message)

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
