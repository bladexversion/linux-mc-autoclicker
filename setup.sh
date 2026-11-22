#!/usr/bin/env bash
# =============================================================================
#  setup.sh — One-command installer for Mouse AutoClicker
#  Run once:  sudo bash setup.sh
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
step_num=0
total_steps=8

header() {
    echo -e ""
    echo -e "${BCYAN}╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "${BCYAN}║${RESET}  ${WHITE}${BOLD}🖱  Mouse AutoClicker — Installer${RESET}                ${BCYAN}║${RESET}"
    echo -e "${BCYAN}╚══════════════════════════════════════════════════╝${RESET}"
    echo ""
}

meta() {
    echo -e "  ${DIM}User   :${RESET}  ${CYAN}$1${RESET}"
    echo -e "  ${DIM}Home   :${RESET}  ${CYAN}$2${RESET}"
    echo -e "  ${DIM}Project:${RESET}  ${CYAN}$3${RESET}"
    echo ""
}

divider() {
    echo -e "  ${DIM}────────────────────────────────────────────────${RESET}"
}

step() {
    step_num=$((step_num + 1))
    echo ""
    echo -e "  ${BOLD}${BLUE}[${step_num}/${total_steps}]${RESET}  ${BOLD}${WHITE}$1${RESET}"
}

ok()   { echo -e "        ${BGREEN}✔${RESET}  $1"; }
skip() { echo -e "        ${DIM}⊘  $1${RESET}"; }
info() { echo -e "        ${YELLOW}›${RESET}  ${DIM}$1${RESET}"; }
fail() {
    echo ""
    echo -e "  ${BRED}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BRED}║  ✖  Error${RESET}"
    echo -e "  ${BRED}║${RESET}  $1"
    echo -e "  ${BRED}╚══════════════════════════════════════════════╝${RESET}"
    echo ""
    exit 1
}

needs_root() {
    echo ""
    echo -e "  ${BRED}┌──────────────────────────────────────────────┐${RESET}"
    echo -e "  ${BRED}│  ✖  Permission denied${RESET}                          ${BRED}│${RESET}"
    echo -e "  ${BRED}└──────────────────────────────────────────────┘${RESET}"
    echo ""
    echo -e "  This installer writes to system directories and needs ${BOLD}root${RESET}."
    echo ""
    echo -e "  ${DIM}Run instead:${RESET}"
    echo -e "  ${BCYAN}  sudo bash setup.sh${RESET}"
    echo ""
    exit 1
}

done_banner() {
    echo ""
    echo -e "  ${BGREEN}╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BGREEN}║  ✔  Setup complete!${RESET}                              ${BGREEN}║${RESET}"
    echo -e "  ${BGREEN}╚══════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "  ${BOLD}Launch options:${RESET}"
    echo -e "  ${DIM}•${RESET}  Applications menu  ${DIM}→${RESET}  ${CYAN}Mouse AutoClicker${RESET}"
    echo -e "  ${DIM}•${RESET}  Desktop shortcut   ${DIM}→${RESET}  double-click the icon"
    echo -e "  ${DIM}•${RESET}  Terminal           ${DIM}→${RESET}  ${CYAN}mouse-autoclicker${RESET}"
    echo ""
    divider
    echo -e "  ${DIM}To uninstall:  ${CYAN}sudo bash uninstall.sh${RESET}"
    echo ""
}

# ── Must run as root ──────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then needs_root; fi

# ── Resolve the real (non-root) user and project dir ─────────────────────────
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="/usr/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python3"

header
meta "$REAL_USER" "$REAL_HOME" "$PROJECT_DIR"

# ── 1. System dependencies ────────────────────────────────────────────────────
step "System dependencies"
MISSING_PKGS=()
for pkg in python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pip python3-venv; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done
if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    info "Installing: ${MISSING_PKGS[*]}"
    apt-get install -y "${MISSING_PKGS[@]}" &>/dev/null || fail "apt-get install failed"
    ok "Installed: ${MISSING_PKGS[*]}"
else
    ok "All system packages already present"
fi

# ── 2. Virtual environment ────────────────────────────────────────────────────
step "Python virtual environment"
if [ -d "$VENV_DIR" ]; then
    skip "venv already exists — skipping creation"
else
    info "Creating venv with system-site-packages..."
    sudo -u "$REAL_USER" "$PYTHON" -m venv --system-site-packages "$VENV_DIR"
    ok "Virtual environment created"
fi
info "Upgrading pip & installing evdev, pynput..."
sudo -u "$REAL_USER" "$VENV_PIP" install --upgrade pip --quiet
sudo -u "$REAL_USER" "$VENV_PIP" install evdev pynput --quiet
ok "Python packages ready  ${DIM}(evdev, pynput)${RESET}"

# ── 3. System launcher ────────────────────────────────────────────────────────
step "System launcher"
info "Writing /usr/local/bin/mouse-autoclicker..."
cat > /usr/local/bin/mouse-autoclicker << LAUNCHER
#!/usr/bin/env bash
export DISPLAY="\${DISPLAY:-:0}"
if [ -z "\$XAUTHORITY" ]; then
    for xauth in "$REAL_HOME/.Xauthority" "/tmp/.Xauthority-$REAL_USER"; do
        if [ -f "\$xauth" ]; then export XAUTHORITY="\$xauth"; break; fi
    done
fi
if [ "\$(id -u)" -ne 0 ]; then
    exec sudo /usr/local/bin/mouse-autoclicker "\$@"
fi
exec "$VENV_PYTHON" "$PROJECT_DIR/right_clicker.py" "\$@"
LAUNCHER
chmod 755 /usr/local/bin/mouse-autoclicker
ok "Launcher installed  ${DIM}→ /usr/local/bin/mouse-autoclicker${RESET}"

# ── 4. Passwordless sudo rule ─────────────────────────────────────────────────
step "Sudo rule"
SUDOERS_FILE="/etc/sudoers.d/mouse-autoclicker"
info "Writing sudoers entry..."
cat > "$SUDOERS_FILE" << SUDOERS
# Mouse AutoClicker — passwordless launch (installed by setup.sh)
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/mouse-autoclicker
SUDOERS
chmod 440 "$SUDOERS_FILE"
if ! visudo -c -f "$SUDOERS_FILE" &>/dev/null; then
    rm -f "$SUDOERS_FILE"
    fail "sudoers syntax error — rule not installed"
fi
ok "Passwordless sudo configured  ${DIM}→ /etc/sudoers.d/mouse-autoclicker${RESET}"

# ── 5. Polkit policy ──────────────────────────────────────────────────────────
step "Polkit policy"
POLICY_SRC="$PROJECT_DIR/com.autoclicker.mouse.policy"
POLICY_DST="/usr/share/polkit-1/actions/com.autoclicker.mouse.policy"
if [ -f "$POLICY_SRC" ]; then
    cp "$POLICY_SRC" "$POLICY_DST"
    chmod 644 "$POLICY_DST"
    ok "Polkit policy installed  ${DIM}→ $POLICY_DST${RESET}"
else
    skip "com.autoclicker.mouse.policy not found — skipped"
fi

# ── 6. App icon ───────────────────────────────────────────────────────────────
step "App icon"
ICON_SRC="$PROJECT_DIR/assets/icon.png"
if [ -f "$ICON_SRC" ]; then
    for RES in 256x256 512x512; do
        ICON_DIR="/usr/share/icons/hicolor/$RES/apps"
        mkdir -p "$ICON_DIR"
        cp "$ICON_SRC" "$ICON_DIR/mouse-autoclicker.png"
    done
    mkdir -p /usr/share/pixmaps
    cp "$ICON_SRC" /usr/share/pixmaps/mouse-autoclicker.png
    USER_ICON_DIR="$REAL_HOME/.local/share/icons"
    mkdir -p "$USER_ICON_DIR"
    cp "$ICON_SRC" "$USER_ICON_DIR/mouse-autoclicker.png"
    chown "$REAL_USER:$REAL_USER" "$USER_ICON_DIR/mouse-autoclicker.png"
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor &>/dev/null || true
    ok "Icons installed  ${DIM}(256×256, 512×512, pixmap, user)${RESET}"
else
    skip "icon PNG not found — skipped"
fi

# ── 7. Desktop entry ──────────────────────────────────────────────────────────
step "Desktop entry  ${DIM}(Applications menu)${RESET}"
DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=Mouse AutoClicker
GenericName=Auto Clicker
Comment=Multi-Binding Auto Clicker for Linux
Exec=/usr/local/bin/mouse-autoclicker
Path=$PROJECT_DIR
Icon=mouse-autoclicker
Terminal=false
Categories=Utility;GTK;Settings;HardwareSettings;
Keywords=mouse;clicker;autoclicker;cps;gaming;bindings;
StartupNotify=true"

echo "$DESKTOP_CONTENT" > /usr/share/applications/mouse-autoclicker.desktop
chmod 644 /usr/share/applications/mouse-autoclicker.desktop

USER_APP_DIR="$REAL_HOME/.local/share/applications"
mkdir -p "$USER_APP_DIR"
echo "$DESKTOP_CONTENT" > "$USER_APP_DIR/mouse-autoclicker.desktop"
chmod 644 "$USER_APP_DIR/mouse-autoclicker.desktop"
chown "$REAL_USER:$REAL_USER" "$USER_APP_DIR/mouse-autoclicker.desktop"

sudo -u "$REAL_USER" update-desktop-database "$USER_APP_DIR" &>/dev/null || true
update-desktop-database /usr/share/applications &>/dev/null || true
ok "Desktop entry installed  ${DIM}(system + user)${RESET}"

# ── 8. Desktop shortcut ───────────────────────────────────────────────────────
step "Desktop shortcut"
DESKTOP_PATH="$REAL_HOME/Desktop/MouseAutoClicker.desktop"
echo "$DESKTOP_CONTENT" > "$DESKTOP_PATH"
chmod 755 "$DESKTOP_PATH"
chown "$REAL_USER:$REAL_USER" "$DESKTOP_PATH"
ok "Shortcut created  ${DIM}→ ~/Desktop/MouseAutoClicker.desktop${RESET}"

# ── Done ──────────────────────────────────────────────────────────────────────
done_banner
