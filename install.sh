#!/usr/bin/env bash
# Sophia installer for macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/ds1734770-dot/Sophia/main/install.sh | bash
#
# Puts Sophia in ~/Sophia (SOPHIA_DIR to change), Python 3.12 and its
# packages in ~/.venvs/sophia (SOPHIA_VENV), adds a `sophia` command, then
# runs the first-run setup (API key, app scan, permissions, voice models).
# No administrator rights needed; nothing outside your home folder changes.

set -euo pipefail

REPO="${SOPHIA_REPO:-https://github.com/ds1734770-dot/Sophia}"
BRANCH="${SOPHIA_BRANCH:-main}"
DIR="${SOPHIA_DIR:-$HOME/Sophia}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }

if [ "$(uname -s)" != "Darwin" ]; then
    echo "This installer is for macOS. On Windows use install.ps1 (see the README)." >&2
    exit 1
fi

bold "Installing Sophia into $DIR"

if [ -d "$DIR/.git" ] && command -v git >/dev/null 2>&1 && git -C "$DIR" rev-parse >/dev/null 2>&1; then
    echo "Updating the existing copy..."
    git -C "$DIR" pull --ff-only
elif [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
    echo "$DIR already exists and is not a Sophia checkout. Set SOPHIA_DIR to another folder." >&2
    exit 1
elif git --version >/dev/null 2>&1; then
    git clone --depth 1 --branch "$BRANCH" "$REPO.git" "$DIR"
else
    # no git (it needs Xcode's command line tools): download the code instead
    mkdir -p "$DIR"
    curl -fsSL "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$DIR" --strip-components 1
fi

chmod +x "$DIR/scripts/setup_mac.sh" "$DIR/Sophia.command"

exec "$DIR/scripts/setup_mac.sh"
