"""Paginas de entrada dos dois fluxos: cameras e links IP.

Elas existem para responder "o que eu faco agora" sem abrir nada. O trabalho em si
acontece no dialogo de importacao (origem -> revisao -> envio -> resumo); aqui
ficam o ponto de partida, as regras que o usuario precisa saber antes e o aviso de
que sem sessao nao ha o que importar.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app import theme as theme_mod
from app.ui import icons
from app.ui.components import (
    Banner,
    Card,
    Divider,
    ScrollPage,
    SectionHeader,
    primary_button,
    secondary_button,
)
from app.ui.tokens import GAP_MD


@dataclass(frozen=True)
class Step:
    title: str
    text: str


@dataclass(frozen=True)
class Note:
    kind: str
    title: str
    text: str


class WorkflowPage(ScrollPage):
    """Pagina de entrada de um fluxo, montada a partir de uma especificacao."""

    primary_clicked = Signal()
    secondary_clicked = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        steps: tuple[Step, ...],
        notes: tuple[Note, ...],
        primary_label: str,
        secondary_label: str,
        primary_icon: str,
        secondary_icon: str,
        needs_inventory: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._primary_icon = primary_icon
        self._secondary_icon = secondary_icon
        self._needs_inventory = needs_inventory
        self._connected = False
        self._inventory_loading = False
        self._note_icon_labels: list[tuple[QLabel, str]] = []

        hero = Card()
        topo = QHBoxLayout()
        topo.setSpacing(GAP_MD)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel(title)
        titulo.setObjectName("CardTitle")
        titulo.setWordWrap(True)
        descricao = QLabel(subtitle)
        descricao.setObjectName("CardSubtitle")
        descricao.setWordWrap(True)
        textos.addWidget(titulo)
        textos.addWidget(descricao)
        topo.addLayout(textos, stretch=1)

        self.secondary_button = secondary_button(secondary_label, secondary_icon)
        self.secondary_button.clicked.connect(self.secondary_clicked.emit)
        topo.addWidget(self.secondary_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.primary_button = primary_button(primary_label, primary_icon)
        self.primary_button.clicked.connect(self.primary_clicked.emit)
        topo.addWidget(self.primary_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        hero.body.addLayout(topo)
        self.body.addWidget(hero)

        self.session_banner = Banner(
            "info",
            "Conecte-se ao NetBox",
            "As ações desta página ficam disponíveis depois que o ambiente for lido.",
        )
        self.body.addWidget(self.session_banner)

        self.inventory_banner = Banner(
            "info",
            "Carregando inventário de devices",
            "Serve para conferir o site de cada link existente. A importação de câmeras "
            "não depende disso.",
        )
        self.inventory_banner.hide()
        if needs_inventory:
            self.body.addWidget(self.inventory_banner)

        etapas_card = Card()
        etapas_card.body.addWidget(
            SectionHeader("Como funciona", "Quatro etapas, com revisão antes de qualquer escrita.")
        )
        etapas_card.body.addWidget(Divider())
        for indice, etapa in enumerate(steps, start=1):
            linha = QHBoxLayout()
            linha.setSpacing(GAP_MD)
            numero = QLabel(str(indice))
            numero.setObjectName("StepDot")
            numero.setProperty("state", "current")
            numero.setFixedSize(26, 26)
            numero.setAlignment(Qt.AlignmentFlag.AlignCenter)
            linha.addWidget(numero, alignment=Qt.AlignmentFlag.AlignTop)

            bloco = QVBoxLayout()
            bloco.setSpacing(1)
            titulo_etapa = QLabel(etapa.title)
            titulo_etapa.setProperty("muted", "true")
            fonte = titulo_etapa.font()
            fonte.setBold(True)
            titulo_etapa.setFont(fonte)
            texto = QLabel(etapa.text)
            texto.setProperty("faint", "true")
            texto.setWordWrap(True)
            bloco.addWidget(titulo_etapa)
            bloco.addWidget(texto)
            linha.addLayout(bloco, stretch=1)
            etapas_card.body.addLayout(linha)
        self.body.addWidget(etapas_card)

        regras = Card()
        regras.body.addWidget(
            SectionHeader("O que o app garante", "Regras aplicadas pelo plano, não pela tela.")
        )
        regras.body.addWidget(Divider())
        for nota in notes:
            linha = QHBoxLayout()
            linha.setSpacing(GAP_MD)
            icone = QLabel()
            icone.setFixedSize(18, 18)
            self._note_icon_labels.append((icone, nota.kind))
            linha.addWidget(icone, alignment=Qt.AlignmentFlag.AlignTop)

            bloco = QVBoxLayout()
            bloco.setSpacing(1)
            titulo_nota = QLabel(nota.title)
            titulo_nota.setProperty("muted", "true")
            fonte = titulo_nota.font()
            fonte.setBold(True)
            titulo_nota.setFont(fonte)
            texto = QLabel(nota.text)
            texto.setProperty("faint", "true")
            texto.setWordWrap(True)
            bloco.addWidget(titulo_nota)
            bloco.addWidget(texto)
            linha.addLayout(bloco, stretch=1)
            regras.body.addLayout(linha)
        self.body.addWidget(regras)
        self.body.addStretch(1)

        self.set_ready(False)
        self.apply_theme(theme_mod.palette())

    def set_ready(self, ready: bool) -> None:
        self._connected = ready
        self.session_banner.setVisible(not ready)
        if not ready:
            self._inventory_loading = False
            self.inventory_banner.hide()
        self._update_actions()

    def set_inventory_loading(self, loading: bool) -> None:
        """Mostra que o inventario de devices esta sendo lido, e segura o clique.

        So o fluxo de links usa isso. A acao continua clicavel antes do primeiro
        pedido: e o clique que dispara a leitura (e explica a espera).
        """
        if not self._needs_inventory:
            return
        self._inventory_loading = loading
        self.inventory_banner.setVisible(loading and self._connected)
        self._update_actions()

    def _update_actions(self) -> None:
        habilitado = self._connected and not self._inventory_loading
        self.primary_button.setEnabled(habilitado)
        self.secondary_button.setEnabled(habilitado)

    def apply_theme(self, palette) -> None:
        self.primary_button.setIcon(
            icons.icon(self._primary_icon, palette.on_accent, 16)
        )
        self.primary_button.setIconSize(QSize(16, 16))
        self.secondary_button.setIcon(
            icons.icon(self._secondary_icon, palette.text_muted, 16)
        )
        self.secondary_button.setIconSize(QSize(16, 16))
        for label, kind in self._note_icon_labels:
            nome = "check" if kind == "success" else "alert"
            label.setPixmap(icons.pixmap(nome, palette.kind_color(kind), 18))


class ImportPage(WorkflowPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Importar câmeras e switches",
            subtitle=(
                "Uma planilha por vez. O app lê, valida e mostra o plano completo antes "
                "de gravar qualquer objeto no NetBox."
            ),
            steps=(
                Step(
                    "Origem",
                    "Escolha o arquivo .xlsx ou .csv. As listas de Site e Papel vêm do NetBox.",
                ),
                Step(
                    "Revisão",
                    "Cada linha aparece como pronta, pendente de referência ou com erro — "
                    "com busca e ordenação na tabela.",
                ),
                Step(
                    "Envio",
                    "O botão de importar só libera quando não há erro, referência pendente "
                    "ou campo obrigatório sem valor. O progresso é por device.",
                ),
                Step(
                    "Resumo",
                    "Criados, atualizados, sem mudança, erros e avisos, com o caminho do "
                    "relatório em log, JSON e CSV.",
                ),
            ),
            notes=(
                Note(
                    "success",
                    "Idempotente",
                    "Cada objeto passa por GET antes de POST ou PATCH: rodar a mesma "
                    "planilha de novo não duplica nada.",
                ),
                Note(
                    "success",
                    "Rede em passos independentes",
                    "Interface, IP e primary_ip4 são etapas separadas. Falha em uma vira "
                    "aviso e o device permanece gravado.",
                ),
                Note(
                    "warning",
                    "Referências só com confirmação",
                    "Fabricante e device-type ausentes não são criados em silêncio: o app "
                    "pede confirmação e mostra o que vai criar.",
                ),
            ),
            primary_label="Importar planilha",
            secondary_label="Baixar planilha modelo",
            primary_icon="import",
            secondary_icon="download",
            parent=parent,
        )


class LinksPage(WorkflowPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Links IP por site",
            subtitle=(
                "Bloco público, bloco LAN e o endereço do roteador no enlace. O device é "
                "reaproveitado quando existe e criado quando não existe."
            ),
            steps=(
                Step(
                    "Origem",
                    "Planilha de links com Site, Device, Bloco público, Interface e IP do link.",
                ),
                Step(
                    "Revisão",
                    "O plano mostra prefixo, IP e situação linha a linha — inclusive IP "
                    "deduzido, que aparece como aviso.",
                ),
                Step(
                    "Envio",
                    "Prefixos, interface e IP são escritos de forma idempotente; falha de "
                    "prefixo vira aviso e não impede o IP.",
                ),
                Step(
                    "Resumo",
                    "Links criados, atualizados e com aviso, devices criados e o relatório "
                    "próprio da importação de links.",
                ),
            ),
            notes=(
                Note(
                    "success",
                    "Escopo no formato da instância",
                    "O app lê o OPTIONS do endpoint e usa scope_type/scope_id ou site, "
                    "conforme a versão do NetBox.",
                ),
                Note(
                    "success",
                    "primary_ip4 preservado",
                    "O IP do link não troca o endereço de gerência: o primário só é "
                    "definido quando o device ainda não tem um.",
                ),
                Note(
                    "warning",
                    "Bloco LAN repetido é aviso",
                    "Dois links do mesmo site podem compartilhar o mesmo /24. Bloco "
                    "público e IP repetidos, não.",
                ),
            ),
            primary_label="Importar links",
            secondary_label="Baixar modelo de links",
            primary_icon="link",
            secondary_icon="download",
            needs_inventory=True,
            parent=parent,
        )
