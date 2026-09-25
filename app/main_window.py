"""Janela principal do app de documentacao de cameras no NetBox.

Fatia 0: conectar com token e **descobrir o ambiente** (o que ja existe na
instancia e quais campos o NetBox aceita). A importacao de devices entra na
proxima etapa, em cima da mesma sessao.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import credentials, provision, theme  # noqa: E402
from app.config import NETBOX_URL  # noqa: E402
from app.import_dialog import ImportDialog  # noqa: E402
from app.loading import Spinner  # noqa: E402
from app.paths import resource_path, writable_base  # noqa: E402
from app.session import SessionWorker  # noqa: E402
from app.spreadsheet import FIXED_COLUMNS, write_example_template  # noqa: E402
from app.toast import ToastManager  # noqa: E402
from app.update_check import UpdateCheckWorker  # noqa: E402
from app.updater import Release  # noqa: E402

# Indices das telas: login -> carregando -> ambiente.
LOGIN_PAGE, LOADING_PAGE, ENV_PAGE = 0, 1, 2

TOKEN_PROMPT = "Token de acesso"
LOGIN_BANNER_HEIGHT = 190
ENV_BANNER_HEIGHT = 76
SNAPSHOT_FILENAME = "netbox_schema.json"
TEMPLATE_FILENAME = "modelo_cameras_netbox.xlsx"
# Depois disso a tela de carregamento sugere que a rede pode estar ruim.
SLOW_HINT_MS = 6000

# Rotulos dos conjuntos descobertos (ordem de exibicao).
SET_LABELS: tuple[tuple[str, str], ...] = (
    ("sites", "Sites"),
    ("locations", "Locations"),
    ("regions", "Regions"),
    ("site_groups", "Grupos de site"),
    ("racks", "Racks"),
    ("device_roles", "Papeis de device (roles)"),
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

# Endpoints cujo OPTIONS revela o que o token pode fazer (ler/criar/editar).
ENDPOINT_LABELS: tuple[tuple[str, str], ...] = (
    ("device", "Devices"),
    ("device_type", "Device types"),
    ("manufacturer", "Fabricantes"),
    ("device_role", "Papeis (roles)"),
    ("site", "Sites"),
    ("location", "Locations"),
    ("tenant", "Tenants"),
    ("interface", "Interfaces"),
    ("ip_address", "IP addresses"),
    ("tag", "Tags"),
)

# Instancias reais tem milhares de sites: mostrar todos na arvore travaria a tela.
PREVIEW_LIMIT = 100


def brand_pixmap(name: str, height: int) -> QPixmap:
    """Carrega um asset da marca (app/assets/) escalado pela altura."""
    pixmap = QPixmap(str(resource_path("app", "assets", name)))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)


def snapshot_user(snapshot: dict) -> str:
    """Dono do token ("usuario", marcado se for superusuario).

    As permissoes sao do dono do token, nao de quem esta logado na interface - por
    isso vale mostrar isso na tela desde o primeiro momento.
    """
    usuario = snapshot.get("current_user") or {}
    nome = usuario.get("username")
    if not nome:
        return ""
    return f"{nome} (superusuario)" if usuario.get("is_superuser") else nome


def snapshot_summary(snapshot: dict) -> str:
    """Linha de resumo com versao e contagens principais."""
    version = provision.netbox_version(snapshot) or "?"
    api_version = snapshot.get("api_version") or "?"
    counts = snapshot.get("counts", {})
    parts = [f"NetBox {version}", f"API {api_version}"]
    for key, label in COUNT_LABELS[:3]:
        value = counts.get(key)
        parts.append(f"{label}: {'-' if value is None else value}")
    if snapshot.get("token_scheme"):
        parts.append(f"auth: {snapshot['token_scheme']}")
    usuario = snapshot_user(snapshot)
    if usuario:
        parts.append(f"token de: {usuario}")
    return "  |  ".join(parts)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Importador de Cameras - NetBox")
        self.resize(1240, 900)

        self._snapshot: dict | None = None
        self._connected = False
        self._saved_token = credentials.load_token()
        self._pending_token = ""

        self._slow_hint_timer = QTimer(self)
        self._slow_hint_timer.setSingleShot(True)
        self._slow_hint_timer.timeout.connect(self._show_slow_hint)

        self._build_ui()
        self._start_session_thread()
        self._start_update_check_thread()

        # Com token guardado, nem aparece a tela de login: vai direto ao carregamento.
        self._refresh_saved_token_ui()
        if self._saved_token:
            self._start_login()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._stack.addWidget(self._build_login_page())
        self._stack.addWidget(self._build_loading_page())
        self._stack.addWidget(self._build_env_page())
        self._toast = ToastManager(self)
        self._toast.set_top_offset(LOGIN_BANNER_HEIGHT + 14)

    def _build_login_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_brand_banner(LOGIN_BANNER_HEIGHT, logo_height=96))

        body = QVBoxLayout()
        body.setContentsMargins(24, 28, 24, 20)
        body.addStretch(1)

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(480)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 30, 32, 26)
        card_layout.setSpacing(10)

        title = QLabel("Entrar no NetBox")
        title.setObjectName("cardTitle")
        subtitle = QLabel(
            "Cole aqui o seu token de acesso. Ele fica guardado com segurança "
            "neste computador, só para você."
        )
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        servidor = QLabel(f"Servidor: {NETBOX_URL}")
        servidor.setObjectName("serverLabel")
        card_layout.addWidget(servidor)
        card_layout.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("Cole o token aqui")
        self.token_edit.returnPressed.connect(self._on_connect_clicked)
        form.addRow(self._field_label(TOKEN_PROMPT), self.token_edit)
        card_layout.addLayout(form)

        token_help = QLabel(
            "Onde achar: no NetBox, clique no seu nome (canto superior direito) "
            "→ Profile → API Tokens → Create."
        )
        token_help.setWordWrap(True)
        token_help.setStyleSheet(f"color: {theme.TEXT_FAINT}; font-size: 11px;")
        card_layout.addWidget(token_help)

        self.saved_note = QLabel("")
        self.saved_note.setObjectName("savedToken")
        self.saved_note.setWordWrap(True)
        self.saved_note.hide()
        card_layout.addWidget(self.saved_note)

        self.forget_button = QPushButton("Esquecer token guardado")
        self.forget_button.setObjectName("flatButton")
        self.forget_button.clicked.connect(self._on_forget_token)
        self.forget_button.hide()
        card_layout.addWidget(self.forget_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.login_error_label = QLabel("")
        self.login_error_label.setWordWrap(True)
        self.login_error_label.setStyleSheet(
            f"color: {theme.ERROR}; font-weight: 600;"
        )
        self.login_error_label.hide()
        card_layout.addWidget(self.login_error_label)

        card_layout.addSpacing(4)
        self.login_button = QPushButton("Entrar")
        self.login_button.setObjectName("primaryButton")
        self.login_button.setMinimumHeight(40)
        self.login_button.clicked.connect(self._on_connect_clicked)
        card_layout.addWidget(self.login_button)

        body.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        body.addStretch(1)

        footer = QLabel("L&K Tecnologia  -  Documentacao de cameras no NetBox")
        footer.setObjectName("loginFooter")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(footer)

        outer.addLayout(body, stretch=1)
        return page

    def _build_loading_page(self) -> QWidget:
        """Tela de carregamento: fundo da marca + spinner enquanto conecta."""
        page = QWidget()
        page.setObjectName("loadingPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)

        self.spinner = Spinner(self, diameter=72, stroke=5)
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(22)

        self.loading_title = QLabel("Conectando ao NetBox")
        self.loading_title.setObjectName("loadingTitle")
        self.loading_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_title)

        servidor = QLabel(NETBOX_URL)
        servidor.setObjectName("loadingServer")
        servidor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(servidor)

        layout.addSpacing(6)
        self.loading_hint = QLabel("")
        self.loading_hint.setObjectName("loadingHint")
        self.loading_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_hint)

        layout.addStretch(1)
        return page

    def _build_brand_banner(self, height: int, logo_height: int) -> QFrame:
        banner = QFrame()
        banner.setObjectName("brandBanner")
        banner.setFixedHeight(height)
        row = QHBoxLayout(banner)
        row.setContentsMargins(34, 16, 34, 16)
        row.setSpacing(18)

        logo = QLabel()
        pixmap = brand_pixmap("lk_white.png", logo_height)
        if not pixmap.isNull():
            logo.setPixmap(pixmap)
        row.addWidget(logo)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title = QLabel("Importador de Cameras")
        title.setObjectName("brandTitle")
        subtitle = QLabel("Documentacao no NetBox")
        subtitle.setObjectName("brandSubtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        row.addLayout(text_col)
        row.addStretch(1)
        return banner

    def _build_env_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        banner = QFrame()
        banner.setObjectName("brandBanner")
        banner.setFixedHeight(ENV_BANNER_HEIGHT)
        bar = QHBoxLayout(banner)
        bar.setContentsMargins(26, 12, 26, 12)
        bar.setSpacing(14)

        logo = QLabel()
        pixmap = brand_pixmap("lk_white.png", 46)
        if not pixmap.isNull():
            logo.setPixmap(pixmap)
        bar.addWidget(logo)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title = QLabel("Importador de Cameras")
        title.setObjectName("brandTitle")
        subtitle = QLabel("Documentacao no NetBox")
        subtitle.setObjectName("brandSubtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        bar.addLayout(text_col)
        bar.addStretch(1)

        self.session_label = QLabel("")
        self.session_label.setObjectName("brandSession")
        bar.addWidget(self.session_label)

        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.setObjectName("bannerButton")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        bar.addWidget(self.refresh_button)

        self.logout_button = QPushButton("Sair")
        self.logout_button.setObjectName("bannerButton")
        self.logout_button.clicked.connect(self._on_logout_clicked)
        bar.addWidget(self.logout_button)

        outer.addWidget(banner)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.summary_label = QLabel("Consultando o ambiente...")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.advanced_button = QToolButton()
        self.advanced_button.setCheckable(True)
        self.advanced_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_button.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_button.setText("Detalhes técnicos (avançado)")
        self.advanced_button.toggled.connect(self._on_advanced_toggled)
        layout.addWidget(self.advanced_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.env_box = QGroupBox("Ambiente NetBox (o que já existe)")
        self.env_box.setVisible(False)
        env_layout = QVBoxLayout(self.env_box)

        self.technical_label = QLabel("")
        self.technical_label.setWordWrap(True)
        self.technical_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        env_layout.addWidget(self.technical_label)

        self.env_tree = QTreeWidget()
        self.env_tree.setHeaderHidden(True)
        self.env_tree.setAlternatingRowColors(True)
        self.env_tree.setUniformRowHeights(True)
        env_layout.addWidget(self.env_tree)

        self.save_button = QPushButton("Salvar schema (JSON)")
        self.save_button.clicked.connect(self._on_save_clicked)
        env_layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.env_box, stretch=1)

        template_box = QGroupBox("Passo 1 · Baixe a planilha modelo")
        template_layout = QHBoxLayout(template_box)

        self.sites_note = QLabel("")
        self.sites_note.setWordWrap(True)
        self.sites_note.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        template_layout.addWidget(self.sites_note, stretch=1)

        self.template_button = QPushButton("Baixar planilha modelo")
        self.template_button.setObjectName("primaryButton")
        self.template_button.setEnabled(False)
        self.template_button.clicked.connect(self._on_download_template)
        template_layout.addWidget(self.template_button)

        layout.addWidget(template_box)

        import_box = QGroupBox("Passo 2 · Importe a planilha preenchida")
        import_layout = QHBoxLayout(import_box)

        import_note = QLabel(
            "Antes de enviar, o app mostra exatamente o que vai ser criado."
        )
        import_note.setWordWrap(True)
        import_note.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        import_layout.addWidget(import_note, stretch=1)

        self.open_import_button = QPushButton("Importar planilha")
        self.open_import_button.setEnabled(False)
        self.open_import_button.clicked.connect(self._on_open_import)
        import_layout.addWidget(self.open_import_button)

        layout.addWidget(import_box)

        self.errors_label = QLabel("")
        self.errors_label.setWordWrap(True)
        self.errors_label.setStyleSheet(f"color: {theme.WARNING};")
        self.errors_label.hide()
        layout.addWidget(self.errors_label)

        outer.addWidget(content, stretch=1)
        return page

    # ------------------------------------------------------------ sessao thread
    def _start_session_thread(self) -> None:
        self._session_thread = QThread(self)
        self._session = SessionWorker()
        self._session.moveToThread(self._session_thread)
        self._session.connected.connect(self._on_connected)
        self._session.connect_failed.connect(self._on_connect_failed)
        self._session.discovered.connect(self._on_discovered)
        self._session.discover_failed.connect(self._on_discover_failed)
        self._session.snapshot_saved.connect(self._on_snapshot_saved)
        self._session.snapshot_failed.connect(self._on_snapshot_failed)
        self._session.disconnected.connect(self._on_disconnected)
        self._session.log.connect(self._notify_log)
        self._session_thread.start()

    def _start_update_check_thread(self) -> None:
        self._update_thread = QThread(self)
        self._update = UpdateCheckWorker()
        self._update.moveToThread(self._update_thread)
        self._update.available.connect(self._on_update_available)

        self._update_thread.started.connect(self._update.request_check.emit)
        self._update_thread.start()

    # ------------------------------------------------------ acoes do usuario
    def _on_connect_clicked(self) -> None:
        token = self.token_edit.text().strip()
        if not token:
            self._show_login_error("Cole o token da API.")
            return
        self._hide_login_error()
        self._pending_token = token
        self._start_login()

    def _start_login(self) -> None:
        """Manda conectar (com o token digitado ou o guardado) e vai ao carregamento."""
        token = self._pending_token or self._saved_token
        if not token:
            self._go_login()
            return
        self._go_loading()
        # Com certificado autoassinado o cliente tenta de novo sozinho (ver session.py).
        self._session.request_connect.emit(NETBOX_URL, token, True)

    def _on_forget_token(self) -> None:
        credentials.clear_token()
        self._saved_token = ""
        self._refresh_saved_token_ui()
        self.token_edit.clear()
        self._notify("O token guardado foi esquecido.", "info")

    def _refresh_saved_token_ui(self) -> None:
        tem = bool(self._saved_token)
        self.saved_note.setText(
            "Ha um token guardado nesta maquina (cifrado pelo Windows)."
        )
        self.saved_note.setVisible(tem)
        self.forget_button.setVisible(tem)

    def _save_pending_token(self) -> None:
        """Guarda o token digitado, para nao pedir de novo na proxima abertura."""
        token = self._pending_token
        self._pending_token = ""
        if not token or token == self._saved_token:
            return
        try:
            credentials.save_token(token)
        except credentials.CredentialError as exc:
            self._notify(f"Conectado, mas nao consegui guardar o token: {exc}", "warning")
            return
        self._saved_token = token
        self._refresh_saved_token_ui()
        self._notify("Token guardado nesta maquina (cifrado pelo Windows).", "info")

    def _on_refresh_clicked(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Atualizando...")
        self._session.request_discover.emit()

    def _on_save_clicked(self) -> None:
        suggested = writable_base() / "reports" / SNAPSHOT_FILENAME
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar schema do NetBox",
            str(suggested),
            "JSON (*.json)",
        )
        if not path:
            return
        self._session.request_save_snapshot.emit(path)

    def _on_logout_clicked(self) -> None:
        self._session.request_logout.emit()

    def _on_advanced_toggled(self, checked: bool) -> None:
        arrow = Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        self.advanced_button.setArrowType(arrow)
        self.env_box.setVisible(checked)

    # ------------------------------------------------------- callbacks da sessao
    def _on_connected(self, snapshot: dict) -> None:
        self._connected = True
        self._stop_loading()
        self.token_edit.clear()
        self._save_pending_token()
        version = provision.netbox_version(snapshot) or "?"
        usuario = snapshot_user(snapshot)
        self.session_label.setText(
            f"Conectado - NetBox {version}" + (f" | {usuario}" if usuario else "")
        )
        self._go_env()
        self._populate(snapshot)
        self._notify(f"Conectado ao NetBox {version}.", "success")

    def _on_connect_failed(self, message: str) -> None:
        self._connected = False
        self._stop_loading()
        self._pending_token = ""
        self._go_login()
        self._show_login_error(f"Falha na conexao: {message}")
        if self._saved_token:
            # O token guardado nao serviu: deixa claro que basta colar outro.
            self.saved_note.setText(
                "O token guardado nesta maquina nao funcionou. Cole um token novo abaixo "
                "- ele substitui o antigo."
            )
            self.saved_note.show()
        self._notify(f"Falha na conexao: {message}", "error")

    def _on_discovered(self, snapshot: dict) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Atualizar")
        self._populate(snapshot)
        self._notify("Ambiente atualizado.", "success")

    def _on_discover_failed(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Atualizar")
        self._notify(message, "error")

    def _on_snapshot_saved(self, path: str) -> None:
        self._notify(f"Schema salvo em: {path}", "success")

    def _on_snapshot_failed(self, message: str) -> None:
        self._notify(message, "error")

    def _on_disconnected(self) -> None:
        self._connected = False
        self._snapshot = None
        self.session_label.setText("")
        self.env_tree.clear()
        self.technical_label.setText("")
        self.sites_note.setText("")
        self.template_button.setEnabled(False)
        self.open_import_button.setEnabled(False)
        self.summary_label.setText("Consultando o ambiente...")
        self._go_login()
        self._notify("Sessao encerrada.", "info")

    def _notify_log(self, message: str) -> None:
        print(f"[netbox] {message}")

    # ------------------------------------------------------------- populacao
    def _populate(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        objects = snapshot.get("objects", {})
        n_sites = len(objects.get("sites", []))
        n_roles = len(objects.get("device_roles", []))
        n_types = len(objects.get("device_types", []))
        errors = snapshot.get("errors", [])
        # "Tudo certo" so vale quando o ambiente foi lido por inteiro.
        abertura = "Conectado." if errors else "Tudo certo!"
        self.summary_label.setText(
            f"{abertura} Encontrei {n_sites} sites, {n_roles} papéis e "
            f"{n_types} tipos de device no NetBox."
        )
        self.technical_label.setText(snapshot_summary(snapshot))
        self._populate_tree(snapshot)
        self._update_sites_note()
        self.open_import_button.setEnabled(True)

        if errors:
            # Resumo curto por conjunto: o texto completo de cada erro ja fica no
            # JSON do schema (e um corpo HTML nunca deve estourar a tela).
            conjuntos = []
            for erro in errors:
                nome = str(erro).split(":", 1)[0].strip() or "?"
                if nome not in conjuntos:
                    conjuntos.append(nome)
            self.errors_label.setText(
                f"Não consegui ler algumas partes do NetBox "
                f"({', '.join(conjuntos)}). Isso não impede a importação. "
                "Veja os detalhes em Detalhes técnicos."
            )
            self.errors_label.show()
        else:
            self.errors_label.hide()

    def _populate_tree(self, snapshot: dict) -> None:
        self.env_tree.clear()

        # Permissoes e contagens primeiro: e o que importa antes de mapear a planilha.
        capabilities = snapshot.get("capabilities", {})
        if capabilities:
            top = QTreeWidgetItem(["Permissoes do token (acoes do OPTIONS)"])
            for key, label in ENDPOINT_LABELS:
                if key not in capabilities:
                    continue
                actions = capabilities.get(key) or []
                detail = ", ".join(actions) if actions else "SEM PERMISSAO (nenhuma acao)"
                top.addChild(QTreeWidgetItem([f"{label}: {detail}"]))
            self.env_tree.addTopLevelItem(top)

        counts = snapshot.get("counts", {})
        top = QTreeWidgetItem(["Contagens"])
        for key, label in COUNT_LABELS:
            value = counts.get(key)
            top.addChild(QTreeWidgetItem([f"{label}: {'-' if value is None else value}"]))
        self.env_tree.addTopLevelItem(top)

        objects = snapshot.get("objects", {})

        for key, label in SET_LABELS:
            items = objects.get(key, [])
            top = QTreeWidgetItem([f"{label} ({len(items)})"])
            for item in items[:PREVIEW_LIMIT]:
                extra = item.get("manufacturer") or item.get("site") or item.get("tenant") or ""
                text = f"{item.get('id')}  {item.get('label', '')}"
                if extra:
                    text += f"   [{extra}]"
                top.addChild(QTreeWidgetItem([text]))
            if len(items) > PREVIEW_LIMIT:
                top.addChild(
                    QTreeWidgetItem([f"... e mais {len(items) - PREVIEW_LIMIT} (veja no NetBox)"])
                )
            self.env_tree.addTopLevelItem(top)

        custom_fields = snapshot.get("custom_fields", [])
        top = QTreeWidgetItem([f"Custom fields ({len(custom_fields)})"])
        for field in custom_fields:
            types = ", ".join(field.get("object_types") or []) or "-"
            top.addChild(
                QTreeWidgetItem([f"{field.get('name')} ({field.get('type')}) -> {types}"])
            )
        self.env_tree.addTopLevelItem(top)

    def _update_sites_note(self) -> None:
        """Diz o que vai nas listas suspensas do modelo (todos os sites)."""
        snapshot = self._snapshot
        if snapshot is None:
            self.sites_note.setText("")
            self.template_button.setEnabled(False)
            return
        sites = provision.site_names(snapshot)
        self.sites_note.setText(
            "O arquivo já vem com as listas de Site e Papel prontas — é só escolher. "
            "Preencha uma linha por câmera."
        )
        self.template_button.setEnabled(bool(sites))

    def _on_download_template(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        sites = provision.site_names(snapshot)
        if not sites:
            self._notify("Nao ha sites no NetBox para montar a lista.", "warning")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar modelo de planilha",
            str(Path.home() / TEMPLATE_FILENAME),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        roles = provision.reference_labels(snapshot, "device_roles")
        try:
            write_example_template(Path(path), sites=sites, roles=roles)
        except Exception as exc:
            self._notify(f"Nao foi possivel salvar o modelo: {exc}", "error")
            return
        self._notify(
            f"Modelo salvo com {len(FIXED_COLUMNS)} colunas do modelo, {len(sites)} sites e "
            f"{len(roles)} papeis nas listas suspensas. Preencha uma linha por device.",
            "success",
        )

    def _on_open_import(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        dialog = ImportDialog(self, snapshot, self._session)
        dialog.exec()
        # A importacao pode ter criado referencias: recarrega a tela.
        self._populate(snapshot)

    # ------------------------------------------------------------- estados
    def _go_login(self) -> None:
        self._stack.setCurrentIndex(LOGIN_PAGE)
        self._toast.set_top_offset(LOGIN_BANNER_HEIGHT + 14)
        self.token_edit.setEnabled(True)
        self._refresh_saved_token_ui()

    def _go_loading(self) -> None:
        self._stack.setCurrentIndex(LOADING_PAGE)
        self._toast.set_top_offset(16)
        self.loading_hint.setText("")
        self.spinner.start()
        self._slow_hint_timer.start(SLOW_HINT_MS)

    def _stop_loading(self) -> None:
        self.spinner.stop()
        self._slow_hint_timer.stop()

    def _show_slow_hint(self) -> None:
        self.loading_hint.setText("Ainda tentando... confira a rede.")

    def _go_env(self) -> None:
        self._stack.setCurrentIndex(ENV_PAGE)
        self._toast.set_top_offset(ENV_BANNER_HEIGHT + 14)

    def _show_login_error(self, message: str) -> None:
        self.login_error_label.setText(message)
        self.login_error_label.show()

    def _hide_login_error(self) -> None:
        self.login_error_label.hide()
        self.login_error_label.setText("")

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _notify(self, message: str, kind: str = "info", duration_ms: int | None = None) -> None:
        self._toast.notify(message, kind, duration_ms)

    def _on_update_available(self, release: Release) -> None:
        self._notify(
            f"Nova versao {release.versao} disponivel. "
            f"Baixe em: {release.page_url}",
            "info",
            9000,
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self._update_thread.quit()
        # O timeout do requests limita a conexao e a leitura separadamente, entao
        # uma rede ruim pode segurar a thread por quase o dobro do TIMEOUT_S.
        self._update_thread.wait(10000)
        self._session_thread.quit()
        self._session_thread.wait(5000)
        super().closeEvent(event)
