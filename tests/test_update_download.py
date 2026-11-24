"""Testes do download do instalador de atualizacao (app/update_download.py).

O download e o unico ponto do app que baixa E executa um binario, entao os testes
cobrem a fronteira de confianca (URL so do GitHub) e o caminho feliz/infeliz do
worker. `requests.get` e o agendamento da instalacao sao substituidos: nenhum
teste toca a rede nem abre um Setup.exe de verdade.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import update_download  # noqa: E402
from app.update_download import UpdateDownloadWorker  # noqa: E402

_app = QApplication.instance() or QApplication([])


class FakeResponse:
    """Resposta falsa de `requests.get` com `iter_content` em memoria."""

    def __init__(
        self,
        blocos: list[bytes],
        headers: dict | None = None,
        url: str = "https://github.com/owner/repo/releases/download/v1/Setup.exe",
    ) -> None:
        self._blocos = blocos
        self.headers = headers or {}
        self.url = url

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int):
        # chunk_size e ignorado de proposito: o worker e quem controla o tamanho
        # real; aqui so devolvemos os pedacos que o teste preparou.
        yield from self._blocos

    def close(self) -> None:
        pass


class TestValidacaoUrl(unittest.TestCase):
    def test_aceita_hosts_do_github(self):
        validas = [
            "https://github.com/lucasdaniel2201/netbox-device-importer/releases/download/v1/ImportadorCamerasSetup-1.0.0.exe",
            "https://api.github.com/repos/lucasdaniel2201/netbox-device-importer/releases/latest",
            "https://objects.githubusercontent.com/algum/asset/ImportadorCamerasSetup-1.0.0.exe",
            "https://raw.githubusercontent.com/lucasdaniel2201/netbox-device-importer/main/Setup.exe",
        ]
        for url in validas:
            with self.subTest(url=url):
                update_download.validar_url_download(url)

    def test_recusa_host_fora_do_github(self):
        invalidas = [
            "https://exemplo.com/setup.exe",
            # O ponto depois de github.com muda o dominio: nao e o GitHub.
            "https://github.com.evil.com/setup.exe",
            "https://githubusercontent.com.evil.com/setup.exe",
        ]
        for url in invalidas:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    update_download.validar_url_download(url)

    def test_recusa_http_mesmo_no_github(self):
        with self.assertRaises(ValueError):
            update_download.validar_url_download("http://github.com/owner/repo/Setup.exe")


class TestAgendamentoDaInstalacao(unittest.TestCase):
    """O Setup roda DEPOIS do app sair, senao o .exe em uso nao pode ser trocado."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_script_espera_o_pid_antes_de_abrir_o_setup(self):
        setup = self.tmp / "ImportadorCamerasSetup-1.2.1.exe"
        with (
            mock.patch.object(update_download.tempfile, "gettempdir", return_value=str(self.tmp)),
            mock.patch.object(update_download.subprocess, "Popen") as popen,
        ):
            script = update_download.agendar_instalacao_apos_sair(setup, pid=4242)

        conteudo = script.read_text(encoding="ascii")
        # Espera o processo do app terminar, senao o Windows mantem o .exe travado
        # e o Inno Setup falha ao substitui-lo.
        self.assertIn("Wait-Process", conteudo)
        self.assertIn("-Id 4242", conteudo)
        self.assertIn("Start-Process", conteudo)
        # O caminho do Setup e passado por argumento e repassado por variavel de
        # ambiente (o .cmd fica em ASCII puro).
        self.assertIn("%~1", conteudo)
        self.assertIn("$env:SETUP", conteudo)
        args = popen.call_args[0][0]
        self.assertEqual(args[-1], str(setup))

    def test_processo_e_destacado_para_sobreviver_ao_app(self):
        setup = self.tmp / "Setup.exe"
        with (
            mock.patch.object(update_download.tempfile, "gettempdir", return_value=str(self.tmp)),
            mock.patch.object(update_download.subprocess, "Popen") as popen,
        ):
            update_download.agendar_instalacao_apos_sair(setup, pid=1)

        flags = popen.call_args[1]["creationflags"]
        self.assertTrue(flags & update_download.subprocess.DETACHED_PROCESS)
        self.assertTrue(flags & update_download.subprocess.CREATE_NEW_PROCESS_GROUP)


class TestDownloadWorker(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.worker = UpdateDownloadWorker()
        self.progresso: list[tuple[int, int]] = []
        self.finalizados: list[str] = []
        self.falhas: list[str] = []
        # `progress` carrega dois inteiros; o append de lista so aceita um, entao
        # embrulhamos para registrar o par como uma tupla.
        self.worker.progress.connect(
            lambda baixados, total: self.progresso.append((baixados, total))
        )
        self.worker.finished.connect(self.finalizados.append)
        self.worker.failed.connect(self.falhas.append)

    def tearDown(self):
        self._tmp.cleanup()

    def _patch_get(self, resposta):
        return mock.patch.object(update_download.requests, "get", return_value=resposta)

    def test_download_grava_o_arquivo_certo(self):
        resposta = FakeResponse([b"abc", b"def"], headers={"Content-Length": "6"})
        with (
            self._patch_get(resposta),
            mock.patch.object(update_download.tempfile, "gettempdir", return_value=str(self.tmp)),
            mock.patch.object(update_download, "agendar_instalacao_apos_sair") as agendar,
        ):
            self.worker.download(
                "https://github.com/lucasdaniel2201/netbox-device-importer/releases/download/"
                "v1/ImportadorCamerasSetup-1.0.0.exe"
            )

        esperado = self.tmp / update_download.DOWNLOAD_DIR_NAME / "ImportadorCamerasSetup-1.0.0.exe"
        self.assertEqual(self.finalizados, [str(esperado)])
        self.assertTrue(esperado.exists())
        self.assertEqual(esperado.read_bytes(), b"abcdef")
        # A instalacao e AGENDADA (nao aberta na hora): com o app aberto o Setup
        # nao conseguiria substituir o .exe.
        agendar.assert_called_once_with(esperado)
        self.assertEqual(self.progresso, [(3, 6), (6, 6)])
        self.assertFalse(self.falhas)

    def test_falha_de_rede_emite_erro_e_nao_agenda(self):
        with (
            mock.patch.object(
                update_download.requests, "get", side_effect=RuntimeError("sem conexao")
            ),
            mock.patch.object(update_download.tempfile, "gettempdir", return_value=str(self.tmp)),
            mock.patch.object(update_download, "agendar_instalacao_apos_sair") as agendar,
        ):
            self.worker.download("https://github.com/owner/repo/ImportadorCamerasSetup.exe")

        self.assertFalse(self.finalizados)
        self.assertEqual(len(self.falhas), 1)
        self.assertIn("sem conexao", self.falhas[0])
        agendar.assert_not_called()

    def test_url_invalida_emite_erro_sem_tocar_a_rede(self):
        with (
            mock.patch.object(update_download.requests, "get") as get,
            mock.patch.object(update_download, "agendar_instalacao_apos_sair") as agendar,
        ):
            self.worker.download("https://exemplo.com/setup.exe")

        self.assertEqual(len(self.falhas), 1)
        self.assertIn("nao e do GitHub", self.falhas[0])
        get.assert_not_called()
        agendar.assert_not_called()

    def test_redirect_para_fora_do_github_emite_erro_sem_gravar(self):
        resposta = FakeResponse([b"abc"], url="https://exemplo.com/setup.exe")
        with (
            self._patch_get(resposta),
            mock.patch.object(update_download.tempfile, "gettempdir", return_value=str(self.tmp)),
            mock.patch.object(update_download, "agendar_instalacao_apos_sair") as agendar,
        ):
            self.worker.download("https://github.com/owner/repo/ImportadorCamerasSetup.exe")

        self.assertEqual(len(self.falhas), 1)
        self.assertIn("nao e do GitHub", self.falhas[0])
        self.assertFalse(self.finalizados)
        agendar.assert_not_called()
        # A validacao do destino final acontece antes de _destino criar a pasta.
        self.assertFalse((self.tmp / update_download.DOWNLOAD_DIR_NAME).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
