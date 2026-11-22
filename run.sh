#!/usr/bin/env bash
# =============================================================================
#  run.sh — Launch Mouse AutoClicker (dev runner, works without full install)
# =============================================================================
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export DISPLAY="${DISPLAY:-:0}"
if [ -z "$XAUTHORITY" ] && [ -f "$HOME/.Xauthority" ]; then
    export XAUTHORITY="$HOME/.Xauthority"
fi

# Prefer the installed system launcher (set up by setup.sh)
if [ -x "/usr/local/bin/mouse-autoclicker" ]; then
    exec /usr/local/bin/mouse-autoclicker "$@"
fi

# Fall back: use venv python if setup.sh has been run
VENV_PYTHON="$DIR/venv/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
    if [ "$(id -u)" -ne 0 ]; then
        exec sudo bash "$0" "$@"
    fi
    exec "$VENV_PYTHON" "$DIR/right_clicker.py" "$@"
fi

# Last resort: system python3
if [ "$(id -u)" -ne 0 ]; then
    exec sudo /usr/bin/python3 "$DIR/right_clicker.py" "$@"
else
    exec /usr/bin/python3 "$DIR/right_clicker.py" "$@"
fi
