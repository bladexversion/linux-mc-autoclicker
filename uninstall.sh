#!/usr/bin/env bash
# =============================================================================
#  uninstall.sh — Completely removes Mouse AutoClicker from the system
#  Run:  sudo bash uninstall.sh
# =============================================================================
set -e

# ── Colours & styles ──────────────────────────────────────────────────────────
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
BGREEN='\033[1;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BCYAN='\033[1;36m'
RED='\033[0;31m'
BRED='\033[1;31m'
BLUE='\033[0;34m'
WHITE='\033[1;37m'

# ── UI helpers ────────────────────────────────────────────────────────────────
header() {
    echo ""
    echo -e "  ${BRED}╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BRED}║${RESET}  ${WHITE}${BOLD}🗑  Mouse AutoClicker — Uninstaller${RESET}               ${BRED}║${RESET}"
    echo -e "  ${BRED}╚══════════════════════════════════════════════════╝${RESET}"
    echo ""
}

meta() {
    echo -e "  ${DIM}User   :${RESET}  ${CYAN}$1${RESET}"
    echo -e "  ${DIM}Project:${RESET}  ${CYAN}$2${RESET}"
    echo ""
}

divider() {
    echo -e "  ${DIM}────────────────────────────────────────────────${RESET}"
}

section() { echo -e "\n  ${BOLD}${BLUE}▸${RESET}  ${BOLD}${WHITE}$1${RESET}"; }
ok()      { echo -e "      ${BGREEN}✔${RESET}  $1"; }
skip()    { echo -e "      ${DIM}⊘  $1${RESET}"; }
info()    { echo -e "      ${YELLOW}›${RESET}  ${DIM}$1${RESET}"; }

needs_root() {
    echo ""
    echo -e "  ${BRED}┌──────────────────────────────────────────────┐${RESET}"
    echo -e "  ${BRED}│  ✖  Permission denied${RESET}                          ${BRED}│${RESET}"
    echo -e "  ${BRED}└──────────────────────────────────────────────┘${RESET}"
    echo ""
    echo -e "  This uninstaller removes system-wide files and needs ${BOLD}root${RESET}."
    echo ""
    echo -e "  ${DIM}Run instead:${RESET}"
    echo -e "  ${BCYAN}  sudo bash uninstall.sh${RESET}"
    echo ""
    exit 1
}

prompt_yn() {
    echo ""
    echo -ne "  ${YELLOW}?${RESET}  ${BOLD}$1${RESET}  ${DIM}[y/N]${RESET}  "
    read -r REPLY
    [[ "$REPLY" =~ ^[Yy]$ ]]
}

remove() {
    if [ -e "$1" ] || [ -L "$1" ]; then
        rm -rf "$1"
        ok "Removed  ${DIM}$1${RESET}"
    else
        skip "Not found  ${DIM}$1${RESET}"
    fi
}

done_banner() {
    echo ""
    echo -e "  ${BGREEN}╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BGREEN}║  ✔  Uninstall complete!${RESET}  Mouse AutoClicker removed.${BGREEN}║${RESET}"
    echo -e "  ${BGREEN}╚══════════════════════════════════════════════════╝${RESET}"
    echo ""
}

# ── Must run as root ──────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then needs_root; fi

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

header
meta "$REAL_USER" "$PROJECT_DIR"
divider

# ── System launcher ───────────────────────────────────────────────────────────
section "System launcher"
remove /usr/local/bin/mouse-autoclicker

# ── Sudoers rule ──────────────────────────────────────────────────────────────
section "Sudo rule"
remove /etc/sudoers.d/mouse-autoclicker

# ── Polkit policy ─────────────────────────────────────────────────────────────
section "Polkit policy"
remove /usr/share/polkit-1/actions/com.autoclicker.mouse.policy

# ── Desktop entries ───────────────────────────────────────────────────────────
section "Desktop entries"
remove /usr/share/applications/mouse-autoclicker.desktop
remove "$REAL_HOME/.local/share/applications/mouse-autoclicker.desktop"
remove "$REAL_HOME/Desktop/MouseAutoClicker.desktop"
info "Refreshing desktop database..."
update-desktop-database /usr/share/applications &>/dev/null || true
sudo -u "$REAL_USER" update-desktop-database "$REAL_HOME/.local/share/applications" &>/dev/null || true
ok "Desktop database updated"

# ── Icons ─────────────────────────────────────────────────────────────────────
section "Icons"
remove /usr/share/pixmaps/mouse-autoclicker.png
remove /usr/share/icons/hicolor/256x256/apps/mouse-autoclicker.png
remove /usr/share/icons/hicolor/512x512/apps/mouse-autoclicker.png
remove "$REAL_HOME/.local/share/icons/mouse-autoclicker.png"
info "Refreshing icon cache..."
gtk-update-icon-cache -f -t /usr/share/icons/hicolor &>/dev/null || true
ok "Icon cache updated"

# ── User config ───────────────────────────────────────────────────────────────
CONFIG_DIR="$REAL_HOME/.config/right_clicker"
if [ -d "$CONFIG_DIR" ]; then
    section "Saved config & keybindings"
    echo -e "  ${DIM}  Found: $CONFIG_DIR${RESET}"
    if prompt_yn "Remove saved config & keybindings?"; then
        rm -rf "$CONFIG_DIR"
        ok "Config removed"
    else
        skip "Config kept  ${DIM}→ $CONFIG_DIR${RESET}"
    fi
fi

# ── Project folder ────────────────────────────────────────────────────────────
section "Project folder"
echo -e "  ${DIM}  $PROJECT_DIR${RESET}"
if prompt_yn "Delete the entire project folder?"; then
    # Remove any root-owned files inside the project folder (created by setup.sh)
    # so the background rm can succeed even without root.
    find "$PROJECT_DIR" -maxdepth 2 ! -writable -exec rm -f {} + 2>/dev/null || true

    # Can't delete the directory we're currently running from — background it.
    CLEANUP_SCRIPT="$(mktemp /tmp/autoclicker_cleanup_XXXX.sh)"
    cat > "$CLEANUP_SCRIPT" << 'CLEANUP_EOF'
#!/usr/bin/env bash
sleep 1
CLEANUP_EOF
    echo "rm -rf \"$PROJECT_DIR\""    >> "$CLEANUP_SCRIPT"
    echo "rm -f  \"$CLEANUP_SCRIPT\"" >> "$CLEANUP_SCRIPT"
    chmod +x "$CLEANUP_SCRIPT"
    bash "$CLEANUP_SCRIPT" &
    ok "Project folder queued for deletion  ${DIM}(deletes in 1 s)${RESET}"
else
    skip "Project folder kept  ${DIM}→ $PROJECT_DIR${RESET}"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
done_banner
