#!/usr/bin/env bash
# =============================================================================
#  uninstall.sh — Completely removes Mouse AutoClicker from the system
#  Run:  sudo bash uninstall.sh
# =============================================================================
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET} $1"; }
info() { echo -e "${YELLOW}→${RESET} $1"; }

if [ "$EUID" -ne 0 ]; then
    echo "This script needs root to remove system-wide files."
    echo "Run:  sudo bash uninstall.sh"
    exit 1
fi

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  Mouse AutoClicker — Uninstall"
echo "  Removing all installed files for user: $REAL_USER"
echo ""

remove() {
    if [ -e "$1" ] || [ -L "$1" ]; then
        rm -rf "$1"
        ok "Removed $1"
    fi
}

# ── System binaries & launcher ────────────────────────────────────────────────
info "Removing launcher..."
remove /usr/local/bin/mouse-autoclicker

# ── Sudoers rule ──────────────────────────────────────────────────────────────
info "Removing sudo rule..."
remove /etc/sudoers.d/mouse-autoclicker

# ── Polkit policy ─────────────────────────────────────────────────────────────
info "Removing polkit policy..."
remove /usr/share/polkit-1/actions/com.autoclicker.mouse.policy

# ── Desktop entries ───────────────────────────────────────────────────────────
info "Removing desktop entries..."
remove /usr/share/applications/mouse-autoclicker.desktop
remove "$REAL_HOME/.local/share/applications/mouse-autoclicker.desktop"
remove "$REAL_HOME/Desktop/MouseAutoClicker.desktop"
# Remove old-style desktop file if present
remove "$PROJECT_DIR/RightClicker.desktop"

# ── Icons ─────────────────────────────────────────────────────────────────────
info "Removing icons..."
remove /usr/share/pixmaps/mouse-autoclicker.png
remove /usr/share/icons/hicolor/256x256/apps/mouse-autoclicker.png
remove /usr/share/icons/hicolor/512x512/apps/mouse-autoclicker.png
remove "$REAL_HOME/.local/share/icons/mouse-autoclicker.png"
gtk-update-icon-cache -f -t /usr/share/icons/hicolor &>/dev/null || true

# ── App menu caches ───────────────────────────────────────────────────────────
update-desktop-database /usr/share/applications &>/dev/null || true
sudo -u "$REAL_USER" update-desktop-database "$REAL_HOME/.local/share/applications" &>/dev/null || true

# ── User config (ask) ─────────────────────────────────────────────────────────
CONFIG_DIR="$REAL_HOME/.config/right_clicker"
if [ -d "$CONFIG_DIR" ]; then
    echo ""
    read -r -p "  Remove saved config & keybindings at $CONFIG_DIR? [y/N] " REPLY
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        ok "Config removed"
    else
        ok "Config kept at $CONFIG_DIR"
    fi
fi

# ── venv (inside project dir — deleted with project) ─────────────────────────
info "Removing venv..."
remove "$PROJECT_DIR/venv"

# ── Python cache ──────────────────────────────────────────────────────────────
remove "$PROJECT_DIR/__pycache__"
find "$PROJECT_DIR" -name "*.pyc" -delete 2>/dev/null || true

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  ✓ Uninstall complete!${RESET}"
echo ""
echo "  The project folder itself was NOT deleted:"
echo "  $PROJECT_DIR"
echo ""
echo "  You can safely delete that folder to remove everything."
echo ""
