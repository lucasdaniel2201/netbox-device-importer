"""Visao geral: estado da sessao, tamanho do ambiente e proximo passo.

A tela responde tres perguntas, nesta ordem: estou conectado? o que existe no
NetBox? o que eu faco agora? Por isso os numeros e as acoes ficam no topo, e o
historico recente fecha a pagina como comprovacao do que ja foi feito.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app import provision, theme as theme_mod
from app.history import Run
from app.ui import icons
from app.ui.components import (
    Badge,
    Banner,
    Card,
    Divider,
    ScrollPage,
    SectionHeader,
    StatTile,
    ghost_button,
    muted,
    primary_button,
    secondary_button,
)
from app.ui.table import Cell, DataTable, Row
from app.ui.tokens import GAP_MD, GAP_SM


class ActionRow(QWidget):
    """Uma acao com titulo, explicacao e botao — sem esconder o efeito."""

    def __init__(
        self,
        icon_name: str,
        title: str,
        text: str,
        button_text: str,
        primary: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP_MD)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        row.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(1)
        titulo = QLabel(title)
        titulo.setProperty("muted", "true")
        fonte = titulo.font()
        fonte.setBold(True)
        titulo.setFont(fonte)
        descricao = muted(text)
        textos.addWidget(titulo)
        textos.addWidget(descricao)
        row.addLayout(textos, stretch=1)

        self.button = primary_button(button_text) if primary else secondary_button(button_text)
        row.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.apply_theme(theme_mod.palette())

    def apply_theme(self, palette) -> None:
        self.icon_label.setPixmap(icons.pixmap(self._icon_name, palette.accent, 20))


class DashboardPage(ScrollPage):
    download_template = Signal()
    open_import = Signal()
    download_link_template = Signal()
    open_link_import = Signal()
    save_schema = Signal()
    open_history = Signal()
    open_settings = Signal()
    refresh = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._connected = False
        self._action_rows: list[ActionRow] = []

        self.banner = Banner(
            "warning",
            "Leitura parcial do ambiente",
            "",
        )
        self.banner.hide()
        self.banner.text_label.setOpenExternalLinks(False)
        self.body.addWidget(self.banner)

        self._build_stats()
        self._build_columns()
        self._build_activity()
        self.set_activity([])

    # ------------------------------------------------------------------ blocos
    def _build_stats(self) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(GAP_MD)
        grid.setVerticalSpacing(GAP_MD)

        self.stats: dict[str, StatTile] = {}
        definicoes = (
            ("sites", "Sites"),
            ("device_roles", "Papéis"),
            ("device_types", "Tipos de device"),
            ("devices", "Devices"),
            ("ip_addresses", "IP addresses"),
            ("prefixes", "Prefixos"),
        )
        for indice, (chave, rotulo) in enumerate(definicoes):
            tile = StatTile(rotulo, "—")
            self.stats[chave] = tile
            grid.addWidget(tile, indice // 3, indice % 3)

        for coluna in range(3):
            grid.setColumnStretch(coluna, 1)
        self.body.addLayout(grid)

    def _build_columns(self) -> None:
        colunas = QHBoxLayout()
        colunas.setSpacing(GAP_MD)

        # acoes
        acoes_card = Card()
        acoes = SectionHeader(
            "Próximo passo",
            "O fluxo padrão: baixar o modelo, preencher e importar com prévia.",
        )
        acoes_card.body.addWidget(acoes)
        acoes_card.body.addWidget(Divider())

        self.row_template = ActionRow(
            "download",
            "Baixar planilha modelo",
            "Excel com as listas de Site e Papel vindas do NetBox.",
            "Baixar",
        )
        self.row_import = ActionRow(
            "import",
            "Importar câmeras e switches",
            "Escolher a planilha, revisar linha a linha e enviar.",
            "Importar",
            primary=True,
        )
        self.row_link_template = ActionRow(
            "file",
            "Baixar modelo de links IP",
            "Blocos público e LAN, IP do link e interface do roteador.",
            "Baixar",
        )
        self.row_link_import = ActionRow(
            "link",
            "Importar links IP",
            "Documentar o enlace de internet de cada site.",
            "Importar",
        )
        for linha in (
            self.row_template,
            self.row_import,
            self.row_link_template,
            self.row_link_import,
        ):
            self._action_rows.append(linha)
            acoes_card.body.addWidget(linha)
        acoes_card.body.addStretch(1)

        self.row_template.button.clicked.connect(self.download_template.emit)
        self.row_import.button.clicked.connect(self.open_import.emit)
        self.row_link_template.button.clicked.connect(self.download_link_template.emit)
        self.row_link_import.button.clicked.connect(self.open_link_import.emit)

        colunas.addWidget(acoes_card, stretch=3)

        # ambiente
        ambiente = Card()
        ambiente.body.addWidget(
            SectionHeader("Ambiente", "O que a sessão atual enxerga no NetBox.")
        )
        ambiente.body.addWidget(Divider())

        self.env_values: dict[str, QLabel] = {}
        for chave, rotulo in (
            ("version", "Versão do NetBox"),
            ("api", "Versão da API"),
            ("user", "Dono do token"),
            ("auth", "Autenticação"),
            ("tls", "Certificado TLS"),
        ):
            linha = QHBoxLayout()
            linha.setSpacing(GAP_SM)
            nome = QLabel(rotulo)
            nome.setProperty("muted", "true")
            valor = QLabel("—")
            valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            valor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            valor.setWordWrap(True)
            linha.addWidget(nome)
            linha.addWidget(valor, stretch=1)
            ambiente.body.addLayout(linha)
            self.env_values[chave] = valor

        self.tls_badge = Badge("—", "neutral")
        ambiente.body.addSpacing(GAP_SM)
        ambiente.body.addWidget(Divider())

        self.save_schema_button = secondary_button("Salvar schema (JSON)", "download")
        self.save_schema_button.clicked.connect(self.save_schema.emit)
        self.settings_button = ghost_button("Abrir configurações")
        self.settings_button.clicked.connect(self.open_settings.emit)

        botoes = QHBoxLayout()
        botoes.setSpacing(GAP_SM)
        botoes.addWidget(self.save_schema_button)
        botoes.addWidget(self.settings_button)
        botoes.addStretch(1)
        ambiente.body.addLayout(botoes)
        ambiente.body.addStretch(1)

        colunas.addWidget(ambiente, stretch=2)
        self.body.addLayout(colunas)

    def _build_activity(self) -> None:
        recentes = Card()
        cabecalho = SectionHeader(
            "Últimas execuções",
            "Relatórios gravados em disco por este computador.",
        )
        self.history_button = ghost_button("Ver histórico completo")
        self.history_button.clicked.connect(self.open_history.emit)
        cabecalho.actions.addWidget(self.history_button)
        recentes.body.addWidget(cabecalho)

        self.activity = DataTable(
            ["Quando", "Tipo", "Linhas", "Situação"],
            status_column=3,
            search_placeholder="Buscar execução...",
            ascending=False,
            compact_columns=(2, 3),
        )
        self.activity.search.hide()
        self.activity.set_empty_message(
            "Nenhuma importação registrada ainda.", icon_name="history"
        )
        recentes.body.addWidget(self.activity)
        self.body.addWidget(recentes)

    # --------------------------------------------------------------- estado
    def set_snapshot(self, snapshot: dict) -> None:
        objetos = snapshot.get("objects", {}) or {}
        contagens = snapshot.get("counts", {}) or {}

        self.stats["sites"].set_value(len(objetos.get("sites", []) or []))
        self.stats["device_roles"].set_value(len(objetos.get("device_roles", []) or []))
        self.stats["device_types"].set_value(len(objetos.get("device_types", []) or []))
        for chave in ("devices", "ip_addresses", "prefixes"):
            self.stats[chave].set_value(contagens.get(chave))

        versao = provision.netbox_version(snapshot) or "—"
        self.env_values["version"].setText(versao)
        self.env_values["api"].setText(str(snapshot.get("api_version") or "—"))

        usuario = snapshot.get("current_user") or {}
        nome = usuario.get("username") or "—"
        if usuario.get("is_superuser"):
            nome += " · superusuário"
        self.env_values["user"].setText(nome)
        self.env_values["auth"].setText(str(snapshot.get("token_scheme") or "—"))

        tls_ok = snapshot.get("tls_verified")
        if tls_ok is None:
            self.env_values["tls"].setText("não informado")
            self.tls_badge.set_state("Desconhecido", "neutral")
        elif tls_ok:
            self.env_values["tls"].setText("verificado")
            self.tls_badge.set_state("Verificado", "success")
        else:
            self.env_values["tls"].setText("aceito sem verificação")
            self.tls_badge.set_state("Não verificado", "warning")

        erros = snapshot.get("errors") or []
        if erros:
            conjuntos = []
            for erro in erros:
                nome_conjunto = str(erro).split(":", 1)[0].strip() or "?"
                if nome_conjunto not in conjuntos:
                    conjuntos.append(nome_conjunto)
            self.banner.set_content(
                "Não foi possível ler algumas partes do NetBox",
                "Falhou em: "
                + ", ".join(conjuntos)
                + ". Isso não impede a importação; os detalhes estão em Configurações.",
                "warning",
            )
            self.banner.show()
        else:
            self.banner.hide()

        self.set_connected(True)

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        for linha in self._action_rows:
            linha.setEnabled(connected)
        self.save_schema_button.setEnabled(connected)
        if not connected:
            for chave in self.env_values:
                self.env_values[chave].setText("—")
            for tile in self.stats.values():
                tile.set_value(None)

    def set_actions_enabled(self, enabled: bool) -> None:
        for linha in self._action_rows:
            linha.setEnabled(enabled)

    def set_activity(self, runs: list[Run]) -> None:
        linhas = [
            Row.of(
                Cell(run.display_time, sort_key=run.timestamp),
                run.kind_label,
                Cell(str(run.total), sort_key=run.total, align="right"),
                Cell(run.status_label, kind=run.status_kind, tip=run.result_label),
            )
            for run in runs
        ]
        self.activity.set_rows(linhas)
        self.activity.fit_height(max_rows=5, max_height=300, min_height=150)
        self.history_button.setVisible(bool(runs))

    def apply_theme(self, palette) -> None:
        for linha in self._action_rows:
            linha.apply_theme(palette)
        self.banner.apply_theme(palette)
        self.activity.apply_theme(palette)
