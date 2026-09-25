"""Testes do cofre do token (app/credentials.py) e higiene de credenciais.

O ponto central: o token guardado **nao** pode ficar em texto claro no disco, e o
arquivo nao pode servir em outra conta/maquina (e o que o DPAPI garante).
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import credentials  # noqa: E402

SEGREDO = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
HEX_40 = re.compile(r"\b[0-9a-fA-F]{40}\b")
DPAPI = credentials.is_available()


class CredentialsTestCase(unittest.TestCase):
    """Nunca escreve no arquivo real do usuario: aponta para uma pasta temporaria."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patch = mock.patch.object(
            credentials, "token_path", lambda: self.tmp / "token.dat"
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()


class TestProtecaoDoToken(CredentialsTestCase):
    @unittest.skipUnless(DPAPI, "DPAPI indisponivel (fora do Windows)")
    def test_guarda_e_recupera(self):
        credentials.save_token(SEGREDO)
        self.assertEqual(credentials.load_token(), SEGREDO)
        self.assertTrue(credentials.has_token())

    @unittest.skipUnless(DPAPI, "DPAPI indisponivel (fora do Windows)")
    def test_nao_fica_em_texto_claro(self):
        """E o motivo de existir: abrir o arquivo nao revela o token."""
        credentials.save_token(SEGREDO)
        bruto = credentials.token_path().read_bytes()
        self.assertNotIn(SEGREDO.encode(), bruto)
        self.assertGreater(len(bruto), len(SEGREDO))

    @unittest.skipUnless(DPAPI, "DPAPI indisponivel (fora do Windows)")
    def test_cifras_do_mesmo_texto_sao_diferentes(self):
        self.assertNotEqual(credentials.protect("token-um"), credentials.protect("token-um"))

    @unittest.skipUnless(DPAPI, "DPAPI indisponivel (fora do Windows)")
    def test_arquivo_corrompido_nao_derruba(self):
        credentials.token_path().write_bytes(b"isto-nao-e-um-blob-dpapi")
        self.assertEqual(credentials.load_token(), "")

    @unittest.skipUnless(DPAPI, "DPAPI indisponivel (fora do Windows)")
    def test_blob_alterado_nao_vira_token(self):
        cifrado = credentials.protect("um-token")
        with self.assertRaises(credentials.CredentialError):
            credentials.unprotect(cifrado[:-1])

    def test_sem_arquivo_devolve_vazio(self):
        self.assertEqual(credentials.load_token(), "")
        self.assertFalse(credentials.has_token())

    def test_token_vazio_e_recusado(self):
        with self.assertRaises(credentials.CredentialError):
            credentials.save_token("")

    def test_esquecer_apaga_o_arquivo(self):
        with mock.patch.object(credentials, "protect", lambda texto: b"cifrado"):
            credentials.save_token("t")
        self.assertTrue(credentials.token_path().exists())
        credentials.clear_token()
        self.assertFalse(credentials.token_path().exists())

    def test_esquecer_sem_arquivo_nao_quebra(self):
        credentials.clear_token()


class TestLocalDoArquivo(unittest.TestCase):
    def test_arquivo_fica_na_pasta_de_dados_do_usuario(self):
        """Nunca ao lado do .exe: pode ser pasta compartilhada ou somente leitura."""
        from app.paths import user_data_dir

        self.assertEqual(credentials.token_path().parent, user_data_dir())


class TestHigieneDeCredenciais(unittest.TestCase):
    """Nada de segredo versionado - regra do projeto desde o comeco."""

    def test_nao_existe_env(self):
        self.assertFalse((ROOT / ".env").exists())
        self.assertFalse((ROOT / ".env.example").exists())

    def test_nenhum_script_usa_dotenv(self):
        for script in list(ROOT.glob("*.py")) + list((ROOT / "app").glob("*.py")):
            with self.subTest(script=script.name):
                self.assertNotIn("dotenv", script.read_text(encoding="utf-8"))

    def test_nenhuma_senha_embutida(self):
        padrao = re.compile(r"""password\s*[=:]\s*["'][^"']+["']""")
        for script in list(ROOT.glob("*.py")) + list((ROOT / "app").glob("*.py")):
            with self.subTest(script=script.name):
                for linha in script.read_text(encoding="utf-8").splitlines():
                    if linha.strip().startswith("#"):
                        continue
                    self.assertIsNone(
                        padrao.search(linha), f"credencial embutida em {script.name}"
                    )

    def test_nenhum_token_de_api_embutido(self):
        """Token do NetBox tem 40 hexadecimais: nenhum pode estar no app nem nos builds.

        Nao varre tests/ de proposito: la os valores sao falsos, declarados no proprio
        teste - o que importa e nao haver token real no app nem nos arquivos de build.
        """
        alvos = [
            *ROOT.glob("*.py"),
            *ROOT.glob("*.md"),
            *ROOT.glob("*.spec"),
            *ROOT.glob("*.iss"),
            *(ROOT / "app").glob("*.py"),
        ]
        for caminho in alvos:
            with self.subTest(arquivo=caminho.name):
                self.assertIsNone(
                    HEX_40.search(caminho.read_text(encoding="utf-8", errors="ignore")),
                    f"possivel token embutido em {caminho.name}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
