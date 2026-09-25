"""Testes do spinner da tela de carregamento (app/loading.py).

Rodam em modo offscreen. O interessante aqui e que a animacao seja de fato uma
animacao (angulo avanca, volta ao inicio) e que o desenho nao quebre em nenhum
angulo - o spinner e desenhado com QPainter, sem asset empacotado.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import loading  # noqa: E402

_app = QApplication.instance() or QApplication([])


class TestSpinner(unittest.TestCase):
    def setUp(self):
        self.spinner = loading.Spinner()

    def tearDown(self):
        self.spinner.stop()

    def test_comeca_parado(self):
        self.assertFalse(self.spinner.is_running())

    def test_start_e_stop(self):
        self.spinner.start()
        self.assertTrue(self.spinner.is_running())
        self.spinner.stop()
        self.assertFalse(self.spinner.is_running())

    def test_start_duas_vezes_nao_muda_nada(self):
        self.spinner.start()
        self.spinner.start()
        self.assertTrue(self.spinner.is_running())

    def test_angulo_avanca(self):
        inicial = self.spinner.angle
        self.spinner.advance()
        self.assertNotEqual(self.spinner.angle, inicial)

    def test_angulo_nunca_passa_de_uma_volta(self):
        for _ in range(200):
            self.spinner.advance()
            self.assertGreaterEqual(self.spinner.angle, 0.0)
            self.assertLess(self.spinner.angle, 360.0)

    def test_angulo_volta_ao_comeco(self):
        self.spinner._angle = 359.0
        self.spinner.advance()
        self.assertLess(self.spinner.angle, 10.0)

    def test_e_quadrado(self):
        self.assertEqual(self.spinner.width(), self.spinner.height())

    def test_desenha_em_varios_angulos(self):
        """Antialiasing + arco: nenhum angulo pode quebrar o desenho."""
        for _ in range(24):
            self.assertFalse(self.spinner.grab().isNull())
            self.spinner.advance()

    def test_tick_do_timer_move_o_angulo(self):
        self.spinner.start()
        self.spinner._timer.timeout.emit()
        self.assertNotEqual(self.spinner.angle, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
