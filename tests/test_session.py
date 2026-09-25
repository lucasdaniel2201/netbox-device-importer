"""Testes do worker de sessao (app/session.py).

Cobrem o bug real: a descoberta e tolerante a falha (um endpoint ruim nao derruba
o resto), e por isso o worker dizia **"conectado" mesmo quando nada foi lido** -
foi o que aconteceu com o certificado autoassinado, e a tela abria vazia.

Tambem cobrem o retry: quando o unico problema e o certificado, o worker tenta de
novo aceitando-o (e o snapshot registra que a verificacao TLS ficou de fora).
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

from app import (  # noqa: E402
    import_plan,
    session as session_mod,
)
from app.session import SessionWorker, first_problem  # noqa: E402

_app = QApplication.instance() or QApplication([])


class FakeClient:
    def __init__(self, verify_tls=True):
        self.base_url = "https://nb.local"
        self.token_scheme = "Token"
        self.verify_tls = verify_tls
        self.closed = False

    def close(self):
        self.closed = True


def snapshot(errors, status=None, sites=None, tls_verified=True, tls_blocked=False):
    return {
        "base_url": "https://nb.local",
        "token_scheme": "Token",
        "tls_verified": tls_verified,
        "tls_blocked": tls_blocked,
        "status": status or {},
        "objects": {"sites": sites or []},
        "counts": {},
        "schema": {},
        "capabilities": {},
        "custom_fields": [],
        "content_types": {},
        "errors": list(errors),
    }


# Mensagem ja traduzida (a que a descoberta grava) + a marca estrutural que diz
# que o certificado foi o problema. Nao dependemos de texto em ingles na mensagem.
TLS_ERROR = "status: o certificado TLS do NetBox nao foi validado (certificado autoassinado)"


class TestFirstProblem(unittest.TestCase):
    def test_uma_ocorrencia(self):
        self.assertEqual(
            first_problem({"errors": ["status: falhou"]}),
            "Nao foi possivel ler nada do NetBox. status: falhou",
        )

    def test_varias_ocorrencias_resume(self):
        msg = first_problem({"errors": ["a", "b", "c"]})
        self.assertIn("e mais 2 endpoints", msg)

    def test_sem_erros(self):
        self.assertIn("sem detalhes", first_problem({}))


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        self.worker = SessionWorker()
        self.connected = []
        self.failed = []
        self.worker.connected.connect(self.connected.append)
        self.worker.connect_failed.connect(self.failed.append)

    def patch(self, func):
        return mock.patch.object(SessionWorker, "_connect_and_discover", side_effect=func)


class TestConexao(SessionTestCase):
    def test_conecta_quando_le_algo(self):
        cliente = FakeClient()

        def fake(url, token, verify_tls):
            return cliente, snapshot([], status={"netbox-version": "4.3.6"})

        with self.patch(fake):
            self.worker.connect_netbox("https://nb.local", "t", False)

        self.assertEqual(len(self.connected), 1)
        self.assertFalse(self.failed)

    def test_nao_diz_conectado_quando_nada_e_lido(self):
        """O bug: ambiente vazio nao pode ser reportado como sucesso."""
        cliente = FakeClient()

        def fake(url, token, verify_tls):
            return cliente, snapshot([TLS_ERROR], tls_blocked=True)

        with self.patch(fake):
            self.worker.connect_netbox("https://nb.local", "t", False)

        self.assertFalse(self.connected)
        self.assertEqual(len(self.failed), 1)
        self.assertIn("Nao foi possivel ler nada", self.failed[0])

    def test_erro_ao_criar_cliente_nao_quebra(self):
        with self.patch(RuntimeError("token invalido")):
            self.worker.connect_netbox("https://nb.local", "", False)
        self.assertEqual(self.failed, ["token invalido"])
        self.assertFalse(self.connected)


class TestRetryDeCertificado(SessionTestCase):
    def test_repete_aceitando_certificado_autoassinado(self):
        primeiro = FakeClient()
        segundo = FakeClient(verify_tls=False)
        chamadas = []

        def fake(url, token, verify_tls):
            chamadas.append(verify_tls)
            if len(chamadas) == 1:
                return primeiro, snapshot([TLS_ERROR], tls_blocked=True)
            return segundo, snapshot(
                [], status={"netbox-version": "4.3.6"}, tls_verified=False
            )

        with self.patch(fake):
            self.worker.connect_netbox("https://nb.local", "t", True)

        self.assertEqual(chamadas, [True, False])
        self.assertTrue(primeiro.closed)
        self.assertEqual(len(self.connected), 1)
        self.assertFalse(self.connected[0]["tls_verified"])

    def test_nao_repete_se_ja_ignora_o_certificado(self):
        """Se o usuario ja pediu para ignorar, nao insistimos duas vezes."""
        cliente = FakeClient(verify_tls=False)
        chamadas = []

        def fake(url, token, verify_tls):
            chamadas.append(verify_tls)
            return cliente, snapshot([TLS_ERROR], tls_blocked=True)

        with self.patch(fake):
            self.worker.connect_netbox("https://nb.local", "t", False)

        self.assertEqual(chamadas, [False])
        self.assertEqual(len(self.failed), 1)

    def test_nao_repete_quando_o_problema_nao_e_tls(self):
        cliente = FakeClient()
        chamadas = []

        def fake(url, token, verify_tls):
            chamadas.append(verify_tls)
            return cliente, snapshot(["status: HTTP 403 (token sem permissao)"])

        with self.patch(fake):
            self.worker.connect_netbox("https://nb.local", "t", True)

        self.assertEqual(chamadas, [True])
        self.assertEqual(len(self.failed), 1)

    def test_falha_tambem_quando_o_retry_nao_resolve(self):
        cliente = FakeClient(verify_tls=False)

        def fake(url, token, verify_tls):
            return cliente, snapshot([TLS_ERROR], tls_blocked=True)

        with self.patch(fake):
            self.worker.connect_netbox("https://nb.local", "t", True)

        self.assertFalse(self.connected)
        self.assertEqual(len(self.failed), 1)

    def test_repete_quando_le_alguma_coisa_mas_nao_tudo(self):
        """Parcial (ex.: so o status) conta como ambiente util: nao repete."""
        cliente = FakeClient()
        chamadas = []

        def fake(url, token, verify_tls):
            chamadas.append(verify_tls)
            return cliente, snapshot(
                [TLS_ERROR], status={"netbox-version": "4.3.6"}, tls_blocked=True
            )

        with self.patch(fake):
            self.worker.connect_netbox("https://nb.local", "t", True)

        self.assertEqual(chamadas, [True])
        self.assertEqual(len(self.connected), 1)


def make_plan(
    site: str = "PSF 1",
    com_rede: bool = False,
    mac: str = "",
    ip: str = "10.0.0.1",
    ip_campos: dict | None = None,
):
    """Plano minimo de 1 device pronto, para exercitar a importacao."""

    class Row:
        row_number = 2
        name_normalized = "CAM-01"
        issues: list = []
        warnings: list = []
        cells = {
            "Name": "CAM-01",
            "Site": site,
            "Role": "",
            "IP": ip,
            "Vendor": "Hikvision",
            "Model": "DS-2CD",
            "Firmware": "",
            "MAC address": mac,
            "Server": "",
            "Description": "",
        }

    class Sheet:
        rows = [Row]

    snapshot = {
        "objects": {
            "sites": [{"id": 1, "label": "PSF 1"}],
            "device_roles": [{"id": 2, "label": "Camera"}],
            "manufacturers": [{"id": 3, "label": "Hikvision"}],
            "device_types": [{"id": 4, "label": "DS-2CD", "manufacturer": "Hikvision"}],
        }
    }
    if com_rede:
        snapshot["schema"] = {
            "interface": {"actions": {"POST": {}, "PUT": {}}},
            "ip_address": {"actions": {"POST": {}, "PUT": {}}},
        }
    return import_plan.build_plan(
        Sheet, snapshot, import_plan.PlanOptions(ip_custom_fields=ip_campos or {})
    )


class ClienteImportacao:
    """Cliente de mentira: o device nao existe e o POST pode falhar."""

    def __init__(self, criar_falha: bool = False) -> None:
        self.base_url = "https://nb.local"
        self.api_version = "4.3"
        self.last_request_id = "req-1"
        self._criar_falha = criar_falha
        self.criados: list[dict] = []

    def get_or_none(self, path, **filters):
        return None

    def create(self, path, payload):
        if self._criar_falha:
            raise RuntimeError(
                "POST /api/dcim/devices/ -> HTTP 400: __all__: Valor invalido para o "
                "campo personalizado 'Validavel': O campo obrigatorio nao pode estar vazio."
            )
        self.criados.append(payload)
        return {"id": 7}


class ClienteRede:
    """Interface ja existe (criada por template) e o PATCH do MAC pode falhar.

    Reproduz o erro real: a interface tem `poe_type` sem `poe_mode` no NetBox, e
    qualquer PATCH nela leva 400 - mas isso nao pode impedir a criacao do IP.
    """

    def __init__(self, falhar_mac: bool = True) -> None:
        self.base_url = "https://nb.local"
        self.api_version = "4.3"
        self.last_request_id = "req-1"
        self._falhar_mac = falhar_mac
        self.chamadas: list[tuple] = []

    def get_or_none(self, path, **filters):
        return None

    def create(self, path, payload):
        self.chamadas.append(("create", path, payload))
        if path == "/api/ipam/ip-addresses/":
            return {"id": 99}
        return {"id": 7}

    def fetch_all(self, path, params=None):
        self.chamadas.append(("fetch_all", path))
        if path == "/api/dcim/interfaces/":
            return [{"id": 16336, "mac_address": ""}]
        return []

    def update(self, path, object_id, payload):
        self.chamadas.append(("update", path, object_id, payload))
        if self._falhar_mac and path == "/api/dcim/interfaces/":
            raise RuntimeError(
                "PATCH /api/dcim/interfaces/16336/ -> HTTP 400: poe_type: Deve "
                "especificar o modo PoE ao designar um tipo de PoE."
            )
        return {"id": object_id}


class TestImportacao(SessionTestCase):
    def _run(self, cliente, plan) -> list[dict]:
        self.worker._client = cliente
        self.worker._snapshot = {}
        feitos: list[dict] = []
        self.worker.import_done.connect(feitos.append)
        with mock.patch.object(
            session_mod.reports, "write_reports", return_value={"json": "x.json"}
        ):
            self.worker.run_import(plan)
        return feitos

    def test_cria_o_device(self):
        cliente = ClienteImportacao()
        summary = self._run(cliente, make_plan())
        self.assertEqual(summary[0]["created"], 1)
        self.assertEqual(summary[0]["errors"], 0)
        self.assertEqual(cliente.criados[0]["name"], "CAM-01")

    def test_relatorio_registra_os_valores_fixos_de_custom_field(self):
        """O que o app manda de custom field tem que ficar registrado no relatorio."""
        cliente = ClienteImportacao()
        summary = self._run(cliente, make_plan())
        enviados = summary[0]["custom_fields"]["dcim.device"]
        self.assertEqual(enviados, {"Validavel": True})
        # e foi exatamente isso que foi no POST
        self.assertEqual(cliente.criados[0]["custom_fields"], enviados)

    def test_resumo_traz_o_motivo_do_erro(self):
        """O erro precisa chegar na tela: antes so existia dentro do JSON."""
        summary = self._run(ClienteImportacao(criar_falha=True), make_plan())
        self.assertEqual(summary[0]["errors"], 1)
        self.assertEqual(len(summary[0]["error_samples"]), 1)
        self.assertIn("Validavel", summary[0]["error_samples"][0]["message"])

    def test_plano_com_pendencia_nao_e_importado(self):
        falhas: list[str] = []
        self.worker._client = ClienteImportacao()
        self.worker.import_failed.connect(falhas.append)
        self.worker.run_import(make_plan(site="NAO EXISTE"))
        self.assertEqual(len(falhas), 1)
        self.assertIn("pendencias", falhas[0])


class TestRede(SessionTestCase):
    """Ordem device -> interface -> IP -> primary_ip4, sem um passo derrubar o outro."""

    def _run_network(self, cliente, **kwargs) -> list[dict]:
        self.worker._client = cliente
        self.worker._snapshot = {}
        feitos: list[dict] = []
        self.worker.import_done.connect(feitos.append)
        with mock.patch.object(
            session_mod.reports, "write_reports", return_value={"json": "x.json"}
        ):
            self.worker.run_import(make_plan(com_rede=True, **kwargs))
        return feitos

    def test_cria_interface_ip_e_primary_ip4(self):
        cliente = ClienteRede(falhar_mac=False)
        summary = self._run_network(cliente, mac="AA-BB-CC-DD-EE-FF")
        self.assertEqual(summary[0]["errors"], 0)
        self.assertEqual(summary[0]["warnings"], 0)

        criados = [c[1] for c in cliente.chamadas if c[0] == "create"]
        self.assertIn("/api/ipam/ip-addresses/", criados)
        primario = [
            c for c in cliente.chamadas
            if c[0] == "update" and c[1] == "/api/dcim/devices/"
        ]
        self.assertEqual(primario[0][3], {"primary_ip4": 99})

    def test_falha_no_mac_nao_impede_o_ip(self):
        """Regressao do erro real: PoE invalido na interface bloqueava o IP."""
        cliente = ClienteRede(falhar_mac=True)
        summary = self._run_network(cliente, mac="AA-BB-CC-DD-EE-FF")

        # O device continua "criado" e o problema vira aviso, nao erro.
        self.assertEqual(summary[0]["errors"], 0)
        self.assertEqual(summary[0]["created"], 1)
        self.assertEqual(summary[0]["warnings"], 1)
        self.assertIn("poe_type", summary[0]["warning_samples"][0]["message"])

        # E o IP foi criado e marcado como primario mesmo assim.
        criados = [c[1] for c in cliente.chamadas if c[0] == "create"]
        self.assertIn("/api/ipam/ip-addresses/", criados)
        primario = [
            c for c in cliente.chamadas
            if c[0] == "update" and c[1] == "/api/dcim/devices/"
        ]
        self.assertEqual(primario[0][3], {"primary_ip4": 99})

    def test_sem_permissao_de_rede_nao_chama_interface(self):
        cliente = ClienteImportacao()
        self.worker._client = cliente
        self.worker._snapshot = {}
        with mock.patch.object(
            session_mod.reports, "write_reports", return_value={"json": "x.json"}
        ):
            self.worker.run_import(make_plan(com_rede=False))
        # ClienteImportacao nem tem fetch_all: se tivesse tentado, teria estourado.
        self.assertEqual(cliente.criados[0]["name"], "CAM-01")

    def test_ip_leva_os_custom_fields_obrigatorios(self):
        """`add_to_zabbix` e obrigatorio no ipam.ipaddress: sem ele o POST da 400."""
        cliente = ClienteRede(falhar_mac=False)
        self._run_network(cliente, ip_campos={"add_to_zabbix": "Sim"})

        payload = next(
            c[2]
            for c in cliente.chamadas
            if c[0] == "create" and c[1] == session_mod.provision.IP_ADDRESS_ENDPOINT
        )
        self.assertEqual(payload["custom_fields"], {"add_to_zabbix": "Sim"})

    def test_ip_sem_custom_fields_nao_leva_a_chave(self):
        cliente = ClienteRede(falhar_mac=False)
        self._run_network(cliente)
        payload = next(
            c[2]
            for c in cliente.chamadas
            if c[0] == "create" and c[1] == session_mod.provision.IP_ADDRESS_ENDPOINT
        )
        self.assertNotIn("custom_fields", payload)

    def test_ip_leva_description_igual_ao_nome_do_device(self):
        """A descricao do IP e o nome do device, para identificacao na lista do NetBox."""
        cliente = ClienteRede(falhar_mac=False)
        self._run_network(cliente)
        payload = next(
            c[2]
            for c in cliente.chamadas
            if c[0] == "create" and c[1] == session_mod.provision.IP_ADDRESS_ENDPOINT
        )
        self.assertEqual(payload["description"], "CAM-01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
