"""Testes do plano de links IP (app/link_plan.py).

O plano e a parte pura: recebe a planilha e o snapshot do NetBox e decide o que
sera criado, sem tocar na rede. O que mais importa aqui:

- o prefixo precisa do escopo no formato da instancia (`scope_type` na 4.3, `site`
  antes dela) - mandar o campo errado da 400;
- IP em branco e deduzido **com aviso**, nunca em silencio;
- o `add_to_zabbix` e obrigatorio em `ipam.ipaddress` e a coluna da planilha manda
  sobre o valor observado num IP existente.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import link_plan, link_sheet as ls  # noqa: E402

SITES = ["SITE EXEMPLO"]
ROLES = ["Reservado"]


def snapshot(
    scope="scope_type",
    ip_required=True,
    sample="0",
    prefix_fields=None,
    devices=None,
    manufacturers=None,
    device_types=None,
):
    """Snapshot minimo no formato que `provision.discover` devolve."""
    campos_prefixo = {"prefix": {"type": "string", "required": True}}
    if scope == "scope_type":
        campos_prefixo["scope_type"] = {"type": "choice", "required": False}
    else:
        campos_prefixo["site"] = {"type": "nested object", "required": False}

    custom_fields = list(prefix_fields or [])
    if ip_required:
        custom_fields.append(
            {
                "name": "add_to_zabbix",
                "label": "Adicionar ao zabbix?",
                "type": "select",
                "required": True,
                "object_types": ["ipam.ipaddress"],
            }
        )

    return {
        "objects": {
            "sites": [{"id": 10, "label": "SITE EXEMPLO"}],
            "prefix_roles": [{"id": 2, "label": "Reservado"}],
            "device_roles": [{"id": 31, "label": "Roteador"}],
            "manufacturers": [{"id": 1, "label": nome} for nome in (manufacturers or [])],
            "device_types": [
                {"id": 40, "label": modelo, "manufacturer": fabricante}
                for fabricante, modelo in (device_types or [])
            ],
            "devices": [
                item if isinstance(item, dict) else {"id": 500, "label": item, "site_id": 10}
                for item in (devices or [])
            ],
        },
        "schema": {"prefix": {"actions": {"POST": campos_prefixo}}},
        "custom_fields": custom_fields,
        "custom_fields_sample": (
            {"ipam.ipaddress": {"add_to_zabbix": sample}} if sample else {}
        ),
    }


def build_sheet(rows: list[list[str]]) -> ls.LinkSheet:
    """Planilha de links escrita num xlsx temporario e lida pelo modulo real."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "links.xlsx"
        import openpyxl

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append([spec.label for spec in ls.COLUMN_SPECS])
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        workbook.close()
        return ls.read_file(path, sites=SITES, prefix_roles=ROLES)


def row(**values) -> list[str]:
    cells = {
        ls.SITE_KEY: "SITE EXEMPLO",
        ls.DEVICE_KEY: "RT-DELEGACIA-GERAL",
        ls.VENDOR_KEY: "MikroTik",
        ls.MODEL_KEY: "RB760iGS",
        ls.DEVICE_ROLE_KEY: "Roteador",
        ls.PUBLIC_KEY: "203.0.113.240/30",
        ls.INTERFACE_KEY: "wan1",
        ls.IP_KEY: "203.0.113.241",
        ls.LAN_KEY: "10.10.48.0/24",
        ls.ROLE_KEY: "",
        ls.ZABBIX_KEY: "",
        ls.DESCRIPTION_KEY: "PROVEDOR",
        ls.PROVIDER_KEY: "",
    }
    cells.update(values)
    return [cells[key] for key in ls.TARGET_FIELDS]


class TestPlano(unittest.TestCase):
    def test_resolve_site_e_papel(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.ROLE_KEY: "Reservado"})]), snapshot()
        )
        linha = plan.rows[0]
        self.assertTrue(linha.ready, linha.issues)
        self.assertEqual(linha.site_id, 10)
        self.assertEqual(linha.role_id, 2)

    def test_site_inexistente_bloqueia(self):
        plan = link_plan.build_plan(build_sheet([row()]), {})
        self.assertFalse(plan.rows[0].ready)
        self.assertFalse(plan.can_import)

    def test_plano_vazio_nao_pode_importar(self):
        plan = link_plan.build_plan(build_sheet([]), snapshot())
        self.assertFalse(plan.can_import)

    def test_escopo_do_prefixo_na_4_3(self):
        plan = link_plan.build_plan(build_sheet([row()]), snapshot("scope_type"))
        self.assertEqual(plan.scope_field, "scope_type")
        payload = plan.rows[0].public_prefix_payload(plan.scope_field)
        self.assertEqual(payload["scope_type"], "dcim.site")
        self.assertEqual(payload["scope_id"], 10)
        self.assertNotIn("site", payload)

    def test_escopo_do_prefixo_antes_da_4_3(self):
        plan = link_plan.build_plan(build_sheet([row()]), snapshot("site"))
        self.assertEqual(plan.scope_field, "site")
        payload = plan.rows[0].public_prefix_payload(plan.scope_field)
        self.assertEqual(payload["site"], 10)
        self.assertNotIn("scope_id", payload)

    def test_payload_do_bloco_publico(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.PROVIDER_KEY: "PROVEDOR - chamado 12345"})]), snapshot()
        )
        payload = plan.rows[0].public_prefix_payload(plan.scope_field)
        self.assertEqual(payload["prefix"], "203.0.113.240/30")
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["description"], "PROVEDOR")
        self.assertEqual(payload["comments"], "PROVEDOR - chamado 12345")

    def test_descricao_cai_para_o_site(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.DESCRIPTION_KEY: ""})]), snapshot()
        )
        self.assertEqual(plan.rows[0].base_description, "SITE EXEMPLO")

    def test_payload_do_bloco_lan(self):
        plan = link_plan.build_plan(build_sheet([row()]), snapshot())
        payload = plan.rows[0].lan_prefix_payload(plan.scope_field)
        self.assertEqual(payload["prefix"], "10.10.48.0/24")
        self.assertIn("(LAN)", payload["description"])

    def test_sem_bloco_lan_nao_cria_payload(self):
        plan = link_plan.build_plan(build_sheet([row(**{ls.LAN_KEY: ""})]), snapshot())
        self.assertIsNone(plan.rows[0].lan_prefix_payload())
        self.assertEqual(plan.prefix_count, 1)

    def test_contagem_de_prefixos(self):
        plan = link_plan.build_plan(build_sheet([row()]), snapshot())
        self.assertEqual(plan.prefix_count, 2)

    def test_ip_deduzido_quando_em_branco(self):
        plan = link_plan.build_plan(build_sheet([row(**{ls.IP_KEY: ""})]), snapshot())
        linha = plan.rows[0]
        self.assertEqual(linha.link_ip, "203.0.113.241/30")
        self.assertTrue(linha.link_ip_deduced)
        self.assertTrue(any("deduzido" in aviso for aviso in linha.warnings))

    def test_ip_vem_do_endereco_na_coluna_do_bloco(self):
        """Planilha real traz o endereco do roteador dentro do bloco."""
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.IP_KEY: "", ls.PUBLIC_KEY: "198.51.100.45/31"})]),
            snapshot(),
        )
        linha = plan.rows[0]
        self.assertEqual(linha.public_block, "198.51.100.44/31")
        self.assertEqual(linha.link_ip, "198.51.100.45/31")
        self.assertFalse(linha.link_ip_deduced)
        self.assertTrue(any("veio do proprio bloco" in aviso for aviso in linha.warnings))

    def test_coluna_ip_manda_sobre_o_endereco_do_bloco(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.PUBLIC_KEY: "203.0.113.241/30", ls.IP_KEY: "203.0.113.242"})]),
            snapshot(),
        )
        linha = plan.rows[0]
        self.assertEqual(linha.link_ip, "203.0.113.242/30")
        self.assertTrue(any("difere do endereco" in aviso for aviso in linha.warnings))

    def test_ip_explicito_recebe_a_mascara_do_bloco(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.IP_KEY: "203.0.113.242"})]), snapshot()
        )
        linha = plan.rows[0]
        self.assertEqual(linha.link_ip, "203.0.113.242/30")
        self.assertFalse(linha.link_ip_deduced)

    def test_device_inexistente_vai_ser_criado(self):
        """Sem device no site, o link cria o roteador (com fabricante e modelo)."""
        plan = link_plan.build_plan(
            build_sheet([row()]), snapshot(devices=["OUTRO-DEVICE"])
        )
        linha = plan.rows[0]
        self.assertTrue(linha.ready, linha.issues)
        self.assertFalse(linha.device_exists)
        self.assertTrue(any("device '" in item for item in linha.pending))
        self.assertEqual(plan.devices_to_create, 1)
        self.assertTrue(plan.can_import, linha.issues)

    def test_device_sem_fabricante_e_modelo_bloqueia(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.VENDOR_KEY: "", ls.MODEL_KEY: ""})]),
            snapshot(devices=["OUTRO-DEVICE"]),
        )
        self.assertTrue(
            any("nao da para cria-lo" in item for item in plan.rows[0].issues)
        )
        self.assertFalse(plan.can_import)

    def test_papel_do_device_inexistente_bloqueia(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.DEVICE_ROLE_KEY: "Papel Fantasma"})]),
            snapshot(devices=["OUTRO-DEVICE"]),
        )
        self.assertTrue(any("Papel de device" in item for item in plan.rows[0].issues))

    def test_papel_do_device_em_branco_vira_roteador(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.DEVICE_ROLE_KEY: ""})]),
            snapshot(devices=["OUTRO-DEVICE"]),
        )
        self.assertEqual(plan.rows[0].device_role, "Roteador")
        self.assertEqual(plan.rows[0].device_role_id, 31)

    def test_device_existente_passa(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.DEVICE_KEY: "RT-1"})]), snapshot(devices=["RT-1"])
        )
        self.assertTrue(plan.can_import, plan.rows[0].issues)

    def test_device_com_caixa_diferente_gera_aviso(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.DEVICE_KEY: "rt-1"})]), snapshot(devices=["RT-1"])
        )
        linha = plan.rows[0]
        self.assertTrue(linha.ready, linha.issues)
        self.assertTrue(any("no NetBox e 'RT-1'" in aviso for aviso in linha.warnings))

    def test_nome_de_device_repetido_e_resolvido_pelo_site(self):
        """O nome do device nao e unico neste NetBox: o site desempata."""
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.DEVICE_KEY: "Mikrotik"})]),
            snapshot(
                devices=[
                    {"id": 1, "label": "Mikrotik", "site_id": 999},
                    {"id": 2, "label": "Mikrotik", "site_id": 10},
                ]
            ),
        )
        linha = plan.rows[0]
        self.assertTrue(linha.ready, linha.issues)
        self.assertTrue(any("resolvido pelo site" in aviso for aviso in linha.warnings))

    def test_nome_existente_em_outro_site_e_criado_aqui_com_aviso(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.DEVICE_KEY: "Mikrotik"})]),
            snapshot(
                devices=[
                    {"id": 1, "label": "Mikrotik", "site_id": 999},
                    {"id": 2, "label": "Mikrotik", "site_id": 888},
                ]
            ),
        )
        linha = plan.rows[0]
        self.assertTrue(linha.ready, linha.issues)
        self.assertFalse(linha.device_exists)
        self.assertTrue(any("outro site" in aviso for aviso in linha.warnings))

    def test_sem_lista_de_devices_nao_valida(self):
        """Descoberta sem devices (token sem permissao): quem valida e a importacao."""
        plan = link_plan.build_plan(build_sheet([row()]), snapshot())
        self.assertTrue(plan.can_import, plan.rows[0].issues)

    def test_interface_padrao(self):
        plan = link_plan.build_plan(build_sheet([row(**{ls.INTERFACE_KEY: ""})]), snapshot())
        self.assertEqual(plan.rows[0].interface, ls.DEFAULT_INTERFACE)

    def test_zabbix_da_planilha_manda(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.ZABBIX_KEY: "1"})]), snapshot(sample="0")
        )
        self.assertEqual(plan.rows[0].ip_custom_fields["add_to_zabbix"], "1")

    def test_zabbix_em_branco_usa_a_amostra(self):
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.ZABBIX_KEY: ""})]), snapshot(sample="0")
        )
        self.assertEqual(plan.rows[0].ip_custom_fields["add_to_zabbix"], "0")

    def test_campo_obrigatorio_sem_valor_bloqueia(self):
        """Sem `add_to_zabbix` o POST do IP leva 400: melhor bloquear antes."""
        plan = link_plan.build_plan(
            build_sheet([row()]), snapshot(sample=None, ip_required=True)
        )
        self.assertTrue(
            any("ipam.ipaddress.add_to_zabbix" in item for item in plan.rows[0].issues)
        )
        self.assertFalse(plan.can_import)

    def test_coluna_zabbix_satisfaz_o_campo_obrigatorio(self):
        """A coluna da planilha e um valor valido: nao pode bloquear a importacao."""
        plan = link_plan.build_plan(
            build_sheet([row(**{ls.ZABBIX_KEY: "1"})]),
            snapshot(sample=None, ip_required=True),
        )
        self.assertTrue(plan.can_import, plan.rows[0].issues)
        self.assertEqual(plan.rows[0].ip_custom_fields["add_to_zabbix"], "1")

    def test_campo_nao_obrigatorio_nao_bloqueia(self):
        plan = link_plan.build_plan(
            build_sheet([row()]), snapshot(sample=None, ip_required=False)
        )
        self.assertEqual(plan.missing_required, [])
        self.assertTrue(plan.can_import, plan.missing_required)

    def test_custom_field_do_prefixo_vai_no_payload(self):
        """Campo obrigatorio em `ipam.prefix` tem que ser enviado e conferido."""
        campo = {
            "name": "contrato",
            "label": "Contrato",
            "type": "text",
            "required": True,
            "object_types": ["ipam.prefix"],
        }
        plan = link_plan.build_plan(
            build_sheet([row()]), snapshot(prefix_fields=[campo])
        )
        # Sem valor declarado em app/config.py, o campo nao tem de onde sair.
        self.assertTrue(
            any("ipam.prefix.contrato" in item for item in plan.rows[0].issues)
        )
        self.assertFalse(plan.can_import)

    def test_custom_field_do_prefixo_declarado_entra_no_payload(self):
        campo = {
            "name": "contrato",
            "label": "Contrato",
            "type": "text",
            "required": False,
            "object_types": ["ipam.prefix"],
        }
        from app import config

        with mock.patch.dict(config.CUSTOM_FIELDS, {"ipam.prefix": {"contrato": "CT-1"}}):
            plan = link_plan.build_plan(
                build_sheet([row()]), snapshot(prefix_fields=[campo])
            )
        payload = plan.rows[0].public_prefix_payload(plan.scope_field)
        self.assertEqual(payload["custom_fields"], {"contrato": "CT-1"})

    def test_registra_o_que_foi_enviado_em_custom_fields(self):
        plan = link_plan.build_plan(build_sheet([row()]), snapshot(sample="0"))
        self.assertEqual(
            plan.custom_fields_used["ipam.ipaddress"], {"add_to_zabbix": "0"}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
