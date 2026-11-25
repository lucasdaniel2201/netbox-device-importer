"""Janela fantasma: nenhum widget pode aparecer como janela de nivel superior.

Sintoma relatado: ao abrir o app, tres ou quatro janelinhas minusculas piscavam no
centro da tela, sem conteudo.

Causa: `setVisible(True)` num widget que ainda **nao tem pai**. O QLabel era criado
solto, recebia `setVisible(True)` e so depois entrava num layout - e o Qt, vendo um
widget visivel sem pai, o tratava como janela de nivel superior e a mostrava de
verdade. Eram os 12 subtitulos de `SectionHeader` (mais os `StatTile`), mostrados
um a um durante a montagem da interface.

Este teste reproduz a condicao: monta a casca inteira e falha se qualquer widget
se mostrar como janela antes da janela principal.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QObject  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app import main as main_mod, theme  # noqa: E402
from app.shell import Shell  # noqa: E402
from app.ui.components import Banner, SectionHeader, StatTile  # noqa: E402

_app = QApplication.instance() or QApplication([])

_FAMILIA = main_mod.load_brand_fonts()
theme.apply(_app, _FAMILIA, "dark")


class EspiaoDeJanelas(QObject):
    """Registra todo widget que o Qt mostra como janela de nivel superior."""

    def __init__(self) -> None:
        super().__init__()
        self.mostrados: list[str] = []

    def instalar(self) -> None:
        # Instalar o filtro na aplicacao faz o Qt entregar TODO evento de Show,
        # inclusive os de widgets que ainda nao tem pai.
        _app.installEventFilter(self)

    def remover(self) -> None:
        _app.removeEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget):
            if obj.isWindow():
                self.mostrados.append(
                    f"{type(obj).__name__}(objectName={obj.objectName()!r})"
                )
        return False


class TestSemJanelasFantasma(unittest.TestCase):
    def setUp(self):
        self.espiao = EspiaoDeJanelas()

    def tearDown(self):
        self.espiao.remover()
        for widget in QApplication.topLevelWidgets():
            widget.close()

    def _widgets_mostrados(self, construir) -> list[str]:
        self.espiao.instalar()
        # A referencia e mantida ate o fim da medicao: sem ela o coletor pode
        # destruir o widget no meio do `processEvents` e a janela nao aparecer.
        self._montado = construir()
        _app.processEvents()
        self.espiao.remover()
        return self.espiao.mostrados

    def test_section_header_com_subtitulo_nao_abre_janela(self):
        mostrados = self._widgets_mostrados(
            lambda: SectionHeader("Titulo", "Subtitulo que aparece")
        )
        self.assertEqual(mostrados, [], f"janelas criadas: {mostrados}")

    def test_section_header_sem_subtitulo_nao_abre_janela(self):
        mostrados = self._widgets_mostrados(lambda: SectionHeader("Titulo", ""))
        self.assertEqual(mostrados, [], f"janelas criadas: {mostrados}")

    def test_subtitulo_vazio_continua_escondido(self):
        cabecalho = SectionHeader("Titulo", "")
        self.assertTrue(cabecalho.subtitle_label.isHidden())
        cabecalho.set_subtitle("Agora tem texto")
        self.assertFalse(cabecalho.subtitle_label.isHidden())
        cabecalho.set_subtitle("")
        self.assertTrue(cabecalho.subtitle_label.isHidden())

    def test_stat_tile_e_banner_nao_abrem_janela(self):
        casos = {
            "StatTile com hint": lambda: StatTile("Sites", "12", "lidos agora"),
            "StatTile sem hint": lambda: StatTile("Sites", "12", ""),
            "Banner com texto": lambda: Banner("info", "Titulo", "Texto do aviso"),
            "Banner sem texto": lambda: Banner("info", "", ""),
        }
        for nome, construir in casos.items():
            with self.subTest(caso=nome):
                self.espiao.mostrados.clear()
                mostrados = self._widgets_mostrados(construir)
                self.assertEqual(mostrados, [], f"{nome} criou janelas: {mostrados}")

    def test_montar_a_casca_nao_abre_janela_nenhuma(self):
        """A casca inteira: e nela que os 12 subtitulos apareciam."""
        mostrados = self._widgets_mostrados(Shell)
        self.assertEqual(mostrados, [], f"janelas criadas ao montar a casca: {mostrados}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
