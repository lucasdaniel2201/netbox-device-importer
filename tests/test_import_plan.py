"""Testes do plano de importacao (app/import_plan.py).

O plano e puro (nao fala com o NetBox), entao da para testar tudo aqui: resolucao
de site/papel/fabricante/device-type pelo snapshot, o que falta criar, o que fica
bloqueado e o corpo do device.

Cenario base = a instancia real: tenant de Pirapora, papel "Camera", os dois
device-types que ja existem e o que falta (iDS-TCM403-BI).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    config,
    import_plan,
)

# Campos obrigatorios de verdade nesta instancia (descobertos via OPTIONS + custom-fields).
CAMPO_DEVICE = {
    "name": "Validavel",
    "label": "Validavel?",
    "type": "boolean",
    "required": True,
    "object_types": ["dcim.device"],
}
CAMPO_IP = {
    "name": "add_to_zabbix",
    "label": "Adicionar ao zabbix?",
    "type": "select",
    "required": True,
    "object_types": ["ipam.ipaddress"],
}


def snapshot(
    sites=None,
    roles=None,
    manufacturers=None,
    device_types=None,
    custom_fields=None,
    custom_fields_sample=None,
):
    """Snapshot no mesmo formato que a descoberta grava."""
    base = {
        "objects": {
            "sites": sites if sites is not None else [
                {"id": 7507, "label": "AME VILANOVA"},
                {"id": 7518, "label": "ESCOLA PADRE CHICO"},
            ],
            "device_roles": roles if roles is not None else [
                {"id": 3, "label": "Camera"},
                {"id": 9, "label": "NVR"},
            ],
            "manufacturers": manufacturers if manufacturers is not None else [
                {"id": 4, "label": "Hikvision"},
                {"id": 5, "label": "Dahua"},
            ],
            "device_types": device_types if device_types is not None else [
                {"id": 210, "label": "DS-2CD3666G2T-IZS", "manufacturer": "Hikvision"},
                {"id": 359, "label": "DH-IPC-HDBW4431EN-ASE-0360B", "manufacturer": "Dahua"},
            ],
        }
    }
    if custom_fields is not None:
        base["custom_fields"] = custom_fields
    if custom_fields_sample is not None:
        base["custom_fields_sample"] = custom_fields_sample
    return base


def snapshot_com_rede(**kwargs):
    """Snapshot com permissao de escrita em interface e ip-address.

    E o que a instancia passou a devolver depois que o usuario virou superusuario:
    todos os endpoints com POST/PUT.
    """
    base = snapshot(**kwargs)
    base["schema"] = {
        "interface": {"actions": {"POST": {}, "PUT": {}}},
        "ip_address": {"actions": {"POST": {}, "PUT": {}}},
    }
    return base


def make_row(**values):
    cells = {
        "Name": "AME-STP2-CAM1-RECEPCAO",
        "Site": "AME VILANOVA",
        "Role": "",
        "IP": "10.100.20.58",
        "Vendor": "Hikvision",
        "Model": "DS-2CD3666G2T-IZS",
        "Firmware": "V5.7.55",
        "MAC address": "AA-BB-CC-DD-EE-FF",
        "Server": "NVR-1 (10.100.20.4)",
        "Description": "Camera da recepcao",
    }
    cells.update(values)

    class Row:
        row_number = 2
        name_normalized = cells["Name"]
        issues = []
        warnings = []

    Row.cells = cells
    return Row


class FakeSheet:
    def __init__(self, *rows):
        self.rows = list(rows)


class TestSlugify(unittest.TestCase):
    def test_tira_acento_e_espaco(self):
        self.assertEqual(import_plan.slugify("Hikvision"), "hikvision")
        self.assertEqual(import_plan.slugify("DS-2CD3666G2T-IZS"), "ds-2cd3666g2t-izs")

    def test_espaco_vira_hifen(self):
        self.assertEqual(import_plan.slugify("AME VILANOVA"), "ame-vilanova")

    def test_vazio_nao_fica_em_branco(self):
        """Slug do NetBox nao pode ser vazio."""
        self.assertEqual(import_plan.slugify("!!!"), "sem-nome")


class TestBuildComments(unittest.TestCase):
    def test_junta_firmware_e_nvr(self):
        texto = import_plan.build_comments("V5.7.55", "NVR-1")
        self.assertIn("Firmware: V5.7.55", texto)
        self.assertIn("NVR: NVR-1", texto)

    def test_so_firmware(self):
        texto = import_plan.build_comments("V1", "")
        self.assertIn("Firmware: V1", texto)
        self.assertNotIn("NVR:", texto)

    def test_sem_nada_nao_gera_comentario(self):
        self.assertEqual(import_plan.build_comments("", ""), "")


class TestBuildPlan(unittest.TestCase):
    def test_linha_que_ja_existe_fica_pronta(self):
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot())
        self.assertEqual(len(plan.devices), 1)
        device = plan.devices[0]
        self.assertTrue(device.ready, device.issues)
        self.assertEqual(device.site_id, 7507)
        self.assertEqual(device.role_id, 3)
        self.assertEqual(device.device_type_id, 210)
        self.assertEqual(plan.references, [])
        self.assertEqual(device.pending, [])
        self.assertTrue(plan.can_import)

    def test_payload_do_device(self):
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot())
        payload = plan.devices[0].payload()
        self.assertEqual(payload["name"], "AME-STP2-CAM1-RECEPCAO")
        self.assertEqual(payload["site"], 7507)
        self.assertEqual(payload["role"], 3)
        self.assertEqual(payload["device_type"], 210)
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["description"], "Camera da recepcao")
        self.assertIn("Firmware: V5.7.55", payload["comments"])
        self.assertIn("NVR: NVR-1", payload["comments"])
        # MAC/IP nao entram no device (vao para interface/ipam, adiados por permissao)
        self.assertNotIn("mac_address", payload)
        self.assertNotIn("ip", payload)

    def test_site_desconhecido_bloqueia_a_linha(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row(**{"Site": "SITE QUE NAO EXISTE"})), snapshot()
        )
        device = plan.devices[0]
        self.assertFalse(device.ready)
        self.assertTrue(any("nao esta no NetBox" in i for i in device.issues))
        self.assertFalse(plan.can_import)

    def test_papel_inexistente_bloqueia(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row()), snapshot(roles=[{"id": 9, "label": "NVR"}])
        )
        self.assertFalse(plan.devices[0].ready)
        self.assertFalse(plan.can_import)

    def test_device_type_faltando_vira_referencia_a_criar(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row(**{"Model": "iDS-TCM403-BI"})), snapshot()
        )
        self.assertEqual(len(plan.references), 1)
        ref = plan.references[0]
        self.assertEqual(ref.kind, "device_type")
        self.assertEqual(ref.manufacturer_name, "Hikvision")
        self.assertEqual(ref.payload["model"], "iDS-TCM403-BI")
        self.assertEqual(ref.payload["slug"], "hikvision-ids-tcm403-bi")
        self.assertFalse(plan.can_import)
        self.assertFalse(plan.devices[0].ready)
        # O motivo precisa aparecer: sem isso a linha ficava bloqueada e muda.
        self.assertEqual(plan.devices[0].pending, ["device-type 'Hikvision iDS-TCM403-BI'"])
        self.assertEqual(plan.devices[0].issues, [])

    def test_fabricante_faltando_vira_referencia_a_criar(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row(**{"Vendor": "Intelbras", "Model": "VIP 3230"})), snapshot()
        )
        kinds = sorted(ref.kind for ref in plan.references)
        self.assertEqual(kinds, ["device_type", "manufacturer"])
        fabricante = next(r for r in plan.references if r.kind == "manufacturer")
        self.assertEqual(fabricante.payload, {"name": "Intelbras", "slug": "intelbras"})
        self.assertIn("fabricante 'Intelbras'", plan.devices[0].pending)
        self.assertIn(
            "device-type 'Intelbras VIP 3230'", plan.devices[0].pending
        )

    def test_referencia_repetida_aparece_uma_vez(self):
        plan = import_plan.build_plan(
            FakeSheet(
                make_row(**{"Model": "iDS-TCM403-BI"}),
                make_row(Name="AME-STP2-CAM2", **{"Model": "iDS-TCM403-BI"}),
            ),
            snapshot(),
        )
        self.assertEqual(len(plan.references), 1)

    def test_dois_fabricantes_geram_duas_referencias(self):
        plan = import_plan.build_plan(
            FakeSheet(
                make_row(**{"Vendor": "Intelbras", "Model": "VIP 3230"}),
                make_row(Name="OUTRA", **{"Vendor": "Axis", "Model": "P1455-LE"}),
            ),
            snapshot(),
        )
        fabricantes = [r for r in plan.references if r.kind == "manufacturer"]
        self.assertEqual(sorted(r.label for r in fabricantes), ["Axis", "Intelbras"])

    def test_sem_fabricante_ou_modelo_bloqueia(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row(**{"Vendor": "", "Model": ""})), snapshot()
        )
        device = plan.devices[0]
        self.assertFalse(device.ready)
        self.assertTrue(any("device-type" in i for i in device.issues))

    def test_erros_da_planilha_sao_carregados_para_o_plano(self):
        linha = make_row()
        linha.issues = ["IP com formato invalido: '999.1.1'."]
        plan = import_plan.build_plan(FakeSheet(linha), snapshot())
        self.assertFalse(plan.devices[0].ready)
        self.assertIn("IP com formato invalido: '999.1.1'.", plan.devices[0].issues)

    def test_erro_de_site_da_planilha_nao_duplica(self):
        linha = make_row()
        linha.issues = ["Site 'XX' nao existe no NetBox (use a lista suspensa do modelo)."]
        plan = import_plan.build_plan(FakeSheet(linha), snapshot())
        mensagens = [i for i in plan.devices[0].issues if i.startswith("Site")]
        self.assertEqual(len(mensagens), 1)

    def test_diferenca_de_caixa_e_acento_no_site_resolve(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row(**{"Site": "ame vilanova"})), snapshot()
        )
        self.assertTrue(plan.devices[0].ready, plan.devices[0].issues)
        self.assertEqual(plan.devices[0].site_id, 7507)

    def test_mac_e_ip_ficam_adiados(self):
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot())
        self.assertTrue(any("dcim.interface" in nota for nota in plan.deferred))

    def test_options_alteram_papel_e_status(self):
        options = import_plan.PlanOptions(role="NVR", status="planned")
        plan = import_plan.build_plan(
            FakeSheet(make_row(**{"Model": "DH-IPC-HDBW4431EN-ASE-0360B", "Vendor": "Dahua"})),
            snapshot(),
            options,
        )
        device = plan.devices[0]
        self.assertTrue(device.ready, device.issues)
        self.assertEqual(device.role_id, 9)
        self.assertEqual(device.payload()["status"], "planned")

    def test_contadores_de_prontos_e_bloqueados(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row(), make_row(Name="OUTRA", **{"Site": "NAO EXISTE"})),
            snapshot(),
        )
        self.assertEqual(len(plan.ready_devices), 1)
        self.assertEqual(len(plan.blocked_devices), 1)
        self.assertFalse(plan.can_import)


class TestCustomFields(unittest.TestCase):
    """Custom fields no payload: foi o que faltava para o "Validavel" passar."""

    def test_remove_vazios(self):
        self.assertEqual(
            import_plan.clean_custom_fields(
                {"a": None, "b": "", "c": "   ", "d": "x", "e": True, "f": False,
                 "g": [], "h": ()}
            ),
            {"d": "x", "e": True, "f": False},
        )

    def test_vazio_nao_quebra(self):
        self.assertEqual(import_plan.clean_custom_fields(None), {})
        self.assertEqual(import_plan.clean_custom_fields({}), {})

    def test_lista_preenchida_e_mantida(self):
        self.assertEqual(
            import_plan.clean_custom_fields({"analitico": ["a"]}), {"analitico": ["a"]}
        )

    def test_payload_inclui_custom_fields(self):
        options = import_plan.PlanOptions(custom_fields={"validavel": True})
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot(), options)
        self.assertEqual(plan.devices[0].payload()["custom_fields"], {"validavel": True})

    def test_payload_inclui_lista_de_verdade(self):
        options = import_plan.PlanOptions(custom_fields={"analitico": ["tipos"]})
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot(), options)
        valor = plan.devices[0].payload()["custom_fields"]["analitico"]
        self.assertEqual(valor, ["tipos"])
        self.assertIsInstance(valor, list)

    def test_payload_omite_custom_fields_vazios(self):
        options = import_plan.PlanOptions(custom_fields={"validavel": "", "outro": []})
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot(), options)
        self.assertNotIn("custom_fields", plan.devices[0].payload())

    def test_payload_explicitamente_vazio_nao_leva_a_chave(self):
        options = import_plan.PlanOptions(custom_fields={})
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot(), options)
        self.assertNotIn("custom_fields", plan.devices[0].payload())

    def test_sem_opcoes_usa_os_valores_fixos_do_app(self):
        """Sem tela de campos personalizados, vale o que esta em app/config.py."""
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot())
        self.assertEqual(
            plan.devices[0].payload()["custom_fields"],
            config.CUSTOM_FIELDS["dcim.device"],
        )

    def test_registra_o_que_foi_enviado(self):
        """Os valores fixos nao podem ser invisiveis: o plano mostra o que manda."""
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot_com_rede())
        self.assertEqual(plan.custom_fields_used["dcim.device"], {"Validavel": True})

    def test_sem_rede_nao_lista_campos_do_ip(self):
        """Sem permissao de IP, o IP nem e criado - nao faz sentido listar campos dele."""
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot())
        self.assertNotIn("ipam.ipaddress", plan.custom_fields_used)


class TestValorVindoDaAmostra(unittest.TestCase):
    """A API nao expoe as opcoes dos selects: usar o valor de um objeto real.

    Foi o que quebrou de verdade: `add_to_zabbix: "Sim"` chutado no config deu
    "Escolha Sim e invalida para o conjunto de escolhas add_to_zabbix".
    """

    def snapshot(self, required=True):
        return snapshot_com_rede(
            custom_fields=[
                dict(CAMPO_IP, required=required),
                dict(CAMPO_DEVICE, required=required),
            ],
            custom_fields_sample={
                "dcim.device": {"Validavel": True},
                "ipam.ipaddress": {"add_to_zabbix": "Sim, CFTV"},
            },
        )

    def test_campo_obrigatorio_sem_valor_declarado_usa_a_amostra(self):
        options = import_plan.PlanOptions(custom_fields={}, ip_custom_fields={})
        plan = import_plan.build_plan(FakeSheet(make_row()), self.snapshot(), options)
        self.assertEqual(
            plan.custom_fields_used["ipam.ipaddress"], {"add_to_zabbix": "Sim, CFTV"}
        )
        self.assertEqual(plan.missing_required, [])
        self.assertTrue(plan.can_import)

    def test_valor_declarado_vence_a_amostra(self):
        options = import_plan.PlanOptions(
            ip_custom_fields={"add_to_zabbix": "Escolha Do Time"}
        )
        plan = import_plan.build_plan(FakeSheet(make_row()), self.snapshot(), options)
        self.assertEqual(
            plan.custom_fields_used["ipam.ipaddress"], {"add_to_zabbix": "Escolha Do Time"}
        )

    def test_campo_opcional_nao_e_preenchido_pela_amostra(self):
        """So os obrigatorios: nao vale inventar valor em campo opcional."""
        snap = snapshot_com_rede(
            custom_fields=[dict(CAMPO_IP, required=False)],
            custom_fields_sample={"ipam.ipaddress": {"add_to_zabbix": "Sim, CFTV"}},
        )
        options = import_plan.PlanOptions(ip_custom_fields={})
        plan = import_plan.build_plan(FakeSheet(make_row()), snap, options)
        self.assertEqual(plan.custom_fields_used.get("ipam.ipaddress", {}), {})

    def test_sem_amostra_e_sem_valor_declarado_bloqueia(self):
        snap = snapshot_com_rede(
            custom_fields=[dict(CAMPO_IP)], custom_fields_sample={"ipam.ipaddress": {}}
        )
        options = import_plan.PlanOptions(ip_custom_fields={})
        plan = import_plan.build_plan(FakeSheet(make_row()), snap, options)
        self.assertEqual(plan.missing_required, ["ipam.ipaddress.add_to_zabbix"])
        self.assertFalse(plan.can_import)

    def test_amostra_vazia_nao_vira_valor(self):
        """Um None observado nao pode virar valor enviado."""
        snap = snapshot_com_rede(
            custom_fields=[dict(CAMPO_IP)],
            custom_fields_sample={"ipam.ipaddress": {"add_to_zabbix": None}},
        )
        options = import_plan.PlanOptions(ip_custom_fields={})
        plan = import_plan.build_plan(FakeSheet(make_row()), snap, options)
        self.assertEqual(plan.missing_required, ["ipam.ipaddress.add_to_zabbix"])


class TestCampoObrigatorioFaltando(unittest.TestCase):
    """Sem a tela, o alarme e este: campo exigido pelo NetBox e nao enviado."""

    def test_campo_do_device_faltando_bloqueia(self):
        options = import_plan.PlanOptions(custom_fields={})  # nao manda Validavel
        plan = import_plan.build_plan(
            FakeSheet(make_row()), snapshot(custom_fields=[CAMPO_DEVICE]), options
        )
        self.assertEqual(plan.missing_required, ["dcim.device.Validavel"])
        self.assertFalse(plan.can_import)

    def test_campo_do_device_enviado_libera(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row()), snapshot(custom_fields=[CAMPO_DEVICE])
        )
        self.assertEqual(plan.missing_required, [])
        self.assertTrue(plan.can_import)

    def test_campo_do_ip_conta_quando_o_ip_vai_ser_criado(self):
        options = import_plan.PlanOptions(ip_custom_fields={})
        plan = import_plan.build_plan(
            FakeSheet(make_row()), snapshot_com_rede(custom_fields=[CAMPO_IP]), options
        )
        self.assertEqual(plan.missing_required, ["ipam.ipaddress.add_to_zabbix"])
        self.assertFalse(plan.can_import)

    def test_campo_do_ip_nao_conta_sem_permissao_de_rede(self):
        options = import_plan.PlanOptions(ip_custom_fields={})
        plan = import_plan.build_plan(
            FakeSheet(make_row()), snapshot(custom_fields=[CAMPO_IP]), options
        )
        self.assertEqual(plan.missing_required, [])

    def test_campo_opcional_nao_bloqueia(self):
        opcional = dict(CAMPO_DEVICE, required=False)
        options = import_plan.PlanOptions(custom_fields={})
        plan = import_plan.build_plan(
            FakeSheet(make_row()), snapshot(custom_fields=[opcional]), options
        )
        self.assertEqual(plan.missing_required, [])
        self.assertTrue(plan.can_import)


class TestPapelPorLinha(unittest.TestCase):
    """A coluna Papel da planilha permite misturar camera e switch num lote so."""

    def test_papel_da_planilha_manda(self):
        plan = import_plan.build_plan(FakeSheet(make_row(Role="NVR")), snapshot())
        self.assertEqual(plan.devices[0].role_id, 9)  # NVR no snapshot de teste

    def test_papel_vazio_usa_o_da_tela(self):
        plan = import_plan.build_plan(FakeSheet(make_row(Role="")), snapshot())
        self.assertEqual(plan.devices[0].role_id, 3)  # Camera (DEFAULT_ROLE)

    def test_papel_da_planilha_ignora_caixa(self):
        plan = import_plan.build_plan(FakeSheet(make_row(Role="nvr")), snapshot())
        self.assertEqual(plan.devices[0].role_id, 9)

    def test_papel_inexistente_bloqueia_a_linha(self):
        plan = import_plan.build_plan(FakeSheet(make_row(Role="Inexistente")), snapshot())
        self.assertFalse(plan.devices[0].ready)
        self.assertTrue(any("Papel" in i for i in plan.devices[0].issues))

    def test_lote_com_papeis_diferentes(self):
        plan = import_plan.build_plan(
            FakeSheet(make_row(Role="Camera"), make_row(Name="SW-01", Role="Switch")),
            snapshot(roles=[{"id": 3, "label": "Camera"}, {"id": 7, "label": "Switch"}]),
        )
        papeis = {d.name: d.role_id for d in plan.devices}
        self.assertEqual(papeis, {"AME-STP2-CAM1-RECEPCAO": 3, "SW-01": 7})

    def test_sem_a_coluna_usa_o_papel_da_tela(self):
        linha = make_row()
        del linha.cells["Role"]
        plan = import_plan.build_plan(FakeSheet(linha), snapshot())
        self.assertEqual(plan.devices[0].role_id, 3)


class TestRede(unittest.TestCase):
    """Interface + IP so entram quando o token pode escrever nos dois endpoints."""

    def test_sem_permissao_fica_adiado(self):
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot())
        self.assertFalse(plan.devices[0].include_network)
        self.assertEqual(plan.devices[0].interface_name, "")
        self.assertTrue(any("dcim.interface" in nota for nota in plan.deferred))

    def test_com_permissao_nao_fica_adiado(self):
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot_com_rede())
        self.assertTrue(plan.devices[0].include_network)
        self.assertEqual(
            plan.devices[0].interface_name, import_plan.provision.DEFAULT_INTERFACE_NAME
        )
        self.assertEqual(plan.deferred, [])

    def test_exige_os_dois_endpoints(self):
        so_interface = {"schema": {"interface": {"actions": {"POST": {}}}}}
        self.assertFalse(import_plan.network_enabled(so_interface))
        so_ip = {"schema": {"ip_address": {"actions": {"POST": {}}}}}
        self.assertFalse(import_plan.network_enabled(so_ip))

    def test_nome_da_interface_e_configuravel(self):
        options = import_plan.PlanOptions(interface_name="NIC1")
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot_com_rede(), options)
        self.assertEqual(plan.devices[0].interface_name, "NIC1")


class TestCustomFieldDefs(unittest.TestCase):
    """Com a permissao de extras.customfield, tipo e obrigatoriedade vem exatos."""

    def snapshot(self):
        return {
            "custom_fields": [
                {
                    "name": "Validavel",
                    "label": "Validavel",
                    "type": "boolean",
                    "required": True,
                    "object_types": ["dcim.device"],
                },
                {
                    "name": "Tamanhos",
                    "label": "Tamanho do SD Card",
                    "type": "select",
                    "required": False,
                    "object_types": ["dcim.device"],
                },
                {
                    "name": "outro",
                    "label": "Outro",
                    "type": "text",
                    "required": True,
                    "object_types": ["dcim.site"],
                },
            ]
        }

    def test_so_o_objeto_pedido(self):
        defs = import_plan.custom_field_defs(self.snapshot())
        self.assertEqual(sorted(defs), ["Tamanhos", "Validavel"])

    def test_marca_quem_e_obrigatorio(self):
        defs = import_plan.custom_field_defs(self.snapshot())
        self.assertTrue(defs["Validavel"]["required"])
        self.assertFalse(defs["Tamanhos"]["required"])

    def test_traz_tipo_e_rotulo(self):
        defs = import_plan.custom_field_defs(self.snapshot())
        self.assertEqual(defs["Validavel"]["type"], "boolean")
        self.assertEqual(defs["Tamanhos"]["label"], "Tamanho do SD Card")

    def test_sem_custom_fields_nao_quebra(self):
        self.assertEqual(import_plan.custom_field_defs({}), {})


class TestCustomFieldKind(unittest.TestCase):
    def test_booleano(self):
        self.assertEqual(import_plan.custom_field_kind(True), "bool")
        self.assertEqual(import_plan.custom_field_kind(False), "bool")

    def test_lista(self):
        self.assertEqual(import_plan.custom_field_kind(["a"]), "list")
        self.assertEqual(import_plan.custom_field_kind([]), "list")

    def test_texto(self):
        self.assertEqual(import_plan.custom_field_kind("x"), "text")
        self.assertEqual(import_plan.custom_field_kind(None), "text")
        self.assertEqual(import_plan.custom_field_kind(7), "text")

    def test_tipo_declarado_manda_sobre_o_exemplo(self):
        self.assertEqual(import_plan.custom_field_kind(None, "boolean"), "bool")
        self.assertEqual(import_plan.custom_field_kind(None, "multiselect"), "list")
        self.assertEqual(import_plan.custom_field_kind(None, "integer"), "int")
        self.assertEqual(import_plan.custom_field_kind(None, "select"), "text")
        self.assertEqual(import_plan.custom_field_kind(["a"], "multiselect"), "list")

    def test_tipo_desconhecido_cai_em_texto(self):
        self.assertEqual(import_plan.custom_field_kind(None, "json"), "text")


class TestParseCustomValue(unittest.TestCase):
    """Regressao do erro real: "Escolha [] e invalida para o conjunto de escolhas"."""

    def test_lista_separada_por_virgula(self):
        self.assertEqual(import_plan.parse_custom_value("list", "a, b"), ["a", "b"])

    def test_lista_separada_por_ponto_e_virgula(self):
        self.assertEqual(import_plan.parse_custom_value("list", "a; b"), ["a", "b"])

    def test_formato_do_netbox_vira_lista(self):
        self.assertEqual(import_plan.parse_custom_value("list", "['a', 'b']"), ["a", "b"])

    def test_lista_vazia_e_omitida(self):
        self.assertIsNone(import_plan.parse_custom_value("list", ""))
        self.assertIsNone(import_plan.parse_custom_value("list", "[]"))
        self.assertIsNone(import_plan.parse_custom_value("list", " , "))

    def test_lista_ja_pronta_e_respeitada(self):
        self.assertEqual(import_plan.parse_custom_value("list", ["a", "b"]), ["a", "b"])

    def test_booleano(self):
        self.assertTrue(import_plan.parse_custom_value("bool", "true"))
        self.assertTrue(import_plan.parse_custom_value("bool", "sim"))
        self.assertFalse(import_plan.parse_custom_value("bool", "false"))
        self.assertIsNone(import_plan.parse_custom_value("bool", ""))

    def test_booleano_desconhecido_e_omitido_nao_chutado(self):
        """Melhor omitir do que gravar um booleano errado em silencio."""
        self.assertIsNone(import_plan.parse_custom_value("bool", "talvez"))

    def test_booleano_aceita_o_rotulo_do_dropdown(self):
        self.assertTrue(import_plan.parse_custom_value("bool", "sim (true)"))
        self.assertFalse(import_plan.parse_custom_value("bool", "nao (false)"))

    def test_texto_apara_espacos(self):
        self.assertEqual(import_plan.parse_custom_value("text", "  x  "), "x")
        self.assertIsNone(import_plan.parse_custom_value("text", "   "))


class TestCustomFieldsDoIP(unittest.TestCase):
    """O IP tem os seus proprios custom fields (`add_to_zabbix` e obrigatorio)."""

    def snapshot(self):
        return {
            "custom_fields_sample": {
                "dcim.device": {"Validavel": True},
                "ipam.ipaddress": {"add_to_zabbix": "Sim", "hostID": None},
            }
        }

    def test_amostra_por_tipo_de_objeto(self):
        self.assertEqual(
            import_plan.custom_field_sample(self.snapshot(), "ipam.ipaddress"),
            {"add_to_zabbix": "Sim", "hostID": None},
        )
        self.assertEqual(
            import_plan.custom_field_sample(self.snapshot(), "dcim.device"),
            {"Validavel": True},
        )

    def test_objeto_sem_amostra(self):
        self.assertEqual(import_plan.custom_field_sample({}, "ipam.ipaddress"), {})
        self.assertEqual(import_plan.custom_field_sample({"custom_fields_sample": {}}, "x"), {})

    def test_formato_antigo_nao_quebra(self):
        """Snapshot antigo trazia o dict plano (so device): nao pode explodir."""
        antigo = {"custom_fields_sample": {"Validavel": True}}
        self.assertEqual(import_plan.custom_field_sample(antigo, "dcim.device"), {})

    def test_ip_custom_fields_vao_para_o_device(self):
        options = import_plan.PlanOptions(ip_custom_fields={"add_to_zabbix": "Sim"})
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot(), options)
        self.assertEqual(plan.devices[0].ip_custom_fields, {"add_to_zabbix": "Sim"})

    def test_ip_custom_fields_vazios_nao_entram(self):
        options = import_plan.PlanOptions(ip_custom_fields={"add_to_zabbix": "", "outro": []})
        plan = import_plan.build_plan(FakeSheet(make_row()), snapshot(), options)
        self.assertEqual(plan.devices[0].ip_custom_fields, {})

    def test_definicoes_do_ip(self):
        snap = {
            "custom_fields": [
                {
                    "name": "add_to_zabbix",
                    "label": "Adicionar ao zabbix?",
                    "type": "select",
                    "required": True,
                    "object_types": ["ipam.ipaddress"],
                }
            ]
        }
        defs = import_plan.custom_field_defs(snap, "ipam.ipaddress")
        self.assertTrue(defs["add_to_zabbix"]["required"])
        self.assertEqual(defs["add_to_zabbix"]["label"], "Adicionar ao zabbix?")
        self.assertEqual(import_plan.custom_field_defs(snap, "dcim.device"), {})


class TestFindObjectId(unittest.TestCase):
    def test_acha_pelo_rotulo_sem_acento_e_caixa(self):
        self.assertEqual(
            import_plan.find_object_id(snapshot(), "manufacturers", "hikvision"), 4
        )

    def test_nao_acha_retorna_none(self):
        self.assertIsNone(import_plan.find_object_id(snapshot(), "manufacturers", "Axis"))


class TestDeviceTypeKey(unittest.TestCase):
    def test_chave_usa_fabricante_e_modelo(self):
        self.assertEqual(
            import_plan.device_type_key("Hikvision", "DS-2CD3666G2T-IZS"),
            import_plan.device_type_key("HIKVISION", "ds-2cd3666g2t-izs"),
        )

    def test_fabricantes_diferentes_nao_colidem(self):
        self.assertNotEqual(
            import_plan.device_type_key("Hikvision", "X"),
            import_plan.device_type_key("Dahua", "X"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
