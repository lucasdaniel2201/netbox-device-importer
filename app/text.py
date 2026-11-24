"""Formatacao de texto exibido na interface.

O portugues concorda em numero: "1 linha" e "2 linhas". Montar isso com `f"{n} linha(s)"`
vaza o parentese na tela do usuario, entao a concordancia fica aqui, num lugar so,
em vez de repetida (e esquecida) em cada tela.
"""

from __future__ import annotations


def plural(quantidade: int, singular: str, plural: str) -> str:
    """Numero seguido do texto na forma certa: `plural(1, "linha", "linhas")` -> "1 linha"."""
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def plural_only(quantidade: int, singular: str, plural: str) -> str:
    """So a palavra flexionada, para quando o numero ja aparece em outro lugar."""
    return singular if quantidade == 1 else plural
