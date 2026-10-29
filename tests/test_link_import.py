"""Testes de escrita dos links IP (app/provision.py + app/session.py).

Sem rede: um cliente falso guarda o que seria enviado. O que se protege aqui:

- idempotencia do prefixo (GET -> POST/PATCH), inclusive a comparacao do **escopo**
  com o site, que mudou de campo na 4.3;
- interface achada **pelo nome** (num roteador a primeira interface pode ser a LAN);
- `primary_ip4` nunca sobrescrito (o primario do roteador costuma ser o IP de gerencia);
- falha de prefixo vira aviso, nao erro: o IP do link ainda e gravado.
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

from app import link_plan, provision, session as session_mod  # noqa: E402
from app.session import SessionWorker  # noqa: E402

_app = QApplication.instance() or QApplication([])


class ClienteLinks:
    """Cliente de mentira com o que os upserts de link usam."""

    def __init__(self, prefixo=None, device=None, interfaces=None, falhar=()):
        self.base_url = "https://nb.local"
        self.api_version = "4.3"
        self.last_request_id = "req-1"
        self._prefixo = prefixo
        self._device = device
        self._interfaces = list(interfaces or [])
        self._falhar = set(falhar)
        self.criados: list[tuple[str, dict]] = []
        self.atualizados: list[tuple[str, int, dict]] = []
        self.buscas: list[tuple[str, dict]] = []

    # --- leitura
    def get_or_none(self, path, **filters):
        if path in self._falhar:
            raise RuntimeError(f"403 em {path}")
        if path == provision.PREFIX_ENDPOINT:
            return self._prefixo
        if path == provision.DEVICE_ENDPOINT:
            return self._device
        return None

    def fetch_all(self, path, params=None):
        self.buscas.append((path, dict(params or {})))
        if path in self._falhar:
            raise RuntimeError(f"403 em {path}")
        return list(self._interfaces)

    # --- escrita
    def create(self, path, payload):
        self.criados.append((path, payload))
        return {"id": 500 + len(self.criados)}

    def update(self, path, object_id, payload):
        self.atualizados.append((path, object_id, payload))
        return {"id": object_id}

    def close(self):
        pass


class TestUpsertPrefixo(unittest.TestCase):
    def test_cria_quando_nao_existe(self):
        cliente = ClienteLinks()
        status, prefixo_id, request_id = provision.upsert_prefix(
            cliente, {"prefix": "203.0.113.240/30", "status": "active"}
        )
        self.assertEqual(status, "created")
        self.assertEqual(prefixo_id, 501)
        self.assertEqual(request_id, "req-1")
        self.assertEqual(cliente.criados[0][0], provision.PREFIX_ENDPOINT)

    def test_nao_faz_patch_quando_esta_igual(self):
        cliente = ClienteLinks(
            prefixo={
                "id": 9,
                "prefix": "10.10.48.0/24",
                "status": {"value": "active"},
                "description": "LAN",
                "role": None,
                "scope_type": "dcim.site",
                "scope_id": 10,
            }
        )
        status, prefixo_id, _ = provision.upsert_prefix(
            cliente,
            {
                "prefix": "10.10.48.0/24",
                "status": "active",
                "description": "LAN",
                "scope_type": "dcim.site",
                "scope_id": 10,
            },
        )
        self.assertEqual((status, prefixo_id), ("exists", 9))
        self.assertEqual(cliente.atualizados, [])

    def test_atualiza_quando_a_descricao_muda(self):
        cliente = ClienteLinks(
            prefixo={
                "id": 9,
                "prefix": "10.10.48.0/24",
                "status": {"value": "active"},
                "description": "LAN antiga",
                "scope_type": "dcim.site",
                "scope_id": 10,
            }
        )
        status, _, _ = provision.upsert_prefix(
            cliente,
            {
                "prefix": "10.10.48.0/24",
                "status": "active",
                "description": "LAN nova",
                "scope_type": "dcim.site",
                "scope_id": 10,
            },
        )
        self.assertEqual(status, "updated")
        self.assertEqual(cliente.atualizados[0][2]["description"], "LAN nova")

    def test_escopo_diferente_dispara_patch(self):
        cliente = ClienteLinks(
            prefixo={
                "id": 9,
                "prefix": "10.10.48.0/24",
                "status": {"value": "active"},
                "description": "LAN",
                "scope_type": "dcim.site",
                "scope_id": 10,
            }
        )
        status, _, _ = provision.upsert_prefix(
            cliente,
            {
                "prefix": "10.10.48.0/24",
                "status": "active",
                "description": "LAN",
                "scope_type": "dcim.site",
                "scope_id": 11,
            },
        )
        self.assertEqual(status, "updated")

    def test_papel_sem_permissao_existente_dispara_patch(self):
        cliente = ClienteLinks(
            prefixo={
                "id": 9,
                "prefix": "10.10.48.0/24",
                "status": {"value": "active"},
                "description": "LAN",
                "role": None,
                "scope_type": "dcim.site",
                "scope_id": 10,
            }
        )
        status, _, _ = provision.upsert_prefix(
            cliente,
            {
                "prefix": "10.10.48.0/24",
                "status": "active",
                "description": "LAN",
                "role": 2,
                "scope_type": "dcim.site",
                "scope_id": 10,
            },
        )
        self.assertEqual(status, "updated")

    def test_status_diferente_dispara_patch(self):
        cliente = ClienteLinks(
            prefixo={
                "id": 9,
                "prefix": "10.10.48.0/24",
                "status": {"value": "reserved"},
                "description": "LAN",
            }
        )
        status, _, _ = provision.upsert_prefix(
            cliente, {"prefix": "10.10.48.0/24", "status": "active", "description": "LAN"}
        )
        self.assertEqual(status, "updated")

    def test_prefixo_container_nao_e_rebaixado_para_active(self):
        """Um /24 que agrupa sub-redes existe como "container": nao mexemos no status."""
        cliente = ClienteLinks(
            prefixo={
                "id": 9,
                "prefix": "10.10.48.0/24",
                "status": {"value": "container"},
                "description": "LAN",
            }
        )
        status, prefixo_id, _ = provision.upsert_prefix(
            cliente, {"prefix": "10.10.48.0/24", "status": "active", "description": "LAN"}
        )
        self.assertEqual((status, prefixo_id), ("exists", 9))
        self.assertEqual(cliente.atualizados, [])

    def test_prefixo_de_outro_tamanho_nao_e_o_alvo(self):
        """O filtro `prefix` pode devolver o container: nao pode virar PATCH nele."""
        cliente = ClienteLinks(
            prefixo={"id": 900, "prefix": "10.10.0.0/16", "status": {"value": "active"}}
        )
        status, prefixo_id, _ = provision.upsert_prefix(
            cliente, {"prefix": "10.10.48.0/24", "status": "active"}
        )
        self.assertEqual(status, "created")
        self.assertEqual(cliente.atualizados, [])
        self.assertEqual(cliente.criados[0][1]["prefix"], "10.10.48.0/24")


class TestEscopoDoPrefixo(unittest.TestCase):
    def test_usa_scope_type_quando_o_options_mostra(self):
        snapshot = {"schema": {"prefix": {"actions": {"POST": {"scope_type": {"type": "x"}}}}}}
        self.assertEqual(provision.prefix_scope_field(snapshot), "scope_type")

    def test_usa_site_quando_e_o_unico_campo(self):
        snapshot = {"schema": {"prefix": {"actions": {"POST": {"site": {"type": "x"}}}}}}
        self.assertEqual(provision.prefix_scope_field(snapshot), "site")

    def test_sem_options_assume_o_formato_da_4_3(self):
        self.assertEqual(provision.prefix_scope_field({}), "scope_type")


class TestInterfaceDoLink(unittest.TestCase):
    def test_reaproveita_interface_com_o_mesmo_nome(self):
        cliente = ClienteLinks(interfaces=[{"id": 77, "name": "wan1"}])
        status, interface_id = provision.upsert_named_interface(cliente, 10, "wan1")
        self.assertEqual((status, interface_id), ("exists", 77))
        self.assertEqual(cliente.criados, [])

    def test_nao_reaproveita_outra_interface(self):
        """A primeira interface de um roteador pode ser a LAN, nao a WAN."""
        cliente = ClienteLinks(interfaces=[{"id": 78, "name": "ether1"}])
        status, interface_id = provision.upsert_named_interface(cliente, 10, "wan1")
        self.assertEqual(status, "created")
        self.assertEqual(interface_id, 501)
        self.assertEqual(cliente.criados[0][1]["name"], "wan1")

    def test_nome_comparado_sem_caixa(self):
        cliente = ClienteLinks(interfaces=[{"id": 79, "name": "WAN1"}])
        status, interface_id = provision.upsert_named_interface(cliente, 10, "wan1")
        self.assertEqual((status, interface_id), ("exists", 79))


class TestPrimaryIp(unittest.TestCase):
    def test_define_quando_o_device_nao_tem(self):
        cliente = ClienteLinks()
        definido = provision.set_primary_ip4_if_empty(cliente, {"id": 10}, 500)
        self.assertTrue(definido)
        self.assertEqual(cliente.atualizados[0][2], {"primary_ip4": 500})

    def test_nao_sobrescreve_o_primario_existente(self):
        cliente = ClienteLinks()
        definido = provision.set_primary_ip4_if_empty(
            cliente, {"id": 10, "primary_ip4": {"id": 1}}, 500
        )
        self.assertFalse(definido)
        self.assertEqual(cliente.atualizados, [])

    def test_device_por_nome_usa_o_filtro_exato(self):
        cliente = ClienteLinks(device={"id": 10, "name": "RT-1"})
        self.assertEqual(provision.device_by_name(cliente, "RT-1")["id"], 10)

    def test_device_por_nome_sem_resultado(self):
        self.assertIsNone(provision.device_by_name(ClienteLinks(), "RT-inexistente"))

    def test_device_por_nome_filtra_pelo_site(self):
        """Com nome repetido em sites diferentes, o filtro de site e o que resolve."""
        capturado = {}

        class Cliente(ClienteLinks):
            def get_or_none(self, path, **filters):
                capturado.update(filters)
                return {"id": 10, "name": "Mikrotik"}

        provision.device_by_name(Cliente(), "Mikrotik", site_id=10)
        self.assertEqual(capturado, {"name": "Mikrotik", "site_id": 10})


def make_plan_two_rows() -> link_plan.LinkPlan:
    """Dois links do mesmo site compartilhando o bloco LAN (caso real da planilha)."""
    comum = {
        "site": "SITE EXEMPLO",
        "device": "RT-DELEGACIA-GERAL",
        "interface": "wan1",
        "lan_block": "10.10.48.0/24",
        "role_label": "",
        "description": "LINK",
        "provider": "",
        "vendor": "MikroTik",
        "model": "RB760iGS",
        "device_role": "Roteador",
        "device_role_id": 31,
        "manufacturer_id": 1,
        "device_type_id": 40,
        "device_exists": True,
        "site_id": 10,
        "ip_custom_fields": {"add_to_zabbix": "0"},
    }
    primeira = link_plan.LinkPlanRow(
        row_number=2, public_block="203.0.113.240/30",
        link_ip="203.0.113.241/30", **comum,
    )
    segunda = link_plan.LinkPlanRow(
        row_number=3, public_block="203.0.113.244/30",
        link_ip="203.0.113.245/30", **comum,
    )
    return link_plan.LinkPlan(rows=[primeira, segunda])


def make_plan(**kwargs) -> link_plan.LinkPlan:
    valores = {
        "row_number": 2,
        "site": "SITE EXEMPLO",
        "device": "RT-DELEGACIA-GERAL",
        "interface": "wan1",
        "public_block": "203.0.113.240/30",
        "lan_block": "10.10.48.0/24",
        "link_ip": "203.0.113.241/30",
        "role_label": "",
        "description": "PROVEDOR",
        "provider": "",
        "vendor": "MikroTik",
        "model": "RB760iGS",
        "device_role": "Roteador",
        "device_role_id": 31,
        "manufacturer_id": 1,
        "device_type_id": 40,
        "device_exists": True,
        "site_id": 10,
        "ip_custom_fields": {"add_to_zabbix": "0"},
    }
    valores.update(kwargs)
    return link_plan.LinkPlan(rows=[link_plan.LinkPlanRow(**valores)])


class TestImportacaoDeLinks(unittest.TestCase):
    def setUp(self):
        self.worker = SessionWorker()
        self.done: list[dict] = []
        self.failed: list[str] = []
        self.worker.links_done.connect(self.done.append)
        self.worker.links_failed.connect(self.failed.append)

    def _run(self, cliente, plan):
        self.worker._client = cliente
        with mock.patch.object(
            session_mod.reports, "write_reports", return_value={"json": "links.json"}
        ) as escritor:
            self.worker.run_links_import(plan)
        self.escritor = escritor
        return self.done

    def test_cria_prefixos_interface_e_ip(self):
        cliente = ClienteLinks(device={"id": 10, "name": "RT-1"})
        resumo = self._run(cliente, make_plan())
        self.assertEqual(len(resumo), 1)
        self.assertEqual(resumo[0]["created"], 1)
        self.assertEqual(resumo[0]["prefixes"], 2)
        caminhos = [
            payload["prefix"]
            for path, payload in cliente.criados
            if path == provision.PREFIX_ENDPOINT
        ]
        self.assertIn("203.0.113.240/30", caminhos)
        self.assertIn("10.10.48.0/24", caminhos)

    def test_relatorio_usa_o_prefixo_de_links(self):
        cliente = ClienteLinks(device={"id": 10, "name": "RT-1"})
        self._run(cliente, make_plan())
        _, kwargs = self.escritor.call_args
        self.assertEqual(kwargs["prefix"], session_mod.reports.LINK_PREFIX)
        self.assertEqual(
            kwargs["fieldnames"], session_mod.reports.LINK_RESULT_FIELDS
        )

    def test_device_inexistente_e_criado_no_site(self):
        cliente = ClienteLinks(device=None)
        resumo = self._run(cliente, make_plan(device_exists=False))
        self.assertEqual(resumo[0]["errors"], 0)
        self.assertEqual(resumo[0]["devices_created"], 1)
        criados = [payload for path, payload in cliente.criados]
        device = next(item for item in criados if item.get("name") == "RT-DELEGACIA-GERAL")
        self.assertEqual(device["site"], 10)
        self.assertEqual(device["role"], 31)
        self.assertEqual(device["device_type"], 40)
    def test_referencias_do_device_sao_criadas_quando_faltam(self):
        """Fabricante e device-type inexistentes sao criados antes do device."""
        cliente = ClienteLinks(device=None)
        resumo = self._run(
            cliente, make_plan(device_exists=False, manufacturer_id=None, device_type_id=None)
        )
        self.assertEqual(resumo[0]["errors"], 0)
        criados = [payload for _path, payload in cliente.criados]
        self.assertIn("MikroTik", [item.get("name") for item in criados])
        device_type = next(item for item in criados if item.get("model") == "RB760iGS")
        self.assertEqual(device_type["manufacturer"], 501)

    def test_device_sem_fabricante_nao_e_criado(self):
        cliente = ClienteLinks(device=None)
        resumo = self._run(cliente, make_plan(device_exists=False, vendor="", model=""))
        self.assertEqual(resumo[0]["errors"], 1)
        self.assertIn("Fabricante", resumo[0]["error_samples"][0]["message"])

    def test_falha_de_prefixo_vira_aviso_e_o_ip_e_criado(self):
        cliente = ClienteLinks(
            device={"id": 10, "name": "RT-1"},
            falhar={provision.PREFIX_ENDPOINT},
        )
        resumo = self._run(cliente, make_plan())
        self.assertEqual(resumo[0]["errors"], 0)
        self.assertEqual(resumo[0]["warnings"], 1)
        self.assertIn("prefixo", resumo[0]["warning_samples"][0]["message"])
        tipos = [path for path, _payload in cliente.criados]
        self.assertIn(provision.IP_ADDRESS_ENDPOINT, tipos)

    def test_primary_ip4_e_definido_quando_o_device_nao_tem(self):
        cliente = ClienteLinks(device={"id": 10, "name": "RT-1"})
        self._run(cliente, make_plan())
        atualizacoes = [payload for _path, _oid, payload in cliente.atualizados]
        self.assertTrue(any("primary_ip4" in payload for payload in atualizacoes))

    def test_primary_ip4_nao_e_sobrescrito(self):
        cliente = ClienteLinks(
            device={"id": 10, "name": "RT-1", "primary_ip4": {"id": 1}}
        )
        self._run(cliente, make_plan())
        self.assertFalse(
            any("primary_ip4" in payload for _p, _o, payload in cliente.atualizados)
        )
        # A mensagem da linha diz que o primario foi mantido: nao pode parecer
        # que o app esqueceu de definir.
        resultados = self.escritor.call_args[0][2]
        self.assertIn("mantido", resultados[0]["message"])

    def test_bloco_lan_compartilhado_e_gravado_uma_vez(self):
        """Duas linhas, um /24: sem dedupe cada linha reescreveria a descricao."""
        cliente = ClienteLinks(device={"id": 10, "name": "RT-1"})
        plano = make_plan_two_rows()
        self._run(cliente, plano)
        prefixos = [
            payload["prefix"]
            for path, payload in cliente.criados
            if path == provision.PREFIX_ENDPOINT
        ]
        self.assertEqual(prefixos.count("10.10.48.0/24"), 1)
        self.assertEqual(sorted(prefixos), ["10.10.48.0/24", "203.0.113.240/30", "203.0.113.244/30"])
        self.assertEqual(plano.prefix_count, 3)

    def test_device_de_outro_site_e_erro(self):
        """Prefixo no site A e IP no device do site B seria documentacao errada."""
        cliente = ClienteLinks(
            device={"id": 10, "name": "RT-1", "site": {"id": 999, "name": "OUTRO"}}
        )
        resumo = self._run(cliente, make_plan())
        self.assertEqual(resumo[0]["errors"], 1)
        self.assertIn("outro site", resumo[0]["error_samples"][0]["message"])
        self.assertEqual(cliente.criados, [])

    def test_plano_com_pendencia_nao_e_importado(self):
        self.worker._client = ClienteLinks()
        self.worker.run_links_import(make_plan(site_id=None))
        self.assertEqual(len(self.failed), 1)
        self.assertIn("pendencias", self.failed[0])

    def test_sem_sessao_avisa(self):
        self.worker._client = None
        self.worker.run_links_import(make_plan())
        self.assertEqual(len(self.failed), 1)
        self.assertIn("desconectada", self.failed[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
