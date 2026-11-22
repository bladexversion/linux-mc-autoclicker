#!/usr/bin/env bash
# One-time setup: install polkit policy so the autoclicker never asks for a password again.
# Run this ONCE with:  sudo bash install_no_password.sh

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_SRC="$DIR/com.autoclicker.mouse.policy"
POLICY_DST="/usr/share/polkit-1/actions/com.autoclicker.mouse.policy"

if [ "$EUID" -ne 0 ]; then
    echo "This script must be run with sudo. Example:"
    echo "  sudo bash \"$0\""
    exit 1
fi

if [ ! -f "$POLICY_SRC" ]; then
    echo "Error: Policy file not found at $POLICY_SRC"
    exit 1
fi

cp "$POLICY_SRC" "$POLICY_DST"
chmod 644 "$POLICY_DST"
echo "✓ Polkit policy installed to $POLICY_DST"
echo "  The autoclicker will no longer ask for your password when opening."

