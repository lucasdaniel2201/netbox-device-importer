"""Testa que a versao do aplicativo esta consistente nos tres lugares.

A versao vive em tres arquivos que sao atualizados a mao:
  1. app/version.py      -> __version__ = "1.0.0"        (Python, 3 componentes)
  2. instalador.iss       -> #define AppVersion "1.0.0"   (Inno Setup, 3 componentes)
  3. version_info.txt     -> filevers=(1, 0, 0, 0)       (Windows, 4 componentes)

O version_info.txt usa quatro componentes porque e convencao do Windows
(MAJOR.MINOR.PATCH.BUILD), enquanto Python e o Inno Setup usam tres.
A comparacao aqui usa so os tres primeiros para ignorar o BUILD.

Se alguem atualizar a versao em um lugar e esquecer dos outros, este teste
fala qual arquivo ficou para tras.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.updater import parse_version  # noqa: E402
from app.version import __version__  # noqa: E402

# Arquivos onde a versao deve estar registrada.
_PATH_INSTALADOR = ROOT / "instalador.iss"
_PATH_VERSION_INFO = ROOT / "version_info.txt"


def _ler_conteudo(caminho: Path) -> str:
    """Le um arquivo e retorna o conteudo como string."""
    return caminho.read_text(encoding="utf-8")


class TestConsistenciaDeVersao(unittest.TestCase):
    """As tres fontes de versao devem apontar para a mesma coisa."""

    def test_o_version_info_tem_os_arquivos_no_lugar(self):
        """Garante que os dois arquivos existem — falha legivel se alguém mover."""
        self.assertTrue(
            _PATH_INSTALADOR.exists(),
            f"instalador.iss nao encontrado em {_PATH_INSTALADOR}",
        )
        self.assertTrue(
            _PATH_VERSION_INFO.exists(),
            f"version_info.txt nao encontrado em {_PATH_VERSION_INFO}",
        )

    def test_a_versao_do_python_e_valida(self):
        """parse_version nao levanta e __version__ so tem digitos e pontos."""
        # So digitos e pontos, sem lixo.
        self.assertRegex(
            __version__,
            r"^\d+\.\d+\.\d+$",
            f"__version__ = {__version__!r} nao segue o formato MAJOR.MINOR.PATCH",
        )
        # parse_version nao levanta excecao.
        partes = parse_version(__version__)
        self.assertEqual(len(partes), 3)

    def test_as_tres_versoes_concordam(self):
        """Versao do Python, do Inno Setup e do version_info sao iguais (3 componentes)."""
        # --- Fonte 1: Python (ja importado como __version__) ---
        versao_python = parse_version(__version__)

        # --- Fonte 2: instalador.iss ---
        conteudo_iss = _ler_conteudo(_PATH_INSTALADOR)
        match_iss = re.search(
            r'#define\s+AppVersion\s+"([^"]+)"',
            conteudo_iss,
            re.MULTILINE,
        )
        self.assertIsNotNone(
            match_iss,
            "Padrao '#define AppVersion ...' nao encontrado em instalador.iss",
        )
        versao_iss = parse_version(match_iss.group(1))

        # --- Fonte 3: version_info.txt (FixedFileInfo.filevers) ---
        conteudo_vi = _ler_conteudo(_PATH_VERSION_INFO)
        match_vi = re.search(
            r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*\d+\)",
            conteudo_vi,
            re.MULTILINE,
        )
        self.assertIsNotNone(
            match_vi,
            "Padrao 'filevers=(...)' nao encontrado em version_info.txt",
        )
        versao_vi = (int(match_vi.group(1)), int(match_vi.group(2)), int(match_vi.group(3)))

        # --- Comparacao ---
        self.assertEqual(
            versao_python,
            versao_iss,
            (
                f"Versao do Python ({__version__}) difere da do Inno Setup "
                f"({match_iss.group(1)}). Atualize ambos para a mesma versao."
            ),
        )
        self.assertEqual(
            versao_python,
            versao_vi,
            (
                f"Versao do Python ({__version__}) difere da do version_info.txt "
                f"({match_vi.group(1)}.{match_vi.group(2)}.{match_vi.group(3)}). "
                f"Atualize ambos para a mesma versao."
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
