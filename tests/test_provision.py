"""Testes da descoberta do ambiente NetBox (app/provision.py).

Sem rede: um cliente falso devolve dados fixos.

IMPORTANTE: os payloads de OPTIONS usados aqui imitam o que a instancia real
(NetBox 4.3.6) devolve - os campos ficam DIRETO sob a acao
(`actions.POST.<campo>`), sem envelope `properties`. Foi exatamente por testar
com um payload inventado com `properties` que um bug passou: na instancia real a
extracao devolvia zero campos.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import provision  # noqa: E402
from app.netbox_client import NetBoxTLSError  # noqa: E402


class FakeClient:
    """Cliente de mentira: devolve o que for configurado, sem tocar a rede."""

    def __init__(self, data=None, counts=None, options=None, status=None, fail=()):
        self.base_url = "https://nb.local"
        self.api_version = "4.3"
        self.token_scheme = "Token"
        self._data = data or {}
        self._counts = counts or {}
        self._options = options or {}
        self._status = {"netbox-version": "4.3.6"} if status is None else status
        self._fail = set(fail)

    def status(self):
        if "status" in self._fail:
            raise RuntimeError("403 Forbidden")
        return self._status

    def fetch_all(self, path, params=None):
        if path in self._fail:
            raise RuntimeError("endpoint indisponivel")
        return list(self._data.get(path, []))

    def count(self, path, **filters):
        if path in self._fail:
            raise RuntimeError("endpoint indisponivel")
        return self._counts.get(path)

    def options(self, path):
        if path in self._fail:
            raise RuntimeError("endpoint indisponivel")
        return self._options.get(path, {})


def device_options() -> dict:
    """OPTIONS de /api/dcim/devices/ no formato real (campos direto na acao)."""
    return {
        "name": "Dispositivo List",
        "renders": ["application/json", "text/html"],
        "parses": ["application/json", "multipart/form-data"],
        "actions": {
            "PUT": {
                "id": {"type": "integer", "required": False, "read_only": True, "label": "ID"},
                "name": {
                    "type": "string",
                    "required": False,
                    "read_only": False,
                    "label": "Nome",
                    "max_length": 64,
                },
            },
            "POST": {
                "id": {"type": "integer", "required": False, "read_only": True, "label": "ID"},
                "url": {"type": "field", "required": False, "read_only": True, "label": "Url"},
                "name": {
                    "type": "string",
                    "required": False,
                    "read_only": False,
                    "label": "Nome",
                    "max_length": 64,
                },
                "device_type": {
                    "type": "nested object",
                    "required": True,
                    "read_only": False,
                    "label": "Device type",
                },
                "role": {
                    "type": "nested object",
                    "required": True,
                    "read_only": False,
                    "label": "Role",
                },
                "site": {
                    "type": "nested object",
                    "required": True,
                    "read_only": False,
                    "label": "Site",
                },
                "status": {
                    "type": "field",
                    "required": False,
                    "read_only": False,
                    "label": "Status",
                    "choices": [
                        {"value": "active", "display_name": "Ativo"},
                        {"value": "offline", "display_name": "Offline"},
                    ],
                },
                "primary_ip4": {
                    "type": "nested object",
                    "required": False,
                    "read_only": False,
                    "label": "Primary IPv4",
                },
            },
        },
    }


class TestSummarizeObject(unittest.TestCase):
    def test_site_usa_name(self):
        resumo = provision.summarize_object({"id": 1, "name": "PSF 1", "slug": "psf1"})
        self.assertEqual(resumo, {"id": 1, "label": "PSF 1", "slug": "psf1"})

    def test_device_type_traz_o_fabricante(self):
        resumo = provision.summarize_object(
            {"id": 2, "model": "DS-2CD", "manufacturer": {"id": 9, "name": "Hikvision"}}
        )
        self.assertEqual(resumo["label"], "DS-2CD")
        self.assertEqual(resumo["manufacturer"], "Hikvision")

    def test_ip_address_usa_address(self):
        resumo = provision.summarize_object({"id": 3, "address": "10.0.0.1/32"})
        self.assertEqual(resumo["label"], "10.0.0.1/32")

    def test_site_traz_o_tenant(self):
        resumo = provision.summarize_object(
            {
                "id": 4,
                "name": "AME VILANOVA",
                "tenant": {"id": 583, "name": "MUNICIPIO DE PIRAPORA DO BOM JESUS - 583"},
            }
        )
        self.assertEqual(resumo["tenant"], "MUNICIPIO DE PIRAPORA DO BOM JESUS - 583")


class TestExtractFields(unittest.TestCase):
    def test_campos_direto_sob_a_acao(self):
        """Formato REAL da instancia: actions.POST.<campo> (sem `properties`).

        Regressao: com este payload a extracao devolvia {} e a tela de campos
        ficava vazia na instancia de verdade.
        """
        campos = provision.extract_fields(device_options())
        self.assertNotEqual(campos, {})
        self.assertEqual(
            set(campos),
            {"id", "url", "name", "device_type", "role", "site", "status", "primary_ip4"},
        )

    def test_obrigatorios(self):
        campos = provision.extract_fields(device_options())
        obrigatorios = sorted(k for k, v in campos.items() if v["required"])
        self.assertEqual(obrigatorios, ["device_type", "role", "site"])

    def test_campos_opcionais_nao_sao_obrigatorios(self):
        campos = provision.extract_fields(device_options())
        self.assertFalse(campos["name"]["required"])
        self.assertFalse(campos["primary_ip4"]["required"])

    def test_choices_sao_achatadas(self):
        campos = provision.extract_fields(device_options())
        self.assertEqual(campos["status"]["choices"], ["active", "offline"])

    def test_read_only_e_marcado(self):
        campos = provision.extract_fields(device_options())
        self.assertTrue(campos["id"]["read_only"])
        self.assertFalse(campos["name"]["read_only"])

    def test_max_length_preservado(self):
        campos = provision.extract_fields(device_options())
        self.assertEqual(campos["name"]["max_length"], 64)

    def test_formato_com_properties_tambem_e_aceito(self):
        """Formato alternativo (envelope `properties`) continua funcionando."""
        payload = {
            "actions": {
                "POST": {
                    "properties": {
                        "name": {"type": "string", "required": True, "label": "Nome"}
                    }
                }
            }
        }
        campos = provision.extract_fields(payload)
        self.assertEqual(list(campos), ["name"])
        self.assertTrue(campos["name"]["required"])

    def test_extrai_de_outra_acao(self):
        campos = provision.extract_fields(device_options(), action="PUT")
        self.assertEqual(set(campos), {"id", "name"})

    def test_chaves_que_nao_sao_campo_sao_ignoradas(self):
        """`renders`/`parses`/`properties` nao tem `type` e nao viram campo."""
        campos = provision.extract_fields(
            {"actions": {"POST": {"renders": ["a"], "properties": {"x": 1}}}}
        )
        self.assertEqual(campos, {})

    def test_payload_vazio_nao_quebra(self):
        self.assertEqual(provision.extract_fields(None), {})
        self.assertEqual(provision.extract_fields({}), {})
        self.assertEqual(provision.extract_fields({"actions": {}}), {})

    def test_campo_sem_label_usa_o_nome(self):
        campos = provision.extract_fields(
            {"actions": {"POST": {"q": {"type": "string"}}}}
        )
        self.assertEqual(campos["q"]["label"], "q")


class TestEndpointActions(unittest.TestCase):
    def test_lista_acoes_permitidas(self):
        snapshot = {"schema": {"device": device_options()}}
        self.assertEqual(provision.endpoint_actions(snapshot, "device"), ["POST", "PUT"])

    def test_interface_sem_acoes(self):
        """Na instancia real o token nao tem permissao: OPTIONS volta sem acoes."""
        snapshot = {"schema": {"interface": {"name": "Interface List"}}}
        self.assertEqual(provision.endpoint_actions(snapshot, "interface"), [])

    def test_endpoint_ausente(self):
        self.assertEqual(provision.endpoint_actions({}, "device"), [])


class TestContentTypes(unittest.TestCase):
    def test_usa_o_primeiro_caminho_que_funciona(self):
        cliente = FakeClient(
            data={
                provision.CONTENT_TYPES_ENDPOINTS[1]: [
                    {"id": 1, "app_label": "dcim", "model": "device"}
                ]
            },
            fail={provision.CONTENT_TYPES_ENDPOINTS[0]},
        )
        self.assertEqual(provision._content_type_map(cliente), {1: "dcim.device"})

    def test_levanta_quando_nenhum_caminho_funciona(self):
        cliente = FakeClient(fail=set(provision.CONTENT_TYPES_ENDPOINTS))
        with self.assertRaises(RuntimeError):
            provision._content_type_map(cliente)


class TestDiscover(unittest.TestCase):
    def build_client(self, **kwargs):
        data = {
            provision.CONTENT_TYPES_ENDPOINTS[0]: [
                {"id": 1, "app_label": "dcim", "model": "device"},
                {"id": 2, "app_label": "ipam", "model": "ipaddress"},
            ],
            provision.CUSTOM_FIELDS_ENDPOINT: [
                {
                    "id": 3,
                    "name": "firmware",
                    "label": "Firmware",
                    "type": {"value": "text", "label": "Text"},
                    "required": False,
                    "object_types": [1],
                    "choices": [],
                },
                {
                    "id": 4,
                    "name": "vlan_id",
                    "label": "VLAN",
                    "type": {"value": "integer", "label": "Integer"},
                    "required": True,
                    "object_types": [2],
                    "choices": [],
                },
            ],
            "/api/dcim/sites/": [
                {"id": 7507, "name": "AME VILANOVA", "slug": "ame_vilanova"}
            ],
            "/api/dcim/manufacturers/": [{"id": 5, "name": "Hikvision", "slug": "hikvision"}],
            "/api/dcim/device-types/": [
                {"id": 210, "model": "DS-2CD3666G2T-IZS", "manufacturer": {"id": 5, "name": "Hikvision"}}
            ],
        }
        counts = {"/api/dcim/devices/": 5442, "/api/ipam/ip-addresses/": 9215}
        options = {
            "/api/dcim/devices/": device_options(),
            "/api/dcim/interfaces/": {"name": "Interface List"},  # sem acoes = sem permissao
        }
        data.update(kwargs.pop("data", {}))
        counts.update(kwargs.pop("counts", {}))
        options.update(kwargs.pop("options", {}))
        return FakeClient(data=data, counts=counts, options=options, **kwargs)

    def test_estrutura_do_snapshot(self):
        snapshot = provision.discover(self.build_client())
        for chave in ("base_url", "status", "objects", "counts", "custom_fields",
                      "content_types", "schema", "capabilities", "errors"):
            self.assertIn(chave, snapshot)
        self.assertEqual(snapshot["base_url"], "https://nb.local")

    def test_objetos_de_referencia_resumidos(self):
        snapshot = provision.discover(self.build_client())
        self.assertEqual(provision.reference_labels(snapshot, "sites"), ["AME VILANOVA"])
        self.assertEqual(snapshot["objects"]["device_types"][0]["manufacturer"], "Hikvision")

    def test_contagens(self):
        snapshot = provision.discover(self.build_client())
        self.assertEqual(snapshot["counts"]["devices"], 5442)
        self.assertEqual(snapshot["counts"]["ip_addresses"], 9215)

    def test_custom_fields_resolvem_o_object_type(self):
        snapshot = provision.discover(self.build_client())
        por_nome = {f["name"]: f for f in snapshot["custom_fields"]}
        self.assertEqual(por_nome["firmware"]["object_types"], ["dcim.device"])
        self.assertEqual(por_nome["firmware"]["type"], "text")
        self.assertEqual(por_nome["vlan_id"]["object_types"], ["ipam.ipaddress"])

    def test_campos_do_device_ficam_disponiveis(self):
        snapshot = provision.discover(self.build_client())
        campos = provision.fields_for(snapshot, "device")
        self.assertTrue(campos["name"]["required"] is False)
        self.assertTrue(campos["device_type"]["required"])
        self.assertTrue(campos["site"]["required"])

    def test_capabilities_por_endpoint(self):
        snapshot = provision.discover(self.build_client())
        self.assertEqual(snapshot["capabilities"]["device"], ["POST", "PUT"])
        self.assertEqual(snapshot["capabilities"]["interface"], [])

    def test_versao_do_netbox(self):
        snapshot = provision.discover(self.build_client())
        self.assertEqual(provision.netbox_version(snapshot), "4.3.6")

    def test_falha_em_um_endpoint_nao_derruba_o_resto(self):
        cliente = self.build_client(fail={"/api/dcim/sites/"})
        snapshot = provision.discover(cliente)
        self.assertEqual(snapshot["objects"]["sites"], [])
        self.assertTrue(any("sites" in erro for erro in snapshot["errors"]))
        self.assertEqual(provision.reference_labels(snapshot, "manufacturers"), ["Hikvision"])

    def test_falha_no_status_nao_impede_a_descoberta(self):
        snapshot = provision.discover(self.build_client(fail={"status"}))
        self.assertTrue(snapshot["errors"])
        self.assertEqual(provision.netbox_version(snapshot), "")
        self.assertEqual(provision.reference_labels(snapshot, "sites"), ["AME VILANOVA"])

    def test_versao_da_api_vem_do_cliente(self):
        snapshot = provision.discover(self.build_client())
        self.assertEqual(snapshot["api_version"], "4.3")

    def test_registra_se_o_tls_foi_verificado(self):
        """O snapshot precisa dizer se a verificacao TLS ficou de fora."""
        snapshot = provision.discover(self.build_client())
        self.assertTrue(snapshot["tls_verified"])

    def test_snapshot_traz_os_custom_fields_de_exemplo(self):
        """A amostra vem por tipo de objeto (device e IP tem campos proprios)."""
        snapshot = provision.discover(self.build_client())
        self.assertEqual(
            sorted(snapshot["custom_fields_sample"]), ["dcim.device", "ipam.ipaddress"]
        )

    def test_snapshot_traz_o_dono_do_token(self):
        snapshot = provision.discover(self.build_client())
        self.assertIn("current_user", snapshot)

    def test_device_types_sao_pedidos_com_brief(self):
        class Espiao(FakeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.chamadas = []

            def fetch_all(self, path, params=None):
                self.chamadas.append((path, params))
                return super().fetch_all(path, params)

        base = self.build_client()
        espiao = Espiao(data=base._data, counts=base._counts, options=base._options)
        provision.discover(espiao)
        parametros = dict(espiao.chamadas)
        self.assertEqual(parametros.get("/api/dcim/device-types/"), {"brief": 1})


class TestEstadoDaConexao(unittest.TestCase):
    """Distingue "conectou" de "nao leu nada" - o bug do certificado autoassinado.

    Antes, a descoberta tolerante a falhas fazia a tela dizer "conectado" com tudo
    vazio; agora quem chama consegue detectar que nada foi lido.
    """

    def test_snapshot_vazio_nao_tem_ambiente(self):
        self.assertFalse(provision.has_environment({}))

    def test_status_preenchido_conta_como_ambiente(self):
        self.assertTrue(provision.has_environment({"status": {"netbox-version": "4.3.6"}}))

    def test_objetos_preenchidos_contam_como_ambiente(self):
        self.assertTrue(provision.has_environment({"objects": {"sites": [{"id": 1}]}}))

    def test_contagens_contam_como_ambiente(self):
        self.assertTrue(provision.has_environment({"counts": {"devices": 1}}))

    def test_schema_conta_como_ambiente(self):
        self.assertTrue(provision.has_environment({"schema": {"device": {"actions": {}}}}))

    def test_objetos_vazios_nao_contam(self):
        self.assertFalse(
            provision.has_environment({"objects": {"sites": []}, "counts": {}, "schema": {}})
        )

    def test_marca_estrutural_de_tls(self):
        """A descoberta grava a marca: nao dependemos de texto na mensagem."""
        self.assertTrue(provision.looks_like_tls_failure({"tls_blocked": True}))

    def test_reconhece_texto_crudo_antigo(self):
        """Rede de seguranca: snapshot antigo, com a mensagem crua do requests."""
        snapshot = {
            "errors": [
                "status: ... [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "self-signed certificate ..."
            ]
        }
        self.assertTrue(provision.looks_like_tls_failure(snapshot))

    def test_erro_comum_nao_e_confundido_com_tls(self):
        self.assertFalse(provision.looks_like_tls_failure({"errors": ["status: HTTP 403"]}))

    def test_pede_retry_quando_tls_falhou_e_nada_foi_lido(self):
        snapshot = {"tls_blocked": True, "errors": ["status: certificado autoassinado"]}
        self.assertTrue(provision.needs_tls_retry(snapshot, verify_tls=True))

    def test_nao_pede_retry_quando_algo_foi_lido(self):
        snapshot = {"tls_blocked": True, "status": {"netbox-version": "4.3.6"}}
        self.assertFalse(provision.needs_tls_retry(snapshot, verify_tls=True))

    def test_nao_pede_retry_se_ja_ignora_o_certificado(self):
        snapshot = {"tls_blocked": True}
        self.assertFalse(provision.needs_tls_retry(snapshot, verify_tls=False))

    def test_nao_pede_retry_para_erro_que_nao_e_de_tls(self):
        self.assertFalse(
            provision.needs_tls_retry({"errors": ["status: HTTP 403"]}, verify_tls=True)
        )

    def test_descoberta_grava_a_marca_quando_o_cliente_levanta_tls(self):
        """Fim a fim: erro de TLS do cliente vira `tls_blocked` no snapshot."""

        class ClienteTLS(FakeClient):
            def status(self):
                raise NetBoxTLSError("certificado autoassinado")

            def fetch_all(self, path, params=None):
                raise NetBoxTLSError("certificado autoassinado")

            def count(self, path, **filters):
                raise NetBoxTLSError("certificado autoassinado")

            def options(self, path):
                raise NetBoxTLSError("certificado autoassinado")

        snapshot = provision.discover(ClienteTLS())
        self.assertTrue(snapshot["tls_blocked"])
        self.assertFalse(provision.has_environment(snapshot))
        self.assertTrue(snapshot["errors"])


class TestCurrentUser(unittest.TestCase):
    """De quem e o token: as permissoes sao sempre do dono dele.

    Um superusuario que use o token de outro usuario continua limitado ao que
    aquele usuario pode - por isso vale mostrar isso na tela.
    """

    class Cliente:
        def __init__(self, payload, fail=False):
            self._payload = payload
            self._fail = fail

        def request(self, method, path):
            if self._fail:
                raise RuntimeError("endpoint indisponivel")
            return self._payload

    def test_le_usuario_e_flags(self):
        cliente = self.Cliente(
            {"username": "lucas", "is_superuser": True, "is_staff": True, "email": "x"}
        )
        self.assertEqual(
            provision.current_user(cliente),
            {"username": "lucas", "is_superuser": True, "is_staff": True},
        )

    def test_usuario_comum(self):
        cliente = self.Cliente({"username": "analista", "is_superuser": False})
        self.assertEqual(provision.current_user(cliente)["is_superuser"], False)

    def test_falha_devolve_vazio(self):
        self.assertEqual(provision.current_user(self.Cliente({}, fail=True)), {})

    def test_resposta_inesperada_devolve_vazio(self):
        self.assertEqual(provision.current_user(self.Cliente(["x"])), {})


class TestCustomFieldSamples(unittest.TestCase):
    """Descobrir custom fields sem a permissao de extras.customfield.

    O OPTIONS nao enumera os custom fields e a listagem deles da 403. Mas um objeto
    existente devolve todas as chaves de `custom_fields` - foi assim que descobrimos
    o "Validavel" obrigatorio que fazia o POST do device falhar com 400.
    """

    class Cliente:
        def __init__(self, payload=None, fail=False):
            self._payload = {"results": payload or []}
            self._fail = fail

        def request(self, method, path, params=None):
            if self._fail:
                raise RuntimeError("403 sem permissao")
            return self._payload

    def test_le_as_chaves_dos_objetos(self):
        cliente = self.Cliente([{"custom_fields": {"validavel": True, "nvr": None}}])
        self.assertEqual(
            provision.custom_field_samples(cliente), {"validavel": True, "nvr": None}
        )

    def test_prefere_valor_preenchido(self):
        cliente = self.Cliente(
            [{"custom_fields": {"validavel": None}}, {"custom_fields": {"validavel": True}}]
        )
        self.assertEqual(provision.custom_field_samples(cliente), {"validavel": True})

    def test_sem_permissao_devolve_vazio(self):
        self.assertEqual(provision.custom_field_samples(self.Cliente(fail=True)), {})

    def test_resposta_sem_paginacao_tambem_serve(self):
        cliente = self.Cliente()
        cliente._payload = [{"custom_fields": {"x": 1}}]
        self.assertEqual(provision.custom_field_samples(cliente), {"x": 1})

    def test_objeto_sem_custom_fields_nao_quebra(self):
        self.assertEqual(provision.custom_field_samples(self.Cliente([{"id": 1}])), {})


class TestIpAddress(unittest.TestCase):
    """O IP tem custom field proprio: `add_to_zabbix` e OBRIGATORIO nesta instancia.

    Sem ele o POST leva 400 ("Valor invalido para o campo personalizado
    'add_to_zabbix': O campo obrigatorio nao pode estar vazio") - foi o que
    aconteceu de verdade.
    """

    class Cliente:
        def __init__(self, existente=None):
            self._existente = existente
            self.criado = None
            self.atualizado = None

        def get_or_none(self, path, **filters):
            return self._existente

        def create(self, path, payload):
            self.criado = payload
            return {"id": 4001}

        def update(self, path, object_id, payload):
            self.atualizado = payload
            return {"id": object_id}

    def test_envia_custom_fields(self):
        cliente = self.Cliente()
        status, ip_id = provision.upsert_ip_address(
            cliente, "10.100.20.58", 16336, custom_fields={"add_to_zabbix": "Sim"}
        )
        self.assertEqual((status, ip_id), ("created", 4001))
        self.assertEqual(cliente.criado["address"], "10.100.20.58/32")
        self.assertEqual(cliente.criado["assigned_object_type"], "dcim.interface")
        self.assertEqual(cliente.criado["assigned_object_id"], 16336)
        self.assertEqual(cliente.criado["custom_fields"], {"add_to_zabbix": "Sim"})

    def test_omite_custom_fields_vazios(self):
        cliente = self.Cliente()
        provision.upsert_ip_address(
            cliente, "10.0.0.1", 1, custom_fields={"a": "", "b": None, "c": []}
        )
        self.assertNotIn("custom_fields", cliente.criado)

    def test_sem_custom_fields_nao_leva_a_chave(self):
        cliente = self.Cliente()
        provision.upsert_ip_address(cliente, "10.0.0.1", 1)
        self.assertNotIn("custom_fields", cliente.criado)

    def _existente(self, valor):
        return {
            "id": 9,
            "status": {"value": "active"},
            "assigned_object": {"id": 16336},
            "custom_fields": {"add_to_zabbix": valor},
        }

    def _com_descricao(self, valor):
        base = self._existente("Sim")
        if valor is not None:
            base["description"] = valor
        return base

    def test_payload_cria_leva_description(self):
        cliente = self.Cliente()
        provision.upsert_ip_address(
            cliente, "10.0.0.1", 1, description="CAM-01"
        )
        self.assertEqual(cliente.criado["description"], "CAM-01")

    def test_description_vazia_nao_leva_a_chave(self):
        cliente = self.Cliente()
        provision.upsert_ip_address(cliente, "10.0.0.1", 1, description="")
        self.assertNotIn("description", cliente.criado)

    def test_ip_existente_sem_description_ganha_patch_com_descricao(self):
        cliente = self.Cliente(existente=self._existente("Sim"))
        status, _ = provision.upsert_ip_address(
            cliente, "10.0.0.1", 16336, custom_fields={"add_to_zabbix": "Sim"}, description="CAM-01"
        )
        self.assertEqual(status, "updated")
        self.assertEqual(cliente.atualizado["description"], "CAM-01")

    def test_ip_existente_com_mesma_description_nao_faz_patch(self):
        """Idempotencia: descricao igual -> nenhum PATCH."""
        cliente = self.Cliente(existente=self._com_descricao("CAM-01"))
        status, _ = provision.upsert_ip_address(
            cliente, "10.0.0.1", 16336, custom_fields={"add_to_zabbix": "Sim"}, description="CAM-01"
        )
        self.assertEqual(status, "exists")
        self.assertIsNone(cliente.atualizado)

    def test_ip_existente_com_description_diferente_dispara_patch(self):
        cliente = self.Cliente(existente=self._com_descricao("CAM-VELHO"))
        status, _ = provision.upsert_ip_address(
            cliente, "10.0.0.1", 16336, custom_fields={"add_to_zabbix": "Sim"}, description="CAM-01"
        )
        self.assertEqual(status, "updated")
        self.assertEqual(cliente.atualizado["description"], "CAM-01")

    def test_ip_existente_sem_description_nao_e_modificado_somente_com_fields_iguais(self):
        """Sem passar descricao, o campo descrição nao é comparado — sem isso, um IP com
        descricao ja gravada seria considerado 'diferente' para sempre."""
        existente = self._com_descricao("algum_texto")
        cliente = self.Cliente(existente=existente)
        status, _ = provision.upsert_ip_address(
            cliente, "10.0.0.1", 16336, custom_fields={"add_to_zabbix": "Sim"}
        )
        self.assertEqual(status, "exists")
        self.assertIsNone(cliente.atualizado)

    def test_ip_igual_nao_faz_patch(self):
        cliente = self.Cliente(existente=self._existente("Sim"))
        status, _ = provision.upsert_ip_address(
            cliente, "10.0.0.1", 16336, custom_fields={"add_to_zabbix": "Sim"}
        )
        self.assertEqual(status, "exists")
        self.assertIsNone(cliente.atualizado)

    def test_custom_field_diferente_dispara_patch(self):
        cliente = self.Cliente(existente=self._existente("Nao"))
        status, _ = provision.upsert_ip_address(
            cliente, "10.0.0.1", 16336, custom_fields={"add_to_zabbix": "Sim"}
        )
        self.assertEqual(status, "updated")
        self.assertEqual(cliente.atualizado["custom_fields"], {"add_to_zabbix": "Sim"})


class TestSampleCustomFields(unittest.TestCase):
    def test_amostra_por_tipo_de_objeto(self):
        class Cliente:
            def request(self, method, path, params=None):
                if path == provision.DEVICE_ENDPOINT:
                    return {"results": [{"custom_fields": {"Validavel": True}}]}
                return {"results": [{"custom_fields": {"add_to_zabbix": "Sim"}}]}

        amostras = provision.sample_custom_fields(Cliente())
        self.assertEqual(sorted(amostras), ["dcim.device", "ipam.ipaddress"])
        self.assertEqual(amostras["dcim.device"], {"Validavel": True})
        self.assertEqual(amostras["ipam.ipaddress"], {"add_to_zabbix": "Sim"})


class TestSaveSnapshot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_grava_json_legivel(self):
        snapshot = {"base_url": "https://nb.local", "counts": {"devices": 3}}
        destino = provision.save_snapshot(snapshot, self.tmp / "sub" / "schema.json")
        self.assertTrue(destino.exists())
        lido = json.loads(destino.read_text(encoding="utf-8"))
        self.assertEqual(lido["counts"]["devices"], 3)

    def test_cria_a_pasta_se_faltar(self):
        destino = provision.save_snapshot({}, self.tmp / "nova" / "pasta" / "s.json")
        self.assertTrue(destino.parent.is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
