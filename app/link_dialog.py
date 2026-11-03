"""Dialogo de importacao de links IP, no mesmo fluxo do de cameras.

Diferenca de escopo: aqui **nao** se cria referencia nem se pergunta nada alem do
plano. O device e achado no site (ou criado, quando falta) e o que a planilha pode
pedir sao os prefixos, a interface e o IP. O plano mostra "vai criar" antes de
qualquer escrita e o resumo separa link pronto de aviso.
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

from app import link_plan, provision, theme as _theme
from app.link_sheet import read_file
from app.ui import icons
from app.ui.components import (
    Badge,
    Card,
    ThinProgress,
    danger_button,
    ghost_button,
    muted,
    primary_button,
    secondary_button,
)
from app.ui.flow import ChecklistCard, DialogHeader, DropArea, SummaryPanel
from app.ui.table import Cell, DataTable, Row
from app.ui.tokens import GAP_LG, GAP_MD, GAP_SM

SHEET_FILTER = "Planilhas (*.xlsx *.csv);;Excel (*.xlsx);;CSV (*.csv)"
STEPS = ["Origem", "Revisão", "Envio", "Resumo"]
PLAN_COLUMNS = ["Linha", "Site", "Device", "Bloco público", "IP do link", "Situação"]
STATUS_LABELS = {
    "created": "criado",
    "updated": "atualizado",
    "exists": "sem mudança",
    "error": "erro",
}


class LinkImportDialog(QDialog):
    def __init__(self, parent, snapshot: dict, session) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar links IP")
        self.setModal(True)
        self.resize(1180, 780)
        self.setMinimumSize(1000, 650)

        self._snapshot = snapshot
        self._session = session
        self._sheet = None
        self._plan = None
        self._busy = False
        self._step = 0
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
            "Importar links IP",
            "Bloco público, bloco LAN e o endereço do roteador no enlace. O plano é "
            "mostrado inteiro antes de qualquer escrita.",
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
        self.back_button.clicked.connect(lambda: self._go_step(0))
        rodape.addWidget(self.back_button)

        self.new_button = secondary_button("Nova planilha")
        self.new_button.clicked.connect(lambda: self._go_step(0))
        rodape.addWidget(self.new_button)

        self.close_button = ghost_button("Fechar")
        self.close_button.clicked.connect(self.reject)
        rodape.addWidget(self.close_button)

        self.import_button = primary_button("Importar links", "link")
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
            "Arraste a planilha de links para cá",
            "Colunas: Site, Device, Bloco público, Interface, IP do link, Bloco LAN, "
            "Papel do prefixo, Adicionar ao Zabbix, Descrição e Fornecedor/chamado.",
            "Escolher planilha de links",
        )
        self.drop.clicked.connect(self._on_choose_sheet)
        self.drop.file_dropped.connect(self._load_sheet)

        colunas = QHBoxLayout()
        colunas.setSpacing(GAP_MD)
        colunas.addWidget(self.drop, stretch=3)
        self.checklist = ChecklistCard(
            "Antes de importar",
            "O que a planilha de links precisa ter.",
            [
                ("success", "Obrigatório: Site, Device e Bloco público."),
                ("info", "Interface em branco vale wan1; se não existir, é criada."),
                ("info", "IP em branco é deduzido do bloco — sempre com aviso no plano."),
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
            "O app normaliza o bloco para a rede, confere se o IP pertence ao bloco e "
            "recusa bloco público ou IP repetido entre linhas — antes de enviar."
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
        self.chip_ready = Badge("0 links prontos", "success")
        self.chip_errors = Badge("0 com erro", "danger")
        self.chip_devices = Badge("0 devices a criar", "info")
        self.chip_prefixes = Badge("0 prefixos", "info")
        self.chip_deduced = Badge("0 IP deduzido", "warning")
        self.chip_fields = Badge("campo sem valor", "danger")
        for chip in (
            self.chip_ready,
            self.chip_errors,
            self.chip_devices,
            self.chip_prefixes,
            self.chip_deduced,
            self.chip_fields,
        ):
            chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)

        self.plan_table = DataTable(
            PLAN_COLUMNS,
            status_column=5,
            search_placeholder="Buscar por site ou IP",
        )
        self.plan_table.set_empty_message(
            "Carregue uma planilha de links para ver o plano.", icon_name="link"
        )
        layout.addWidget(self.plan_table, stretch=1)

        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        layout.addWidget(self.plan_label)
        return pagina

    def _build_progress(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)

        titulo = QLabel("Enviando links para o NetBox")
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

    def _connect_session(self) -> None:
        self._session.links_progress.connect(self._on_progress)
        self._session.links_done.connect(self._on_import_done)
        self._session.links_failed.connect(self._on_import_failed)
        self._signals_connected = True

    def _disconnect_session(self) -> None:
        # Fechar duas vezes (X e Esc, por exemplo) nao pode desconectar de novo:
        # o Python avisa em stderr quando o sinal ja nao tem aquela conexao.
        if not self._signals_connected:
            return
        self._signals_connected = False
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
        self.import_button.setVisible(step == 1 and not busy)
        self.cancel_run_button.setVisible(step == 2 and busy)
        if not busy:
            self.status.setText("")

    def _refresh_ui(self) -> None:
        plan = self._plan
        if plan is None:
            self.plan_table.set_rows([])
            for chip in (
                self.chip_ready,
                self.chip_errors,
                self.chip_devices,
                self.chip_prefixes,
                self.chip_deduced,
                self.chip_fields,
            ):
                chip.hide()
            self.plan_label.setText("")
            self.sheet_label.setText("Nenhuma planilha carregada.")
            if hasattr(self, "import_button"):
                self.import_button.setText("Importar links")
                self.import_button.setEnabled(False)
            self._update_footer()
            return

        self._fill_table(plan)

        prontos = len(plan.ready_rows)
        com_erro = len(plan.blocked_rows)
        deduzidos = sum(1 for row in plan.ready_rows if row.link_ip_deduced)
        sem_campo = plan.missing_required

        self.chip_ready.setText(f"{prontos} link(s) pronto(s)")
        self.chip_ready.show()
        self.chip_errors.setVisible(bool(com_erro))
        self.chip_errors.setText(f"{com_erro} com erro")
        self.chip_devices.setVisible(bool(plan.devices_to_create))
        self.chip_devices.setText(f"{plan.devices_to_create} device(s) a criar")
        self.chip_prefixes.setText(f"{plan.prefix_count} prefixo(s)")
        self.chip_prefixes.show()
        self.chip_deduced.setVisible(bool(deduzidos))
        self.chip_deduced.setText(f"{deduzidos} com IP deduzido")
        self.chip_fields.setVisible(bool(sem_campo))
        self.chip_fields.setText(
            "campo do NetBox sem valor: " + ", ".join(sem_campo) if sem_campo else ""
        )

        partes = []
        if com_erro:
            partes.append(f"{com_erro} linha(s) com erro")
        if not com_erro and not sem_campo and prontos:
            partes.append("Tudo pronto para enviar.")
        if sem_campo:
            partes.append("Campo obrigatório do NetBox sem valor.")
        self.plan_label.setText(" | ".join(partes))
        if com_erro or sem_campo:
            cor = _theme.palette().danger
        elif prontos:
            cor = _theme.palette().success
        else:
            cor = _theme.palette().warning
        self.plan_label.setStyleSheet(f"color: {cor}; font-weight: 600;")

        if self._busy:
            rotulo, habilitado = "Importando...", False
        elif sem_campo:
            rotulo, habilitado = "Configure o campo no app (config.py)", False
        elif com_erro:
            rotulo, habilitado = "Corrija as pendências na planilha", False
        elif prontos:
            rotulo, habilitado = f"Importar {prontos} link(s)", True
        else:
            rotulo, habilitado = "Importar links", False
        self.import_button.setText(rotulo)
        self.import_button.setEnabled(habilitado)
        self._update_footer()

    def _fill_table(self, plan) -> None:
        linhas = []
        for row in plan.rows:
            if row.issues:
                situacao, kind = "erro", "danger"
                detalhe = " | ".join(row.issues)
            elif row.pending:
                situacao, kind = "vai criar", "warning"
                detalhe = ", ".join(row.pending)
            elif row.warnings:
                situacao, kind = "pronto · aviso", "warning"
                detalhe = " | ".join(row.warnings)
            else:
                situacao, kind = "pronto", "success"
                detalhe = ""
            linhas.append(
                Row.of(
                    Cell(str(row.row_number), sort_key=row.row_number, align="right"),
                    row.site,
                    Cell(row.device, tip=row.device),
                    row.public_block,
                    row.link_ip,
                    Cell(situacao, kind=kind, tip=detalhe),
                )
            )
        self.plan_table.set_rows(linhas)

    def _rebuild_plan(self) -> None:
        if self._sheet is None:
            self._plan = None
            self._refresh_ui()
            return
        self._plan = link_plan.build_plan(self._sheet, self._snapshot)
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
    def _on_choose_sheet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher planilha de links", str(Path.home()), SHEET_FILTER
        )
        if path:
            self._load_sheet(path)

    def _load_sheet(self, path: str) -> None:
        try:
            sheet = read_file(
                Path(path),
                sites=provision.site_names(self._snapshot),
                prefix_roles=provision.reference_labels(self._snapshot, "prefix_roles"),
            )
        except Exception as exc:
            self._sheet = None
            self._plan = None
            self._refresh_ui()
            QMessageBox.warning(self, "Planilha de links inválida", str(exc))
            return

        self._sheet = sheet
        self.sheet_label.setText(
            f"{Path(path).name}  ·  {len(sheet.valid_rows)} linhas válidas  ·  "
            f"{len(sheet.rows_with_errors)} com erro"
        )
        self._rebuild_plan()
        self._go_step(1)

    def _on_import(self) -> None:
        plan = self._plan
        if plan is None or not plan.can_import:
            return
        self._set_busy(True)
        self._go_step(2)
        self.progress_bar.setRange(0, len(plan.ready_rows))
        self.progress_bar.setValue(0)
        self.progress_detail.setText("Gravando prefixos, interface e IP de cada link...")
        self._session.request_import_links.emit(plan)

    def _on_cancel(self) -> None:
        self._session.request_cancel.emit()
        self.cancel_run_button.setEnabled(False)
        self.status.setText("Cancelamento pedido: a execução para após o link atual.")

    # --------------------------------------------------- callbacks da sessao
    def _on_progress(self, index: int, total: int, name: str, status: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index)
        rotulo = STATUS_LABELS.get(status, status)
        self.progress_detail.setText(f"{index} de {total}  ·  {name}  ·  {rotulo}")

    def _on_import_done(self, summary: dict) -> None:
        self._set_busy(False)
        extras = []
        if summary.get("prefixes"):
            extras.append(f"{summary['prefixes']} prefixo(s) envolvidos")
        if summary.get("devices_created"):
            extras.append(f"{summary['devices_created']} device(s) criado(s)")
        if summary.get("deduced_ips"):
            extras.append(f"{summary['deduced_ips']} IP(s) deduzido(s)")
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
                    Cell(
                        f"{item.get('site', '')} · {item.get('device', '')} · {item.get('link_ip', '')}",
                        tip=str(item.get("public_block") or ""),
                    ),
                    Cell(STATUS_LABELS.get(status, status), kind=kinds.get(status, "neutral"), tip=detalhe),
                )
            )
        return linhas

    def _on_import_failed(self, message: str) -> None:
        self._set_busy(False)
        self._go_step(1)
        QMessageBox.critical(self, "Falha na importação de links", message)

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
