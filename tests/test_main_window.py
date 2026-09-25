"""Testes do fluxo de abertura da janela (app/main_window.py).

O que importa aqui e o que o usuario pediu: com token guardado, o app **nao** mostra
a tela de login - vai direto ao carregamento e conecta sozinho; e o token digitado
passa a ficar guardado. A conexao de rede e substituida por um espiao.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import (  # noqa: E402
    credentials,
    session as session_mod,
    update_check,
)
from app.config import NETBOX_URL  # noqa: E402
from app.main_window import LOADING_PAGE, LOGIN_PAGE, MainWindow  # noqa: E402

_app = QApplication.instance() or QApplication([])


class MainWindowTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._token_patch = mock.patch.object(
            credentials, "token_path", lambda: self.tmp / "token.dat"
        )
        self._token_patch.start()

        # Espiao no lugar da conexao: nada de rede nos testes.
        self.chamadas: list[tuple] = []

        def espiao(_worker, url, token, verify_tls):
            self.chamadas.append((url, token, verify_tls))

        self._connect_patch = mock.patch.object(
            session_mod.SessionWorker, "connect_netbox", espiao
        )
        self._connect_patch.start()

        # Espiao no lugar do worker de atualizacao: evita requicao HTTP real
        # para api.github.com dentro do __init__ da MainWindow.
        self._update_patch = mock.patch.object(
            update_check.UpdateCheckWorker, "check", lambda _worker: None
        )
        self._update_patch.start()
        self.window: MainWindow | None = None

    def tearDown(self):
        if self.window is not None:
            self.window.close()
            self.window = None
        self._connect_patch.stop()
        self._update_patch.stop()
        self._token_patch.stop()
        self._tmp.cleanup()

    def abrir(self) -> MainWindow:
        self.window = MainWindow()
        return self.window

    def esperar_chamadas(self, quantas: int = 1, timeout: float = 2.0) -> bool:
        """O pedido de conexao e entregue na thread do worker: espera chegar."""
        fim = time.monotonic() + timeout
        while len(self.chamadas) < quantas and time.monotonic() < fim:
            _app.processEvents()
            time.sleep(0.01)
        return len(self.chamadas) >= quantas


class TestAbertura(MainWindowTestCase):
    def test_sem_token_guardado_abre_no_login(self):
        window = self.abrir()
        self.assertEqual(window._stack.currentIndex(), LOGIN_PAGE)
        self.assertEqual(self.chamadas, [])

    def test_com_token_guardado_vai_direto_ao_carregamento(self):
        credentials.save_token("token-guardado")
        window = self.abrir()

        self.assertEqual(window._stack.currentIndex(), LOADING_PAGE)
        self.assertTrue(window.spinner.is_running())
        self.assertTrue(self.esperar_chamadas(), "o worker nao recebeu o pedido")
        url, token, verify_tls = self.chamadas[0]
        self.assertEqual(url, NETBOX_URL)
        self.assertEqual(token, "token-guardado")
        self.assertTrue(verify_tls)

    def test_token_digitado_e_guardado_depois_de_conectar(self):
        window = self.abrir()
        window.token_edit.setText("token-novo")
        window._on_connect_clicked()

        self.assertEqual(window._stack.currentIndex(), LOADING_PAGE)
        self.assertTrue(self.esperar_chamadas())
        self.assertEqual(self.chamadas[-1][1], "token-novo")

        window._on_connected({})
        self.assertEqual(credentials.load_token(), "token-novo")
        self.assertTrue(window._saved_token)

    def test_token_guardado_que_funciona_nao_e_regravado(self):
        credentials.save_token("token-guardado")
        window = self.abrir()
        window._on_connected({})
        self.assertEqual(credentials.load_token(), "token-guardado")

    def test_conectar_sem_token_digitado_avisa(self):
        window = self.abrir()
        window.token_edit.setText("")
        window._on_connect_clicked()
        self.assertEqual(self.chamadas, [])
        self.assertIn("token", window.login_error_label.text().lower())

    def test_falha_do_token_guardado_volta_ao_login_com_aviso(self):
        credentials.save_token("token-velho")
        window = self.abrir()
        window._on_connect_failed("HTTP 403 (token expirado)")

        self.assertEqual(window._stack.currentIndex(), LOGIN_PAGE)
        self.assertFalse(window.spinner.is_running())
        self.assertIn("nao funcionou", window.saved_note.text())
        self.assertIn("403", window.login_error_label.text())
        # O token continua guardado: so sai se o usuario pedir.
        self.assertEqual(credentials.load_token(), "token-velho")

    def test_esquecer_token_apaga_e_limpa_a_tela(self):
        credentials.save_token("token-velho")
        window = self.abrir()
        window._on_forget_token()
        self.assertFalse(credentials.has_token())
        self.assertEqual(window._saved_token, "")

    def test_aviso_de_conexao_lenta(self):
        window = self.abrir()
        window._go_loading()
        self.assertEqual(window.loading_hint.text(), "")
        window._show_slow_hint()
        self.assertIn("rede", window.loading_hint.text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
