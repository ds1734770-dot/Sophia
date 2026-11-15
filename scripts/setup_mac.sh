#!/bin/zsh
# Set up Sophia on a Mac (install.sh runs this; safe to run again).
#
# The Python environment lives outside the project folder
# (~/.venvs/sophia), so a project kept in a synced folder (Google Drive,
# iCloud) does not sync tens of thousands of library files, and a Windows
# .venv in the same folder does not get in the way.
#
#   --no-setup   install only; skip the first-run setup questions

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${SOPHIA_VENV:-$HOME/.venvs/sophia}"
BIN="$HOME/.local/bin"

export PATH="$BIN:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (Python manager, in your home folder, no admin rights)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

echo "Python 3.12 environment: $VENV"
uv python install 3.12
[ -x "$VENV/bin/python" ] || uv venv "$VENV" --python 3.12

echo "Installing packages (a few minutes the first time)..."
VIRTUAL_ENV="$VENV" uv pip install -r "$ROOT/requirements.txt"

if [ -f "$ROOT/requirements-dev.txt" ] && [ -d "$ROOT/.git" ]; then
    VIRTUAL_ENV="$VENV" uv pip install pytest ruff >/dev/null
fi

# Personal data from an older copy in the project folder (memories,
# notes, profile, routines), once; app and file indexes are rebuilt
DATA="$HOME/Library/Application Support/Sophia"
mkdir -p "$DATA"

if [ -d "$ROOT/data" ]; then
    for f in memories.json memory.json notes.json profile.json routines.json schedules.json summary.json mcp.json; do
        if [ -f "$ROOT/data/$f" ] && [ ! -f "$DATA/$f" ]; then
            cp "$ROOT/data/$f" "$DATA/$f"
            echo "Copied $f"
        fi
    done
fi

# The `sophia` command
mkdir -p "$BIN"

cat > "$BIN/sophia" <<EOF
#!/bin/zsh
cd "$ROOT" && exec "$VENV/bin/python" "$ROOT/main.py" "\$@"
EOF

chmod +x "$BIN/sophia" "$ROOT/Sophia.command"

if ! grep -q "$BIN" "$HOME/.zshrc" 2>/dev/null; then
    echo "export PATH=\"$BIN:\$PATH\"" >> "$HOME/.zshrc"
fi

echo
echo "Installed. The 'sophia' command works in new Terminal windows."

if [[ "$1" != "--no-setup" && "${SOPHIA_SKIP_SETUP:-0}" != "1" ]]; then

    # under `curl | bash` the keyboard is not standard input: ask through
    # the terminal when there is one
    if (exec < /dev/tty) 2>/dev/null; then
        "$VENV/bin/python" "$ROOT/main.py" --setup < /dev/tty
    else
        "$VENV/bin/python" "$ROOT/main.py" --setup --yes
    fi
fi
