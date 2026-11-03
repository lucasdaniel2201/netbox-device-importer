"""Configuracoes: conexao, token, aparencia e o ambiente tecnico descoberto.

Tudo o que era painel avancado na tela antiga esta aqui, mas organizado por assunto.
Nenhuma informacao sensivel e exibida: o token nunca volta para a tela, so o tipo
de protecao em uso e o dono dele.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import credentials, provision, theme as theme_mod, version as version_mod
from app.config import NETBOX_URL
from app.ui import icons
from app.ui.components import (
    Badge,
    Card,
    Divider,
    ScrollPage,
    SearchField,
    SectionHeader,
    danger_button,
    ghost_button,
    muted,
    secondary_button,
)
from app.ui.tokens import GAP_MD, GAP_SM

PREVIEW_LIMIT = 100

SET_LABELS: tuple[tuple[str, str], ...] = (
    ("sites", "Sites"),
    ("locations", "Locations"),
    ("regions", "Regions"),
    ("site_groups", "Grupos de site"),
    ("racks", "Racks"),
    ("device_roles", "Papéis de device (roles)"),
    ("manufacturers", "Fabricantes"),
    ("device_types", "Tipos de device"),
    ("tags", "Tags"),
    ("tenants", "Tenants"),
)

COUNT_LABELS: tuple[tuple[str, str], ...] = (
    ("devices", "Devices"),
    ("interfaces", "Interfaces"),
    ("ip_addresses", "IP addresses"),
    ("prefixes", "Prefixes"),
    ("journal_entries", "Journal entries"),
)

ENDPOINT_LABELS: tuple[tuple[str, str], ...] = (
    ("device", "Devices"),
    ("device_type", "Device types"),
    ("manufacturer", "Fabricantes"),
    ("device_role", "Papéis (roles)"),
    ("site", "Sites"),
    ("location", "Locations"),
    ("tenant", "Tenants"),
    ("interface", "Interfaces"),
    ("ip_address", "IP addresses"),
    ("prefix", "Prefixos de IP"),
    ("tag", "Tags"),
)


class SettingsPage(ScrollPage):
    refresh_clicked = Signal()
    logout_clicked = Signal()
    forget_token_clicked = Signal()
    save_schema_clicked = Signal()
    theme_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(max_width=980, parent=parent)
        self._snapshot: dict | None = None
        self._tree_open = False

        self._build_connection()
        self._build_token()
        self._build_appearance()
        self._build_technical()
        self._build_about()
        self.body.addStretch(1)
        self.apply_theme(theme_mod.palette())

    # ------------------------------------------------------------- conexao
    def _build_connection(self) -> None:
        cartao = Card()
        cabecalho = SectionHeader(
            "Conexão", "Servidor fixo nesta versão do app. Só o token é informado."
        )
        self.refresh_button = secondary_button("Atualizar ambiente", "refresh")
        self.refresh_button.clicked.connect(self.refresh_clicked.emit)
        cabecalho.actions.addWidget(self.refresh_button)
        cartao.body.addWidget(cabecalho)
        cartao.body.addWidget(Divider())

        self.connection_badge = Badge("Desconectado", "neutral")
        linha_status = QHBoxLayout()
        linha_status.setSpacing(GAP_SM)
        rotulo = QLabel("Status")
        rotulo.setProperty("muted", "true")
        linha_status.addWidget(rotulo)
        linha_status.addStretch(1)
        linha_status.addWidget(self.connection_badge)
        cartao.body.addLayout(linha_status)

        self.connection_values: dict[str, QLabel] = {}
        for chave, nome in (
            ("server", "Servidor"),
            ("version", "Versão do NetBox"),
            ("api", "Versão da API"),
            ("user", "Dono do token"),
            ("auth", "Esquema de autenticação"),
            ("tls", "Certificado TLS"),
        ):
            linha = QHBoxLayout()
            linha.setSpacing(GAP_SM)
            rotulo = QLabel(nome)
            rotulo.setProperty("muted", "true")
            valor = QLabel(NETBOX_URL if chave == "server" else "—")
            valor.setObjectName("Mono" if chave == "server" else "")
            valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            valor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            valor.setWordWrap(True)
            linha.addWidget(rotulo)
            linha.addWidget(valor, stretch=1)
            cartao.body.addLayout(linha)
            self.connection_values[chave] = valor

        rodape = QHBoxLayout()
        self.logout_button = danger_button("Sair da sessão")
        self.logout_button.clicked.connect(self.logout_clicked.emit)
        rodape.addWidget(self.logout_button)
        rodape.addStretch(1)
        cartao.body.addLayout(rodape)
        self.body.addWidget(cartao)

    # --------------------------------------------------------------- token
    def _build_token(self) -> None:
        cartao = Card()
        cartao.body.addWidget(
            SectionHeader(
                "Token de API",
                "As permissões da sessão são as do dono do token, não as de quem opera o app.",
            )
        )
        cartao.body.addWidget(Divider())

        self.token_state = QLabel("Nenhum token guardado nesta máquina.")
        self.token_state.setProperty("muted", "true")
        self.token_state.setWordWrap(True)
        cartao.body.addWidget(self.token_state)

        self.token_path_label = QLabel("")
        self.token_path_label.setObjectName("Mono")
        self.token_path_label.setWordWrap(True)
        cartao.body.addWidget(self.token_path_label)

        self.forget_button = danger_button("Esquecer token guardado")
        self.forget_button.clicked.connect(self.forget_token_clicked.emit)
        cartao.body.addWidget(self.forget_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.body.addWidget(cartao)

    # ---------------------------------------------------------- aparencia
    def _build_appearance(self) -> None:
        cartao = Card()
        cartao.body.addWidget(
            SectionHeader("Aparência", "O tema vale para todas as telas e é lembrado.")
        )
        cartao.body.addWidget(Divider())

        linha = QHBoxLayout()
        linha.setSpacing(GAP_MD)
        rotulo = QLabel("Tema da interface")
        rotulo.setProperty("muted", "true")
        linha.addWidget(rotulo)
        linha.addStretch(1)

        segmentado = QFrame()
        segmentado.setObjectName("Segmented")
        grupo_layout = QHBoxLayout(segmentado)
        grupo_layout.setContentsMargins(2, 2, 2, 2)
        grupo_layout.setSpacing(2)

        self.dark_button = QPushButton("Escuro")
        self.light_button = QPushButton("Claro")
        self._theme_group = QButtonGroup(self)
        self._theme_group.setExclusive(True)
        for indice, botao in enumerate((self.dark_button, self.light_button)):
            botao.setObjectName("Segment")
            botao.setCheckable(True)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setMinimumHeight(28)
            self._theme_group.addButton(botao, indice)
            grupo_layout.addWidget(botao)
        self.dark_button.clicked.connect(lambda: self.theme_changed.emit("dark"))
        self.light_button.clicked.connect(lambda: self.theme_changed.emit("light"))
        linha.addWidget(segmentado)
        cartao.body.addLayout(linha)
        self.body.addWidget(cartao)

    def set_theme_mode(self, mode: str) -> None:
        self.dark_button.setChecked(mode != "light")
        self.light_button.setChecked(mode == "light")

    # ---------------------------------------------------------- tecnico
    def _build_technical(self) -> None:
        cartao = Card()
        cabecalho = SectionHeader(
            "Ambiente técnico",
            "Tudo o que foi lido na conexão: permissões, contagens, objetos e custom fields.",
        )
        self.schema_button = secondary_button("Salvar schema (JSON)", "download")
        self.schema_button.clicked.connect(self.save_schema_clicked.emit)
        cabecalho.actions.addWidget(self.schema_button)
        cartao.body.addWidget(cabecalho)
        cartao.body.addWidget(Divider())

        self.disclosure = ghost_button("Mostrar detalhes técnicos")
        self.disclosure.setIconSize(QSize(14, 14))
        self.disclosure.clicked.connect(self._toggle_tree)
        cartao.body.addWidget(self.disclosure, alignment=Qt.AlignmentFlag.AlignLeft)

        self.technical_container = QWidget()
        tecnico = QVBoxLayout(self.technical_container)
        tecnico.setContentsMargins(0, 0, 0, 0)
        tecnico.setSpacing(GAP_SM)

        self.tree_search = SearchField("Filtrar por nome...")
        self.tree_search.textChanged.connect(self._filter_tree)
        tecnico.addWidget(self.tree_search)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(300)
        tecnico.addWidget(self.tree)

        self.technical_container.hide()
        cartao.body.addWidget(self.technical_container)
        self.body.addWidget(cartao)

    def _toggle_tree(self) -> None:
        self._tree_open = not self._tree_open
        self.technical_container.setVisible(self._tree_open)
        self.disclosure.setText(
            "Ocultar detalhes técnicos" if self._tree_open else "Mostrar detalhes técnicos"
        )
        self.apply_theme(theme_mod.palette())

    def _filter_tree(self, termo: str) -> None:
        termo = termo.strip().casefold()
        for indice in range(self.tree.topLevelItemCount()):
            topo = self.tree.topLevelItem(indice)
            visivel_filho = False
            for filho in range(topo.childCount()):
                item = topo.child(filho)
                combina = not termo or termo in item.text(0).casefold()
                item.setHidden(not combina)
                visivel_filho = visivel_filho or combina
            combina_topo = not termo or termo in topo.text(0).casefold() or visivel_filho
            topo.setHidden(not combina_topo)
            if termo and visivel_filho:
                topo.setExpanded(True)

    # --------------------------------------------------------------- sobre
    def _build_about(self) -> None:
        cartao = Card()
        cartao.setProperty("tone", "flat")
        linha = QHBoxLayout()
        linha.setSpacing(GAP_MD)
        textos = QVBoxLayout()
        textos.setSpacing(1)
        titulo = QLabel(f"Importador NetBox · versão {version_mod.__version__}")
        titulo.setObjectName("CardTitle")
        descricao = muted(
            "L&K Tecnologia — documentação de infraestrutura. Relatórios e preferências "
            "ficam na pasta de dados do usuário."
        )
        textos.addWidget(titulo)
        textos.addWidget(descricao)
        linha.addLayout(textos, stretch=1)
        cartao.body.addLayout(linha)
        self.body.addWidget(cartao)

    # --------------------------------------------------------------- estado
    def set_snapshot(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        objetos = snapshot.get("objects", {}) or {}
        contagens = snapshot.get("counts", {}) or {}

        versao = provision.netbox_version(snapshot) or "—"
        self.connection_values["version"].setText(versao)
        self.connection_values["api"].setText(str(snapshot.get("api_version") or "—"))
        usuario = snapshot.get("current_user") or {}
        nome = usuario.get("username") or "—"
        if usuario.get("is_superuser"):
            nome += " · superusuário"
        self.connection_values["user"].setText(nome)
        self.connection_values["auth"].setText(str(snapshot.get("token_scheme") or "—"))
        tls = snapshot.get("tls_verified")
        self.connection_values["tls"].setText(
            "—" if tls is None else ("verificado" if tls else "aceito sem verificação")
        )
        self.connection_badge.set_state("Conectado", "success")
        self.refresh_button.setEnabled(True)

        self.tree.clear()
        capacidades = snapshot.get("capabilities", {}) or {}
        if capacidades:
            topo = QTreeWidgetItem(["Permissões do token (ações do OPTIONS)"])
            for chave, rotulo in ENDPOINT_LABELS:
                if chave not in capacidades:
                    continue
                acoes = capacidades.get(chave) or []
                detalhe = ", ".join(acoes) if acoes else "SEM PERMISSÃO (nenhuma ação)"
                topo.addChild(QTreeWidgetItem([f"{rotulo}: {detalhe}"]))
            self.tree.addTopLevelItem(topo)

        topo = QTreeWidgetItem(["Contagens"])
        for chave, rotulo in COUNT_LABELS:
            valor = contagens.get(chave)
            topo.addChild(QTreeWidgetItem([f"{rotulo}: {'—' if valor is None else valor}"]))
        self.tree.addTopLevelItem(topo)

        for chave, rotulo in SET_LABELS:
            itens = objetos.get(chave, []) or []
            topo = QTreeWidgetItem([f"{rotulo} ({len(itens)})"])
            for item in itens[:PREVIEW_LIMIT]:
                extra = item.get("manufacturer") or item.get("site") or item.get("tenant") or ""
                texto = f"{item.get('id')}  {item.get('label', '')}"
                if extra:
                    texto += f"   [{extra}]"
                topo.addChild(QTreeWidgetItem([texto]))
            if len(itens) > PREVIEW_LIMIT:
                topo.addChild(
                    QTreeWidgetItem([f"... e mais {len(itens) - PREVIEW_LIMIT} (veja no NetBox)"])
                )
            self.tree.addTopLevelItem(topo)

        campos = snapshot.get("custom_fields", []) or []
        topo = QTreeWidgetItem([f"Custom fields ({len(campos)})"])
        for campo in campos:
            tipos = ", ".join(campo.get("object_types") or []) or "—"
            marca = " · obrigatório" if campo.get("required") else ""
            topo.addChild(
                QTreeWidgetItem(
                    [f"{campo.get('name')} ({campo.get('type')}{marca}) → {tipos}"]
                )
            )
        self.tree.addTopLevelItem(topo)

        if not self._tree_open:
            # Ha o que ver: sinaliza sem forcar a abertura.
            self.disclosure.setText("Mostrar detalhes técnicos")

    def clear_snapshot(self) -> None:
        self._snapshot = None
        for valor in self.connection_values.values():
            valor.setText("—")
        self.connection_values["server"].setText(NETBOX_URL)
        self.connection_badge.set_state("Desconectado", "neutral")
        self.tree.clear()
        self.tree_search.clear()
        self.schema_button.setEnabled(False)
        self.refresh_button.setEnabled(False)

    def set_token_state(self, saved: bool, protection: str) -> None:
        self.forget_button.setVisible(saved)
        self.schema_button.setEnabled(self._snapshot is not None)
        if saved:
            self.token_state.setText(
                f"Token guardado nesta máquina ({protection}). O login é automático."
            )
            self.token_path_label.setText(str(credentials.token_path()))
            self.token_path_label.show()
            return
        self.token_state.setText("Nenhum token guardado nesta máquina.")
        self.token_path_label.hide()

    def set_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)
        self.refresh_button.setText("Atualizando..." if busy else "Atualizar ambiente")

    def apply_theme(self, palette) -> None:
        self.disclosure.setIcon(
            icons.icon("chevron_down" if self._tree_open else "chevron_right", palette.text_muted, 14)
        )
        self.refresh_button.setIcon(icons.icon("refresh", palette.text_muted, 16))
        self.schema_button.setIcon(icons.icon("download", palette.text_muted, 16))
        self.forget_button.setIcon(icons.icon("trash", palette.danger, 16))
