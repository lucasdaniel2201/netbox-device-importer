"""Ponto de entrada do executavel (usado pelo PyInstaller).

Mantem a raiz do projeto no sys.path para que `app` seja importavel, tanto
rodando do codigo-fonte quanto empacotado.

Uso:
  python run_app.py      (equivalente a: python -m app.main)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
