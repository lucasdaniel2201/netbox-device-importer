"""Testes automatizados do projeto (stdlib unittest).

Executar da raiz do projeto:

    python -m unittest discover -s tests -v
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
