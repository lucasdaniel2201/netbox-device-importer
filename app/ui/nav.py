"""Estrutura de navegacao: barra lateral, cabecalho e estado da conexao.

A barra lateral diz onde o usuario esta e qual e o estado da sessao; o cabecalho
diz o que a pagina atual faz e concentra as acoes globais (atualizar ambiente,
trocar tema, ver o dono do token). Nada aqui conhece a logica de importacao: os
sinais sobem para a janela, que decide.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import theme as theme_mod
from app.paths import resource_path
from app.ui import icons
from app.ui.components import IconButton, repolish
from app.ui.tokens import GAP_LG, GAP_MD, GAP_SM, HEADER_HEIGHT, SIDEBAR_WIDTH


def _logo_pixmap(size: int) -> QPixmap:
    """Marca do app. O icone tem fundo escuro proprio, entao serve nos dois temas."""
    pixmap = QPixmap(str(resource_path("app", "assets", "app_icon.png")))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class NavButton(QPushButton):
    """Item de navegacao com icone desenhado e estado ativo explicito."""

    def __init__(self, name: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._name = name
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(40)
        self.apply_theme(theme_mod.palette())

    def apply_theme(self, palette) -> None:
        self.setIcon(
            icons.icon(
                self._name,
                palette.text_muted,
                18,
                checked_color=palette.accent,
                disabled_color=palette.disabled_text,
            )
        )


class ConnectionDot(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionDot")
        self.setFixedSize(8, 8)
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        self.setProperty("connected", "true" if connected else "false")
        repolish(self)


class Sidebar(QFrame):
    """Navegacao principal, marca e estado da sessao."""

    page_changed = Signal(int)
    logout_clicked = Signal()

    def __init__(self, items: list[tuple[str, str, str]], parent: QWidget | None = None) -> None:
        """`items` = (icone, titulo, descricao para tooltip)."""
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(GAP_LG, GAP_LG, GAP_MD, GAP_MD)
        layout.setSpacing(GAP_MD)

        # marca
        marca = QHBoxLayout()
        marca.setSpacing(GAP_SM)
        self.logo = QLabel()
        pixmap = _logo_pixmap(32)
        if not pixmap.isNull():
            self.logo.setPixmap(pixmap)
        marca.addWidget(self.logo)

        nomes = QVBoxLayout()
        nomes.setSpacing(0)
        titulo = QLabel("Importador NetBox")
        titulo.setObjectName("BrandName")
        versao = QLabel("")
        versao.setObjectName("BrandVersion")
        self.version_label = versao
        nomes.addWidget(titulo)
        nomes.addWidget(versao)
        marca.addLayout(nomes, stretch=1)
        layout.addLayout(marca)

        layout.addSpacing(GAP_SM)
        secao = QLabel("NAVEGAÇÃO")
        secao.setObjectName("NavSection")
        layout.addWidget(secao)

        self.buttons: list[NavButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, (icone, texto, dica) in enumerate(items):
            botao = NavButton(icone, texto)
            botao.setToolTip(dica)
            self._group.addButton(botao, index)
            self.buttons.append(botao)
            layout.addWidget(botao)
        self._group.idClicked.connect(self.page_changed.emit)

        layout.addStretch(1)

        # estado da conexao
        self.connection_card = QFrame()
        self.connection_card.setObjectName("ConnectionCard")
        cartao = QVBoxLayout(self.connection_card)
        cartao.setContentsMargins(GAP_MD, GAP_MD, GAP_MD, GAP_MD)
        cartao.setSpacing(4)

        linha = QHBoxLayout()
        linha.setSpacing(GAP_SM)
        self.dot = ConnectionDot()
        self.connection_title = QLabel("Desconectado")
        self.connection_title.setObjectName("ConnectionTitle")
        self.connection_text = QLabel("Sem sessão ativa")
        self.connection_text.setObjectName("ConnectionText")
        self.connection_text.setWordWrap(True)
        linha.addWidget(self.dot)
        linha.addWidget(self.connection_title, stretch=1)
        cartao.addLayout(linha)
        cartao.addWidget(self.connection_text)
        layout.addWidget(self.connection_card)

        self.logout_button = QPushButton("Sair")
        self.logout_button.setObjectName("ghostButton")
        self.logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_button.setIconSize(QSize(16, 16))
        self.logout_button.clicked.connect(self.logout_clicked.emit)
        layout.addWidget(self.logout_button)

        self.set_active(0)

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)

    def set_version(self, versao: str) -> None:
        self.version_label.setText(f"v{versao}" if versao else "")

    def set_connection(self, connected: bool, title: str, detail: str) -> None:
        self.dot.set_connected(connected)
        self.connection_title.setText(title)
        self.connection_text.setText(detail)
        self.logout_button.setVisible(connected)

    def apply_theme(self, palette) -> None:
        self.logout_button.setIcon(
            icons.icon("logout", palette.text_muted, 16, disabled_color=palette.disabled_text)
        )
        for botao in self.buttons:
            botao.apply_theme(palette)


class ConnectionBadge(QLabel):
    """Pilula de estado no cabecalho: conectado, aviso de TLS ou desconectado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set_unknown()

    def _set(self, text: str, connected: bool, tls: bool = True) -> None:
        self.setText(text)
        self.setProperty("connected", "true" if connected else "false")
        self.setProperty("tls", "true" if tls else "false")
        repolish(self)

    def set_unknown(self) -> None:
        self._set("Sem conexão", False, True)

    def set_connected(self, versao: str, tls_verified: bool = True) -> None:
        if tls_verified:
            self._set(f"● Conectado · NetBox {versao}", True, True)
        else:
            self._set("● Conectado · TLS não verificado", True, False)


class Avatar(QPushButton):
    """Iniciais do dono do token. Guarda o nome completo no tooltip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Avatar")
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_username("")

    def set_username(self, nome: str) -> None:
        limpo = (nome or "").strip()
        if not limpo:
            self.setText("?")
            self.setToolTip("Token sem usuário identificado")
            return
        partes = [p for p in limpo.replace(".", " ").replace("_", " ").split() if p]
        iniciais = (partes[0][0] + (partes[1][0] if len(partes) > 1 else ""))[:2]
        self.setText(iniciais.upper())
        self.setToolTip(f"Token de: {limpo}")


class ThemeButton(IconButton):
    """Alternador de tema: mostra o destino (sol no escuro, lua no claro)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("sun", "Alternar tema claro/escuro", 18, 34, parent=parent)
        self.setCheckable(False)

    def apply_theme(self, palette) -> None:
        # O icone mostra o destino: sol quando o tema claro e o proximo.
        self._name = "sun" if palette.is_dark else "moon"
        self.setToolTip(
            "Mudar para o tema claro" if palette.is_dark else "Mudar para o tema escuro"
        )
        super().apply_theme(palette)


class PageHeader(QFrame):
    """Titulo da pagina, migalha e acoes globais."""

    refresh_clicked = Signal()
    theme_clicked = Signal()
    user_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppHeader")
        self.setFixedHeight(HEADER_HEIGHT)

        row = QHBoxLayout(self)
        row.setContentsMargins(GAP_LG, GAP_SM, GAP_LG, GAP_SM)
        row.setSpacing(GAP_MD)

        coluna = QVBoxLayout()
        coluna.setSpacing(0)
        self.breadcrumb = QLabel("")
        self.breadcrumb.setObjectName("Breadcrumb")
        self.title = QLabel("")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("PageSubtitle")
        coluna.addWidget(self.breadcrumb)
        coluna.addWidget(self.title)
        coluna.addWidget(self.subtitle)
        row.addLayout(coluna, stretch=1)

        self.badge = ConnectionBadge()
        row.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.refresh_button = IconButton(
            "refresh", "Reler o ambiente do NetBox", 18, 34, parent=self
        )
        self.refresh_button.clicked.connect(self.refresh_clicked.emit)
        row.addWidget(self.refresh_button)

        self.theme_button = ThemeButton(self)
        self.theme_button.clicked.connect(self.theme_clicked.emit)
        row.addWidget(self.theme_button)

        self.avatar = Avatar()
        self.avatar.clicked.connect(self.user_clicked.emit)
        row.addWidget(self.avatar)

    def set_page(self, title: str, subtitle: str = "", breadcrumb: str = "") -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self.breadcrumb.setText(breadcrumb)
        self.breadcrumb.setVisible(bool(breadcrumb))

    def set_refreshing(self, refreshing: bool) -> None:
        self.refresh_button.setEnabled(not refreshing)
        self.refresh_button.setToolTip(
            "Atualizando o ambiente..." if refreshing else "Reler o ambiente do NetBox"
        )
