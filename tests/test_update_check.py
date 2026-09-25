"""Testes do worker de checagem de atualizacoes (app/update_check.py).

Cobrem o que o usuario sente:

- avisa quando ha versao mais nova, com o Release inteiro (inclusive setup_url);
- nao avisa quando a versao e a mesma;
- **falha silenciosa**: sem internet e o caso normal do analista em campo, entao
  a checagem nao pode avisar nada nem deixar a excecao escapar.

O `buscar_ultima_release` e substituido por um falso: nenhum teste aqui toca a rede.
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import update_check  # noqa: E402
from app.update_check import UpdateCheckWorker  # noqa: E402
from app.updater import Release  # noqa: E402
from app.version import __version__  # noqa: E402

_app = QApplication.instance() or QApplication([])


def release(versao: str, setup_url: str | None = None) -> Release:
    """Atalho para montar um Release de teste."""
    return Release(
        versao=versao,
        page_url=f"https://github.com/lucasdaniel2201/netbox-device-importer/releases/tag/v{versao}",
        setup_url=setup_url,
    )


class UpdateCheckTestCase(unittest.TestCase):
    def setUp(self):
        self.worker = UpdateCheckWorker()
        self.avisos = []
        self.worker.available.connect(self.avisos.append)

    def patch(self, func):
        return mock.patch.object(update_check, "buscar_ultima_release", side_effect=func)


class TestAviso(UpdateCheckTestCase):
    def test_avisa_quando_ha_versao_mais_nova(self):
        with self.patch(lambda: release("99.0.0", "https://exemplo/setup.exe")):
            self.worker.check()

        self.assertEqual(len(self.avisos), 1)
        self.assertEqual(self.avisos[0].versao, "99.0.0")
        self.assertEqual(self.avisos[0].setup_url, "https://exemplo/setup.exe")

    def test_nao_avisa_quando_a_versao_e_a_mesma(self):
        """O caso do app ja atualizado: nao pode incomodar o usuario."""
        with self.patch(lambda: release(__version__)):
            self.worker.check()

        self.assertFalse(self.avisos)

    def test_nao_avisa_quando_a_remota_e_mais_velha(self):
        with self.patch(lambda: release("0.0.1")):
            self.worker.check()

        self.assertFalse(self.avisos)


class TestFalhaSilenciosa(UpdateCheckTestCase):
    def test_falha_de_rede_nao_avisa_nem_levanta(self):
        """Sem internet e o caso normal do analista, nao um erro para mostrar."""
        with self.patch(RuntimeError("sem conexao")):
            self.worker.check()

        self.assertFalse(self.avisos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
