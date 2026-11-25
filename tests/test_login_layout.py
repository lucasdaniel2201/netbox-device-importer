"""A tela de login nao pode comprimir texto com quebra de linha.

Este defeito apareceu duas vezes (campo do servidor e passo a passo do token):
um QLabel com wordWrap reporta altura minima de UMA linha, o layout aperta em
janela baixa e as linhas do texto se sobrepoem. O teste compara, para cada
label visivel, a altura real com a altura que o texto precisa na largura atual.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel  # noqa: E402

from app import (  # noqa: E402
    main as main_mod,
    theme,
)
from app.pages.login_page import LoginPage  # noqa: E402

_app = QApplication.instance() or QApplication([])
# Mesma configuracao do app real. `load_brand_fonts` e obrigatorio: sem ele a
# familia "Inter" nao resolve (QFontInfo devolve vazio) e o Qt usa a fonte de
# fallback, cujas metricas dao altura diferente da que o usuario ve.
_app.setStyle("Fusion")
_FAMILIA = main_mod.load_brand_fonts()
_app.setFont(QFont(_FAMILIA, 10))
theme.apply(_app, _FAMILIA, "dark")

# Tamanhos reais de janela: a menor tela que o app aceita e telas comuns.
TAMANHOS = ((512, 817), (900, 700), (1024, 640), (1280, 880))


class TestSemSobreposicao(unittest.TestCase):
    def _labels_comprimidos(self, largura: int, altura: int) -> list[tuple[str, int, int]]:
        with mock.patch("app.pages.login_page.NETBOX_URL", "https://192.168.90.123"):
            page = LoginPage()
            page.resize(largura, altura)
            page.show()
            for _ in range(20):
                _app.processEvents()

            problemas = []
            for label in page.findChildren(QLabel):
                if not label.isVisible() or not label.wordWrap():
                    continue
                if len(label.text()) < 15:
                    continue
                necessario = label.heightForWidth(label.width())
                if necessario > label.height():
                    problemas.append((label.text()[:40], label.height(), necessario))
            page.close()
            page.deleteLater()
            return problemas

    def test_nenhum_texto_se_sobrepoe_em_nenhum_tamanho(self):
        for largura, altura in TAMANHOS:
            with self.subTest(tamanho=f"{largura}x{altura}"):
                problemas = self._labels_comprimidos(largura, altura)
                self.assertEqual(
                    problemas,
                    [],
                    "labels com altura menor que o texto precisa "
                    f"(altura real, altura necessaria): {problemas}",
                )


class TestRespiroDoAviso(unittest.TestCase):
    """O aviso de token guardado nao pode encostar no painel de passos.

    Ja esteve a -3px (sobreposto) porque os dois eram filhos soltos do layout do
    cartao. Agora o aviso e o botao vivem num bloco com margem propria.
    """

    def _gap(self, largura: int, altura: int) -> int:
        with mock.patch("app.pages.login_page.NETBOX_URL", "https://192.168.90.123"):
            page = LoginPage()
            # Ordem igual a do app: redimensiona, deixa o layout assentar e so
            # entao revela o aviso (esse e o caminho que a MainWindow percorre).
            page.resize(largura, altura)
            page.show()
            for _ in range(20):
                _app.processEvents()
            page.set_saved_token(True, "cifrado pelo Windows (DPAPI)")
            for _ in range(20):
                _app.processEvents()

            # O painel dos passos e o unico "Card" flat que contem o titulo
            # "Como obter o token". Filtrar por altura pegava o bloco do
            # servidor, que tambem e flat e mudava de altura com a fonte.
            painel = None
            for frame in page.findChildren(QFrame):
                if frame.objectName() != "Card":
                    continue
                titulos = [
                    lbl.text()
                    for lbl in frame.findChildren(QLabel)
                    if lbl.objectName() == "TokenStepsTitle"
                ]
                if titulos:
                    painel = frame
                    break
            self.assertIsNotNone(painel, "painel dos passos nao encontrado")

            # A margem de respiro mora no BLOCO (saved_block), entao a conta e da
            # base do painel ao topo do bloco, nao ao topo do label de aviso.
            base = painel.mapTo(page, painel.rect().bottomLeft()).y()
            topo_bloco = page.saved_block.mapTo(
                page, page.saved_block.rect().topLeft()
            ).y()
            page.close()
            page.deleteLater()
            return topo_bloco - base

    def test_aviso_nao_encosta_no_painel(self):
        # 1536x864 = 1920x1080 com 125% de escala, o caso relatado pelo usuario.
        for tamanho in ((1536, 864), (1536, 740), (1180, 820), (1024, 640)):
            with self.subTest(tamanho=f"{tamanho[0]}x{tamanho[1]}"):
                gap = self._gap(*tamanho)
                # 8px e o piso: o essencial e nao haver sobreposicao (gap
                # negativo). O valor exato varia com a fonte resolvida pelo Qt.
                self.assertGreaterEqual(
                    gap, 8, f"aviso a {gap}px do painel: nao pode encostar"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
