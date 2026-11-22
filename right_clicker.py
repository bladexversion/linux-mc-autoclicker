#!/usr/bin/env python3
"""
Mouse AutoClicker for Linux Mint XFCE / Modern Linux Desktops.
Features:
- Dynamic list of customizable bindings (Trigger button, Action, CPS, Mode, Sub-delay).
- Extensible Action Registry (Left, Right, Middle, Double, Triple, Back, Forward, Hold Down, Scroll Up/Down).
- "Detect" button to quickly assign any mouse button as trigger.
- Global Start/Stop switch with system-wide background Hotkey (default: F6).
- Real-time status bar reporting active bindings, clicks, and mouse hardware.
- Native GTK3 interface with modern dark theme CSS.
- Persistent JSON configuration in ~/.config/right_clicker/config.json.
- Zero-swallowing click engine using evdev + uinput with precision deadline sleep.
"""

import os
import sys
import time
import random
import threading
import subprocess
import argparse
import json
import uuid

# Setup environment for GUI under sudo/pkexec if needed
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

if "XAUTHORITY" not in os.environ:
    for u_var in ["SUDO_USER", "PKEXEC_USER"]:
        u = os.environ.get(u_var)
        if u and u != "root":
            candidate = f"/home/{u}/.Xauthority"
            if os.path.exists(candidate):
                os.environ["XAUTHORITY"] = candidate
                break
    if "XAUTHORITY" not in os.environ:
        pkexec_uid = os.environ.get("PKEXEC_UID")
        if pkexec_uid:
            try:
                import pwd
                u = pwd.getpwuid(int(pkexec_uid)).pw_name
                if u != "root" and os.path.exists(f"/home/{u}/.Xauthority"):
                    os.environ["XAUTHORITY"] = f"/home/{u}/.Xauthority"
            except Exception:
                pass
    if "XAUTHORITY" not in os.environ and os.path.exists("/home/aravsun/.Xauthority"):
        os.environ["XAUTHORITY"] = "/home/aravsun/.Xauthority"

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

try:
    import evdev
    from evdev import UInput, ecodes as e
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    e = None


# ==============================================================================
# ACTION REGISTRY - Easily extendable: add any new action definition here!
# ==============================================================================
class ActionDefinition:
    """
    Defines an autoclicker action.
    To add a new action type in the future, simply add an ActionDefinition
    instance to the ACTION_REGISTRY list below.
    """
    def __init__(self, key, label, category, code=None, burst_count=1,
                 has_sub_delay=False, default_sub_delay_ms=35, scroll_delta=0,
                 description=""):
        self.key = key                    # Unique identifier (e.g. "left", "double", "scroll_up")
        self.label = label                # Human-readable label in GUI dropdown
        self.category = category          # "click", "burst", "hold", "scroll"
        self.code = code                  # evdev keycode (e.g. e.BTN_LEFT)
        self.burst_count = burst_count    # Clicks per burst (for "burst" category)
        self.has_sub_delay = has_sub_delay  # Requires adjustable delay between sub-clicks
        self.default_sub_delay_ms = default_sub_delay_ms
        self.scroll_delta = scroll_delta  # +1 for up, -1 for down
        self.description = description


ACTION_REGISTRY = [
    ActionDefinition("left", "Left Click (Auto)", "click", code=(e.BTN_LEFT if e else 272)),
    ActionDefinition("right", "Right Click (Auto)", "click", code=(e.BTN_RIGHT if e else 273)),
    ActionDefinition("double_left", "Double Left Click", "burst", code=(e.BTN_LEFT if e else 272),
                     burst_count=2, has_sub_delay=True, default_sub_delay_ms=35),
    ActionDefinition("double_right", "Double Right Click", "burst", code=(e.BTN_RIGHT if e else 273),
                     burst_count=2, has_sub_delay=True, default_sub_delay_ms=35),
    ActionDefinition("remap_left", "Normal Left Click (1:1)", "hold", code=(e.BTN_LEFT if e else 272)),
    ActionDefinition("remap_right", "Normal Right Click (1:1)", "hold", code=(e.BTN_RIGHT if e else 273)),
]

def get_action_by_key(key):
    # Backward compatibility for legacy configs
    if key in ("double", "double_click"):
        key = "double_left"
    for act in ACTION_REGISTRY:
        if act.key == key:
            return act
    return ACTION_REGISTRY[0]


# Standard trigger mouse buttons
TRIGGER_OPTIONS = [
    {"key": "left", "label": "Left Button", "code": e.BTN_LEFT if e else 272, "x_button": 1},
    {"key": "right", "label": "Right Button", "code": e.BTN_RIGHT if e else 273, "x_button": 3},
    {"key": "middle", "label": "Middle Button", "code": e.BTN_MIDDLE if e else 274, "x_button": 2},
    {"key": "back", "label": "Back Button", "code": e.BTN_SIDE if e else 275, "x_button": 8},
    {"key": "forward", "label": "Forward Button", "code": e.BTN_EXTRA if e else 276, "x_button": 9},
]

def get_trigger_label(key, code=None):
    for opt in TRIGGER_OPTIONS:
        if opt["key"] == key or (code is not None and opt["code"] == code):
            return opt["label"]
    if code is not None:
        return f"Button ({code})"
    return "Custom Button"

def code_to_trigger_key(code):
    for opt in TRIGGER_OPTIONS:
        if opt["code"] == code:
            return opt["key"]
    return f"custom_{code}"

def trigger_key_to_code(key):
    for opt in TRIGGER_OPTIONS:
        if opt["key"] == key:
            return opt["code"]
    if key.startswith("custom_"):
        try:
            return int(key.split("_")[1])
        except Exception:
            pass
    return e.BTN_SIDE if e else 275


# ==============================================================================
# CSS DARK THEME STYLING
# ==============================================================================
CSS_STYLES = b"""
/* =========================================================
   SUPABASE DATABASE THEME - DARK PALETTE
   ========================================================= */
window, .main-window {
    background-color: #0c0c0c;
    color: #ededed;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Ubuntu, Cantarell, sans-serif;
}

/* Base Cards */
.card {
    background-color: #121212;
    border-radius: 6px;
    border: 1px solid #1f1f1f;
    padding: 8px 12px;
    margin-bottom: 6px;
}

/* ScrolledWindow & Viewport - DARK BACKGROUND (PREVENTS WHITE CONTAINER) */
scrolledwindow,
scrolledwindow viewport,
viewport,
viewport.frame,
.frame {
    background-color: #121212;
    background-image: none;
    border: none;
    box-shadow: none;
    color: #ededed;
}

/* Table Header */
.table-header {
    background-color: #141414;
    border: 1px solid #202020;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
}
.th-label {
    color: #555555;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.6px;
}

/* Table Container & Rows */
.table-container {
    background-color: #0c0c0c;
    background-image: none;
    border: none;
    border-radius: 0;
    padding: 4px 0;
}

.binding-card {
    background-color: #111111;
    background-image: none;
    border: 1px solid #1e1e1e;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 0 0 6px 0;
}
.binding-card:hover {
    background-color: #161616;
    border-color: #282828;
}
.binding-card-active {
    background-color: #0c1a14;
    border-color: #3ecf8e;
}

/* Trigger big button */
.trigger-btn {
    background-color: #1a1a1a;
    background-image: none;
    color: #ffffff;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    min-height: 32px;
}
.trigger-btn:hover {
    background-color: #222222;
    border-color: #3ecf8e;
    color: #3ecf8e;
}
.trigger-btn-detecting {
    background-color: #261a05;
    background-image: none;
    color: #f59e0b;
    border: 1px solid #63430a;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    min-height: 32px;
}

/* Action pill buttons */
.action-pill {
    background-color: #1a1a1a;
    background-image: none;
    color: #666666;
    border: 1px solid #252525;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    min-height: 26px;
}
.action-pill:hover {
    background-color: #202020;
    color: #aaaaaa;
}
.action-pill-active {
    background-color: #0d2419;
    background-image: none;
    color: #3ecf8e;
    border: 1px solid #1a4832;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 10px;
    min-height: 26px;
}

/* Mode pill buttons */
.mode-pill {
    background-color: #1a1a1a;
    background-image: none;
    color: #666666;
    border: 1px solid #252525;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    min-height: 26px;
}
.mode-pill:hover {
    background-color: #202020;
    color: #aaaaaa;
}
.mode-pill-active {
    background-color: #1a1420;
    background-image: none;
    color: #a78bfa;
    border: 1px solid #3d2d6e;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 10px;
    min-height: 26px;
}

/* Card section labels */
.card-section-label {
    color: #444444;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

/* Speed slider label */
.speed-label {
    color: #555555;
    font-size: 10px;
    font-weight: 600;
}

.card-title {
    font-size: 10px;
    font-weight: 600;
    color: #666666;
    letter-spacing: 0.5px;
}

/* Header & Subtitle */
.app-title {
    font-size: 14px;
    font-weight: 700;
    color: #ffffff;
}
.app-subtitle {
    font-size: 11px;
    color: #888888;
}

/* Master Toggle Button */
.master-btn-active {
    background-color: #0d2419;
    background-image: none;
    color: #3ecf8e;
    border: 1px solid #1a4832;
    border-radius: 14px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
}
.master-btn-active:hover {
    background-color: #113022;
    color: #55e6a5;
}
.master-btn-paused {
    background-color: #181818;
    background-image: none;
    color: #666666;
    border: 1px solid #262626;
    border-radius: 14px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
}
.master-btn-paused:hover {
    background-color: #202020;
    color: #aaaaaa;
}

.hotkey-badge {
    background-color: #161616;
    background-image: none;
    color: #777777;
    border: 1px solid #242424;
    border-radius: 4px;
    padding: 3px 7px;
    font-size: 10px;
    font-weight: 600;
}
.hotkey-badge:hover {
    background-color: #1f1f1f;
    color: #cccccc;
}

/* =========================================================
   TABLE CELLS: COMBOBOX (FLAT, ZERO BULK)
   ========================================================= */
combobox {
    background-color: transparent;
    border: none;
    padding: 0;
    margin: 0;
}
combobox button,
combobox > button.combo {
    background-color: #161616;
    background-image: none;
    color: #d4d4d4;
    border: 1px solid #242424;
    border-radius: 4px;
    padding: 1px 4px;
    font-size: 11px;
    font-weight: 500;
    min-height: 22px;
    box-shadow: none;
}
combobox button:hover,
combobox > button.combo:hover {
    background-color: #1d1d1d;
    border-color: #333333;
    color: #ffffff;
}
combobox button:focus,
combobox > button.combo:focus {
    border-color: #3ecf8e;
}
combobox arrow,
.combo arrow {
    color: #555555;
    min-width: 10px;
    min-height: 10px;
}

/* Dropdown Menu */
menu, .combo-menu {
    background-color: #141414;
    color: #cccccc;
    border: 1px solid #262626;
    border-radius: 5px;
    padding: 2px;
}
menuitem, menu menuitem {
    background-color: transparent;
    color: #cccccc;
    padding: 3px 6px;
    border-radius: 3px;
    font-size: 11px;
}
menuitem:hover, menuitem:selected,
menu menuitem:hover, menu menuitem:selected {
    background-color: #222222;
    color: #ffffff;
}
treeview, treeview.view, .combo treeview {
    background-color: #141414;
    color: #cccccc;
}
treeview row, .combo treeview row {
    background-color: #141414;
    color: #cccccc;
    padding: 2px 4px;
}
treeview row:hover, .combo treeview row:hover {
    background-color: #202020;
    color: #ffffff;
}
treeview row:selected,
.combo treeview row:selected {
    background-color: #222222;
    color: #ffffff;
}
window.popup, .popup, window.popup frame, .popup frame {
    background-color: #141414;
    color: #cccccc;
    border: 1px solid #262626;
    border-radius: 5px;
}
cellrenderertext, .cell {
    color: #cccccc;
    background-color: transparent;
}
row:selected .cell {
    color: #ffffff;
}

/* =========================================================
   TABLE CELLS: NUMERIC ENTRY (DARK, NO + / - BUTTONS)
   ========================================================= */
entry,
entry text,
.num-cell {
    color: #ffffff;
    background-color: #161616;
    background-image: none;
    border: 1px solid #242424;
    border-radius: 4px;
    padding: 1px 4px;
    font-size: 11px;
    font-weight: 500;
    min-height: 22px;
    box-shadow: none;
}
entry:focus,
entry text:focus,
.num-cell:focus {
    border-color: #3ecf8e;
    background-color: #1a1a1a;
}

/* =========================================================
   BUTTONS (TOOLBAR & MINIMAL ROW ACTIONS)
   ========================================================= */
button {
    background-color: #181818;
    background-image: none;
    color: #cccccc;
    border: 1px solid #282828;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
    box-shadow: none;
    text-shadow: none;
    min-height: 22px;
}
button:hover {
    background-color: #202020;
    border-color: #363636;
    color: #ffffff;
}
button:active {
    background-color: #121212;
}

.btn-primary {
    background-color: #1c1c1c;
    background-image: none;
    color: #ededed;
    border: 1px solid #2c2c2c;
    border-radius: 4px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 11px;
}
.btn-primary:hover {
    background-color: #242424;
    border-color: #3a3a3a;
    color: #ffffff;
}

.btn-save {
    background-color: #3ecf8e;
    background-image: none;
    color: #071710;
    border: 1px solid #3ecf8e;
    border-radius: 4px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}
.btn-save:hover {
    background-color: #48d897;
    color: #040e0a;
}
.btn-saved {
    background-color: #133827;
    background-image: none;
    color: #3ecf8e;
    border: 1px solid #287450;
}
.btn-save-disabled {
    background-color: #1e1e1e;
    background-image: none;
    color: #444444;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}
.btn-save-disabled:hover {
    background-color: #1e1e1e;
    color: #444444;
}

/* Detect Tag */
.btn-detect {
    background-color: #161616;
    background-image: none;
    color: #777777;
    border: 1px solid #242424;
    border-radius: 3px;
    padding: 1px 4px;
    font-size: 9px;
    font-weight: 600;
    min-height: 22px;
}
.btn-detect:hover {
    background-color: #0d1e16;
    color: #3ecf8e;
    border-color: #1f4e37;
}
.btn-detect-active {
    background-color: #261a05;
    background-image: none;
    color: #f59e0b;
    border: 1px solid #63430a;
}

/* Ghost Delete Button */
.btn-danger {
    background-color: transparent;
    background-image: none;
    color: #555555;
    border: none;
    border-radius: 3px;
    padding: 0;
    font-size: 11px;
    min-width: 18px;
    min-height: 18px;
}
.btn-danger:hover {
    background-color: #261111;
    color: #f87171;
}

/* Parameters Label & Badges */
.param-label {
    color: #888888;
    font-size: 10px;
    font-weight: 600;
}
.badge-hold-mode {
    color: #3ecf8e;
    background-color: #0d2117;
    border: 1px solid #1a4430;
    border-radius: 3px;
    padding: 1px 6px;
    font-size: 9px;
    font-weight: 600;
}
.badge-idle {
    color: #333333;
    font-size: 10px;
}
.badge-clicking {
    color: #3ecf8e;
    font-size: 10px;
    font-weight: 800;
}

/* Checkbox */
checkbutton {
    background-color: transparent;
    border: none;
    padding: 0;
}
checkbutton check {
    background-color: #161616;
    background-image: none;
    border: 1px solid #282828;
    border-radius: 3px;
    min-width: 14px;
    min-height: 14px;
}
checkbutton:checked check,
checkbutton check:checked {
    background-color: #3ecf8e;
    background-image: none;
    border-color: #3ecf8e;
    color: #071710;
}
checkbutton:hover check {
    border-color: #3c3c3c;
}

/* Sliders */
scale trough {
    background-color: #161616;
    border: 1px solid #242424;
    border-radius: 4px;
    min-height: 4px;
}
scale highlight {
    background-color: #3ecf8e;
    border-radius: 4px;
}
scale slider {
    background-color: #cccccc;
    border: 2px solid #3ecf8e;
    border-radius: 6px;
    min-width: 10px;
    min-height: 10px;
}

/* Status Bar */
.status-bar-box {
    background-color: #080808;
    border-top: 1px solid #181818;
    padding: 4px 10px;
}
.status-text {
    font-size: 10px;
    color: #555555;
}
.status-bold {
    font-size: 10px;
    font-weight: 700;
    color: #3ecf8e;
}

/* Click Tester */
.test-click-area {
    background-color: #101010;
    border: 1px dashed #222222;
    border-radius: 5px;
    padding: 6px 10px;
}
.test-click-area label {
    font-size: 11px;
    color: #555555;
}
.test-click-area:hover {
    background-color: #141414;
    border-color: #3ecf8e;
}
.test-click-area:hover label {
    color: #3ecf8e;
}

/* Scrollbars */
scrollbar slider {
    background-color: #222222;
    border-radius: 3px;
    min-width: 4px;
}
scrollbar slider:hover {
    background-color: #303030;
}

/* Expander */
expander title, expander > title {
    color: #555555;
    font-size: 10px;
    font-weight: 600;
}
expander title:hover, expander > title:hover {
    color: #cccccc;
}

/* Separator */
separator {
    background-color: #1c1c1c;
    min-height: 1px;
    min-width: 1px;
}
"""




# ==============================================================================
# CONFIG & PATH HELPERS
# ==============================================================================
def get_desktop_user():
    """Detect real non-root desktop user under sudo or pkexec."""
    for var in ["SUDO_USER", "PKEXEC_USER"]:
        u = os.environ.get(var)
        if u and u != "root":
            return u
    pkexec_uid = os.environ.get("PKEXEC_UID")
    if pkexec_uid:
        try:
            import pwd
            u = pwd.getpwuid(int(pkexec_uid)).pw_name
            if u != "root":
                return u
        except Exception:
            pass
    try:
        for u in os.listdir("/home"):
            if os.path.isdir(f"/home/{u}") and u != "lost+found":
                return u
    except Exception:
        pass
    return os.environ.get("USER", "aravsun")


def get_config_path():
    """Returns path to the user configuration file in ~/.config/right_clicker/config.json."""
    user = get_desktop_user()
    if user and user != "root":
        config_dir = f"/home/{user}/.config/right_clicker"
    else:
        config_dir = os.path.expanduser("~/.config/right_clicker")
    try:
        os.makedirs(config_dir, exist_ok=True)
        if os.geteuid() == 0 and user and user != "root":
            import pwd
            p = pwd.getpwnam(user)
            os.chown(config_dir, p.pw_uid, p.pw_gid)
    except Exception:
        pass
    return os.path.join(config_dir, "config.json")


def load_config():
    """Load persistent settings dictionary from disk."""
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_config(data):
    """Save persistent settings dictionary to disk with correct user ownership."""
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        user = get_desktop_user()
        if os.geteuid() == 0 and user and user != "root":
            import pwd
            p = pwd.getpwnam(user)
            os.chown(path, p.pw_uid, p.pw_gid)
    except Exception:
        pass


def install_polkit_policy():
    """Auto-install polkit policy so pkexec won't prompt for a password."""
    if os.geteuid() != 0:
        return
    app_dir = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(app_dir, "com.autoclicker.mouse.policy")
    dst = "/usr/share/polkit-1/actions/com.autoclicker.mouse.policy"
    if os.path.exists(src):
        try:
            import shutil
            shutil.copy2(src, dst)
            os.chmod(dst, 0o644)
        except Exception:
            pass


def install_desktop_entry():
    """Ensure the app is registered in Linux Applications / Whisker Menu."""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    icon_png = os.path.join(app_dir, "assets", "icon.png")
    user_home = f"/home/{get_desktop_user()}"

    user_icon_dir = os.path.join(user_home, ".local/share/icons")
    try:
        os.makedirs(user_icon_dir, exist_ok=True)
        for old_svg in [os.path.join(user_icon_dir, "mouse-autoclicker.svg"),
                        "/usr/share/icons/hicolor/scalable/apps/mouse-autoclicker.svg"]:
            if os.path.exists(old_svg):
                try:
                    os.remove(old_svg)
                except Exception:
                    pass

        if os.path.exists(icon_png):
            import shutil
            shutil.copy2(icon_png, os.path.join(user_icon_dir, "mouse-autoclicker.png"))
            if os.geteuid() == 0:
                os.makedirs("/usr/share/pixmaps", exist_ok=True)
                shutil.copy2(icon_png, "/usr/share/pixmaps/mouse-autoclicker.png")
                for res in ["256x256", "512x512", "scalable"]:
                    res_dir = f"/usr/share/icons/hicolor/{res}/apps"
                    os.makedirs(res_dir, exist_ok=True)
                    shutil.copy2(icon_png, os.path.join(res_dir, "mouse-autoclicker.png"))
                subprocess.run(["gtk-update-icon-cache", "-f", "-t", "/usr/share/icons/hicolor"],
                               capture_output=True)
            subprocess.run(["gtk-update-icon-cache", "-f", "-t", user_icon_dir],
                           capture_output=True)
    except Exception:
        pass

    desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Mouse AutoClicker
GenericName=Auto Clicker
Comment=Multi-Binding Auto Clicker for Linux Mint XFCE
Exec=/usr/local/bin/mouse-autoclicker
Path={app_dir}
Icon=mouse-autoclicker
Terminal=false
Categories=Utility;GTK;Settings;HardwareSettings;
Keywords=mouse;clicker;autoclicker;cps;gaming;bindings;
StartupNotify=true
"""
    targets = [
        os.path.join(user_home, ".local/share/applications/mouse-autoclicker.desktop"),
        os.path.join(app_dir, "RightClicker.desktop")
    ]
    if os.geteuid() == 0:
        targets.append("/usr/share/applications/mouse-autoclicker.desktop")

    for target in targets:
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(desktop_content)
            os.chmod(target, 0o755)
            subprocess.run(["update-desktop-database", os.path.dirname(target)],
                           capture_output=True, timeout=2)
        except Exception:
            pass


# ==============================================================================
# X11 MUTE MANAGER (Restricted solely to browser navigation buttons 8 and 9)
# ==============================================================================
def run_xinput(args):
    """Run xinput safely with desktop user's XAUTHORITY and DISPLAY."""
    user = get_desktop_user()
    display = os.environ.get("DISPLAY", ":0")
    xauth = os.environ.get("XAUTHORITY")
    if not xauth and user:
        candidate = f"/home/{user}/.Xauthority"
        if os.path.exists(candidate):
            xauth = candidate

    env = os.environ.copy()
    env["DISPLAY"] = display
    if xauth:
        env["XAUTHORITY"] = xauth

    if os.geteuid() == 0 and user and user != "root":
        cmd = ["sudo", "-u", user, "env", f"DISPLAY={display}"]
        if xauth:
            cmd.append(f"XAUTHORITY={xauth}")
        cmd += ["xinput"] + args
    else:
        cmd = ["xinput"] + args

    try:
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def xinput_ids(name):
    out = run_xinput(["list", "--id-only", name])
    ids = [int(x) for x in out.split() if x.isdigit()]
    if not ids:
        list_out = run_xinput(["list", "--short"])
        for line in list_out.splitlines():
            if "pointer" in line.lower() and name.lower() in line.lower():
                import re
                m = re.search(r"id=(\d+)", line)
                if m:
                    ids.append(int(m.group(1)))
    return ids


class ButtonMuteManager:
    """
    Manages muting X11 browser Back/Forward navigation buttons (8 & 9).
    CRITICAL: Left (1), Middle (2), and Right (3) buttons are NEVER muted
    so physical mouse clicks can NEVER be swallowed.
    """
    def __init__(self):
        self.saved_maps = {}

    def mute(self, dev_name, button_numbers):
        # Strictly filter to only 8 (Back) and 9 (Forward)
        safe_buttons = [b for b in button_numbers if b in (8, 9)]
        if not safe_buttons:
            return

        for xid in xinput_ids(dev_name):
            out = run_xinput(["get-button-map", str(xid)])
            mapping = [int(x) for x in out.split() if x.isdigit()]
            if not mapping:
                continue
            modified = False
            new_map = mapping.copy()
            for btn in safe_buttons:
                if len(new_map) >= btn:
                    if (xid, btn) not in self.saved_maps:
                        self.saved_maps[(xid, btn)] = mapping[btn - 1]
                    new_map[btn - 1] = 0
                    modified = True
            if modified:
                run_xinput(["set-button-map", str(xid)] + [str(x) for x in new_map])

    def restore_all(self):
        if not self.saved_maps:
            return
        by_xid = {}
        for (xid, btn), orig in self.saved_maps.items():
            by_xid.setdefault(xid, {})[btn] = orig

        for xid, btn_dict in by_xid.items():
            out = run_xinput(["get-button-map", str(xid)])
            mapping = [int(x) for x in out.split() if x.isdigit()]
            if mapping:
                for btn, orig in btn_dict.items():
                    if len(mapping) >= btn:
                        mapping[btn - 1] = orig
                run_xinput(["set-button-map", str(xid)] + [str(x) for x in mapping])
        self.saved_maps.clear()


# ==============================================================================
# BINDING MODEL
# ==============================================================================
class Binding:
    """Represents a single configurable mouse binding row."""
    def __init__(self, id=None, name="Binding", enabled=True, trigger="back",
                 trigger_code=None, action="left", cps=20.0, mode="hold",
                 sub_delay_ms=35):
        self.id = id or str(uuid.uuid4())[:8]
        self.name = name
        self.enabled = enabled
        self.trigger = trigger            # "left", "right", "middle", "back", "forward", or "custom_..."
        self.trigger_code = trigger_code if trigger_code is not None else trigger_key_to_code(trigger)
        if action in ("double", "double_click"):
            action = "double_left"
        self.action = action              # key in ACTION_REGISTRY
        self.cps = float(cps)
        self.mode = mode                  # "hold" or "toggle"
        self.sub_delay_ms = int(sub_delay_ms)

        # Runtime states
        self.held = threading.Event()
        self.toggle_active = False
        self.is_clicking = False
        self.total_clicks = 0
        self.detecting = False            # True when detecting next mouse press
        self.detect_start_time = 0.0      # time.monotonic() when detecting started (debounce)
        self.row_widget = None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "trigger": self.trigger,
            "trigger_code": self.trigger_code,
            "action": self.action,
            "cps": round(self.cps, 1),
            "mode": self.mode,
            "sub_delay_ms": self.sub_delay_ms,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d.get("id"),
            name=d.get("name", "Binding"),
            enabled=d.get("enabled", True),
            trigger=d.get("trigger", "back"),
            trigger_code=d.get("trigger_code"),
            action=d.get("action", "left"),
            cps=float(d.get("cps", 20.0)),
            mode=d.get("mode", "hold"),
            sub_delay_ms=int(d.get("sub_delay_ms", 35)),
        )


# ==============================================================================
# CORE CLICK ENGINE
# ==============================================================================
class AutoClickerCore:
    def __init__(self):
        saved = load_config()
        self.master_enabled = saved.get("master_enabled", True)
        self.hotkey = saved.get("hotkey", "F6")
        self.jitter = float(saved.get("jitter", 0.0))
        self.mute_nav = saved.get("mute_nav", True)
        self.mimic = saved.get("mimic", False)
        self.running = True

        # Load or migrate bindings
        self.bindings = []
        if "bindings" in saved and isinstance(saved["bindings"], list) and len(saved["bindings"]) > 0:
            for b_dict in saved["bindings"]:
                self.bindings.append(Binding.from_dict(b_dict))
        else:
            # Backward-compatibility migration: load from old back/forward format
            back_saved = saved.get("back", {})
            fwd_saved = saved.get("forward", {})
            b1 = Binding(
                name="Back (Thumb) Button",
                enabled=back_saved.get("enabled", True),
                trigger="back",
                action=back_saved.get("action", "right"),
                cps=float(back_saved.get("cps", 90.0)),
                mode="hold"
            )
            b2 = Binding(
                name="Forward Button",
                enabled=fwd_saved.get("enabled", True),
                trigger="forward",
                action=fwd_saved.get("action", "left"),
                cps=float(fwd_saved.get("cps", 40.0)),
                mode="hold"
            )
            self.bindings = [b1, b2]

        self.ui = None
        self.uinput_lock = threading.Lock()
        self.mice = []
        self.keyboards = []
        self.watchers = []
        self.worker_threads = {}
        self.mute_mgr = ButtonMuteManager()

        self.on_state_change = None
        self.on_device_update = None
        self.lock = threading.Lock()

    def init_uinput(self):
        if not EVDEV_AVAILABLE or e is None:
            return False
        try:
            cap = {
                e.EV_KEY: [
                    e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE,
                    e.BTN_SIDE, e.BTN_EXTRA, e.BTN_FORWARD, e.BTN_BACK
                ],
                e.EV_REL: [
                    e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL
                ],
            }
            name = "autoclicker-virtual"
            kwargs = {}
            if self.mimic and self.mice:
                try:
                    first = self.mice[0]
                    info = first.info
                    name = first.name
                    kwargs = dict(vendor=info.vendor, product=info.product,
                                  version=info.version, bustype=info.bustype)
                except Exception:
                    kwargs = {}

            with self.uinput_lock:
                if self.ui is not None:
                    try:
                        self.ui.close()
                    except Exception:
                        pass
                self.ui = UInput(cap, name=name, **kwargs)
            return True
        except Exception as ex:
            print(f"[AutoClicker] uinput init failed: {ex}")
            with self.uinput_lock:
                self.ui = None
            return False

    def rescan_devices(self):
        if not EVDEV_AVAILABLE or e is None:
            return []
        found_mice = []
        found_kbs = []
        try:
            for path in evdev.list_devices():
                try:
                    d = evdev.InputDevice(path)
                    keys = d.capabilities().get(e.EV_KEY, [])
                    # Mouse check
                    if e.BTN_LEFT in keys and "autoclicker-virtual" not in d.name and "back-rightclick" not in d.name:
                        found_mice.append(d)
                    # Keyboard check (for system-wide hotkey listening)
                    if (e.KEY_F6 in keys or e.KEY_A in keys) and "autoclicker-virtual" not in d.name:
                        found_kbs.append(d)
                except Exception:
                    continue
        except Exception:
            pass

        self.mice = found_mice
        self.keyboards = found_kbs
        if self.on_device_update:
            GLib.idle_add(self.on_device_update, [m.name for m in self.mice])
        return self.mice

    def start(self):
        self.rescan_devices()
        self.init_uinput()
        self.update_mutes()

        # Start worker thread for each binding
        for b in self.bindings:
            self._ensure_worker_for_binding(b)

        self._start_watchers()

    def _ensure_worker_for_binding(self, binding):
        with self.lock:
            if binding.id in self.worker_threads:
                return
            t = threading.Thread(target=self._worker_loop, args=(binding,), daemon=True)
            self.worker_threads[binding.id] = t
            t.start()

    def update_mutes(self):
        self.mute_mgr.restore_all()
        if not self.master_enabled or not self.mute_nav:
            return

        # ONLY mute buttons 8 and 9 if they are used as triggers AND their action is NOT navigation
        active_x_buttons = []
        with self.lock:
            for b in self.bindings:
                if b.enabled and b.trigger in ["back", "forward"]:
                    if b.action not in ["back", "forward"]:
                        x_btn = 8 if b.trigger == "back" else 9
                        if x_btn not in active_x_buttons:
                            active_x_buttons.append(x_btn)

        if active_x_buttons:
            for m in self.mice:
                self.mute_mgr.mute(m.name, active_x_buttons)

    def _start_watchers(self):
        self.watchers.clear()
        # Watch mouse devices
        for d in self.mice:
            t = threading.Thread(target=self._watch_mouse_device, args=(d.path,), daemon=True)
            t.start()
            self.watchers.append(t)
        # Watch keyboard devices for hotkey (evdev — works below X11, survives game grabs)
        for d in self.keyboards:
            t = threading.Thread(target=self._watch_keyboard_device, args=(d.path,), daemon=True)
            t.start()
            self.watchers.append(t)
        # Fallback: pynput X11 global hotkey listener (works when window is unfocused)
        self._start_pynput_hotkey_listener()

    def _watch_mouse_device(self, path):
        try:
            dev = evdev.InputDevice(path)
            # Read loop WITHOUT dev.grab() so mouse clicks are NEVER swallowed
            for ev in dev.read_loop():
                if not self.running:
                    break
                if ev.type == e.EV_KEY:
                    # 1. Check if any binding is in "Detect" mode
                    detecting_binding = None
                    with self.lock:
                        for b in self.bindings:
                            if b.detecting and ev.value == 1:
                                # Debounce: ignore events within 300 ms of detect mode starting
                                # so the click that opened detect mode does not self-capture
                                if time.monotonic() - b.detect_start_time < 0.3:
                                    break
                                detecting_binding = b
                                break

                    if detecting_binding:
                        with self.lock:
                            detecting_binding.trigger_code = ev.code
                            detecting_binding.trigger = code_to_trigger_key(ev.code)
                            detecting_binding.detecting = False
                        if self.on_state_change:
                            GLib.idle_add(self.on_state_change)
                        continue

                    # 2. Normal trigger checking
                    with self.lock:
                        master_ok = self.master_enabled
                        bindings_list = list(self.bindings)

                    for b in bindings_list:
                        if not b.enabled:
                            continue
                        if ev.code == b.trigger_code:
                            if b.mode == "hold":
                                if ev.value == 1 and master_ok:
                                    b.held.set()
                                elif ev.value == 0:
                                    b.held.clear()
                            elif b.mode == "toggle":
                                if ev.value == 1 and master_ok:
                                    b.toggle_active = not b.toggle_active
                                    if b.toggle_active:
                                        b.held.set()
                                    else:
                                        b.held.clear()
                                    if self.on_state_change:
                                        GLib.idle_add(self.on_state_change)
        except Exception:
            pass
        finally:
            with self.lock:
                for b in self.bindings:
                    b.held.clear()

    def _watch_keyboard_device(self, path):
        """Watch a keyboard device for the global hotkey. Auto-restarts on error (e.g. game grabbing device)."""
        import time as _time
        while self.running:
            try:
                dev = evdev.InputDevice(path)
                for ev in dev.read_loop():
                    if not self.running:
                        return
                    if ev.type == e.EV_KEY and ev.value == 1:
                        key_str = self._evdev_code_to_key_str(ev.code)
                        if key_str and key_str.upper() == self.hotkey.upper():
                            self.toggle_master()
            except Exception:
                # Device temporarily unavailable (e.g. game grabbed it) — wait and retry
                if not self.running:
                    return
                _time.sleep(2.0)

    def _evdev_code_to_key_str(self, code):
        if not EVDEV_AVAILABLE or e is None:
            return None
        name = e.KEY.get(code)
        if isinstance(name, list):
            name = name[0]
        if name and name.startswith("KEY_"):
            return name[4:]
        return name

    def _start_pynput_hotkey_listener(self):
        """Start a pynput global keyboard listener as a fallback hotkey mechanism.

        This catches keypresses via X11 even when evdev watchers are blocked (e.g. game
        has grabbed the device). It runs in its own daemon thread and self-restarts on error.
        """
        def _listener_loop():
            import time as _time
            while self.running:
                try:
                    from pynput import keyboard as _kb

                    _hotkey_map = {
                        "F1": _kb.Key.f1, "F2": _kb.Key.f2, "F3": _kb.Key.f3,
                        "F4": _kb.Key.f4, "F5": _kb.Key.f5, "F6": _kb.Key.f6,
                        "F7": _kb.Key.f7, "F8": _kb.Key.f8, "F9": _kb.Key.f9,
                        "F10": _kb.Key.f10, "F11": _kb.Key.f11, "F12": _kb.Key.f12,
                    }

                    def _on_press(key):
                        if not self.running:
                            return False  # stop listener
                        target = _hotkey_map.get(self.hotkey.upper())
                        if target is not None and key == target:
                            self.toggle_master()
                        elif hasattr(key, 'char') and key.char and key.char.upper() == self.hotkey.upper():
                            self.toggle_master()

                    with _kb.Listener(on_press=_on_press) as listener:
                        listener.join()
                except Exception:
                    if not self.running:
                        return
                    _time.sleep(3.0)

        t = threading.Thread(target=_listener_loop, daemon=True)
        t.start()
        self.watchers.append(t)

    def toggle_master(self):
        """Toggle master Start/Stop state system-wide."""
        with self.lock:
            self.master_enabled = not self.master_enabled
            if not self.master_enabled:
                for b in self.bindings:
                    b.held.clear()
                    b.toggle_active = False
                    b.is_clicking = False
                    # Release any held buttons
                    if b.action == "hold_down":
                        act_def = get_action_by_key(b.action)
                        with self.uinput_lock:
                            if self.ui and act_def.code:
                                self.ui.write(e.EV_KEY, act_def.code, 0)
                                self.ui.syn()

        self.update_mutes()
        if self.on_state_change:
            GLib.idle_add(self.on_state_change)

    def _deadline_sleep(self, deadline):
        """High-precision sleep using hybrid sleep+busy-wait to hit a perf_counter deadline."""
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > 0.003:
            time.sleep(remaining - 0.002)
        while time.perf_counter() < deadline:
            pass

    def _worker_loop(self, binding):
        """Dedicated worker thread for an individual binding."""
        holding_active = False

        while self.running:
            binding.held.wait(timeout=0.1)
            if not self.running:
                break

            cycle_start = time.perf_counter()

            while (binding.held.is_set() and self.running and
                   self.master_enabled and binding.enabled):

                with self.lock:
                    cps = binding.cps
                    act_key = binding.action
                    sub_delay_ms = binding.sub_delay_ms
                    jitter = self.jitter

                act_def = get_action_by_key(act_key)
                interval = 1.0 / max(cps, 1.0)

                if jitter > 0:
                    var = random.uniform(-jitter, jitter)
                    interval = max(0.008, interval * (1.0 + var))

                cycle_end = cycle_start + interval

                with self.uinput_lock:
                    ui_ready = self.ui is not None

                if not ui_ready:
                    time.sleep(0.05)
                    cycle_start = time.perf_counter()
                    continue

                try:
                    # 1. HOLD DOWN / 1:1 NORMAL REMAP ACTION (Instant 2ms response)
                    if act_def.category == "hold":
                        if not holding_active:
                            with self.uinput_lock:
                                self.ui.write(e.EV_KEY, act_def.code, 1)
                                self.ui.syn()
                            holding_active = True
                            binding.is_clicking = True
                            binding.total_clicks += 1
                            if self.on_state_change:
                                GLib.idle_add(self.on_state_change)
                        time.sleep(0.002)

                    # 2. SCROLL ACTIONS
                    elif act_def.category == "scroll":
                        with self.uinput_lock:
                            self.ui.write(e.EV_REL, e.REL_WHEEL, act_def.scroll_delta)
                            self.ui.syn()
                        binding.is_clicking = True
                        binding.total_clicks += 1
                        if self.on_state_change:
                            GLib.idle_add(self.on_state_change)
                        self._deadline_sleep(cycle_end)

                    # 3. BURST ACTIONS (Double / Triple Click)
                    elif act_def.category == "burst":
                        burst_n = act_def.burst_count
                        sub_delay = max(0.005, sub_delay_ms / 1000.0)
                        down_dur = min(0.012, max(0.005, interval * 0.15))

                        for i in range(burst_n):
                            # Click Down
                            with self.uinput_lock:
                                self.ui.write(e.EV_KEY, act_def.code, 1)
                                self.ui.syn()
                            binding.total_clicks += 1
                            binding.is_clicking = True
                            if self.on_state_change:
                                GLib.idle_add(self.on_state_change)

                            self._deadline_sleep(time.perf_counter() + down_dur)

                            # Click Up
                            with self.uinput_lock:
                                if self.ui is not None:
                                    self.ui.write(e.EV_KEY, act_def.code, 0)
                                    self.ui.syn()

                            if i < burst_n - 1:
                                self._deadline_sleep(time.perf_counter() + sub_delay)

                        self._deadline_sleep(cycle_end)

                    # 4. STANDARD SINGLE CLICK (Left, Right, Middle, Back, Forward)
                    else:
                        press_duration = max(0.005, min(0.025, interval * 0.40))
                        press_deadline = cycle_start + press_duration

                        # Down
                        with self.uinput_lock:
                            self.ui.write(e.EV_KEY, act_def.code, 1)
                            self.ui.syn()
                        binding.total_clicks += 1
                        binding.is_clicking = True
                        if self.on_state_change:
                            GLib.idle_add(self.on_state_change)

                        self._deadline_sleep(press_deadline)

                        # Up
                        with self.uinput_lock:
                            if self.ui is not None:
                                self.ui.write(e.EV_KEY, act_def.code, 0)
                                self.ui.syn()

                        self._deadline_sleep(cycle_end)

                except Exception:
                    time.sleep(0.005)

                cycle_start = cycle_end

            # When exiting active clicking
            if holding_active:
                act_def = get_action_by_key(binding.action)
                with self.uinput_lock:
                    if self.ui and act_def.code:
                        self.ui.write(e.EV_KEY, act_def.code, 0)
                        self.ui.syn()
                holding_active = False

            if binding.is_clicking:
                binding.is_clicking = False
                if self.on_state_change:
                    GLib.idle_add(self.on_state_change)

    def add_binding(self):
        """Add a new binding and start its worker thread."""
        new_b = Binding(
            name=f"Binding #{len(self.bindings) + 1}",
            enabled=True,
            trigger="back",
            action="left",
            cps=25.0,
            mode="hold"
        )
        with self.lock:
            self.bindings.append(new_b)
        self._ensure_worker_for_binding(new_b)
        self.update_mutes()
        return new_b

    def remove_binding(self, binding):
        """Remove a binding from list and clean its states."""
        with self.lock:
            if binding in self.bindings:
                binding.held.clear()
                binding.toggle_active = False
                binding.enabled = False
                self.bindings.remove(binding)
        self.update_mutes()

    def stop(self):
        self.running = False
        with self.lock:
            for b in self.bindings:
                b.held.clear()
        self.mute_mgr.restore_all()
        with self.uinput_lock:
            if self.ui:
                try:
                    self.ui.close()
                except Exception:
                    pass


# ==============================================================================
# GTK3 MAIN APPLICATION WINDOW
# ==============================================================================
class AutoClickerWindow(Gtk.Window):
    def __init__(self, core):
        super().__init__(title="Mouse AutoClicker")
        self.core = core
        self.saved_config = load_config()
        self.core.on_state_change = self._on_core_state_change
        self.core.on_device_update = self._on_core_device_update

        # Clean window sizing
        self.set_default_size(650, 640)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(True)
        self.set_border_width(10)
        self.get_style_context().add_class("main-window")

        # Set Window Icon — prefer custom Neon Icon PNG
        app_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path_png = os.path.join(app_dir, "assets", "icon.png")
        icon_loaded = False
        if os.path.exists(icon_path_png):
            try:
                from gi.repository import GdkPixbuf
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path_png, 64, 64, True)
                self.set_icon(pixbuf)
                icon_loaded = True
            except Exception:
                pass
        if not icon_loaded:
            self.set_icon_name("input-mouse")

        # Apply Dark Theme CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS_STYLES)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(screen, provider,
                                                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.connect("destroy", self._on_close)
        self.connect("key-press-event", self._on_window_key_press)

        # Main Layout Box
        window_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(window_vbox)

        # 1. Header Card (Title, Start/Stop Switch, Hotkey)
        window_vbox.pack_start(self._build_header(), False, False, 0)

        # 1.5 Permission warning banner
        self.warning_box = self._build_permission_card()
        window_vbox.pack_start(self.warning_box, False, False, 0)

        # 2. Action Toolbar ("+ Add Binding" button)
        window_vbox.pack_start(self._build_toolbar(), False, False, 0)

        # 2.5 Table Column Header
        window_vbox.pack_start(self._build_table_header(), False, False, 0)

        # 3. Scrollable Bindings List (Table Rows)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_shadow_type(Gtk.ShadowType.NONE)
        window_vbox.pack_start(self.scrolled_window, True, True, 0)

        self.bindings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.bindings_box.get_style_context().add_class("table-container")
        self.scrolled_window.add(self.bindings_box)

        # Populate initial bindings
        self._rebuild_bindings_list()

        # 4. Advanced Settings Expander (Mute browser nav, Jitter, Hardware Mimic, Click Tester)
        window_vbox.pack_start(self._build_advanced_expander(), False, False, 0)

        # 5. Status Bar at Bottom
        window_vbox.pack_end(self._build_status_bar(), False, False, 0)

        # Start Core Engine
        self.core.start()
        install_desktop_entry()
        install_polkit_policy()

    def _prevent_scale_scroll(self, widget, event):
        """Prevent mouse wheel from altering slider values, delegating to scrolled window."""
        if hasattr(self, "scrolled_window") and self.scrolled_window:
            self.scrolled_window.emit("scroll-event", event)
        return True

    def _on_window_key_press(self, widget, event):
        """Handle window-focused hotkey presses."""
        keyval = event.keyval
        key_name = Gdk.keyval_name(keyval)
        if key_name and key_name.upper() == self.core.hotkey.upper():
            self.core.toggle_master()
            return True
        return False

    def _build_header(self):
        header_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_card.get_style_context().add_class("card")

        # Title Block
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label="Mouse AutoClicker", xalign=0)
        title.get_style_context().add_class("app-title")
        subtitle = Gtk.Label(label="Multi-Binding Automation • Linux Mint XFCE", xalign=0)
        subtitle.get_style_context().add_class("app-subtitle")
        vbox.pack_start(title, False, False, 0)
        vbox.pack_start(subtitle, False, False, 0)
        header_card.pack_start(vbox, True, True, 0)

        # Hotkey badge button
        self.hotkey_btn = Gtk.Button(label=f"Hotkey: {self.core.hotkey}")
        self.hotkey_btn.get_style_context().add_class("hotkey-badge")
        self.hotkey_btn.connect("clicked", self._on_change_hotkey_clicked)
        header_card.pack_end(self.hotkey_btn, False, False, 0)

        # Global Master Start/Stop Switch
        if self.core.master_enabled:
            self.master_btn = Gtk.Button(label="● RUNNING")
            self.master_btn.get_style_context().add_class("master-btn-active")
        else:
            self.master_btn = Gtk.Button(label="○ PAUSED")
            self.master_btn.get_style_context().add_class("master-btn-paused")
        self.master_btn.connect("clicked", lambda _: self.core.toggle_master())
        header_card.pack_end(self.master_btn, False, False, 0)

        return header_card

    def _on_change_hotkey_clicked(self, widget):
        dialog = Gtk.Dialog(
            title="Set Global Hotkey",
            parent=self,
            flags=0,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        )
        dialog.set_default_size(280, 140)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        lbl = Gtk.Label(label="Select global trigger key for Master Start/Stop:")
        box.pack_start(lbl, False, False, 0)

        combo = Gtk.ComboBoxText()
        hotkeys = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
                   "Pause", "ScrollLock", "Insert", "Delete"]
        for hk in hotkeys:
            combo.append_text(hk)
        if self.core.hotkey in hotkeys:
            combo.set_active(hotkeys.index(self.core.hotkey))
        else:
            combo.append_text(self.core.hotkey)
            combo.set_active(len(hotkeys))
        box.pack_start(combo, False, False, 4)

        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            chosen = combo.get_active_text()
            if chosen:
                self.core.hotkey = chosen
                self.hotkey_btn.set_label(f"Hotkey: {chosen}")
                self._update_status_bar()
                self._save_current_settings()
        dialog.destroy()

    def _build_permission_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("card")
        card.set_no_show_all(True)

        title = Gtk.Label(label="⚠️ Root Privileges Required", xalign=0)
        title.get_style_context().add_class("card-title")
        body = Gtk.Label(xalign=0)
        body.set_line_wrap(True)
        body.set_markup("<small>Linux requires root permissions to read hardware mouse events.</small>")

        relaunch_btn = Gtk.Button(label="Relaunch with Root")
        relaunch_btn.get_style_context().add_class("btn-primary")
        relaunch_btn.connect("clicked", self._on_relaunch_root)

        card.pack_start(title, False, False, 0)
        card.pack_start(body, False, False, 0)
        card.pack_start(relaunch_btn, False, False, 2)
        return card

    def _check_permissions(self):
        has_root = (os.geteuid() == 0)
        has_uinput = os.access("/dev/uinput", os.W_OK)
        if has_root or has_uinput:
            self.warning_box.set_visible(False)
        else:
            self.warning_box.set_visible(True)

    def _on_relaunch_root(self, widget):
        cmd = ["/usr/local/bin/mouse-autoclicker"] if os.path.exists("/usr/local/bin/mouse-autoclicker") else ["pkexec", "/usr/bin/python3", os.path.abspath(sys.argv[0])]
        try:
            subprocess.Popen(cmd)
            Gtk.main_quit()
        except Exception as e:
            dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, f"Could not launch: {e}")
            dialog.run()
            dialog.destroy()

    def _build_toolbar(self):
        tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label="MOUSE BINDINGS", xalign=0)
        lbl.get_style_context().add_class("card-title")
        tb.pack_start(lbl, True, True, 0)

        # "Save Changes" Button
        self.save_btn = Gtk.Button(label="Save Changes")
        self.save_btn.get_style_context().add_class("btn-save")
        self.save_btn.set_tooltip_text("Save all bindings and configuration immediately to disk")
        self.save_btn.connect("clicked", self._on_save_clicked)
        tb.pack_end(self.save_btn, False, False, 0)

        # "+ Add Binding" Button
        add_btn = Gtk.Button(label="+ Add Binding")
        add_btn.get_style_context().add_class("btn-primary")
        add_btn.connect("clicked", self._on_add_binding_clicked)
        tb.pack_end(add_btn, False, False, 0)

        return tb

    def _get_current_state_snapshot(self):
        """Return a comparable snapshot of all saveable state."""
        adv_expanded = False
        if hasattr(self, "expander") and self.expander:
            adv_expanded = self.expander.get_expanded()
        return {
            "master_enabled": self.core.master_enabled,
            "hotkey": self.core.hotkey,
            "mute_nav": self.core.mute_nav,
            "jitter": round(self.core.jitter, 3),
            "mimic": self.core.mimic,
            "advanced_expanded": adv_expanded,
            "bindings": [b.to_dict() for b in self.core.bindings],
        }

    def _mark_saved_snapshot(self):
        """Take a snapshot of the current state as 'saved baseline'."""
        self._saved_snapshot = self._get_current_state_snapshot()

    def _is_dirty(self):
        """Return True if current state differs from the last saved snapshot."""
        if not hasattr(self, "_saved_snapshot"):
            return True
        return self._get_current_state_snapshot() != self._saved_snapshot

    def _update_save_btn_state(self):
        """Enable or disable the save button based on dirty state."""
        if not hasattr(self, "save_btn"):
            return
        ctx = self.save_btn.get_style_context()
        if self._is_dirty():
            self.save_btn.set_sensitive(True)
            self.save_btn.set_label("Save Changes")
            ctx.remove_class("btn-save-disabled")
            ctx.remove_class("btn-saved")
            ctx.add_class("btn-save")
        else:
            self.save_btn.set_sensitive(False)
            self.save_btn.set_label("Saved")
            ctx.remove_class("btn-save")
            ctx.remove_class("btn-saved")
            ctx.add_class("btn-save-disabled")

    def _on_save_clicked(self, widget):
        self._save_current_settings()
        self._mark_saved_snapshot()
        widget.set_label("✓ Saved!")
        ctx = widget.get_style_context()
        ctx.remove_class("btn-save")
        ctx.add_class("btn-saved")
        GLib.timeout_add(1200, self._reset_save_btn_after_save, widget)

    def _reset_save_btn_after_save(self, widget):
        """After the brief '✓ Saved!' flash, switch to disabled gray since we just saved."""
        ctx = widget.get_style_context()
        ctx.remove_class("btn-saved")
        ctx.remove_class("btn-save")
        ctx.add_class("btn-save-disabled")
        widget.set_label("Saved")
        widget.set_sensitive(False)
        return False

    def _reset_save_btn(self, widget):
        widget.set_label("Save Changes")
        widget.get_style_context().remove_class("btn-saved")
        return False

    def _on_add_binding_clicked(self, widget):
        new_b = self.core.add_binding()
        row = self._create_binding_row(new_b)
        self.bindings_box.pack_start(row, False, False, 0)
        row.show_all()
        self._update_status_bar()
        # Adding a binding is immediately saved (structural change), then snapshot
        self._save_current_settings()
        self._mark_saved_snapshot()
        self._update_save_btn_state()

    def _rebuild_bindings_list(self):
        for child in self.bindings_box.get_children():
            self.bindings_box.remove(child)

        for b in self.core.bindings:
            row = self._create_binding_row(b)
            self.bindings_box.pack_start(row, False, False, 0)

        self.bindings_box.show_all()

    def _build_table_header(self):
        """No column headers needed — card layout is self-labelled."""
        return Gtk.Box()  # empty placeholder, kept so callers don't break

    def _create_binding_row(self, binding):
        """Card layout: trigger button | type pills | button pills | mode pills | status/delete"""

        # ── Action key helpers ────────────────────────────────────────────────
        # type pill keys
        TYPE_DOUBLE = "double"
        TYPE_AUTO   = "auto"
        TYPE_REMAP  = "remap"

        # button pill keys
        BTN_LEFT  = "left"
        BTN_RIGHT = "right"

        # Map (type, button) → actual action key
        ACTION_MAP = {
            (TYPE_DOUBLE, BTN_LEFT):  "double_left",
            (TYPE_DOUBLE, BTN_RIGHT): "double_right",
            (TYPE_AUTO,   BTN_LEFT):  "left",
            (TYPE_AUTO,   BTN_RIGHT): "right",
            (TYPE_REMAP,  BTN_LEFT):  "remap_left",
            (TYPE_REMAP,  BTN_RIGHT): "remap_right",
        }
        REVERSE_MAP = {v: k for k, v in ACTION_MAP.items()}

        def _action_to_type_btn(key):
            return REVERSE_MAP.get(key, (TYPE_AUTO, BTN_LEFT))

        # Outer card — vertical stack
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("binding-card")
        binding.row_widget = card

        # ── Top row ───────────────────────────────────────────────────────────
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.pack_start(top, False, False, 0)

        # 1. Trigger big button
        trig_label = get_trigger_label(binding.trigger, binding.trigger_code)
        trig_btn = Gtk.Button(label=f"🖱  {trig_label}")
        trig_btn.get_style_context().add_class("trigger-btn")
        trig_btn.set_size_request(150, 34)
        trig_btn.set_tooltip_text("Click to detect — then press any mouse button")
        binding.detect_btn = trig_btn
        binding.trigger_combo = None

        def _on_trig_btn_clicked(btn, b=binding):
            b.detecting = not b.detecting
            if b.detecting:
                b.detect_start_time = time.monotonic()
                btn.set_label("⬤  Press any button…")
                btn.get_style_context().remove_class("trigger-btn")
                btn.get_style_context().add_class("trigger-btn-detecting")
                GLib.timeout_add(50, lambda: btn.set_sensitive(False))
            else:
                lbl = get_trigger_label(b.trigger, b.trigger_code)
                btn.set_label(f"🖱  {lbl}")
                btn.get_style_context().remove_class("trigger-btn-detecting")
                btn.get_style_context().add_class("trigger-btn")

        trig_btn.connect("clicked", _on_trig_btn_clicked)
        top.pack_start(trig_btn, False, False, 0)

        sep0 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        top.pack_start(sep0, False, False, 0)

        # 2. Type pills: Double Click | Auto Click | 1:1 Remap
        cur_type, cur_btn_side = _action_to_type_btn(binding.action)

        type_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_type = Gtk.Label(label="TYPE", xalign=0)
        lbl_type.get_style_context().add_class("card-section-label")
        type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        type_col.pack_start(lbl_type, False, False, 0)
        type_col.pack_start(type_box, False, False, 0)
        top.pack_start(type_col, False, False, 0)

        TYPE_PILLS = [
            ("⚡  Double",  TYPE_DOUBLE, "Sends 2 clicks per trigger — great for Minecraft PVP"),
            ("🖱  Auto",    TYPE_AUTO,   "Rapid-fires clicks while held"),
            ("🔀  Remap",   TYPE_REMAP,  "Makes this button act exactly like another button — 1:1, no auto-fire"),
        ]
        type_pill_btns = {}

        def _set_type_pill(active):
            for k, b2 in type_pill_btns.items():
                ctx = b2.get_style_context()
                ctx.remove_class("action-pill"); ctx.remove_class("action-pill-active")
                ctx.add_class("action-pill-active" if k == active else "action-pill")

        def _on_type_pill(t_key, b=binding):
            nonlocal cur_type
            cur_type = t_key
            new_action = ACTION_MAP.get((cur_type, cur_btn_side), "left")
            b.action = new_action
            _set_type_pill(t_key)
            _update_speed_row(new_action)
            _update_mode_sensitivity(new_action)
            self.core.update_mutes()
            self._update_save_btn_state()

        for pill_lbl, pill_key, tip in TYPE_PILLS:
            btn = Gtk.Button(label=pill_lbl)
            btn.set_tooltip_text(tip)
            btn.get_style_context().add_class(
                "action-pill-active" if pill_key == cur_type else "action-pill"
            )
            btn.connect("clicked", lambda w, k=pill_key: _on_type_pill(k))
            type_pill_btns[pill_key] = btn
            type_box.pack_start(btn, False, False, 0)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        top.pack_start(sep1, False, False, 0)

        # 3. Button pills: Left | Right
        btn_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_btn_side = Gtk.Label(label="BUTTON", xalign=0)
        lbl_btn_side.get_style_context().add_class("card-section-label")
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_col.pack_start(lbl_btn_side, False, False, 0)
        btn_col.pack_start(btn_box, False, False, 0)
        top.pack_start(btn_col, False, False, 0)

        BTN_PILLS = [
            ("Left",  BTN_LEFT),
            ("Right", BTN_RIGHT),
        ]
        btn_pill_btns = {}

        def _set_btn_pill(active):
            for k, b2 in btn_pill_btns.items():
                ctx = b2.get_style_context()
                ctx.remove_class("action-pill"); ctx.remove_class("action-pill-active")
                ctx.add_class("action-pill-active" if k == active else "action-pill")

        def _on_btn_pill(side_key, b=binding):
            nonlocal cur_btn_side
            cur_btn_side = side_key
            new_action = ACTION_MAP.get((cur_type, cur_btn_side), "left")
            b.action = new_action
            _set_btn_pill(side_key)
            _update_speed_row(new_action)
            self.core.update_mutes()
            self._update_save_btn_state()

        for pill_lbl, pill_key in BTN_PILLS:
            btn = Gtk.Button(label=pill_lbl)
            btn.get_style_context().add_class(
                "action-pill-active" if pill_key == cur_btn_side else "action-pill"
            )
            btn.connect("clicked", lambda w, k=pill_key: _on_btn_pill(k))
            btn_pill_btns[pill_key] = btn
            btn_box.pack_start(btn, False, False, 0)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        top.pack_start(sep2, False, False, 0)

        # 4. Mode pills: PVP (Hold) | AFK (Toggle)
        mode_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_mode = Gtk.Label(label="ACTIVATION", xalign=0)
        lbl_mode.get_style_context().add_class("card-section-label")
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mode_col.pack_start(lbl_mode, False, False, 0)
        mode_col.pack_start(mode_box, False, False, 0)
        top.pack_start(mode_col, False, False, 0)

        MODE_PILLS = [
            ("⚔  PVP",    "hold",   "Clicks only while you hold the button"),
            ("🤖  AFK",   "toggle", "Press once to start, press again to stop"),
        ]
        mode_pill_btns = {}

        def _set_mode_pill(active):
            for m, b2 in mode_pill_btns.items():
                ctx = b2.get_style_context()
                ctx.remove_class("mode-pill"); ctx.remove_class("mode-pill-active")
                ctx.add_class("mode-pill-active" if m == active else "mode-pill")

        def _on_mode_pill(mode, b=binding):
            b.mode = mode
            b.held.clear()
            b.toggle_active = False
            _set_mode_pill(mode)
            self._update_save_btn_state()

        def _update_mode_sensitivity(action_key):
            # Remap is always hold-mode — hide AFK pill
            is_remap = get_action_by_key(action_key).category == "hold"
            for m, b2 in mode_pill_btns.items():
                b2.set_sensitive(not is_remap)
            if is_remap:
                _set_mode_pill("hold")

        for pill_lbl, pill_mode, tip in MODE_PILLS:
            btn = Gtk.Button(label=pill_lbl)
            btn.set_tooltip_text(tip)
            btn.get_style_context().add_class(
                "mode-pill-active" if pill_mode == binding.mode else "mode-pill"
            )
            btn.connect("clicked", lambda w, m=pill_mode: _on_mode_pill(m))
            mode_pill_btns[pill_mode] = btn
            mode_box.pack_start(btn, False, False, 0)

        # 5. Status dot + delete — right-aligned
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top.pack_end(right_box, False, False, 0)

        live_badge = Gtk.Label(label="●")
        live_badge.get_style_context().add_class("badge-idle")
        live_badge.set_tooltip_text("Status: Idle")
        binding.badge_widget = live_badge
        right_box.pack_start(live_badge, False, False, 0)

        del_btn = Gtk.Button(label="✕")
        del_btn.set_size_request(22, 22)
        del_btn.get_style_context().add_class("btn-danger")
        del_btn.set_tooltip_text("Remove this binding")
        del_btn.connect("clicked", lambda _: self._on_delete_binding_clicked(binding, card))
        right_box.pack_start(del_btn, False, False, 0)

        # ── Bottom row: speed slider (hidden for Remap) ───────────────────────
        speed_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.pack_start(speed_row, False, False, 0)

        # Descriptive label — updates based on selected type
        spd_desc_lbl = Gtk.Label(xalign=0)
        spd_desc_lbl.get_style_context().add_class("speed-label")
        speed_row.pack_start(spd_desc_lbl, False, False, 0)

        slider_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        speed_row.pack_start(slider_row, False, False, 0)

        lbl_slow = Gtk.Label(label="Slow")
        lbl_slow.get_style_context().add_class("speed-label")
        slider_row.pack_start(lbl_slow, False, False, 0)

        spd_adj = Gtk.Adjustment(value=min(binding.cps, 150.0),
                                 lower=1.0, upper=150.0,
                                 step_increment=1.0, page_increment=5.0)
        spd_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=spd_adj)
        spd_scale.set_draw_value(True)
        spd_scale.set_digits(0)
        spd_scale.set_hexpand(True)
        spd_scale.set_value_pos(Gtk.PositionType.TOP)
        spd_scale.connect("scroll-event", self._prevent_scale_scroll)
        spd_scale.add_mark(30,  Gtk.PositionType.BOTTOM, None)
        spd_scale.add_mark(75,  Gtk.PositionType.BOTTOM, None)
        spd_scale.add_mark(150, Gtk.PositionType.BOTTOM, None)

        def _on_speed_changed(scale, b=binding):
            b.cps = scale.get_value()
            self._update_save_btn_state()

        spd_scale.connect("value-changed", _on_speed_changed)
        slider_row.pack_start(spd_scale, True, True, 0)

        lbl_fast = Gtk.Label(label="Fast")
        lbl_fast.get_style_context().add_class("speed-label")
        slider_row.pack_start(lbl_fast, False, False, 0)

        def _update_speed_row(action_key):
            act_def = get_action_by_key(action_key)
            is_remap = act_def.category == "hold"
            is_double = act_def.category == "burst"
            speed_row.set_visible(not is_remap)
            gap_row.set_visible(is_double)
            if is_double:
                cps = int(spd_adj.get_value())
                spd_desc_lbl.set_text(
                    f"Speed — {cps} double-clicks/sec  ({cps * 2} total hits/sec on enemy)"
                )
                def _live_update_double(scale):
                    v = int(scale.get_value())
                    spd_desc_lbl.set_text(
                        f"Speed — {v} double-clicks/sec  ({v * 2} total hits/sec on enemy)"
                    )
                spd_scale.connect("value-changed", _live_update_double)
            else:
                spd_desc_lbl.set_text("Speed — clicks per second (CPS)")

        # ── Gap row: only shown for Double Click ──────────────────────────────
        gap_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.pack_start(gap_row, False, False, 0)

        gap_lbl = Gtk.Label(xalign=0)
        gap_lbl.get_style_context().add_class("speed-label")
        gap_row.pack_start(gap_lbl, False, False, 0)

        gap_lbl_slow = Gtk.Label(label="Tight")
        gap_lbl_slow.get_style_context().add_class("speed-label")
        gap_row.pack_start(gap_lbl_slow, False, False, 0)

        gap_adj = Gtk.Adjustment(value=float(binding.sub_delay_ms),
                                 lower=5.0, upper=150.0,
                                 step_increment=5.0, page_increment=10.0)
        gap_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=gap_adj)
        gap_scale.set_draw_value(True)
        gap_scale.set_digits(0)
        gap_scale.set_hexpand(True)
        gap_scale.set_value_pos(Gtk.PositionType.TOP)
        gap_scale.connect("scroll-event", self._prevent_scale_scroll)
        # Tick marks: safe minimum for Minecraft, recommended, loose
        gap_scale.add_mark(25,  Gtk.PositionType.BOTTOM, "min")
        gap_scale.add_mark(35,  Gtk.PositionType.BOTTOM, "rec")
        gap_scale.add_mark(80,  Gtk.PositionType.BOTTOM, None)

        def _on_gap_changed(scale, b=binding):
            ms = int(scale.get_value())
            b.sub_delay_ms = ms
            gap_lbl.set_text(f"Gap between clicks — {ms} ms")
            self._update_save_btn_state()

        gap_scale.connect("value-changed", _on_gap_changed)
        gap_row.pack_start(gap_scale, True, True, 0)

        gap_lbl_fast = Gtk.Label(label="Wide")
        gap_lbl_fast.get_style_context().add_class("speed-label")
        gap_row.pack_start(gap_lbl_fast, False, False, 0)

        # Set initial label text
        gap_lbl.set_text(f"Gap between clicks — {binding.sub_delay_ms} ms")

        # Apply initial state
        _update_speed_row(binding.action)
        _update_mode_sensitivity(binding.action)

        return card

    # Binding Event Handlers
    def _on_binding_enable_toggled(self, widget, binding):
        binding.enabled = widget.get_active()
        self.core.update_mutes()
        self._update_status_bar()
        self._update_save_btn_state()

    def _on_binding_name_changed(self, widget, binding):
        binding.name = widget.get_text()
        self._update_save_btn_state()

    def _on_delete_binding_clicked(self, binding, row_widget):
        self.core.remove_binding(binding)
        self.bindings_box.remove(row_widget)
        self._update_status_bar()
        # Deleting a binding is an immediate save action (structural change)
        self._save_current_settings()
        self._mark_saved_snapshot()
        self._update_save_btn_state()

    def _on_trigger_changed(self, combo, binding):
        chosen = combo.get_active_id()
        if chosen:
            binding.trigger = chosen
            binding.trigger_code = trigger_key_to_code(chosen)
            self.core.update_mutes()
            self._update_save_btn_state()

    def _on_detect_clicked(self, btn, binding):
        # Toggle detection state
        binding.detecting = not binding.detecting
        if binding.detecting:
            btn.set_label("⬤  Press any button…")
            btn.get_style_context().remove_class("trigger-btn")
            btn.get_style_context().add_class("trigger-btn-detecting")
        else:
            lbl = get_trigger_label(binding.trigger, binding.trigger_code)
            btn.set_label(f"🖱  {lbl}")
            btn.get_style_context().remove_class("trigger-btn-detecting")
            btn.get_style_context().add_class("trigger-btn")

    def _on_action_changed(self, combo, binding, callback):
        act_key = combo.get_active_id()
        if act_key:
            binding.action = act_key
            callback(act_key)
            self.core.update_mutes()
            self._update_save_btn_state()

    def _on_mode_changed(self, combo, binding):
        mode = combo.get_active_id()
        if mode:
            binding.mode = mode
            binding.held.clear()
            binding.toggle_active = False
            self._update_save_btn_state()

    def _on_cps_changed(self, val, binding):
        binding.cps = float(val)
        self._update_save_btn_state()

    def _on_burst_delay_changed(self, val, binding):
        binding.sub_delay_ms = int(val)
        self._update_save_btn_state()

    # Advanced Expander Section
    def _build_advanced_expander(self):
        expander = Gtk.Expander(label="⚙ Advanced Options & Click Tester")
        expander.set_expanded(self.saved_config.get("advanced_expanded", False))
        expander.connect("notify::expanded", lambda *_: self._update_save_btn_state())
        self.expander = expander

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("card")
        card.set_margin_top(4)

        # Mute browser navigation
        self.mute_check = Gtk.CheckButton(label="Mute Browser Back/Forward navigation")
        self.mute_check.set_active(self.core.mute_nav)
        self.mute_check.connect("toggled", self._on_mute_toggled)
        card.pack_start(self.mute_check, False, False, 0)

        # Jitter Slider
        j_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        j_lbl = Gtk.Label(label="Humanizer Randomness:", xalign=0)
        self.j_val_lbl = Gtk.Label(label=f"±{int(round(self.core.jitter * 100))}%", xalign=1)
        self.j_val_lbl.set_sensitive(False)
        j_box.pack_start(j_lbl, True, True, 0)
        j_box.pack_end(self.j_val_lbl, False, False, 0)
        card.pack_start(j_box, False, False, 0)

        self.jitter_adj = Gtk.Adjustment(value=self.core.jitter, lower=0.0, upper=0.5, step_increment=0.01, page_increment=0.05)
        self.jitter_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.jitter_adj)
        self.jitter_scale.set_digits(2)
        self.jitter_scale.set_draw_value(False)
        self.jitter_scale.connect("scroll-event", self._prevent_scale_scroll)
        self.jitter_scale.connect("value-changed", self._on_jitter_changed)
        card.pack_start(self.jitter_scale, False, False, 0)

        # Hardware mimic toggle
        self.mimic_check = Gtk.CheckButton(label="Mimic real mouse hardware IDs")
        self.mimic_check.set_active(self.core.mimic)
        self.mimic_check.connect("toggled", self._on_mimic_toggled)
        card.pack_start(self.mimic_check, False, False, 0)

        # In-app Click Tester
        test_box = Gtk.EventBox()
        self.test_lbl = Gtk.Label(label="🎯 Click Tester: Click or trigger here to test live clicks")
        test_box.add(self.test_lbl)
        test_box.get_style_context().add_class("test-click-area")
        test_box.set_above_child(True)
        test_box.connect("button-press-event", self._on_test_click)
        card.pack_start(test_box, False, False, 2)
        self.test_stats = {"count": 0, "first_time": 0, "last_time": 0}

        # Device info & rescan
        dev_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.dev_label = Gtk.Label(label="Mouse: Scanning...", xalign=0)
        self.dev_label.set_ellipsize(Pango.EllipsizeMode.END)
        dev_box.pack_start(self.dev_label, True, True, 0)

        rescan_btn = Gtk.Button(label="Rescan Mice")
        rescan_btn.connect("clicked", self._on_rescan_clicked)
        dev_box.pack_end(rescan_btn, False, False, 0)
        card.pack_start(dev_box, False, False, 0)

        expander.add(card)
        return expander

    def _on_test_click(self, widget, event):
        now = time.time()
        st = self.test_stats
        if now - st.get("last_time", 0) > 0.8:
            st["count"] = 0
            st["first_time"] = now
        st["count"] += 1
        st["last_time"] = now

        duration = max(0.05, now - st["first_time"])
        cps = st["count"] / duration if st["count"] > 1 else 1.0
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            btn_type = "Double Click"
        elif event.type == Gdk.EventType._3BUTTON_PRESS:
            btn_type = "Triple Click"
        else:
            btn_type = "Left Click" if event.button == 1 else ("Right Click" if event.button == 3 else f"Button {event.button}")
        self.test_lbl.set_text(f"✓ Detected: {btn_type} | {cps:.1f} CPS ({st['count']} clicks)")
        return True

    def _on_mute_toggled(self, widget):
        self.core.mute_nav = widget.get_active()
        self.core.update_mutes()
        self._update_save_btn_state()

    def _on_jitter_changed(self, scale):
        val = scale.get_value()
        with self.core.lock:
            self.core.jitter = val
        pct = int(round(val * 100))
        self.j_val_lbl.set_text(f"±{pct}%" if pct > 0 else "±0% (Exact)")
        self._update_save_btn_state()

    def _on_mimic_toggled(self, widget):
        self.core.mimic = widget.get_active()
        self.core.init_uinput()
        self._update_save_btn_state()

    def _on_rescan_clicked(self, widget):
        mice = self.core.rescan_devices()
        self._on_core_device_update([m.name for m in mice])
        self.core.update_mutes()

    def _on_core_device_update(self, names):
        text = f"Mouse: {', '.join(names)}" if names else "Mouse: None found (check permissions)"
        self.dev_label.set_text(text)
        self._update_status_bar()

    # Status Bar Section
    def _build_status_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.get_style_context().add_class("status-bar-box")

        self.sb_master_lbl = Gtk.Label(xalign=0)
        self.sb_master_lbl.get_style_context().add_class("status-bold")
        bar.pack_start(self.sb_master_lbl, False, False, 0)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        bar.pack_start(sep1, False, False, 2)

        self.sb_bindings_lbl = Gtk.Label(xalign=0)
        self.sb_bindings_lbl.get_style_context().add_class("status-text")
        bar.pack_start(self.sb_bindings_lbl, True, True, 0)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        bar.pack_start(sep2, False, False, 2)

        self.sb_clicks_lbl = Gtk.Label(xalign=1)
        self.sb_clicks_lbl.get_style_context().add_class("status-bold")
        bar.pack_end(self.sb_clicks_lbl, False, False, 0)

        self._update_status_bar()
        return bar

    def _update_status_bar(self):
        if self.core.master_enabled:
            self.sb_master_lbl.set_text(f"● RUNNING [{self.core.hotkey}]")
        else:
            self.sb_master_lbl.set_text(f"○ PAUSED [{self.core.hotkey}]")

        total_clicks = sum(b.total_clicks for b in self.core.bindings)
        enabled_count = sum(1 for b in self.core.bindings if b.enabled)
        active_count = sum(1 for b in self.core.bindings if b.is_clicking)

        self.sb_bindings_lbl.set_text(f"Bindings: {enabled_count} enabled ({active_count} active)")
        self.sb_clicks_lbl.set_text(f"Total: {total_clicks:,} clicks")

    def _on_core_state_change(self):
        # Update Master button
        ctx = self.master_btn.get_style_context()
        if self.core.master_enabled:
            self.master_btn.set_label("● RUNNING")
            ctx.remove_class("master-btn-paused")
            ctx.add_class("master-btn-active")
        else:
            self.master_btn.set_label("○ PAUSED")
            ctx.remove_class("master-btn-active")
            ctx.add_class("master-btn-paused")

        # Update each binding row badge and card style
        for b in self.core.bindings:
            if hasattr(b, "badge_widget") and b.badge_widget:
                bctx = b.badge_widget.get_style_context()
                cctx = b.row_widget.get_style_context() if b.row_widget else None
                if b.is_clicking:
                    b.badge_widget.set_text("⚡")
                    b.badge_widget.set_tooltip_text(f"Clicking: {b.total_clicks:,} clicks")
                    bctx.remove_class("badge-idle")
                    bctx.add_class("badge-clicking")
                    if cctx:
                        cctx.add_class("binding-card-active")
                elif b.mode == "toggle" and b.toggle_active:
                    b.badge_widget.set_text("●")
                    b.badge_widget.set_tooltip_text("Toggled ON")
                    bctx.remove_class("badge-idle")
                    bctx.add_class("badge-clicking")
                    if cctx:
                        cctx.add_class("binding-card-active")
                else:
                    b.badge_widget.set_text("●")
                    b.badge_widget.set_tooltip_text("Status: Idle")
                    bctx.remove_class("badge-clicking")
                    bctx.add_class("badge-idle")
                    if cctx:
                        cctx.remove_class("binding-card-active")

            if hasattr(b, "detect_btn") and b.detect_btn:
                if not b.detecting:
                    # Reset trigger button label to current trigger name
                    lbl = get_trigger_label(b.trigger, b.trigger_code)
                    b.detect_btn.set_label(f"🖱  {lbl}")
                    b.detect_btn.get_style_context().remove_class("trigger-btn-detecting")
                    b.detect_btn.get_style_context().add_class("trigger-btn")
                    b.detect_btn.set_sensitive(True)  # re-enable after detect completes

            # trigger_combo is None in card layout — skip combo update
            if hasattr(b, "trigger_combo") and b.trigger_combo:
                current_id = b.trigger_combo.get_active_id()
                if current_id != b.trigger:
                    # If not present, append
                    all_ids = [opt["key"] for opt in TRIGGER_OPTIONS]
                    if b.trigger not in all_ids:
                        b.trigger_combo.append(b.trigger, get_trigger_label(b.trigger, b.trigger_code))
                    b.trigger_combo.set_active_id(b.trigger)

        self._update_status_bar()

    def _save_current_settings(self):
        adv_expanded = False
        if hasattr(self, "expander") and self.expander:
            adv_expanded = self.expander.get_expanded()

        bindings_data = [b.to_dict() for b in self.core.bindings]
        data = {
            "master_enabled": self.core.master_enabled,
            "hotkey": self.core.hotkey,
            "mute_nav": self.core.mute_nav,
            "jitter": round(self.core.jitter, 3),
            "mimic": self.core.mimic,
            "advanced_expanded": adv_expanded,
            "bindings": bindings_data
        }
        save_config(data)
        # Keep the saved snapshot in sync whenever we write to disk
        self._mark_saved_snapshot()
        self._update_save_btn_state()

    def _on_close(self, widget):
        self._save_current_settings()
        self.core.stop()
        Gtk.main_quit()


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Mouse AutoClicker GUI")
    args = parser.parse_args()

    init_success, _ = Gtk.init_check(sys.argv)
    if not init_success:
        print("[Error] Could not initialize GTK. Please ensure DISPLAY is set (e.g. DISPLAY=:0).")
        sys.exit(1)

    core = AutoClickerCore()
    win = AutoClickerWindow(core)
    win.show_all()
    # Take the initial saved snapshot so Save button starts disabled (nothing changed yet)
    win._mark_saved_snapshot()
    win._update_save_btn_state()
    win._check_permissions()
    Gtk.main()


if __name__ == "__main__":
    main()
