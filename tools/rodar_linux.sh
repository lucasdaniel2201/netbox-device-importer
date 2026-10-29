#!/usr/bin/env bash
# Roda o app no Linux a partir do codigo-fonte (ambiente de teste).
#
# Cria o .venv na primeira execucao e instala as dependencias que faltarem.
# Nao e instalador: e o caminho rapido para abrir a janela e testar uma planilha
# sem gerar o .exe. A versao distribuida continua sendo o executavel do Windows.
#
# Uso:
#   tools/rodar_linux.sh            abre o app
#   tools/rodar_linux.sh --testes   roda a suite de testes
#
# O token so e guardado entre execucoes se houver chaveiro do sistema
# (`pip install keyring`); sem ele, o app pede o token a cada abertura.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

if [ ! -x .venv/bin/python ]; then
    echo "Criando .venv..."
    python3 -m venv .venv
fi

if ! .venv/bin/python -c "import PySide6, openpyxl, requests" >/dev/null 2>&1; then
    echo "Instalando dependencias..."
    .venv/bin/pip install --quiet -r requirements.txt
fi

if [ "${1:-}" = "--testes" ]; then
    shift
    exec .venv/bin/python -m unittest discover -s tests "$@"
fi

exec .venv/bin/python -m app.main "$@"
