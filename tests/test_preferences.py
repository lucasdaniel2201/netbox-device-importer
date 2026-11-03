"""Testes das preferencias locais (app/preferences.py).

Preferencia e conveniencia: arquivo corrompido, valor invalido ou pasta sem
permissao nao podem impedir o app de abrir. O tema cai no padrao.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import preferences  # noqa: E402


class TestPreferencias(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.arquivo = Path(self._tmp.name) / "preferences.json"
        self._patch = mock.patch.object(preferences, "preferences_path", lambda: self.arquivo)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_padrao_e_escuro(self):
        self.assertEqual(preferences.theme_mode(), "dark")

    def test_grava_e_le_o_tema(self):
        preferences.set_theme_mode("light")
        self.assertEqual(preferences.theme_mode(), "light")
        self.assertEqual(json.loads(self.arquivo.read_text())["theme"], "light")

    def test_grava_sem_apagar_outras_chaves(self):
        preferences.update(theme="light", outra="valor")
        preferences.update(theme="dark")
        dados = json.loads(self.arquivo.read_text())
        self.assertEqual(dados["theme"], "dark")
        self.assertEqual(dados["outra"], "valor")

    def test_arquivo_corrompido_cai_no_padrao(self):
        self.arquivo.write_text("{isto nao e json")
        self.assertEqual(preferences.load(), {})
        self.assertEqual(preferences.theme_mode(), "dark")

    def test_tema_invalido_cai_no_padrao(self):
        self.arquivo.write_text(json.dumps({"theme": "solar"}))
        self.assertEqual(preferences.theme_mode(), "dark")

    def test_set_theme_ignora_valor_invalido(self):
        preferences.set_theme_mode("solar")
        self.assertFalse(self.arquivo.exists())

    def test_falha_de_escrita_nao_levanta(self):
        with mock.patch.object(Path, "write_text", side_effect=OSError("disco cheio")):
            preferences.update(theme="light")
        self.assertEqual(preferences.theme_mode(), "dark")


if __name__ == "__main__":
    unittest.main(verbosity=2)
