#!/usr/bin/env bash
# =============================================================================
#  setup.sh — One-command installer for Mouse AutoClicker
#  Run once:  sudo bash setup.sh
# =============================================================================
set -e

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET} $1"; }
info() { echo -e "${YELLOW}→${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; exit 1; }

# ── Must run as root ──────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "This script needs root to install system-wide files."
    echo "Run:  sudo bash setup.sh"
    exit 1
fi

# ── Resolve the real (non-root) user and project dir ─────────────────────────
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="/usr/bin/python3"

echo ""
echo "  Mouse AutoClicker — Setup"
echo "  Project : $PROJECT_DIR"
echo "  User    : $REAL_USER ($REAL_HOME)"
echo ""

# ── 1. System dependencies ────────────────────────────────────────────────────
info "Checking system dependencies..."
MISSING_PKGS=()
for pkg in python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pip python3-venv; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done
if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    info "Installing missing packages: ${MISSING_PKGS[*]}"
    apt-get install -y "${MISSING_PKGS[@]}" || fail "apt-get install failed"
fi
ok "System dependencies satisfied"

# ── 2. Virtual environment ────────────────────────────────────────────────────
info "Creating virtual environment with system-site-packages..."
if [ -d "$VENV_DIR" ]; then
    info "venv already exists — skipping creation"
else
    sudo -u "$REAL_USER" "$PYTHON" -m venv --system-site-packages "$VENV_DIR"
fi

VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python3"

info "Installing Python packages into venv..."
sudo -u "$REAL_USER" "$VENV_PIP" install --upgrade pip --quiet
sudo -u "$REAL_USER" "$VENV_PIP" install evdev pynput --quiet
ok "Python packages installed (evdev, pynput)"

# ── 3. Launcher script at /usr/local/bin/mouse-autoclicker ───────────────────
info "Installing launcher to /usr/local/bin/mouse-autoclicker..."
cat > /usr/local/bin/mouse-autoclicker << LAUNCHER
#!/usr/bin/env bash
export DISPLAY="\${DISPLAY:-:0}"
# Pick up Xauthority from the real desktop user
if [ -z "\$XAUTHORITY" ]; then
    for xauth in "$REAL_HOME/.Xauthority" "/tmp/.Xauthority-$REAL_USER"; do
        if [ -f "\$xauth" ]; then export XAUTHORITY="\$xauth"; break; fi
    done
fi
# Escalate to root if not already root
if [ "\$(id -u)" -ne 0 ]; then
    exec sudo /usr/local/bin/mouse-autoclicker "\$@"
fi
# Run with venv Python
exec "$VENV_PYTHON" "$PROJECT_DIR/right_clicker.py" "\$@"
LAUNCHER
chmod 755 /usr/local/bin/mouse-autoclicker
ok "Launcher installed at /usr/local/bin/mouse-autoclicker"

# ── 4. Passwordless sudo rule ─────────────────────────────────────────────────
info "Configuring passwordless sudo..."
SUDOERS_FILE="/etc/sudoers.d/mouse-autoclicker"
cat > "$SUDOERS_FILE" << SUDOERS
# Mouse AutoClicker — passwordless launch (installed by setup.sh)
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/mouse-autoclicker
SUDOERS
chmod 440 "$SUDOERS_FILE"
# Validate — if visudo check fails, remove and abort
if ! visudo -c -f "$SUDOERS_FILE" &>/dev/null; then
    rm -f "$SUDOERS_FILE"
    fail "sudoers syntax error — rule not installed"
fi
ok "Passwordless sudo configured"

# ── 5. Polkit policy (pkexec fallback) ────────────────────────────────────────
info "Installing polkit policy..."
POLICY_SRC="$PROJECT_DIR/com.autoclicker.mouse.policy"
POLICY_DST="/usr/share/polkit-1/actions/com.autoclicker.mouse.policy"
if [ -f "$POLICY_SRC" ]; then
    cp "$POLICY_SRC" "$POLICY_DST"
    chmod 644 "$POLICY_DST"
    ok "Polkit policy installed"
else
    echo "  (skipped — com.autoclicker.mouse.policy not found)"
fi

# ── 6. App icon ───────────────────────────────────────────────────────────────
info "Installing app icon..."
ICON_SRC="$PROJECT_DIR/Neon Click Mouse Icon.png"
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
    ok "Icon installed"
else
    echo "  (skipped — icon PNG not found)"
fi

# ── 7. Desktop entry (shows in app menu) ─────────────────────────────────────
info "Installing desktop entry..."
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

# System-wide
echo "$DESKTOP_CONTENT" > /usr/share/applications/mouse-autoclicker.desktop
chmod 644 /usr/share/applications/mouse-autoclicker.desktop

# Per-user
USER_APP_DIR="$REAL_HOME/.local/share/applications"
mkdir -p "$USER_APP_DIR"
echo "$DESKTOP_CONTENT" > "$USER_APP_DIR/mouse-autoclicker.desktop"
chmod 644 "$USER_APP_DIR/mouse-autoclicker.desktop"
chown "$REAL_USER:$REAL_USER" "$USER_APP_DIR/mouse-autoclicker.desktop"

# Refresh app menu
sudo -u "$REAL_USER" update-desktop-database "$USER_APP_DIR" &>/dev/null || true
update-desktop-database /usr/share/applications &>/dev/null || true
ok "Desktop entry installed (check Applications menu)"

# ── 8. Desktop shortcut (optional) ───────────────────────────────────────────
DESKTOP_PATH="$REAL_HOME/Desktop/MouseAutoClicker.desktop"
echo "$DESKTOP_CONTENT" > "$DESKTOP_PATH"
chmod 755 "$DESKTOP_PATH"
chown "$REAL_USER:$REAL_USER" "$DESKTOP_PATH"
ok "Desktop shortcut created"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  ✓ Setup complete!${RESET}"
echo ""
echo "  Launch options:"
echo "    • Double-click 'Mouse AutoClicker' in your Applications menu"
echo "    • Double-click the desktop shortcut"
echo "    • Terminal: mouse-autoclicker"
echo ""
echo "  To uninstall cleanly:  sudo bash uninstall.sh"
echo ""
