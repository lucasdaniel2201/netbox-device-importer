"""Testes da leitura do historico de relatorios (app/history.py).

O historico e uma leitura de disco: nao pode derrubar o app por arquivo corrompido
nem inventar execucao que nao existe. Roda sem rede e sem interface.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import history, reports  # noqa: E402


def escrever(pasta: Path, nome: str, **resumo) -> Path:
    caminho = pasta / nome
    caminho.write_text(
        json.dumps({"summary": resumo, "results": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return caminho


class TestHistorico(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pasta_vazia_devolve_lista_vazia(self):
        self.assertEqual(history.list_runs(self.pasta), [])

    def test_pasta_inexistente_nao_levanta(self):
        self.assertEqual(history.list_runs(self.pasta / "nao-existe"), [])

    def test_le_resumo_e_ordena_do_mais_recente(self):
        escrever(
            self.pasta,
            "netbox-import-20261020-120000.json",
            timestamp="20261020-120000",
            total=10,
            created=8,
            updated=1,
            exists=1,
            errors=0,
        )
        escrever(
            self.pasta,
            f"{reports.LINK_PREFIX}-20261029-090000.json",
            timestamp="20261029-090000",
            total=3,
            created=2,
            errors=1,
        )
        execucoes = history.list_runs(self.pasta)

        self.assertEqual([run.timestamp for run in execucoes], ["20261029-090000", "20261020-120000"])
        self.assertEqual(execucoes[0].kind, "links")
        self.assertEqual(execucoes[0].kind_label, "Links IP")
        self.assertEqual(execucoes[1].kind_label, "Câmeras")
        self.assertEqual(execucoes[1].created, 8)

    def test_arquivo_corrompido_e_ignorado(self):
        (self.pasta / "netbox-import-20261020-120000.json").write_text("{nao e json")
        escrever(self.pasta, "netbox-import-20261021-120000.json", timestamp="20261021-120000")
        execucoes = history.list_runs(self.pasta)
        self.assertEqual(len(execucoes), 1)
        self.assertEqual(execucoes[0].timestamp, "20261021-120000")

    def test_json_sem_summary_e_ignorado(self):
        (self.pasta / "netbox-import-20261020-120000.json").write_text(
            json.dumps({"results": []})
        )
        self.assertEqual(history.list_runs(self.pasta), [])

    def test_situacao_reflete_erro_e_cancelamento(self):
        run = history.Run(path=self.pasta / "x.json", timestamp="20261029-090000", kind="cameras")
        self.assertEqual(run.status_label, "Concluída")
        self.assertEqual(run.status_kind, "neutral")

        com_erro = history.Run(
            path=run.path, timestamp=run.timestamp, kind="cameras", errors=2, created=1
        )
        self.assertEqual(com_erro.status_label, "Com erros")
        self.assertEqual(com_erro.status_kind, "danger")
        self.assertIn("1 criado(s)", com_erro.result_label)

        cancelada = history.Run(
            path=run.path, timestamp=run.timestamp, kind="links", canceled=True
        )
        self.assertEqual(cancelada.status_label, "Cancelada")
        self.assertEqual(cancelada.status_kind, "warning")

    def test_data_legivel(self):
        run = history.Run(
            path=self.pasta / "x.json", timestamp="20261029-090500", kind="cameras"
        )
        self.assertEqual(run.display_time, "29/10/2026 09:05")

    def test_timestamp_invalido_nao_quebra(self):
        run = history.Run(path=self.pasta / "x.json", timestamp="", kind="cameras")
        self.assertEqual(run.display_time, "—")

    def test_limite_de_linhas(self):
        for dia in range(1, 6):
            escrever(
                self.pasta,
                f"netbox-import-2026100{dia}-120000.json",
                timestamp=f"2026100{dia}-120000",
            )
        self.assertEqual(len(history.list_runs(self.pasta, limit=2)), 2)

    def test_relatorio_de_links_com_prefixo_proprio(self):
        nome = f"{reports.LINK_PREFIX}-20261029-090000.json"
        escrever(self.pasta, nome, timestamp="20261029-090000", prefixes=4)
        run = history.list_runs(self.pasta)[0]
        self.assertEqual(run.kind, "links")


if __name__ == "__main__":
    unittest.main(verbosity=2)
