"""Testes da camada de apresentacao nova (design system, tabela, fluxo e casca).

Rodam em modo offscreen e sem rede. O que interessa aqui e o comportamento que o
usuario percebe: a etapa certa aparece, a tabela filtra e ordena, o tema troca, e
o resumo mostra o resultado por linha.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import theme  # noqa: E402
from app.import_dialog import ImportDialog  # noqa: E402
from app.pages.workflow_page import ImportPage, LinksPage  # noqa: E402
from app.shell import DASHBOARD, HISTORY_PAGE, LINKS_PAGE, SETTINGS_PAGE, Shell  # noqa: E402
from app.spreadsheet import write_example_template  # noqa: E402
from app.ui.components import Stepper  # noqa: E402
from app.ui.table import Cell, DataTable, Row  # noqa: E402

_app = QApplication.instance() or QApplication([])


def snapshot() -> dict:
    return {
        "base_url": "https://netbox.exemplo.local",
        "api_version": "4.3",
        "status": {"netbox-version": "4.3.6"},
        "current_user": {"username": "analista.exemplo", "is_superuser": False},
        "objects": {
            "sites": [{"id": 1, "label": "Matriz Centro"}],
            "device_roles": [{"id": 2, "label": "Camera"}],
            "manufacturers": [{"id": 3, "label": "Hikvision"}],
            "device_types": [
                {"id": 4, "label": "DS-2CD3666G2T-IZS", "manufacturer": "Hikvision"}
            ],
            "locations": [],
            "regions": [],
            "site_groups": [],
            "racks": [],
            "tags": [],
            "tenants": [],
        },
        "counts": {"devices": 3, "interfaces": 4, "ip_addresses": 3, "prefixes": 1},
        "capabilities": {
            "device": ["GET", "POST", "PATCH"],
            "interface": ["GET", "POST", "PATCH"],
            "ip_address": ["GET", "POST"],
        },
        "schema": {
            "device": {"actions": {"GET": {}, "POST": {}, "PATCH": {}}},
            "interface": {"actions": {"GET": {}, "POST": {}, "PATCH": {}}},
            "ip_address": {"actions": {"GET": {}, "POST": {}}},
        },
        "custom_fields": [],
        "tls_verified": True,
        "token_scheme": "Token",
        "errors": [],
    }


class SessaoFalsa(QObject):
    """Sinais do SessionWorker sem thread e sem rede."""

    progress = Signal(int, int, str, str)
    import_done = Signal(dict)
    import_failed = Signal(str)
    provision_done = Signal(dict)
    provision_failed = Signal(str)
    links_progress = Signal(int, int, str, str)
    links_done = Signal(dict)
    links_failed = Signal(str)
    request_import = Signal(object)
    request_import_links = Signal(object)
    request_provision = Signal(object)
    request_cancel = Signal()


class TestStepper(unittest.TestCase):
    def test_estados_das_etapas(self):
        stepper = Stepper(["Origem", "Revisão", "Envio", "Resumo"])
        stepper.set_step(2)
        self.assertEqual(stepper._dots[0].text(), "✓")
        self.assertEqual(stepper._dots[0].property("state"), "done")
        self.assertEqual(stepper._dots[2].property("state"), "current")
        self.assertEqual(stepper._dots[3].property("state"), "upcoming")
        self.assertTrue(stepper._lines[0].property("done") == "true")
        self.assertTrue(stepper._lines[2].property("done") == "false")


class TestDataTable(unittest.TestCase):
    def setUp(self):
        self.table = DataTable(
            ["Linha", "Nome", "Situação"],
            status_column=2,
            compact_columns=(2,),
        )

    def test_busca_filtra_linhas(self):
        self.table.set_rows(
            [
                Row.of(Cell("2"), "CAM-A", Cell("pronto", kind="success")),
                Row.of(Cell("3"), "CAM-B", Cell("erro", kind="danger")),
            ]
        )
        self.assertEqual(self.table.table.rowCount(), 2)
        self.table.search.setText("cam-b")
        visiveis = [
            linha
            for linha in range(self.table.table.rowCount())
            if not self.table.table.isRowHidden(linha)
        ]
        self.assertEqual(visiveis, [1])
        self.assertIn("1 de 2", self.table.counter.text())

    def test_ordena_por_coluna(self):
        self.table.set_rows(
            [
                Row.of(Cell("10", sort_key=10, align="right"), "B", Cell("pronto", kind="success")),
                Row.of(Cell("2", sort_key=2, align="right"), "A", Cell("erro", kind="danger")),
            ]
        )
        self.assertEqual(self.table.table.item(0, 0).text(), "2")
        self.table._on_header_clicked(1)
        self.assertEqual(self.table.table.item(0, 1).text(), "A")

    def test_altura_acompanha_o_numero_de_linhas(self):
        self.table.set_rows([Row.of(Cell("2"), "A", Cell("pronto", kind="success"))])
        self.table.fit_height(max_rows=8)
        baixa = self.table.table.height()
        self.table.set_rows(
            [Row.of(Cell(str(i)), f"item {i}", Cell("pronto", kind="success")) for i in range(8)]
        )
        self.table.fit_height(max_rows=8)
        self.assertGreater(self.table.table.height(), baixa)

    def test_payload_da_linha_selecionada(self):
        self.table.set_rows([Row.of(Cell("2"), "CAM-A", Cell("pronto", kind="success"), payload="x")])
        self.table.table.selectRow(0)
        self.assertEqual(self.table.selected_payload(), "x")


class TestTema(unittest.TestCase):
    def tearDown(self):
        theme.apply(_app, _app.font().family(), "dark")

    def test_dois_temas_completos(self):
        escuro = theme.set_mode("dark")
        self.assertTrue(escuro.is_dark)
        claro = theme.toggle_mode()
        self.assertEqual(claro.mode, "light")
        self.assertNotEqual(escuro.bg, claro.bg)
        self.assertNotEqual(escuro.text, claro.text)

    def test_qss_muda_com_o_tema(self):
        qss_escuro = theme.style_sheet("Inter", "dark")
        qss_claro = theme.style_sheet("Inter", "light")
        self.assertNotEqual(qss_escuro, qss_claro)
        self.assertIn(theme.set_mode("light").accent, qss_claro)

    def test_apply_muda_a_paleta_do_qt(self):
        theme.apply(_app, _app.font().family(), "light")
        self.assertEqual(_app.palette().window().color().name(), theme.palette().bg.lower())
        self.assertIn(theme.palette().bg, _app.styleSheet().upper())


class TestCasca(unittest.TestCase):
    def setUp(self):
        self.shell = Shell()

    def test_navegacao_atualiza_titulo_e_item_ativo(self):
        self.shell.set_page(LINKS_PAGE, animate=False)
        self.assertEqual(self.shell.header.title.text(), "Links IP")
        self.assertTrue(self.shell.sidebar.buttons[LINKS_PAGE].isChecked())
        self.assertFalse(self.shell.sidebar.buttons[DASHBOARD].isChecked())

    def test_estado_da_conexao_aparece_no_cabecalho_e_na_barra(self):
        self.shell.set_connected(True, "4.3.6", tls=False)
        self.assertIn("TLS não verificado", self.shell.header.badge.text())
        self.assertIn("Conectado", self.shell.sidebar.connection_title.text())

        self.shell.set_connected(False)
        self.assertEqual(self.shell.header.badge.text(), "Sem conexão")
        self.assertTrue(self.shell.sidebar.logout_button.isHidden())

    def test_pagina_de_importacao_comeca_desabilitada(self):
        pagina = ImportPage()
        self.assertFalse(pagina.primary_button.isEnabled())
        self.assertFalse(pagina.session_banner.isHidden())
        pagina.set_ready(True)
        self.assertTrue(pagina.primary_button.isEnabled())

    def test_icones_proprios_sao_pintados_na_criacao(self):
        """Pagina criada depois de theme.apply nao pode ficar sem icone."""
        pagina = ImportPage()
        for label, _kind in pagina._note_icon_labels:
            self.assertFalse(label.pixmap().isNull())
        self.assertFalse(pagina.secondary_button.icon().isNull())

    def test_links_carregam_o_inventario_so_quando_pedidos(self):
        pagina = LinksPage()
        pagina.set_ready(True)
        # Antes do primeiro pedido, a acao esta disponivel: e ela que dispara a leitura.
        self.assertTrue(pagina.primary_button.isEnabled())
        self.assertTrue(pagina.inventory_banner.isHidden())

        pagina.set_inventory_loading(True)
        self.assertFalse(pagina.inventory_banner.isHidden())
        self.assertFalse(pagina.primary_button.isEnabled())

        pagina.set_inventory_loading(False)
        self.assertTrue(pagina.primary_button.isEnabled())
        self.assertTrue(pagina.inventory_banner.isHidden())

    def test_cameras_nao_dependem_do_inventario(self):
        pagina = ImportPage()
        pagina.set_ready(True)
        self.assertTrue(pagina.primary_button.isEnabled())
        self.assertTrue(pagina.inventory_banner.isHidden())

    def test_paginas_principais_existem(self):
        self.assertEqual(self.shell.stack.count(), 5)
        self.shell.set_page(SETTINGS_PAGE, animate=False)
        self.assertEqual(self.shell.stack.currentIndex(), SETTINGS_PAGE)
        self.shell.set_page(HISTORY_PAGE, animate=False)
        self.assertEqual(self.shell.header.title.text(), "Histórico")


class TestDialogoDeImportacao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.planilha = self.tmp / "planilha.xlsx"
        write_example_template(
            self.planilha, sites=["Matriz Centro"], roles=["Camera"]
        )
        self.sessao = SessaoFalsa()
        self.dialog = ImportDialog(None, snapshot(), self.sessao)

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        self._tmp.cleanup()

    def test_planilha_valida_leva_a_revisao_e_libera_importacao(self):
        self.dialog._load_sheet(str(self.planilha))
        self.assertEqual(self.dialog._step, 1)
        self.assertEqual(self.dialog.stack.currentIndex(), 1)
        self.assertEqual(self.dialog.plan_table.table.rowCount(), 1)
        self.assertTrue(self.dialog.import_button.isEnabled())
        self.assertIn("Importar", self.dialog.import_button.text())

    def test_resumo_mostra_tabela_por_linha(self):
        self.dialog._load_sheet(str(self.planilha))
        resumo = {
            "total": 1,
            "processed": 1,
            "created": 1,
            "updated": 0,
            "exists": 0,
            "errors": 0,
            "warnings": 0,
            "canceled": False,
            "results": [
                {
                    "row_number": 2,
                    "name": "CAM-1",
                    "site": "Matriz Centro",
                    "status": "created",
                    "message": "ok",
                }
            ],
            "report_paths": {"json": str(self.tmp / "relatorio.json")},
        }
        self.dialog._on_import_done(resumo)
        self.assertEqual(self.dialog._step, 3)
        self.assertEqual(self.dialog.summary.tiles["created"].value.text(), "1")
        self.assertFalse(self.dialog.summary.details.isHidden())
        self.assertEqual(self.dialog.summary.details.table.rowCount(), 1)
        self.assertIn("relatorio.json", self.dialog.summary.report_label.text())

    def test_planilha_invalida_nao_avanca(self):
        invalida = self.tmp / "quebrada.xlsx"
        invalida.write_bytes(b"nao e uma planilha")
        from unittest import mock

        with mock.patch("app.import_dialog.QMessageBox.warning", lambda *a, **k: None):
            self.dialog._load_sheet(str(invalida))
        self.assertEqual(self.dialog._step, 0)
        self.assertFalse(self.dialog.import_button.isEnabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
