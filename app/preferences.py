"""Preferencias locais do usuario (poucas e nao sensiveis).

Guarda apenas escolhas de interface, como o tema. O token **nao** passa por aqui:
ele tem modulo proprio (`app/credentials.py`) e protecao do sistema operacional.
Arquivo corrompido ou ilegivel nunca derruba o app: volta ao padrao.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.paths import user_data_dir

FILENAME = "preferences.json"
THEME_KEY = "theme"
VALID_THEMES = ("dark", "light")


def preferences_path() -> Path:
    return user_data_dir() / FILENAME


def load() -> dict:
    """Preferencias salvas (dicionario vazio se nao houver ou estiver corrompido)."""
    try:
        data = json.loads(preferences_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(key: str, default=None):
    return load().get(key, default)


def update(**values) -> dict:
    """Grava as chaves informadas preservando as demais."""
    data = load()
    data.update(values)
    destino = preferences_path()
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(".tmp")
        temporario.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporario.replace(destino)
    except OSError:
        # Preferencia e conveniencia, nao funcao do app: falhar aqui nao pode
        # impedir a troca de tema na sessao atual.
        pass
    return data


def theme_mode(default: str = "dark") -> str:
    """Tema salvo ("dark" ou "light"); qualquer outro valor cai no padrao."""
    valor = get(THEME_KEY)
    return valor if valor in VALID_THEMES else default


def set_theme_mode(mode: str) -> None:
    if mode in VALID_THEMES:
        update(**{THEME_KEY: mode})
