"""Tela de login por token.

A regra do produto nao mudou: o servidor e fixo no codigo e so o token e digitado.
O que mudou e a apresentacao - uma coluna de marca explica o que o app faz e a
outra concentra a unica acao da tela. O token guardado e anunciado com o tipo de
protecao em uso, nunca como uma suposicao.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import theme as theme_mod, version as version_mod
from app.config import NETBOX_URL
from app.paths import resource_path
from app.ui import icons
from app.ui.components import primary_button
from app.ui.tokens import GAP_LG, GAP_MD, GAP_SM

FEATURES: tuple[tuple[str, str, str], ...] = (
    (
        "shield",
        "Token protegido pelo sistema",
        "Cifrado pelo Windows ou guardado no chaveiro — nunca em texto claro.",
    ),
    (
        "import",
        "Prévia antes de enviar",
        "Cada linha da planilha aparece validada antes de qualquer escrita.",
    ),
    (
        "history",
        "Relatório de cada execução",
        "Log, JSON e CSV com o identificador de cada requisição ao NetBox.",
    ),
)


class LoginPage(QWidget):
    submit = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PageArea")
        self._brand_panel: QFrame | None = None
        self._brand_logo: QLabel | None = None
        self._feature_icons: list[tuple[QLabel, str]] = []

        externo = QHBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.setSpacing(0)

        self._build_brand(externo)
        self._build_form(externo)
        self.apply_theme(theme_mod.palette())

    # ------------------------------------------------------------------ marca
    def _build_brand(self, externo: QHBoxLayout) -> None:
        painel = QFrame()
        painel.setObjectName("LoginBrand")
        painel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._brand_panel = painel

        coluna = QVBoxLayout(painel)
        coluna.setContentsMargins(56, 48, 56, 40)
        coluna.setSpacing(GAP_MD)

        topo = QHBoxLayout()
        topo.setSpacing(GAP_SM)
        logo = QLabel()
        logo.setFixedSize(36, 36)
        self._brand_logo = logo
        topo.addWidget(logo)
        nome = QLabel("Importador NetBox")
        nome.setObjectName("FeatureTitle")
        topo.addWidget(nome)
        topo.addStretch(1)
        coluna.addLayout(topo)

        coluna.addStretch(2)

        titulo = QLabel("O parque de câmeras e links\ndocumentado direto no NetBox.")
        titulo.setObjectName("LoginBrandTitle")
        titulo.setWordWrap(True)
        coluna.addWidget(titulo)

        tagline = QLabel(
            "Valide a planilha inteira, veja o que será criado e só então envie. "
            "Sem digitação manual e sem duplicar objeto."
        )
        tagline.setObjectName("LoginBrandTagline")
        tagline.setWordWrap(True)
        coluna.addWidget(tagline)
        coluna.addSpacing(GAP_LG)

        for icone, titulo_item, texto in FEATURES:
            linha = QHBoxLayout()
            linha.setSpacing(GAP_MD)
            icone_label = QLabel()
            icone_label.setFixedSize(18, 18)
            self._feature_icons.append((icone_label, icone))
            linha.addWidget(icone_label, alignment=Qt.AlignmentFlag.AlignTop)
            textos = QVBoxLayout()
            textos.setSpacing(1)
            nome_item = QLabel(titulo_item)
            nome_item.setObjectName("FeatureTitle")
            descricao = QLabel(texto)
            descricao.setObjectName("FeatureText")
            descricao.setWordWrap(True)
            textos.addWidget(nome_item)
            textos.addWidget(descricao)
            linha.addLayout(textos, stretch=1)
            coluna.addLayout(linha)
            coluna.addSpacing(GAP_SM)

        coluna.addStretch(2)

        rodape = QLabel(f"L&K Tecnologia  ·  versão {version_mod.__version__}")
        rodape.setObjectName("LoginFooter")
        coluna.addWidget(rodape)

        externo.addWidget(painel, stretch=11)

    # ---------------------------------------------------------------- formulario
    def _build_form(self, externo: QHBoxLayout) -> None:
        area = QWidget()
        area.setObjectName("PageArea")
        area_layout = QVBoxLayout(area)
        area_layout.setContentsMargins(48, 40, 48, 32)
        area_layout.addStretch(1)

        cartao = QFrame()
        cartao.setObjectName("AuthCard")
        cartao.setFixedWidth(420)
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(32, 32, 32, 28)
        cartao_layout.setSpacing(GAP_MD)

        titulo = QLabel("Entrar no NetBox")
        titulo.setObjectName("AuthTitle")
        subtitulo = QLabel("Use um token de API com permissão de leitura e escrita.")
        subtitulo.setObjectName("AuthSubtitle")
        subtitulo.setWordWrap(True)
        cartao_layout.addWidget(titulo)
        cartao_layout.addWidget(subtitulo)

        # servidor (fixo no codigo, exibido como contexto)
        servidor = QFrame()
        servidor.setProperty("tone", "flat")
        servidor.setObjectName("Card")
        linha_servidor = QHBoxLayout(servidor)
        linha_servidor.setContentsMargins(GAP_MD, GAP_SM, GAP_MD, GAP_SM)
        linha_servidor.setSpacing(GAP_SM)
        self.server_icon = QLabel()
        self.server_icon.setFixedSize(16, 16)
        linha_servidor.addWidget(self.server_icon)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        rotulo = QLabel("SERVIDOR")
        rotulo.setObjectName("FieldLabel")
        self.server_label = QLabel(NETBOX_URL)
        self.server_label.setObjectName("Mono")
        textos.addWidget(rotulo)
        textos.addWidget(self.server_label)
        linha_servidor.addLayout(textos, stretch=1)
        cartao_layout.addWidget(servidor)
        cartao_layout.addSpacing(GAP_SM)

        rotulo_token = QLabel("TOKEN DE ACESSO")
        rotulo_token.setObjectName("FieldLabel")
        cartao_layout.addWidget(rotulo_token)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("Cole o token aqui")
        self.token_edit.setMinimumHeight(38)
        self.token_edit.returnPressed.connect(self._on_submit)
        self._eye_action = QAction(self.token_edit)
        self._eye_action.setToolTip("Mostrar o token")
        self._eye_action.triggered.connect(self._toggle_echo)
        self.token_edit.addAction(self._eye_action, QLineEdit.ActionPosition.TrailingPosition)
        cartao_layout.addWidget(self.token_edit)

        ajuda = QLabel(
            "No NetBox: clique no seu nome (canto superior direito) → "
            "Profile → API Tokens → Create."
        )
        ajuda.setProperty("faint", "true")
        ajuda.setWordWrap(True)
        cartao_layout.addWidget(ajuda)

        self.saved_note = QLabel("")
        self.saved_note.setProperty("muted", "true")
        self.saved_note.setWordWrap(True)
        self.saved_note.hide()
        cartao_layout.addWidget(self.saved_note)

        self.forget_button = QPushButton("Esquecer token guardado")
        self.forget_button.setObjectName("linkButton")
        self.forget_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forget_button.hide()
        cartao_layout.addWidget(self.forget_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.login_error_label = QLabel("")
        self.login_error_label.setObjectName("InlineError")
        self.login_error_label.setWordWrap(True)
        self.login_error_label.hide()
        cartao_layout.addWidget(self.login_error_label)

        cartao_layout.addSpacing(GAP_SM)
        self.login_button = primary_button("Entrar")
        self.login_button.setMinimumHeight(40)
        self.login_button.clicked.connect(self._on_submit)
        cartao_layout.addWidget(self.login_button)

        nota = QLabel(
            "As permissões são as do dono do token. O app não envia a planilha "
            "para nenhum outro destino."
        )
        nota.setProperty("faint", "true")
        nota.setWordWrap(True)
        cartao_layout.addWidget(nota)

        area_layout.addWidget(cartao, 0, Qt.AlignmentFlag.AlignHCenter)
        area_layout.addStretch(1)

        externo.addWidget(area, stretch=9)

    # ------------------------------------------------------------------ acoes
    def _on_submit(self) -> None:
        token = self.token_edit.text().strip()
        if not token:
            self.show_error("Cole o token da API.")
            return
        self.clear_error()
        self.submit.emit(token)

    def _toggle_echo(self) -> None:
        senha = self.token_edit.echoMode() == QLineEdit.EchoMode.Password
        self.token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if senha else QLineEdit.EchoMode.Password
        )
        self._eye_action.setToolTip("Ocultar o token" if senha else "Mostrar o token")
        self.apply_theme(theme_mod.palette())

    def show_error(self, message: str) -> None:
        self.login_error_label.setText(message)
        self.login_error_label.show()
        self.token_edit.setProperty("error", "true")
        self.token_edit.style().unpolish(self.token_edit)
        self.token_edit.style().polish(self.token_edit)

    def clear_error(self) -> None:
        self.login_error_label.hide()
        self.login_error_label.setText("")
        self.token_edit.setProperty("error", "false")
        self.token_edit.style().unpolish(self.token_edit)
        self.token_edit.style().polish(self.token_edit)

    def set_busy(self, busy: bool) -> None:
        self.login_button.setEnabled(not busy)
        self.login_button.setText("Conectando..." if busy else "Entrar")
        self.token_edit.setEnabled(not busy)

    def set_saved_token(self, saved: bool, protection: str) -> None:
        self.saved_note.setText(
            f"Já existe um token guardado nesta máquina ({protection})."
        )
        self.saved_note.setVisible(saved)
        self.forget_button.setVisible(saved)

    def set_saved_token_invalid(self) -> None:
        self.saved_note.setText(
            "O token guardado nesta máquina não funcionou. Cole um token novo abaixo "
            "— ele substitui o antigo."
        )
        self.saved_note.show()

    def focus_token(self) -> None:
        self.token_edit.setFocus()

    # --------------------------------------------------------------- responsivo
    def resizeEvent(self, event) -> None:  # noqa: N802
        # Abaixo disso a coluna de marca vira ruido: o formulario fica com a tela.
        if self._brand_panel is not None:
            self._brand_panel.setVisible(self.width() >= 900)
        super().resizeEvent(event)

    # ------------------------------------------------------------------- tema
    def apply_theme(self, palette) -> None:
        mostrar = self.token_edit.echoMode() == QLineEdit.EchoMode.Normal
        self._eye_action.setIcon(icons.icon("eye_off" if mostrar else "eye", palette.text_faint, 16))
        self.server_icon.setPixmap(icons.pixmap("server", palette.text_muted, 16))
        if self._brand_logo is not None:
            from PySide6.QtGui import QPixmap

            pixmap = QPixmap(str(resource_path("app", "assets", "app_icon.png")))
            if not pixmap.isNull():
                self._brand_logo.setPixmap(
                    pixmap.scaled(
                        36,
                        36,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        for label, nome in self._feature_icons:
            label.setPixmap(icons.pixmap(nome, palette.accent, 18))
