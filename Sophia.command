#!/bin/zsh
# Double-click in Finder to start Sophia on a Mac (run scripts/setup_mac.sh once first).
# Extra options pass through, e.g.  ./Sophia.command --chat

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="${SOPHIA_VENV:-$HOME/.venvs/sophia}"

if [ ! -x "$VENV/bin/python" ]; then
    echo "Sophia is not set up on this Mac yet. Running setup..."
    "$ROOT/scripts/setup_mac.sh" || exit 1
fi

cd "$ROOT"
exec "$VENV/bin/python" "$ROOT/main.py" "$@"
