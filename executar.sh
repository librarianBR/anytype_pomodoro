#!/usr/bin/env bash
# Executa o Anytype + Pomodoro no Linux/macOS.
#   ./executar.sh        -> interface gráfica (gui.py)
#   ./executar.sh cli    -> linha de comando (main.py)
set -e
cd "$(dirname "$0")"

script="gui.py"
if [ "$1" = "cli" ]; then
    script="main.py"
    shift
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run "$script" "$@"
elif [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python "$script" "$@"
elif command -v python3 >/dev/null 2>&1; then
    exec python3 "$script" "$@"
else
    echo "Erro: nem o uv nem o Python 3 foram encontrados. Veja o README.md." >&2
    exit 1
fi
