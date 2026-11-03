"""Leitura dos relatorios de importacao para a tela de historico.

Puro de proposito: recebe uma pasta, le os JSONs e devolve objetos simples. Nao
importa Qt nem fala com a rede, entao roda em teste sem interface. Arquivo
corrompido, incompleto ou de outro formato e ignorado - o historico nunca deve
derrubar o app por causa de um relatorio antigo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app import reports

KIND_LABELS = {"cameras": "Câmeras", "links": "Links IP"}


@dataclass(frozen=True)
class Run:
    """Uma execucao registrada em `reports/`."""

    path: Path
    timestamp: str
    kind: str
    total: int = 0
    created: int = 0
    updated: int = 0
    exists: int = 0
    errors: int = 0
    warnings: int = 0
    canceled: bool = False
    url: str = ""

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, "Execução")

    @property
    def display_time(self) -> str:
        try:
            momento = datetime.strptime(self.timestamp, "%Y%m%d-%H%M%S")
        except (TypeError, ValueError):
            return self.timestamp or "—"
        return momento.strftime("%d/%m/%Y %H:%M")

    @property
    def result_label(self) -> str:
        """Resumo curto do que aconteceu, na ordem em que importa."""
        partes = []
        if self.created:
            partes.append(f"{self.created} criado(s)")
        if self.updated:
            partes.append(f"{self.updated} atualizado(s)")
        if self.exists:
            partes.append(f"{self.exists} sem mudança")
        if self.errors:
            partes.append(f"{self.errors} erro(s)")
        if not partes:
            partes.append("sem alterações")
        if self.canceled:
            partes.append("cancelada")
        return " · ".join(partes)

    @property
    def status_kind(self) -> str:
        if self.canceled:
            return "warning"
        if self.errors:
            return "danger"
        if self.created or self.updated:
            return "success"
        return "neutral"

    @property
    def status_label(self) -> str:
        """Situação em uma palavra, para a coluna da tabela."""
        if self.canceled:
            return "Cancelada"
        if self.errors:
            return "Com erros"
        return "Concluída"


def _kind_for(path: Path) -> str:
    nome = path.name
    if nome.startswith(f"{reports.LINK_PREFIX}-"):
        return "links"
    return "cameras"


def parse_run(path: Path) -> Run | None:
    """Le um JSON de relatorio. Devolve None se o arquivo nao for utilizavel."""
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    resumo = dados.get("summary")
    if not isinstance(resumo, dict):
        return None

    def inteiro(chave: str) -> int:
        valor = resumo.get(chave, 0)
        try:
            return int(valor)
        except (TypeError, ValueError):
            return 0

    return Run(
        path=path,
        timestamp=str(resumo.get("timestamp") or ""),
        kind=_kind_for(path),
        total=inteiro("total"),
        created=inteiro("created"),
        updated=inteiro("updated"),
        exists=inteiro("exists"),
        errors=inteiro("errors"),
        warnings=inteiro("warnings"),
        canceled=bool(resumo.get("canceled")),
        url=str(resumo.get("url") or ""),
    )


def list_runs(directory: Path | None = None, limit: int | None = None) -> list[Run]:
    """Execucoes do mais recente para o mais antigo."""
    pasta = Path(directory) if directory is not None else reports.reports_dir()
    try:
        arquivos = sorted(pasta.glob("*.json"))
    except OSError:
        return []

    execucoes = [run for run in (parse_run(arquivo) for arquivo in arquivos) if run is not None]
    # O nome carrega o timestamp (`netbox-import-AAAAMMDD-HHMMSS.json`), entao o
    # desempate e estavel mesmo quando o JSON nao traz o campo.
    execucoes.sort(key=lambda run: (run.timestamp, run.path.name), reverse=True)
    return execucoes[:limit] if limit else execucoes
