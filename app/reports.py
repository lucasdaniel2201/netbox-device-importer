"""Relatorios da importacao: log, JSON e CSV numa pasta gravavel.

Ficam em `reports/` (ao lado do .exe quando empacotado, via app/paths.py) - nunca
na pasta temporaria do PyInstaller, senao sumiriam ao fechar o app.

O JSON guarda o resumo + o resultado por linha, incluindo o `X-Request-ID` de cada
escrita: da para auditar depois em /api/extras/object-changes/.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.paths import output_dir

PREFIX = "netbox-import"

# Colunas do CSV de resultado (as mesmas chaves do JSON).
RESULT_FIELDS: tuple[str, ...] = (
    "row_number",
    "name",
    "site",
    "device_type",
    "status",
    "message",
    "warnings",
    "request_id",
)


def reports_dir() -> Path:
    """Pasta gravavel dos relatorios (criada se necessario)."""
    return output_dir("reports")


def report_paths(timestamp: str) -> dict[str, Path]:
    base = reports_dir() / f"{PREFIX}-{timestamp}"
    return {
        "log": Path(f"{base}.log"),
        "json": Path(f"{base}.json"),
        "csv": Path(f"{base}.csv"),
    }


def write_reports(
    timestamp: str,
    summary: dict[str, Any],
    results: list[dict[str, Any]],
    log_lines: list[str],
) -> dict[str, Path]:
    """Grava os tres arquivos da execucao e devolve os caminhos."""
    paths = report_paths(timestamp)
    paths["log"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    paths["json"].write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with paths["csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RESULT_FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    return paths
