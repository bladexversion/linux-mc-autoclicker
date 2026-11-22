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
echo "  User   : $REAL_USER"
echo "  Project: $PROJECT_DIR"
echo ""

remove() {
    if [ -e "$1" ] || [ -L "$1" ]; then
        rm -rf "$1"
        ok "Removed $1"
    fi
}

# ── System launcher ───────────────────────────────────────────────────────────
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
update-desktop-database /usr/share/applications &>/dev/null || true
sudo -u "$REAL_USER" update-desktop-database "$REAL_HOME/.local/share/applications" &>/dev/null || true

# ── Icons ─────────────────────────────────────────────────────────────────────
info "Removing icons..."
remove /usr/share/pixmaps/mouse-autoclicker.png
remove /usr/share/icons/hicolor/256x256/apps/mouse-autoclicker.png
remove /usr/share/icons/hicolor/512x512/apps/mouse-autoclicker.png
remove "$REAL_HOME/.local/share/icons/mouse-autoclicker.png"
gtk-update-icon-cache -f -t /usr/share/icons/hicolor &>/dev/null || true

# ── User config ───────────────────────────────────────────────────────────────
CONFIG_DIR="$REAL_HOME/.config/right_clicker"
if [ -d "$CONFIG_DIR" ]; then
    echo ""
    read -r -p "  Remove saved config & keybindings? [y/N] " REPLY
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        ok "Config removed"
    else
        ok "Config kept at $CONFIG_DIR"
    fi
fi

# ── Project folder ────────────────────────────────────────────────────────────
echo ""
read -r -p "  Delete the project folder itself ($PROJECT_DIR)? [y/N] " REPLY
if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    # Can't delete our own running directory — schedule it via a temp script
    CLEANUP_SCRIPT="$(mktemp /tmp/autoclicker_cleanup_XXXX.sh)"
    cat > "$CLEANUP_SCRIPT" << CLEANUP
#!/usr/bin/env bash
sleep 1
rm -rf "$PROJECT_DIR"
rm -f "$CLEANUP_SCRIPT"
CLEANUP
    chmod +x "$CLEANUP_SCRIPT"
    bash "$CLEANUP_SCRIPT" &
    ok "Project folder will be deleted in 1 second"
else
    ok "Project folder kept at $PROJECT_DIR"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  ✓ Uninstall complete! Mouse AutoClicker has been fully removed.${RESET}"
echo ""
