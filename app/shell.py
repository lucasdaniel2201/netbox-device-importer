"""Casca da aplicacao: barra lateral, cabecalho e as paginas internas.

A janela principal conhece a sessao e o NetBox; a casca conhece apenas navegacao.
Trocar de pagina nao recria nada: as paginas vivem no `QStackedWidget` e mantem
estado (filtro de busca, tabela preenchida, arvore expandida).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from app import theme as theme_mod
from app.pages.dashboard_page import DashboardPage
from app.pages.history_page import HistoryPage
from app.pages.settings_page import SettingsPage
from app.pages.workflow_page import ImportPage, LinksPage
from app.ui.motion import fade_in
from app.ui.nav import PageHeader, Sidebar

DASHBOARD, IMPORT_PAGE, LINKS_PAGE, HISTORY_PAGE, SETTINGS_PAGE = 0, 1, 2, 3, 4

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "Visão geral", "Ambiente, ações e execuções recentes"),
    ("import", "Importação", "Importar câmeras e switches a partir de planilha"),
    ("link", "Links IP", "Blocos público/LAN e endereço do link por site"),
    ("history", "Histórico", "Relatórios das importações já executadas"),
    ("settings", "Configurações", "Conexão, token, aparência e ambiente técnico"),
)

PAGE_META: tuple[tuple[str, str], ...] = (
    ("Visão geral", "NETBOX / AMBIENTE"),
    ("Importação de câmeras", "NETBOX / IMPORTAÇÃO"),
    ("Links IP", "NETBOX / LINKS IP"),
    ("Histórico", "NETBOX / HISTÓRICO"),
    ("Configurações", "NETBOX / CONFIGURAÇÕES"),
)


class Shell(QWidget):
    """Layout mestre do app depois do login."""

    refresh_clicked = Signal()
    theme_clicked = Signal()
    user_clicked = Signal()
    logout_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppRoot")

        self.sidebar = Sidebar(list(NAV_ITEMS))
        self.header = PageHeader()
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageArea")

        self.dashboard = DashboardPage()
        self.import_page = ImportPage()
        self.links_page = LinksPage()
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage()
        for pagina in (
            self.dashboard,
            self.import_page,
            self.links_page,
            self.history_page,
            self.settings_page,
        ):
            self.stack.addWidget(pagina)
            pagina.setObjectName("PageArea")

        direita = QWidget()
        direita.setObjectName("AppRoot")
        coluna = QVBoxLayout(direita)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self.header)
        coluna.addWidget(self.stack, stretch=1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.sidebar)
        root.addWidget(direita, stretch=1)

        # navegacao
        self.sidebar.page_changed.connect(self.set_page)
        self.sidebar.logout_clicked.connect(self.logout_clicked.emit)

        # acoes globais do cabecalho
        self.header.refresh_clicked.connect(self.refresh_clicked.emit)
        self.header.theme_clicked.connect(self.theme_clicked.emit)
        self.header.user_clicked.connect(self.user_clicked.emit)

        # atalhos vindos das paginas
        self.dashboard.open_settings.connect(lambda: self.set_page(SETTINGS_PAGE))
        self.dashboard.open_history.connect(lambda: self.set_page(HISTORY_PAGE))
        self.dashboard.refresh.connect(self.refresh_clicked.emit)
        self.settings_page.refresh_clicked.connect(self.refresh_clicked.emit)
        self.settings_page.logout_clicked.connect(self.logout_clicked.emit)
        self.history_page.refresh_clicked.connect(self.history_page.load)

        self.set_connected(False)
        self.set_page(DASHBOARD, animate=False)
        # A casca e criada depois de o tema ser aplicado ao QApplication: os
        # widgets que desenham icones precisam ser avisados agora.
        theme_mod.apply_to(self)

    # ------------------------------------------------------------- navegacao
    def set_page(self, index: int, animate: bool = True) -> None:
        if not 0 <= index < self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.set_active(index)

        titulo, migalha = PAGE_META[index]
        legendas = {
            DASHBOARD: "Ambiente, próximas ações e execuções recentes.",
            IMPORT_PAGE: "Planilha, revisão linha a linha e envio com relatório.",
            LINKS_PAGE: "Prefixos, IP do link e interface do roteador por site.",
            HISTORY_PAGE: "Relatórios gravados nesta máquina, em ordem de execução.",
            SETTINGS_PAGE: "Conexão, token, aparência e o ambiente lido do NetBox.",
        }
        self.header.set_page(titulo, legendas[index], migalha)
        if animate:
            fade_in(self.stack.currentWidget())

    def current_page(self) -> int:
        return self.stack.currentIndex()

    # ---------------------------------------------------------------- estado
    def set_connected(self, connected: bool, versao: str = "", tls: bool = True) -> None:
        if connected:
            self.header.badge.set_connected(versao or "?", tls)
            self.sidebar.set_connection(
                True,
                f"Conectado · NetBox {versao or '?'}",
                "Sessão ativa nesta máquina",
            )
        else:
            self.header.badge.set_unknown()
            self.sidebar.set_connection(False, "Desconectado", "Configure o token para começar")

    def set_user(self, nome: str) -> None:
        self.header.avatar.set_username(nome)

    def set_ready(self, ready: bool) -> None:
        self.import_page.set_ready(ready)
        self.links_page.set_ready(ready)
        self.dashboard.set_connected(ready)
        self.header.refresh_button.setEnabled(ready)

    def set_inventory_loading(self, loading: bool) -> None:
        self.links_page.set_inventory_loading(loading)

    def set_version(self, versao: str) -> None:
        self.sidebar.set_version(versao)
