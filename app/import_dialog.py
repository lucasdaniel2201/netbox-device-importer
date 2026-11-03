"""Dialogo de importacao de cameras e switches.

O fluxo tem quatro etapas visiveis: origem -> revisao -> envio -> resumo. As regras
do produto continuam sendo do plano, nao da tela:

- o plano e mostrado ANTES de qualquer envio;
- referencias que faltam sao criadas so com confirmacao explicita;
- enquanto houver pendencia, o botao de importar fica bloqueado;
- durante o envio ha progresso por device e botao de cancelar.

Separar a revisao do envio e o que impede o "clicou e enviou": o usuario ve a
tabela inteira, corrige a planilha se precisar e so entao confirma.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import import_plan, provision, theme as _theme
from app.spreadsheet import read_file
from app.ui import icons
from app.ui.components import (
    Badge,
    Card,
    ThinProgress,
    danger_button,
    ghost_button,
    muted,
    primary_button,
    repolish,
    secondary_button,
)
from app.ui.flow import ChecklistCard, DialogHeader, DropArea, SummaryPanel
from app.ui.table import Cell, DataTable, Row
from app.ui.tokens import GAP_LG, GAP_MD, GAP_SM

SHEET_FILTER = "Planilhas (*.xlsx *.csv);;Excel (*.xlsx);;CSV (*.csv)"
STEPS = ["Origem", "Revisão", "Envio", "Resumo"]
PLAN_COLUMNS = ["Linha", "Nome", "Site", "Tipo", "Situação"]
STATUS_LABELS = {
    "created": "criado",
    "updated": "atualizado",
    "exists": "sem mudança",
    "error": "erro",
}


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
        self.setWindowTitle("Importar câmeras e switches")
        self.setModal(True)
        self.resize(1160, 780)
        self.setMinimumSize(980, 640)

        self._snapshot = snapshot
        self._session = session
        self._sheet = None
        self._plan = None
        self._busy = False
        self._step = 0
        self._sheet_path = ""
        self._signals_connected = False

        self._build_ui()
        self._connect_session()
        self._refresh_ui()
        self._go_step(0)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GAP_LG + 4, GAP_LG, GAP_LG + 4, GAP_LG)
        layout.setSpacing(GAP_MD)

        self.header = DialogHeader(
            "Importar câmeras e switches",
            "Escolha a planilha, confira o plano linha a linha e envie. Nada é gravado "
            "antes da sua confirmação.",
            STEPS,
        )
        layout.addWidget(self.header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_source())
        self.stack.addWidget(self._build_review())
        self.stack.addWidget(self._build_progress())
        self.stack.addWidget(self._build_result())
        layout.addWidget(self.stack, stretch=1)

        rodape = QHBoxLayout()
        rodape.setSpacing(GAP_SM)
        self.status = QLabel("")
        self.status.setProperty("muted", "true")
        self.status.setWordWrap(True)
        rodape.addWidget(self.status, stretch=1)

        self.back_button = ghost_button("Voltar")
        self.back_button.clicked.connect(self._on_back)
        rodape.addWidget(self.back_button)

        self.new_button = secondary_button("Nova planilha")
        self.new_button.clicked.connect(lambda: self._go_step(0))
        rodape.addWidget(self.new_button)

        self.close_button = ghost_button("Fechar")
        self.close_button.clicked.connect(self.reject)
        rodape.addWidget(self.close_button)

        self.provision_button = secondary_button("Criar o que está faltando")
        self.provision_button.clicked.connect(self._on_provision)
        rodape.addWidget(self.provision_button)

        self.import_button = primary_button("Importar câmeras", "import")
        self.import_button.clicked.connect(self._on_import)
        rodape.addWidget(self.import_button)

        self.cancel_run_button = danger_button("Cancelar importação")
        self.cancel_run_button.clicked.connect(self._on_cancel)
        rodape.addWidget(self.cancel_run_button)

        layout.addLayout(rodape)

    def _build_source(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP_MD)
        layout.addStretch(1)

        self.drop = DropArea(
            "Arraste a planilha para cá",
            "Aceita .xlsx com as listas de Site e Papel vindas do NetBox, "
            "ou .csv (nesse caso, confira Site e Papel à mão).",
            "Escolher planilha",
        )
        self.drop.clicked.connect(self._on_choose_sheet)
        self.drop.file_dropped.connect(self._load_sheet)

        colunas = QHBoxLayout()
        colunas.setSpacing(GAP_MD)
        colunas.addWidget(self.drop, stretch=3)
        self.checklist = ChecklistCard(
            "Antes de importar",
            "O que a planilha precisa ter.",
            [
                ("success", "Obrigatório: Nome do host e Site."),
                ("success", "Opcional: papel, IP, fabricante, modelo, firmware, MAC e NVR."),
                ("info", "Uma linha por device. Papel em branco usa o padrão do app."),
            ],
        )
        colunas.addWidget(self.checklist, stretch=2)
        layout.addLayout(colunas)

        info = Card()
        info.setProperty("tone", "flat")
        linha = QHBoxLayout()
        linha.setSpacing(GAP_MD)
        self.source_icon = QLabel()
        self.source_icon.setFixedSize(18, 18)
        linha.addWidget(self.source_icon, alignment=Qt.AlignmentFlag.AlignTop)
        self.source_note = muted(
            "O app valida a planilha inteira e monta o plano sem enviar nada. "
            "Falha de leitura aparece aqui, antes de qualquer requisição."
        )
        linha.addWidget(self.source_note, stretch=1)
        info.body.addLayout(linha)
        layout.addWidget(info)
        layout.addStretch(1)
        self.source_icon.setPixmap(icons.pixmap("shield", _theme.palette().text_muted, 18))
        return pagina

    def _build_review(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP_MD)

        self.sheet_label = QLabel("Nenhuma planilha carregada.")
        self.sheet_label.setProperty("muted", "true")
        self.sheet_label.setWordWrap(True)
        layout.addWidget(self.sheet_label)

        chips = QHBoxLayout()
        chips.setSpacing(GAP_SM)
        self.chip_ready = Badge("0 prontos", "success")
        self.chip_errors = Badge("0 com erro", "danger")
        self.chip_pending = Badge("0 aguardando referência", "warning")
        self.chip_refs = Badge("0 referências a criar", "info")
        self.chip_fields = Badge("campo sem valor", "danger")
        for chip in (
            self.chip_ready,
            self.chip_errors,
            self.chip_pending,
            self.chip_refs,
            self.chip_fields,
        ):
            chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)

        self.plan_table = DataTable(
            PLAN_COLUMNS,
            status_column=4,
            search_placeholder="Buscar por nome ou site",
        )
        self.plan_table.set_empty_message(
            "Carregue uma planilha para ver o plano.", icon_name="file"
        )
        layout.addWidget(self.plan_table, stretch=1)

        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        layout.addWidget(self.plan_label)

        self.fields_label = QLabel("")
        self.fields_label.setProperty("faint", "true")
        self.fields_label.setWordWrap(True)
        layout.addWidget(self.fields_label)
        return pagina

    def _build_progress(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)

        titulo = QLabel("Enviando para o NetBox")
        titulo.setObjectName("CardTitle")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        self.progress_detail = QLabel("Preparando...")
        self.progress_detail.setProperty("muted", "true")
        self.progress_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_detail.setWordWrap(True)
        layout.addWidget(self.progress_detail)

        self.progress_bar = ThinProgress()
        self.progress_bar.setMaximumWidth(520)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return pagina

    def _build_result(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = SummaryPanel()
        layout.addWidget(self.summary)
        layout.addStretch(1)
        return pagina

    # --------------------------------------------------------------- sessao
    def _connect_session(self) -> None:
        self._session.progress.connect(self._on_progress)
        self._session.import_done.connect(self._on_import_done)
        self._session.import_failed.connect(self._on_import_failed)
        self._session.provision_done.connect(self._on_provision_done)
        self._session.provision_failed.connect(self._on_provision_failed)
        self._signals_connected = True

    def _disconnect_session(self) -> None:
        # Fechar duas vezes (X e Esc, por exemplo) nao pode desconectar de novo:
        # o Python avisa em stderr quando o sinal ja nao tem aquela conexao.
        if not self._signals_connected:
            return
        self._signals_connected = False
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
        return provision.site_names(self._snapshot)

    def _go_step(self, index: int) -> None:
        self._step = index
        self.stack.setCurrentIndex(index)
        self.header.set_step(index)
        self._update_footer()

    def _update_footer(self) -> None:
        step = self._step
        busy = self._busy
        self.back_button.setVisible(step == 1 and not busy)
        self.close_button.setVisible(not busy and step != 2)
        self.new_button.setVisible(step == 3 and not busy)
        tem_referencias = self._plan is not None and bool(self._plan.references)
        self.provision_button.setVisible(step == 1 and not busy and tem_referencias)
        self.import_button.setVisible(step == 1 and not busy)
        self.cancel_run_button.setVisible(step == 2 and busy)

        if not busy:
            self.status.setText("")

    def _refresh_ui(self) -> None:
        plan = self._plan
        if plan is None:
            self.plan_table.set_rows([])
            self.chip_ready.hide()
            self.chip_errors.hide()
            self.chip_pending.hide()
            self.chip_refs.hide()
            self.chip_fields.hide()
            self.plan_label.setText("")
            self.fields_label.setText("")
            self.sheet_label.setText("Nenhuma planilha carregada.")
            if hasattr(self, "provision_button"):
                self.provision_button.setText("Criar o que está faltando")
                self.import_button.setText("Importar câmeras")
                self.import_button.setEnabled(False)
            self._update_footer()
            return

        self._fill_table(plan)

        prontos = len(plan.ready_devices)
        bloqueados = len(plan.blocked_devices)
        faltando = len(plan.references)
        com_erro = sum(1 for device in plan.devices if device.issues)
        aguardando = bloqueados - com_erro
        sem_campo = plan.missing_required

        self.chip_ready.setText(f"{prontos} pronto(s)")
        self.chip_ready.show()
        self.chip_errors.setVisible(bool(com_erro))
        self.chip_errors.setText(f"{com_erro} com erro")
        self.chip_pending.setVisible(bool(aguardando))
        self.chip_pending.setText(f"{aguardando} aguardando referência")
        self.chip_refs.setVisible(bool(faltando))
        self.chip_refs.setText(f"{faltando} referência(s) a criar")
        self.chip_fields.setVisible(bool(sem_campo))
        self.chip_fields.setText(
            "campo do NetBox sem valor: " + ", ".join(sem_campo) if sem_campo else ""
        )

        partes = []
        if bloqueados:
            partes.append(f"{bloqueados} linha(s) ainda bloqueada(s)")
        if not plan.deferred and not partes:
            partes.append("Tudo pronto: cada linha será conferida no NetBox antes de gravar.")
        if plan.deferred:
            partes.append(plan.deferred[0])
        self.plan_label.setText(" | ".join(partes))
        if com_erro or sem_campo:
            cor = _theme.palette().danger
        elif bloqueados or faltando:
            cor = _theme.palette().warning
        else:
            cor = _theme.palette().success
        self.plan_label.setStyleSheet(f"color: {cor}; font-weight: 600;")

        campos = describe_custom_fields(plan.custom_fields_used)
        self.fields_label.setText(
            f"Custom fields enviados → {campos}" if campos else ""
        )

        self.provision_button.setText(f"Criar o que está faltando ({faltando})")
        self.provision_button.setEnabled(bool(faltando) and not self._busy)
        # Quando criar referencias e o proximo passo obrigatorio, ele e a acao
        # principal da tela - e nao o botao de importar, que esta bloqueado.
        self.provision_button.setObjectName(
            "primaryButton" if faltando and not self._busy else ""
        )
        repolish(self.provision_button)

        if self._busy:
            rotulo, habilitado = "Importando...", False
        elif faltando:
            rotulo, habilitado = "Crie as referências primeiro", False
        elif sem_campo:
            rotulo, habilitado = "Configure o campo no app (config.py)", False
        elif bloqueados:
            rotulo, habilitado = "Corrija as pendências na planilha", False
        elif prontos:
            rotulo, habilitado = f"Importar {prontos} câmeras", True
        else:
            rotulo, habilitado = "Importar câmeras", False
        self.import_button.setText(rotulo)
        self.import_button.setEnabled(habilitado)
        self._update_footer()

    def _fill_table(self, plan) -> None:
        linhas = []
        for device in plan.devices:
            if device.issues:
                situacao, kind = "erro", "danger"
                detalhe = " | ".join(device.issues)
            elif device.pending:
                situacao, kind = "pendente", "warning"
                detalhe = "criar " + ", ".join(device.pending)
            else:
                situacao, kind = "pronto", "success"
                detalhe = ""
            linhas.append(
                Row.of(
                    Cell(str(device.row_number), sort_key=device.row_number, align="right"),
                    Cell(device.name, tip=device.name),
                    device.site,
                    device.device_type_label,
                    Cell(situacao, kind=kind, tip=detalhe),
                )
            )
        self.plan_table.set_rows(linhas)

    def _rebuild_plan(self) -> None:
        if self._sheet is None:
            self._plan = None
            self._refresh_ui()
            return
        self._plan = import_plan.build_plan(self._sheet, self._snapshot)
        self._refresh_ui()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.cancel_run_button.setEnabled(True)
        self.close_button.setEnabled(not busy)
        self.drop.setEnabled(not busy)
        if not busy:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        self._refresh_ui()

    # ----------------------------------------------------- acoes do usuario
    def _on_back(self) -> None:
        if self._busy:
            return
        self._go_step(0)

    def _on_choose_sheet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher planilha", str(Path.home()), SHEET_FILTER
        )
        if path:
            self._load_sheet(path)

    def _load_sheet(self, path: str) -> None:
        try:
            sheet = read_file(
                Path(path),
                sites=self._all_sites(),
                roles=provision.reference_labels(self._snapshot, "device_roles"),
            )
        except Exception as exc:
            self._sheet = None
            self._plan = None
            self._refresh_ui()
            QMessageBox.warning(self, "Planilha inválida", str(exc))
            return

        self._sheet = sheet
        self._sheet_path = path
        self.sheet_label.setText(
            f"{Path(path).name}  ·  {len(sheet.valid_rows)} linhas válidas  ·  "
            f"{len(sheet.rows_with_errors)} com erro"
        )
        self._rebuild_plan()
        self._go_step(1)

    def _on_provision(self) -> None:
        plan = self._plan
        if plan is None or not plan.references:
            return
        lista = "\n".join(f"  • {ref.kind}: {ref.label}" for ref in plan.references)
        resposta = QMessageBox.question(
            self,
            "Criar referências no NetBox",
            "Vou criar estes objetos antes de importar:\n\n"
            f"{lista}\n\nConfirma?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        self.status.setText("Criando referências no NetBox...")
        self._session.request_provision.emit(plan.references)

    def _on_import(self) -> None:
        plan = self._plan
        if plan is None or not plan.can_import:
            return
        self._set_busy(True)
        self._go_step(2)
        self.progress_bar.setRange(0, len(plan.ready_devices))
        self.progress_bar.setValue(0)
        self.progress_detail.setText("Conferindo e gravando cada device...")
        self._session.request_import.emit(plan)

    def _on_cancel(self) -> None:
        self._session.request_cancel.emit()
        self.cancel_run_button.setEnabled(False)
        self.status.setText("Cancelamento pedido: a execução para após o device atual.")

    # --------------------------------------------------- callbacks da sessao
    def _on_progress(self, index: int, total: int, name: str, status: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index)
        rotulo = STATUS_LABELS.get(status, status)
        self.progress_detail.setText(f"{index} de {total}  ·  {name}  ·  {rotulo}")

    def _on_provision_done(self, payload: dict) -> None:
        self._set_busy(False)
        criados = payload.get("created", [])
        self._rebuild_plan()
        if criados:
            nomes = ", ".join(item["label"] for item in criados)
            QMessageBox.information(
                self, "Referências criadas", f"Criado no NetBox: {nomes}"
            )

    def _on_provision_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Falha ao criar referência", message)

    def _on_import_done(self, summary: dict) -> None:
        self._set_busy(False)
        extras = []
        if summary.get("deferred"):
            extras.append(f"Pendência: {summary['deferred'][0]}")
        self.summary.set_summary(summary, extras)
        self.summary.set_details(self._result_rows(summary.get("results") or []))
        self._go_step(3)

    @staticmethod
    def _result_rows(resultados: list[dict]) -> list[Row]:
        kinds = {"created": "success", "updated": "info", "exists": "neutral", "error": "danger"}
        linhas = []
        for item in resultados:
            status = str(item.get("status") or "")
            detalhe = str(item.get("message") or "")
            if item.get("warnings"):
                detalhe += " | aviso: " + str(item["warnings"])
            linhas.append(
                Row.of(
                    Cell(str(item.get("row_number", "")), sort_key=item.get("row_number") or 0, align="right"),
                    Cell(str(item.get("name") or ""), tip=str(item.get("site") or "")),
                    Cell(STATUS_LABELS.get(status, status), kind=kinds.get(status, "neutral"), tip=detalhe),
                )
            )
        return linhas

    def _on_import_failed(self, message: str) -> None:
        self._set_busy(False)
        self._go_step(1)
        QMessageBox.critical(self, "Falha na importação", message)

    # --------------------------------------------------------------- fechar
    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy:
            resposta = QMessageBox.question(
                self,
                "Importação em andamento",
                "Há uma importação rodando. Cancelar e fechar?",
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

    def apply_theme(self, palette) -> None:
        self.source_icon.setPixmap(icons.pixmap("shield", palette.text_muted, 18))
        self.drop.apply_theme(palette)
        self.summary.apply_theme(palette)
        self.plan_table.apply_theme(palette)
