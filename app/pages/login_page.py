"""Tela de login por token.

A regra do produto nao mudou: o servidor e fixo no codigo e so o token e digitado.
O que mudou e a apresentacao - uma coluna de marca explica o que o app faz e a
outra concentra a unica acao da tela. O token guardado e anunciado com o tipo de
protecao em uso, nunca como uma suposicao.
"""

from __future__ import annotations

import html

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import theme as theme_mod, version as version_mod
from app.config import NETBOX_URL
from app.paths import resource_path
from app.ui import icons
from app.ui.components import WrappedLabel, primary_button
from app.ui.tokens import FONT_CAPTION, GAP_LG, GAP_MD, GAP_SM

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

# Passos para obter o token. O texto existe porque o caminho no NetBox muda de
# lugar conforme a versao e o usuario leigo nao sabe que "API token" mora no
# perfil. Os passos nao citam nome de menu de proposito: quem executa o passo 2 e
# o botao ao lado, e o rotulo do menu varia entre versoes do NetBox. A rota foi
# conferida no codigo do NetBox 4.3.6 (account/urls.py: usertoken_add).
TOKEN_STEPS: tuple[str, ...] = (
    "Abra o NetBox no navegador e entre com seu usuário.",
    "O botão abaixo já abre a página de tokens do seu perfil.",
    "Crie o token com leitura e escrita e copie o valor.",
    "Cole no campo acima. O valor aparece uma única vez.",
)

# Rota da tela de criacao de token no NetBox 4.3 (account/urls.py: usertoken_add).
TOKEN_PAGE_PATH = "/user/api-tokens/add/"

# Largura do cartao de login. O maximo e o valor que a tela sempre usou; o
# minimo permite encolher em janela estreita em vez de espremer o conteudo.
FORM_WIDTH = 420
MIN_FORM_WIDTH = 320

# Largura do circulo com o numero do passo (18px, ver _build_token_steps).
PASSO_LARGURA = 18


def token_page_url(base_url: str) -> str:
    """URL da tela de criacao de token, a partir da URL do NetBox."""
    return base_url.rstrip("/") + TOKEN_PAGE_PATH


class LoginPage(QWidget):
    submit = Signal(str)
    # Pede a janela para abrir a tela de token no navegador. A pagina nao abre
    # nada sozinha: quem conhece o resto do app e a janela.
    open_token_page = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PageArea")
        self._brand_panel: QFrame | None = None
        self._brand_logo: QLabel | None = None
        self._feature_icons: list[tuple[QLabel, str]] = []
        # Preenchidos em _build_token_steps; usados por _ajustar_altura_passos
        # depois que o layout deu largura aos labels.
        self._steps_panel: QFrame | None = None
        self._steps_layout: QVBoxLayout | None = None
        self._cartao: QFrame | None = None

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
        # Area rolavel: o cartao tem mais conteudo do que cabe numa janela baixa.
        # Sem a rolagem, o layout comprimia os QLabel com wordWrap abaixo da
        # altura necessaria e as linhas do passo a passo se sobrepunham (o mesmo
        # defeito que o campo do servidor teve antes).
        self.form_scroll = QScrollArea()
        self.form_scroll.setObjectName("PageArea")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        area = QWidget()
        area.setObjectName("PageArea")
        area_layout = QVBoxLayout(area)
        area_layout.setContentsMargins(48, 40, 48, 32)
        # Sem stretches: com `addStretch` nas duas pontas o conteudo era espremido
        # entre elas quando a janela ficava menor que a altura do cartao, e o
        # passo a passo se sobrepunha. A area rolavel cuida do excedente.
        area_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        cartao = QFrame()
        cartao.setObjectName("AuthCard")
        self._cartao = cartao
        # Largura fixa: um cartao que muda de largura com o conteudo do aviso
        # recalculava a altura dos textos e a sobreposicao voltava em tamanhos
        # diferentes. 420 e a largura que a tela sempre usou; o container
        # rolavel ja cuida de janela menor.
        cartao.setFixedWidth(FORM_WIDTH)
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(32, 32, 32, 28)
        cartao_layout.setSpacing(GAP_MD)
        # SEM setSizeConstraint aqui: SetMinAndMaxSize ignora o setFixedWidth do
        # cartao (a largura ia para 544) e SetMinimumSize espremia o conteudo.
        # A altura certa vem de _reflow_cartao, que mede o texto na largura real.

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
        # Rotulo e URL num widget so: duas QLabel empilhadas dependiam da altura
        # calculada pela fonte, que nem sempre bate com a fonte pintada (o texto
        # do servidor aparecia sobreposto). Um rich text resolve o espacamento
        # entre as linhas de uma vez.
        self.server_label = QLabel()
        self.server_label.setTextFormat(Qt.TextFormat.RichText)
        # Sem word wrap: com ele o QLabel reporta altura minima de UMA linha e,
        # quando a janela fica apertada, a segunda linha some/cobre a primeira.
        self.server_label.setWordWrap(False)
        self.server_label.setText(self._server_html(theme_mod.palette()))
        linha_servidor.addWidget(self.server_label, stretch=1)
        cartao_layout.addWidget(servidor)
        cartao_layout.addSpacing(GAP_SM)

        rotulo_token = QLabel("TOKEN DE ACESSO")
        rotulo_token.setObjectName("FieldLabel")
        cartao_layout.addWidget(rotulo_token)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("Cole o token aqui")
        # O rotulo "TOKEN DE ACESSO" esta acima, mas nao e um <label for>: no Qt
        # nao existe essa ligacao, entao o nome acessivel vai explicito.
        self.token_edit.setAccessibleName("Token de acesso")
        self.token_edit.setAccessibleDescription(
            "Token de API do NetBox. Cole o valor e pressione Enter para entrar."
        )
        self.token_edit.setMinimumHeight(40)
        self.token_edit.returnPressed.connect(self._on_submit)
        self._eye_action = QAction(self.token_edit)
        self._eye_action.setToolTip("Mostrar o token")
        self._eye_action.triggered.connect(self._toggle_echo)
        self.token_edit.addAction(self._eye_action, QLineEdit.ActionPosition.TrailingPosition)
        cartao_layout.addWidget(self.token_edit)

        cartao_layout.addWidget(self._build_token_steps())

        # Aviso de token guardado + acao de esquecer, num bloco proprio.
        # Soltos no layout do cartao, o aviso ficava a -3px do painel de passos
        # (grudado, chegando a encostar). O bloco garante o respiro acima dele e
        # o par aviso/acao continua junto, que e como ele deve ser lido.
        self.saved_block = QWidget()
        bloco = QVBoxLayout(self.saved_block)
        # Sem margem no bloco: o respiro vem do `addSpacing` abaixo, no layout do
        # cartao. Margem dentro do bloco entrava na conta do `minimumSizeHint`
        # do proprio widget e o Qt posicionava o bloco 16px acima, invadindo o
        # painel dos passos.
        bloco.setContentsMargins(0, 0, 0, 0)
        bloco.setSpacing(GAP_SM)

        self.saved_note = QLabel("")
        self.saved_note.setProperty("muted", "true")
        self.saved_note.setWordWrap(True)
        bloco.addWidget(self.saved_note)

        self.forget_button = QPushButton("Esquecer token guardado")
        self.forget_button.setObjectName("linkButton")
        self.forget_button.setCursor(Qt.CursorShape.PointingHandCursor)
        bloco.addWidget(self.forget_button, alignment=Qt.AlignmentFlag.AlignLeft)
        # Bloco inteiro escondido: sem o aviso nao ha o que esquecer.
        self.saved_block.hide()
        # Respiro entre o painel de passos e o aviso, no layout do cartao (nao
        # dentro do bloco, que e medido como um widget unico).
        cartao_layout.addSpacing(GAP_MD)
        cartao_layout.addWidget(self.saved_block)

        self.login_error_label = QLabel("")
        self.login_error_label.setObjectName("InlineError")
        self.login_error_label.setWordWrap(True)
        self.login_error_label.hide()
        # `hide()` esconde mas nao zera a altura: o label ficava com 480px no
        # layout e, mesmo invisivel, empurrava o aviso de token guardado para
        # cima do painel de passos.
        self.login_error_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
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
        self.form_scroll.setWidget(area)

        externo.addWidget(self.form_scroll, stretch=9)

    def _build_token_steps(self) -> QFrame:
        """Passo a passo para obter o token, com a acao de abrir a pagina certa.

        Antes era uma unica linha cinza dizendo "Profile -> API Tokens -> Create":
        o caminho muda entre versoes do NetBox e quem nunca usou a API nao sabe
        onde ele mora. Aqui vira lista numerada, e o botao abre a tela de criacao
        ja no servidor configurado - o usuario so clica em Criar e copia.
        """
        painel = QFrame()
        painel.setObjectName("Card")
        painel.setProperty("tone", "flat")
        coluna = QVBoxLayout(painel)
        coluna.setContentsMargins(GAP_MD, GAP_MD, GAP_MD, GAP_MD)
        coluna.setSpacing(GAP_SM)
        # SetMinimumSize obriga o painel a ter, no minimo, o que o layout precisa.
        # Sem isso o QVBoxLayout do cartao espremia o painel (214px onde o
        # conteudo pedia 261) e o texto dos passos se sobrepunha. Quem cuida do
        # excedente em janela baixa e a area rolavel.
        coluna.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        titulo = QLabel("Como obter o token")
        titulo.setObjectName("TokenStepsTitle")
        coluna.addWidget(titulo)

        for numero, texto in enumerate(TOKEN_STEPS, start=1):
            linha = QHBoxLayout()
            linha.setSpacing(GAP_SM)
            passo = QLabel(str(numero))
            passo.setObjectName("TokenStepDot")
            passo.setFixedSize(18, 18)
            passo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            linha.addWidget(passo, alignment=Qt.AlignmentFlag.AlignTop)

            descricao = WrappedLabel(texto)
            descricao.setProperty("muted", "true")
            descricao.setWordWrap(True)
            # O texto e quem dita a altura da linha; sem o minimo de largura o
            # QHBoxLayout deixava o label crescer alem do cartao.
            descricao.setMinimumWidth(1)
            linha.addWidget(descricao, stretch=1)
            coluna.addLayout(linha)

        self.open_token_button = QPushButton("Abrir a página de tokens no navegador")
        # Secundario, nao primario: a acao principal desta tela continua sendo
        # "Entrar". Este botao ajuda, nao compete.
        self.open_token_button.setIcon(icons.icon("external", theme_mod.palette().text_muted, 16))
        self.open_token_button.setIconSize(QSize(16, 16))
        self.open_token_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_token_button.setMinimumHeight(36)
        # O rotulo e longo: sem quebra, o `minimumSizeHint` do botao virava 478px
        # e empurrava o cartao para 566 dentro de um espaco de 420 - o painel
        # transbordava e o texto dos passos era medido numa largura falsa.
        self.open_token_button.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.open_token_button.setText("Abrir página de tokens no navegador")
        self.open_token_button.setToolTip(token_page_url(NETBOX_URL))
        self.open_token_button.setAccessibleName(
            "Abrir a página de criação de token no navegador"
        )
        self.open_token_button.clicked.connect(self.open_token_page.emit)
        coluna.addWidget(self.open_token_button)
        self._steps_panel = painel
        self._steps_layout = coluna
        return painel

    def _ajustar_altura_passos(self) -> None:
        """Fixa a altura do painel de passos na que o texto realmente ocupa.

        Medir `sizeHint()` cedo demais da um valor de UMA linha por label: na
        construcao a largura ainda e 0, e mesmo depois do layout o painel pode
        ser medido com a largura do cartao inteiro (452px), onde o texto cabe em
        uma linha. O aviso de token guardado, entao, subia por cima do painel.
        Aqui a largura usada e a que o painel de fato tem, e a altura e a soma do
        `heightForWidth` de cada passo.
        """
        if self._steps_panel is None or self._steps_layout is None:
            return
        # A largura do CARTAO, nao a do painel: o painel chega a ser medido com
        # 502px dentro de um cartao de 420, e nessa largura falsa o texto cabe em
        # uma linha. Medir pelo cartao da o valor que o texto vai ocupar de fato.
        cartao = self._steps_panel.parentWidget()
        largura = cartao.width() if cartao is not None else self._steps_panel.width()
        if largura <= 0:
            return
        margens = self._steps_layout.contentsMargins()
        disponivel = largura - margens.left() - margens.right()
        if disponivel <= 0:
            return

        total = margens.top() + margens.bottom()
        total += self._altura_itens(self._steps_layout, disponivel)
        if total > self._steps_panel.minimumHeight():
            self._steps_panel.setMinimumHeight(total)

    def _altura_itens(self, layout, disponivel: int) -> int:
        """Soma a altura necessaria de um layout, descendo nos layouts aninhados.

        Cada passo e um QHBoxLayout (numero + texto), nao um widget direto: ler
        so `itemAt().widget()` do layout externo pulava justamente os textos, que
        e onde a altura varia com a largura.
        """
        total = 0
        for indice in range(layout.count()):
            item = layout.itemAt(indice)
            if item is None:
                continue
            widget = item.widget()
            interno = item.layout()
            if isinstance(widget, WrappedLabel):
                largura_texto = disponivel - PASSO_LARGURA - GAP_SM
                total += max(
                    widget.heightForWidth(max(1, largura_texto)),
                    widget.sizeHint().height(),
                )
            elif interno is not None:
                total += self._altura_itens(interno, disponivel - PASSO_LARGURA - GAP_SM)
            elif widget is not None and widget.isVisible():
                total += widget.sizeHint().height()
            total += layout.spacing()
        return total

    def _server_html(self, palette) -> str:
        """Servidor fixo em duas linhas de um unico texto (rotulo + URL)."""
        cor = palette.text_muted
        return (
            f"<span style='font-size:{FONT_CAPTION}px;font-weight:700;color:{cor}'>"
            "SERVIDOR</span>"
            f"<br><span style='font-size:{FONT_CAPTION}px;color:{cor}'>"
            f"{html.escape(NETBOX_URL)}</span>"
        )

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
        # O bloco inteiro, nao o label: e ele que carrega o respiro acima do
        # aviso e agrupa o botao de esquecer.
        self.saved_block.setVisible(saved)
        # Mostrar o bloco muda a altura exigida pelo cartao. Sem isto o Qt
        # redistribui o espaco em cima do que ja existe e o aviso sobe por cima
        # do painel de passos (chegou a -15px).
        self._reflow_cartao()

    def set_saved_token_invalid(self) -> None:
        self.saved_note.setText(
            "O token guardado nesta máquina não funcionou. Cole um token novo abaixo "
            "— ele substitui o antigo."
        )
        self.saved_block.show()
        self._reflow_cartao()

    def _reflow_cartao(self) -> None:
        """Ajusta a altura do painel de passos e do cartao ao conteudo real.

        O `QLabel` com quebra de linha informa altura de UMA linha no `sizeHint`,
        entao o layout distribuia menos altura do que o texto ocupa e os ultimos
        itens se sobrepunham aos primeiros. Aqui a altura do painel e fixada na
        soma real (medida na largura final) e, com ela, o layout do cartao e
        reativado para reposicionar os filhos.
        """
        if self._cartao is None or self._steps_panel is None:
            return
        self._ajustar_altura_passos()
        layout = self._cartao.layout()
        if layout is None:
            return
        # `activate` redistribui usando os minimos atuais. Sem ele o Qt mantem as
        # posicoes antigas e o bloco do aviso fica sobre o painel.
        layout.activate()

    def focus_token(self) -> None:
        self.token_edit.setFocus()

    # --------------------------------------------------------------- responsivo
    def resizeEvent(self, event) -> None:  # noqa: N802
        # Abaixo disso a coluna de marca vira ruido: o formulario fica com a tela.
        if self._brand_panel is not None:
            self._brand_panel.setVisible(self.width() >= 900)
        super().resizeEvent(event)
        # A altura do texto dos passos depende da largura: remede depois que o
        # Qt distribuiu o espaco nesta largura.
        self._ajustar_altura_passos()

    # ------------------------------------------------------------------- tema
    def apply_theme(self, palette) -> None:
        mostrar = self.token_edit.echoMode() == QLineEdit.EchoMode.Normal
        self._eye_action.setIcon(icons.icon("eye_off" if mostrar else "eye", palette.text_faint, 16))
        self.server_icon.setPixmap(icons.pixmap("server", palette.text_muted, 16))
        self.server_label.setText(self._server_html(palette))
        # Rich text: o minimo informado pelo QLabel e de uma linha, entao fixamos a
        # altura de duas linhas para o layout nunca comprimir o bloco.
        self.server_label.setMinimumHeight(self.server_label.sizeHint().height())
        self.open_token_button.setIcon(
            icons.icon("external", palette.text_muted, 16, disabled_color=palette.disabled_text)
        )
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
