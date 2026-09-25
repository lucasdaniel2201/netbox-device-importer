"""Testes da comparacao de versoes (app/updater.py).

Cobrem o caso que quebra a maioria dos verificadores de atualizacao: comparar a
versao como texto diz que "1.10.0" e **menor** que "1.9.0", e o aviso nunca
apareceria justamente na passagem da 1.9 para a 1.10. Comparar tuplas de inteiros
resolve, porque o Python compara elemento a elemento, da esquerda para a direita.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.updater import ha_atualizacao, parse_version  # noqa: E402


class TestParseVersion(unittest.TestCase):
    def test_aceita_com_e_sem_v(self):
        self.assertEqual(parse_version("v1.10.0"), (1, 10, 0))
        self.assertEqual(parse_version("1.10.0"), (1, 10, 0))

    def test_separa_os_numeros_na_ordem(self):
        self.assertEqual(parse_version("v2.0.1"), (2, 0, 1))


class TestHaAtualizacao(unittest.TestCase):
    def test_1_10_e_mais_nova_que_1_9(self):
        self.assertTrue(ha_atualizacao("1.9.0", "1.10.0"))
        self.assertFalse(ha_atualizacao("1.10.0", "1.9.0"))

    def test_versao_igual_nao_e_atualizacao(self):
        self.assertFalse(ha_atualizacao("1.0.0", "1.0.0"))

    def test_salto_de_versao_major(self):
        self.assertTrue(ha_atualizacao("1.9.0", "2.0.0"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
