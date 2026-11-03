"""Janela principal: liga a sessao do NetBox a interface em paginas.

Principio preservado do projeto original: **a interface pede, o worker executa.**
Nenhuma tela fala com a rede. O que mudou e a organizacao: a janela deixou de ser
uma tela unica com grupos empilhados e passou a ser uma casca (`app/shell.py`) com
paginas independentes. Esta classe fica com o que e dela de fato - o estado da
sessao, o token e o roteamento entre telas.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QStackedWidget

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    credentials,
    preferences,
    provision,
    reports,
    theme,
    version as version_mod,  # noqa: E402
)
from app.config import NETBOX_URL  # noqa: E402
from app.history import list_runs  # noqa: E402
from app.import_dialog import ImportDialog  # noqa: E402
from app.link_dialog import LinkImportDialog  # noqa: E402
from app.link_sheet import write_example_template as write_link_template  # noqa: E402
from app.pages.loading_page import LoadingPage  # noqa: E402
from app.pages.login_page import LoginPage  # noqa: E402
from app.paths import writable_base  # noqa: E402
from app.session import SessionWorker  # noqa: E402
from app.shell import SETTINGS_PAGE, Shell  # noqa: E402
from app.spreadsheet import FIXED_COLUMNS, write_example_template  # noqa: E402
from app.toast import ToastItem, ToastManager  # noqa: E402
from app.update_check import UpdateCheckWorker  # noqa: E402
from app.update_download import UpdateDownloadWorker  # noqa: E402
from app.updater import Release  # noqa: E402

# Indices das telas principais: login -> carregando -> casca com paginas.
LOGIN_PAGE, LOADING_PAGE, ENV_PAGE = 0, 1, 2

SNAPSHOT_FILENAME = "netbox_schema.json"
TEMPLATE_FILENAME = "modelo_cameras_netbox.xlsx"
TEMPLATE_LINKS_FILENAME = "modelo_links_netbox.xlsx"
# Depois disso a tela de carregamento sugere que a rede pode estar ruim.
SLOW_HINT_MS = 6000
TOAST_TOP_LOGIN = 16
TOAST_TOP_SHELL = 88


def snapshot_user(snapshot: dict) -> str:
    """Dono do token ("usuario", marcado se for superusuario)."""
    usuario = snapshot.get("current_user") or {}
    nome = usuario.get("username")
    if not nome:
        return ""
    return f"{nome} (superusuário)" if usuario.get("is_superuser") else nome


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Importador NetBox")
        self.resize(1280, 880)
        self.setMinimumSize(1040, 700)

        self._snapshot: dict | None = None
        self._connected = False
        self._saved_token = credentials.load_token()
        self._pending_token = ""
        # Referencia o toast de download enquanto ele existir: os sinais do worker
        # podem chegar depois de o usuario fechar o aviso.
        self._download_item: ToastItem | None = None
        self._shutting_down = False
        # Inventario de devices: carregado sob demanda pelo fluxo de links.
        self._inventory_loading = False
        self._pending_inventory_action = None
        self._theme_mode = preferences.theme_mode()

        self._slow_hint_timer = QTimer(self)
        self._slow_hint_timer.setSingleShot(True)
        self._slow_hint_timer.timeout.connect(self._show_slow_hint)

        self._build_ui()
        self._start_session_thread()
        self._start_update_check_thread()
        self._start_download_thread()

        # Com token guardado, nem aparece a tela de login: vai direto ao carregamento.
        self._refresh_saved_token_ui()
        if self._saved_token:
            self._start_login()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._login_page = LoginPage()
        self._loading_page = LoadingPage()
        self._shell = Shell()
        self._stack.addWidget(self._login_page)
        self._stack.addWidget(self._loading_page)
        self._stack.addWidget(self._shell)

        # Superficie de compatibilidade: os testes e as ferramentas de captura
        # acessam estes widgets pelo nome historico da janela.
        self.token_edit = self._login_page.token_edit
        self.login_error_label = self._login_page.login_error_label
        self.saved_note = self._login_page.saved_note
        self.forget_button = self._login_page.forget_button
        self.login_button = self._login_page.login_button
        self.spinner = self._loading_page.spinner
        self.loading_hint = self._loading_page.hint
        self.loading_title = self._loading_page.title

        self._toast = ToastManager(self)
        self._toast.set_top_offset(TOAST_TOP_LOGIN)

        self._connect_ui()

    def _connect_ui(self) -> None:
        login = self._login_page
        login.submit.connect(self._on_token_submitted)
        login.forget_button.clicked.connect(self._on_forget_token)

        shell = self._shell
        shell.refresh_clicked.connect(self._on_refresh_clicked)
        shell.theme_clicked.connect(self._on_theme_clicked)
        shell.user_clicked.connect(lambda: shell.set_page(SETTINGS_PAGE))
        shell.logout_clicked.connect(self._on_logout_clicked)
        shell.set_version(version_mod.__version__)

        shell.dashboard.download_template.connect(self._on_download_template)
        shell.dashboard.open_import.connect(self._on_open_import)
        shell.dashboard.download_link_template.connect(self._on_download_link_template)
        shell.dashboard.open_link_import.connect(self._on_open_link_import)
        shell.dashboard.save_schema.connect(self._on_save_clicked)

        shell.import_page.primary_clicked.connect(self._on_open_import)
        shell.import_page.secondary_clicked.connect(self._on_download_template)
        shell.links_page.primary_clicked.connect(self._on_open_link_import)
        shell.links_page.secondary_clicked.connect(self._on_download_link_template)

        shell.history_page.open_folder.connect(self._on_open_reports_folder)
        shell.history_page.open_report.connect(self._on_open_report)

        shell.settings_page.save_schema_clicked.connect(self._on_save_clicked)
        shell.settings_page.forget_token_clicked.connect(self._on_forget_token)
        shell.settings_page.theme_changed.connect(self._on_theme_selected)
        shell.settings_page.set_theme_mode(self._theme_mode)

        self._shell.set_ready(False)

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
        self._session.discovery_progress.connect(self._on_discovery_progress)
        self._session.device_inventory_ready.connect(self._on_inventory_ready)
        self._session.log.connect(self._notify_log)
        self._session_thread.start()

    def _start_update_check_thread(self) -> None:
        self._update_thread = QThread(self)
        self._update = UpdateCheckWorker()
        self._update.moveToThread(self._update_thread)
        self._update.available.connect(self._on_update_available)

        self._update_thread.started.connect(self._update.request_check.emit)
        self._update_thread.start()

    def _start_download_thread(self) -> None:
        self._download_thread = QThread(self)
        self._download = UpdateDownloadWorker()
        self._download.moveToThread(self._download_thread)
        self._download.progress.connect(self._on_download_progress)
        self._download.finished.connect(self._on_download_finished)
        self._download.failed.connect(self._on_download_failed)

        self._download_thread.start()

    # ------------------------------------------------------ acoes do usuario
    def _on_token_submitted(self, token: str) -> None:
        self._hide_login_error()
        self._pending_token = token
        self._start_login()

    def _on_connect_clicked(self) -> None:
        token = self.token_edit.text().strip()
        if not token:
            self._show_login_error("Cole o token da API.")
            return
        self._on_token_submitted(token)

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
        protection = credentials.protection_label()
        self._login_page.set_saved_token(tem, protection)
        self._shell.settings_page.set_token_state(tem, protection)

    def _save_pending_token(self) -> None:
        """Guarda o token digitado, para nao pedir de novo na proxima abertura."""
        token = self._pending_token
        self._pending_token = ""
        if not token or token == self._saved_token:
            return
        try:
            credentials.save_token(token)
        except credentials.CredentialError as exc:
            self._notify(f"Conectado, mas não consegui guardar o token: {exc}", "warning")
            return
        self._saved_token = token
        self._refresh_saved_token_ui()
        self._notify(
            f"Token guardado nesta máquina ({credentials.protection_label()}).", "info"
        )

    def _on_refresh_clicked(self) -> None:
        self._shell.header.set_refreshing(True)
        self._shell.settings_page.set_busy(True)
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

    def _on_theme_clicked(self) -> None:
        modo = "light" if theme.palette().is_dark else "dark"
        self._on_theme_selected(modo)

    def _on_theme_selected(self, modo: str) -> None:
        self._theme_mode = modo
        preferences.set_theme_mode(modo)
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, app.font().family(), modo)
        self._shell.settings_page.set_theme_mode(modo)
        self._toast.set_top_offset(
            TOAST_TOP_SHELL if self._stack.currentIndex() == ENV_PAGE else TOAST_TOP_LOGIN
        )

    def _on_open_reports_folder(self) -> None:
        pasta = reports.reports_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta)))

    def _on_open_report(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ------------------------------------------------------- callbacks da sessao
    def _on_connected(self, snapshot: dict) -> None:
        self._connected = True
        self._inventory_loading = False
        self._pending_inventory_action = None
        self._stop_loading()
        self.token_edit.clear()
        self._save_pending_token()

        versao = provision.netbox_version(snapshot) or "?"
        usuario = snapshot_user(snapshot)
        tls = snapshot.get("tls_verified")
        self._shell.set_connected(True, versao, True if tls is None else bool(tls))
        self._shell.set_user(usuario)
        self._go_env()
        self._populate(snapshot)
        self._notify(f"Conectado ao NetBox {versao}.", "success")

    def _on_connect_failed(self, message: str) -> None:
        self._connected = False
        self._shell.set_connected(False)
        self._stop_loading()
        self._pending_token = ""
        self._go_login()
        self._show_login_error(f"Falha na conexão: {message}")
        if self._saved_token:
            # O token guardado nao serviu: deixa claro que basta colar outro.
            self._login_page.set_saved_token_invalid()
        self._notify(f"Falha na conexão: {message}", "error")

    def _on_discovered(self, snapshot: dict) -> None:
        self._shell.header.set_refreshing(False)
        self._shell.settings_page.set_busy(False)
        self._populate(snapshot)
        self._notify("Ambiente atualizado.", "success")

    def _on_discover_failed(self, message: str) -> None:
        self._shell.header.set_refreshing(False)
        self._shell.settings_page.set_busy(False)
        self._notify(message, "error")

    def _on_snapshot_saved(self, path: str) -> None:
        self._notify(f"Schema salvo em: {path}", "success")

    def _on_snapshot_failed(self, message: str) -> None:
        self._notify(message, "error")

    def _on_disconnected(self) -> None:
        self._connected = False
        self._snapshot = None
        self._shell.set_ready(False)
        self._shell.set_connected(False)
        self._shell.set_user("")
        self._shell.settings_page.clear_snapshot()
        self._shell.history_page.set_runs([])
        self._inventory_loading = False
        self._pending_inventory_action = None
        self._shell.set_inventory_loading(False)
        self._go_login()
        self._notify("Sessão encerrada.", "info")

    def _notify_log(self, message: str) -> None:
        print(f"[netbox] {message}")

    # ------------------------------------------------------------- populacao
    def _populate(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        versao = provision.netbox_version(snapshot) or "?"
        tls = snapshot.get("tls_verified")
        self._shell.set_connected(True, versao, True if tls is None else bool(tls))
        self._shell.set_user(snapshot_user(snapshot))
        self._shell.dashboard.set_snapshot(snapshot)
        self._shell.settings_page.set_snapshot(snapshot)
        self._shell.history_page.load()
        self._shell.dashboard.set_activity(list_runs(limit=5))
        self._shell.set_ready(True)
        self._shell.settings_page.set_token_state(
            bool(self._saved_token), credentials.protection_label()
        )

    # --------------------------------------------------------------- modelos
    def _on_download_template(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        sites = provision.site_names(snapshot)
        if not sites:
            self._notify("Não há sites no NetBox para montar a lista.", "warning")
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
            self._notify(f"Não foi possível salvar o modelo: {exc}", "error")
            return
        self._notify(
            f"Modelo salvo com {len(FIXED_COLUMNS)} colunas, {len(sites)} sites e "
            f"{len(roles)} papéis nas listas suspensas.",
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
        self._shell.history_page.load()

    def _on_download_link_template(self) -> None:
        self._ensure_inventory(self._download_link_template_now)

    def _download_link_template_now(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        sites = provision.site_names(snapshot)
        if not sites:
            self._notify("Não há sites no NetBox para montar a lista.", "warning")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar modelo de links IP",
            str(Path.home() / TEMPLATE_LINKS_FILENAME),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        papeis = provision.reference_labels(snapshot, "prefix_roles")
        devices = provision.device_names(snapshot)
        try:
            write_link_template(
                Path(path),
                sites=sites,
                prefix_roles=papeis,
                devices=devices,
            )
        except Exception as exc:
            self._notify(f"Não foi possível salvar o modelo de links: {exc}", "error")
            return
        self._notify(
            f"Modelo de links salvo: {len(sites)} sites, {len(papeis)} papéis de prefixo "
            f"e {len(devices)} devices nas listas suspensas.",
            "success",
        )

    def _on_open_link_import(self) -> None:
        self._ensure_inventory(self._open_link_import_now)

    def _open_link_import_now(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        dialog = LinkImportDialog(self, snapshot, self._session)
        dialog.exec()
        # A importacao cria prefixos e IPs: recarrega as contagens da tela.
        self._populate(snapshot)
        self._shell.history_page.load()

    # ------------------------------------------------- inventario de devices
    def _ensure_inventory(self, callback) -> None:
        """Executa a ação quando o inventário estiver pronto (ou na hora, se já estiver)."""
        snapshot = self._snapshot
        if snapshot is None:
            return
        if snapshot.get("inventory_ready", True):
            callback()
            return

        self._pending_inventory_action = callback
        self._shell.set_inventory_loading(True)
        if not self._inventory_loading:
            self._notify(
                "Carregando o inventário de devices do NetBox antes de continuar…",
                "info",
                8000,
            )
        self._start_inventory_load()

    def _start_inventory_load(self) -> None:
        if self._inventory_loading or not self._connected:
            return
        self._inventory_loading = True
        self._shell.set_inventory_loading(True)
        self._session.request_device_inventory.emit()

    def _on_inventory_ready(self, snapshot: dict) -> None:
        if self._shutting_down or not self._connected:
            return
        self._inventory_loading = False
        self._snapshot = snapshot
        self._shell.set_inventory_loading(False)
        self._populate(snapshot)
        if snapshot.get("inventory_error"):
            self._notify(
                "Não foi possível ler o inventário de devices. A conferência de site "
                "será feita na importação.",
                "warning",
                9000,
            )

        callback = self._pending_inventory_action
        self._pending_inventory_action = None
        if callback is not None:
            callback()

    def _on_discovery_progress(self, texto: str) -> None:
        if self._stack.currentIndex() != LOADING_PAGE:
            return
        self._loading_page.set_stage(texto)
        # O aviso de rede ruim so faz sentido quando NADA esta avancando: cada
        # etapa concluida reinicia a contagem.
        self._slow_hint_timer.start(SLOW_HINT_MS)

    # ------------------------------------------------------------- estados
    def _go_login(self) -> None:
        self._stack.setCurrentIndex(LOGIN_PAGE)
        self._toast.set_top_offset(TOAST_TOP_LOGIN)
        self._login_page.set_busy(False)
        self._refresh_saved_token_ui()

    def _go_loading(self) -> None:
        self._stack.setCurrentIndex(LOADING_PAGE)
        self._toast.set_top_offset(TOAST_TOP_LOGIN)
        self._loading_page.reset()
        self._login_page.set_busy(True)
        self.spinner.start()
        self._slow_hint_timer.start(SLOW_HINT_MS)

    def _stop_loading(self) -> None:
        self.spinner.stop()
        self._slow_hint_timer.stop()
        self._login_page.set_busy(False)

    def _show_slow_hint(self) -> None:
        self.loading_hint.setText("Ainda tentando... confira a rede.")

    def _go_env(self) -> None:
        self._stack.setCurrentIndex(ENV_PAGE)
        self._toast.set_top_offset(TOAST_TOP_SHELL)
        self._shell.set_page(0, animate=True)

    def _show_login_error(self, message: str) -> None:
        self._login_page.show_error(message)

    def _hide_login_error(self) -> None:
        self._login_page.clear_error()

    def _notify(self, message: str, kind: str = "info", duration_ms: int | None = None) -> None:
        self._toast.notify(message, kind, duration_ms)

    # ---------------------------------------------------------- atualizacao
    def _on_update_available(self, release: Release) -> None:
        if release.setup_url is None:
            # Release sem instalador anexado: mantem o aviso antigo, so com o link.
            self._notify(
                f"Nova versão {release.versao} disponível. Baixe em: {release.page_url}",
                "info",
                9000,
            )
            return

        # duration_ms=0 de proposito: um aviso com botao nao pode sumir sozinho -
        # quem decide se baixa precisa de tempo, e o toast so liga o timer quando
        # a duracao e maior que zero.
        item = self._toast.notify(
            f"Nova versão {release.versao} disponível.",
            "info",
            duration_ms=0,
            action_label="Baixar e instalar",
            action_callback=lambda: self._on_download_clicked(release),
        )
        self._download_item = item
        item.dismissed.connect(self._on_download_item_dismissed)

    def _on_download_clicked(self, release: Release) -> None:
        item = self._download_item
        if item is None or release.setup_url is None:
            return
        item.set_action_enabled(False)
        item.set_action_label("Baixando...")
        self._download.request_download.emit(release.setup_url)

    def _on_download_item_dismissed(self, item: ToastItem) -> None:
        if self._download_item is item:
            self._download_item = None

    def _on_download_progress(self, baixados: int, total: int) -> None:
        if self._shutting_down:
            return
        item = self._download_item
        if item is None:
            return
        if total > 0:
            percentual = int(baixados * 100 / total)
            item.set_action_label(f"Baixando... {percentual}%")
        else:
            # Sem Content-Length: nao da para calcular percentual; o rotulo so
            # deixa claro que continua baixando.
            item.set_action_label("Baixando...")

    def _on_download_finished(self, _caminho: str) -> None:
        if self._shutting_down:
            return
        item = self._download_item
        if item is None:
            return
        item.set_action_label("Abrindo o instalador...")
        item.set_action_enabled(False)

    def _on_download_failed(self, message: str) -> None:
        if self._shutting_down:
            return
        item = self._download_item
        if item is not None:
            # Acao explicita do usuario NAO e silenciosa, diferente da checagem
            # automatica em update_check.py.
            item.close_now()
            self._download_item = None
        self._notify(f"Não foi possível baixar a atualização: {message}", "error")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._shutting_down = True
        # Pede o cancelamento do download antes de qualquer espera: evita que um
        # bloco recem-chegado continue escrevendo enquanto encerramos as threads.
        self._download.cancel()
        self._update_thread.quit()
        # O timeout do requests limita a conexao e a leitura separadamente, entao
        # uma rede ruim pode segurar a thread por quase o dobro do TIMEOUT_S.
        self._update_thread.wait(10000)
        self._download_thread.quit()
        self._download_thread.wait(10000)
        self._session_thread.quit()
        self._session_thread.wait(5000)
        super().closeEvent(event)
