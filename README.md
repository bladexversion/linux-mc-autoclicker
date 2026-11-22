# Mouse AutoClicker

A system-wide multi-binding mouse auto-clicker for Linux, built with Python + GTK3.

## Features
- Left/Right click autoclicker at configurable CPS
- Double-click modes (Left & Right)
- 1:1 button remapping (e.g. Back button → normal Left click)
- Global hotkey (default **F8**) to toggle on/off — works in-game
- Compact dark-themed GUI (Supabase-style table layout)
- Saves/loads config automatically

## Requirements
- Linux with X11 (tested on Linux Mint XFCE)
- Python 3.10+
- GTK3 (`python3-gi`) — system package, pre-installed on most distros

## Install (one command)

```bash
sudo bash setup.sh
```

That's it. The script will:
1. Create a `venv/` with all Python dependencies (`evdev`, `pynput`)
2. Install a launcher at `/usr/local/bin/mouse-autoclicker`
3. Add a passwordless sudo rule so it never asks for your password
4. Install a polkit policy
5. Add it to your Applications menu
6. Create a desktop shortcut

## Launch
After setup, open from:
- **Applications menu** → Mouse AutoClicker
- **Desktop shortcut** → MouseAutoClicker
- **Terminal** → `mouse-autoclicker`

## Uninstall

```bash
sudo bash uninstall.sh
```

Removes the launcher, sudo rules, desktop entries, icons, and venv. Optionally removes your saved config too. Then just delete the project folder.

## Development

```bash
# Install deps into venv manually
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install evdev pynput

# Run directly (needs root for /dev/uinput)
sudo venv/bin/python3 right_clicker.py
```

## Files
| File | Purpose |
|---|---|
| `right_clicker.py` | Main application |
| `setup.sh` | One-command installer |
| `uninstall.sh` | Full system cleanup |
| `run.sh` | Dev launcher |
| `com.autoclicker.mouse.policy` | Polkit policy |
| `venv/` | Python venv (not committed) |
