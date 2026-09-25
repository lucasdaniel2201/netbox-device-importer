"""Testes do cliente REST do NetBox (app/netbox_client.py).

Sem rede: a sessao do `requests` e substituida por respostas falsas. Cobrem os
pontos que mais quebram na pratica - barra final obrigatoria, paginacao (sem
`limit` so vem a primeira pagina), formato do header de autenticacao e leitura
das mensagens de erro.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import netbox_client as nb  # noqa: E402


class FakeResponse:
    """Resposta minima compativel com o que o cliente consome."""

    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text
        self.content = b"x" if payload is not None else b""

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("resposta sem JSON")
        return self._payload


def empty_page():
    return {"count": 0, "next": None, "previous": None, "results": []}


class ClientTestCase(unittest.TestCase):
    def client(self, token="t", **kwargs):
        return nb.NetBoxClient("https://nb.local", token, **kwargs)


class TestUrl(ClientTestCase):
    def test_barra_final_e_adicionada(self):
        self.assertEqual(nb.normalize_path("/api/dcim/devices"), "/api/dcim/devices/")

    def test_barra_final_unica(self):
        self.assertEqual(nb.normalize_path("/api/dcim/devices/"), "/api/dcim/devices/")
        self.assertEqual(nb.normalize_path("api/dcim/devices//"), "/api/dcim/devices/")

    def test_barra_inicial_e_adicionada(self):
        self.assertEqual(nb.normalize_path("api/status/"), "/api/status/")

    def test_base_url_sem_barra_final(self):
        self.assertEqual(nb.normalize_base_url("https://nb.local/"), "https://nb.local")

    def test_base_url_ganha_https(self):
        self.assertEqual(nb.normalize_base_url("192.168.90.123"), "https://192.168.90.123")

    def test_base_url_vazia_e_erro(self):
        with self.assertRaises(ValueError):
            nb.normalize_base_url("   ")

    def test_url_completa_do_endpoint(self):
        self.assertEqual(
            self.client()._full_url("/api/dcim/devices/"),
            "https://nb.local/api/dcim/devices/",
        )

    def test_caminho_de_detalhe(self):
        self.assertEqual(
            nb.detail_path("/api/dcim/devices/", 7), "/api/dcim/devices/7/"
        )


class TestAutenticacao(ClientTestCase):
    def test_token_obrigatorio(self):
        with self.assertRaises(ValueError):
            nb.NetBoxClient("https://nb.local", "   ")

    def test_header_usa_esquema_token(self):
        headers = self.client()._headers()
        self.assertEqual(headers["Authorization"], "Token t")
        self.assertEqual(headers["Accept"], "application/json")

    def test_troca_para_bearer_quando_token_falha(self):
        """Instancia 4.5+ espera `Bearer`; o cliente descobre isso sozinho."""
        client = self.client("abc")
        enviados = []
        respostas = iter(
            [
                FakeResponse(401, {"detail": "Invalid token."}),
                FakeResponse(200, {"netbox-version": "4.5.0"}),
            ]
        )

        def fake(method, url, **kwargs):
            enviados.append(kwargs["headers"]["Authorization"])
            return next(respostas)

        with mock.patch.object(client.session, "request", side_effect=fake):
            data = client.status()

        self.assertEqual(data["netbox-version"], "4.5.0")
        self.assertEqual(enviados, ["Token abc", "Bearer abc"])
        self.assertEqual(client.token_scheme, "Bearer")

    def test_esquema_travado_apos_sucesso(self):
        """Depois que um esquema funciona, um 403 nao deve trocar o header."""
        client = self.client("abc")
        enviados = []
        respostas = iter(
            [
                FakeResponse(200, empty_page()),
                FakeResponse(403, {"detail": "You do not have permission to perform this action."}),
            ]
        )

        def fake(method, url, **kwargs):
            enviados.append(kwargs["headers"]["Authorization"])
            return next(respostas)

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.request("GET", "/api/dcim/devices/")
            with self.assertRaises(nb.NetBoxError):
                client.request("GET", "/api/dcim/devices/")

        self.assertEqual(enviados, ["Token abc", "Token abc"])
        self.assertEqual(client.token_scheme, "Token")


class TestHeadersDeResposta(ClientTestCase):
    def test_captura_versao_da_api_e_request_id(self):
        client = self.client()
        response = FakeResponse(
            200,
            empty_page(),
            headers={"API-Version": "4.3", "X-Request-ID": "req-123"},
        )
        with mock.patch.object(client.session, "request", return_value=response):
            client.request("GET", "/api/dcim/devices/")
        self.assertEqual(client.api_version, "4.3")
        self.assertEqual(client.last_request_id, "req-123")

    def test_verify_tls_desligado_e_repassado(self):
        client = self.client(verify_tls=False)
        capturado = {}

        def fake(method, url, **kwargs):
            capturado.update(kwargs)
            return FakeResponse(200, empty_page())

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.request("GET", "/api/dcim/sites/")

        self.assertFalse(capturado["verify"])

    def test_verify_tls_ligado_por_padrao(self):
        client = self.client()
        capturado = {}

        def fake(method, url, **kwargs):
            capturado.update(kwargs)
            return FakeResponse(200, empty_page())

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.request("GET", "/api/dcim/sites/")

        self.assertTrue(capturado["verify"])


class TestPaginacao(ClientTestCase):
    def test_fetch_all_usa_limit_maximo(self):
        client = self.client()
        visto = {}

        def fake(method, url, **kwargs):
            visto.update(kwargs)
            return FakeResponse(200, empty_page())

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.fetch_all("/api/dcim/sites/")

        self.assertEqual(visto["params"]["limit"], nb.MAX_PAGE_SIZE)

    def test_fetch_all_segue_o_campo_next(self):
        """Sem seguir `next` so vinha a primeira pagina (erro classico)."""
        client = self.client()
        list_url = "https://nb.local/api/dcim/sites/"
        next_url = "https://nb.local/api/dcim/sites/?limit=1000&offset=1000"
        paginas = {
            list_url: FakeResponse(
                200,
                {
                    "count": 2,
                    "next": next_url,
                    "previous": None,
                    "results": [{"id": 1, "name": "A"}],
                },
            ),
            next_url: FakeResponse(
                200,
                {
                    "count": 2,
                    "next": None,
                    "previous": list_url,
                    "results": [{"id": 2, "name": "B"}],
                },
            ),
        }
        pedidos = []

        def fake(method, url, **kwargs):
            pedidos.append(url)
            return paginas[url]

        with mock.patch.object(client.session, "request", side_effect=fake):
            resultado = client.fetch_all("/api/dcim/sites/")

        self.assertEqual([item["id"] for item in resultado], [1, 2])
        self.assertEqual(pedidos, [list_url, next_url])

    def test_fetch_all_aceita_resposta_sem_paginacao(self):
        client = self.client()
        with mock.patch.object(
            client.session, "request", return_value=FakeResponse(200, [{"id": 1}])
        ):
            self.assertEqual(client.fetch_all("/api/x/"), [{"id": 1}])

    def test_count_le_o_total_mesmo_com_limit_1(self):
        client = self.client()
        with mock.patch.object(
            client.session,
            "request",
            return_value=FakeResponse(200, {"count": 42, "results": [{"id": 1}]}),
        ):
            self.assertEqual(client.count("/api/dcim/devices/"), 42)


class TestGetOrNone(ClientTestCase):
    def _with(self, count, results):
        client = self.client()
        payload = {"count": count, "next": None, "results": results}
        return client, mock.patch.object(
            client.session, "request", return_value=FakeResponse(200, payload)
        )

    def test_sem_resultado_retorna_none(self):
        client, patch = self._with(0, [])
        with patch:
            self.assertIsNone(client.get_or_none("/api/dcim/devices/", name="X"))

    def test_um_resultado_retorna_o_objeto(self):
        client, patch = self._with(1, [{"id": 9, "name": "X"}])
        with patch:
            self.assertEqual(
                client.get_or_none("/api/dcim/devices/", name="X"), {"id": 9, "name": "X"}
            )

    def test_mais_de_um_resultado_e_erro(self):
        """Chave ambigua e erro de validacao no NetBox: falhar cedo, com clareza."""
        client, patch = self._with(2, [{"id": 9}, {"id": 10}])
        with patch:
            with self.assertRaises(nb.NetBoxError) as ctx:
                client.get_or_none("/api/dcim/devices/", name="X")
        self.assertIn("unica", str(ctx.exception))


class TestErros(ClientTestCase):
    def test_detail_vira_mensagem(self):
        self.assertEqual(
            nb.describe_error(403, {"detail": "Authentication credentials were not provided."}),
            "Authentication credentials were not provided.",
        )

    def test_erro_por_campo(self):
        self.assertEqual(
            nb.describe_error(400, {"name": ["Este campo e obrigatorio."]}),
            "name: Este campo e obrigatorio.",
        )

    def test_erro_sem_json_usa_o_texto(self):
        self.assertEqual(nb.describe_error(500, None, "Internal Server Error"),
                         "Internal Server Error")

    def test_erro_vazio_tem_fallback(self):
        self.assertEqual(nb.describe_error(502, None, ""), "HTTP 502")

    def test_erro_html_e_resumido(self):
        """404 que devolve a pagina HTML do app nao deve poluir o log."""
        pagina = '<!DOCTYPE html>\n<html lang="en" data-netbox-version="4.3.6">'
        mensagem = nb.describe_error(404, None, pagina)
        self.assertIn("HTML", mensagem)
        self.assertIn("404", mensagem)
        self.assertNotIn("DOCTYPE", mensagem)

    def test_request_inexistente_levanta_com_caminho(self):
        client = self.client()
        with mock.patch.object(
            client.session, "request", return_value=FakeResponse(404, {"detail": "Not found."})
        ):
            with self.assertRaises(nb.NetBoxError) as ctx:
                client.request("GET", "/api/dcim/devices/999/")
        mensagem = str(ctx.exception)
        self.assertIn("404", mensagem)
        self.assertIn("/api/dcim/devices/999/", mensagem)

    def test_rate_limit_espera_e_repete(self):
        client = self.client()
        respostas = iter(
            [
                FakeResponse(429, {"detail": "throttled"}, headers={"Retry-After": "1"}),
                FakeResponse(200, empty_page()),
            ]
        )
        with mock.patch.object(
            client.session, "request", side_effect=lambda *a, **k: next(respostas)
        ):
            with mock.patch.object(nb.time, "sleep") as dormir:
                client.request("GET", "/api/dcim/sites/")
        dormir.assert_called_once()


class TestErrosDeRede(ClientTestCase):
    def test_certificado_autoassinado_mensagem_curta(self):
        """O texto cru do requests nao diz o que houve - o nosso diz.

        Foi o erro real na instancia: certificado autoassinado. O app repete a
        conexao sozinho (session.py), entao a mensagem nao manda mexer em nada.
        """
        exc = requests.exceptions.SSLError(
            "HTTPSConnectionPool(host='192.168.90.123', port=443): Max retries exceeded "
            "with url: /api/status/ (Caused by SSLError(SSLCertVerificationError(1, "
            "'[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed "
            "certificate (_ssl.c:1082)')))"
        )
        mensagem = nb.describe_transport_error(exc, "https://192.168.90.123")
        self.assertIn("certificado autoassinado", mensagem)
        self.assertNotIn("HTTPSConnectionPool", mensagem)
        # Nao pode citar caixa de opcao: ela deixou de existir na tela.
        self.assertNotIn("Marque", mensagem)

    def test_falha_de_conexao_menciona_a_url(self):
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='192.168.90.123', port=443): Max retries exceeded"
        )
        mensagem = nb.describe_transport_error(exc, "https://192.168.90.123")
        self.assertIn("nao foi possivel conectar", mensagem)
        self.assertIn("192.168.90.123", mensagem)

    def test_timeout_e_acionavel(self):
        exc = requests.exceptions.ConnectTimeout("timed out")
        self.assertIn("Tempo esgotado".lower(), nb.describe_transport_error(exc, "x").lower())

    def test_transporte_vira_netbox_error_legivel(self):
        client = self.client()
        with mock.patch.object(
            client.session,
            "request",
            side_effect=requests.exceptions.SSLError(
                "certificate verify failed: self-signed certificate"
            ),
        ):
            with self.assertRaises(nb.NetBoxError) as ctx:
                client.request("GET", "/api/status/")
        self.assertIn("certificado autoassinado", str(ctx.exception))

    def test_certificado_levanta_o_tipo_especifico(self):
        """Quem chama precisa distinguir TLS de outros erros - sem grepar texto."""
        client = self.client()
        with mock.patch.object(
            client.session,
            "request",
            side_effect=requests.exceptions.SSLError("self-signed certificate"),
        ):
            with self.assertRaises(nb.NetBoxTLSError):
                client.request("GET", "/api/status/")

    def test_erro_de_conexao_nao_e_confundido_com_tls(self):
        client = self.client()
        with mock.patch.object(
            client.session,
            "request",
            side_effect=requests.exceptions.ConnectionError("Max retries exceeded"),
        ):
            with self.assertRaises(nb.NetBoxError) as ctx:
                client.request("GET", "/api/status/")
        self.assertNotIsInstance(ctx.exception, nb.NetBoxTLSError)


class TestEscrita(ClientTestCase):
    def test_create_posta_na_lista(self):
        client = self.client()
        capturado = {}

        def fake(method, url, **kwargs):
            capturado["method"] = method
            capturado["url"] = url
            capturado["json"] = kwargs.get("json")
            return FakeResponse(201, {"id": 1})

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.create("/api/dcim/devices/", {"name": "CAM-01"})

        self.assertEqual(capturado["method"], "POST")
        self.assertEqual(capturado["url"], "https://nb.local/api/dcim/devices/")
        self.assertEqual(capturado["json"], {"name": "CAM-01"})

    def test_update_faz_patch_no_detalhe(self):
        client = self.client()
        capturado = {}

        def fake(method, url, **kwargs):
            capturado["method"] = method
            capturado["url"] = url
            return FakeResponse(200, {"id": 7})

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.update("/api/dcim/devices/", 7, {"description": "x"})

        self.assertEqual(capturado["method"], "PATCH")
        self.assertEqual(capturado["url"], "https://nb.local/api/dcim/devices/7/")

    def test_delete_faz_delete_no_detalhe(self):
        client = self.client()
        capturado = {}

        def fake(method, url, **kwargs):
            capturado["method"] = method
            capturado["url"] = url
            return FakeResponse(204, None)

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.delete("/api/dcim/devices/", 7)

        self.assertEqual(capturado["method"], "DELETE")
        self.assertEqual(capturado["url"], "https://nb.local/api/dcim/devices/7/")

    def test_bulk_create_envia_lista(self):
        client = self.client()
        capturado = {}

        def fake(method, url, **kwargs):
            capturado["json"] = kwargs.get("json")
            return FakeResponse(201, [])

        with mock.patch.object(client.session, "request", side_effect=fake):
            client.bulk_create("/api/dcim/devices/", [{"name": "A"}, {"name": "B"}])

        self.assertEqual(capturado["json"], [{"name": "A"}, {"name": "B"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
