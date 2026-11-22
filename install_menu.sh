#!/usr/bin/env bash
# Install Mouse AutoClicker to the Linux Applications Menu

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="${HOME}"

# If run under sudo, determine real user's home
if [ -n "$SUDO_USER" ]; then
    USER_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
fi

TARGET_DIR="$USER_HOME/.local/share/applications"
mkdir -p "$TARGET_DIR" 2>/dev/null || true

DESKTOP_FILE="$TARGET_DIR/mouse-autoclicker.desktop"

ICON_DIR="$USER_HOME/.local/share/icons"
mkdir -p "$ICON_DIR" 2>/dev/null || true
if [ -f "$DIR/Neon Click Mouse Icon.png" ]; then
    cp "$DIR/Neon Click Mouse Icon.png" "$ICON_DIR/mouse-autoclicker.png" 2>/dev/null || true
    if [ "$EUID" -eq 0 ]; then
        cp "$DIR/Neon Click Mouse Icon.png" "/usr/share/pixmaps/mouse-autoclicker.png" 2>/dev/null || true
    fi
fi

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=Mouse AutoClicker
GenericName=Auto Clicker
Comment=Auto-clicker for mouse side and forward buttons with dynamic CPS control
Exec=/usr/local/bin/mouse-autoclicker
Path=$DIR
Icon=mouse-autoclicker
Terminal=false
Categories=Utility;GTK;Settings;HardwareSettings;
Keywords=mouse;clicker;autoclicker;cps;gaming;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE" 2>/dev/null || true

# If running as root, also install system-wide
if [ "$EUID" -eq 0 ]; then
    cp "$DESKTOP_FILE" "/usr/share/applications/mouse-autoclicker.desktop" 2>/dev/null || true
    chmod +x "/usr/share/applications/mouse-autoclicker.desktop" 2>/dev/null || true
fi

# Update desktop databases so it shows immediately in the Whisker/Start menu
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$TARGET_DIR" 2>/dev/null || true
    [ "$EUID" -eq 0 ] && update-desktop-database "/usr/share/applications" 2>/dev/null || true
fi

echo "Mouse AutoClicker has been added to your Applications menu!"
