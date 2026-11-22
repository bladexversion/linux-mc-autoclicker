#!/usr/bin/env python3
"""
Hold the mouse BACK button -> continuous right clicks.

Your real mouse is NOT grabbed or cloned, so it keeps all of its own settings
(acceleration, speed, etc.). The script only listens for the back button and
sends right clicks through a tiny separate virtual device that never moves.

To stop the back button from also doing "go back" in apps, the script
temporarily disables X button 8 on your mouse with xinput, and restores it on exit.

Setup (Linux Mint XFCE):
    sudo apt install python3-evdev xinput
Run:
    sudo python3 back_rightclick.py
Options:
    --cps 20          clicks per second (default 20)
    --button side     'side' = back button (default), 'extra' = forward button
    --keep-back       don't disable the normal back action
Stop with Ctrl+C.
"""
import argparse
import os
import random
import subprocess
import threading
import time

import evdev
from evdev import UInput, ecodes as e


def run_xinput(args):
    """Run xinput as the logged-in user (root has no access to the X display)."""
    user = os.environ.get("SUDO_USER")
    env = {"DISPLAY": os.environ.get("DISPLAY", ":0")}
    if user:
        env["XAUTHORITY"] = f"/home/{user}/.Xauthority"
        cmd = ["sudo", "-u", user, "env"] + [f"{k}={v}" for k, v in env.items()] + ["xinput"] + args
    else:
        cmd = ["xinput"] + args
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def xinput_ids(name):
    out = run_xinput(["list", "--id-only", name])
    return [int(x) for x in out.split() if x.isdigit()]


class BackButtonMute:
    """Disable the X-level back/forward button so apps don't navigate."""

    def __init__(self, dev_name, x_button):
        self.saved = {}
        for xid in xinput_ids(dev_name):
            out = run_xinput(["get-button-map", str(xid)])
            mapping = [int(x) for x in out.split() if x.isdigit()]
            if len(mapping) >= x_button:
                self.saved[xid] = mapping
                new = mapping.copy()
                new[x_button - 1] = 0
                run_xinput(["set-button-map", str(xid)] + [str(x) for x in new])

    def restore(self):
        for xid, mapping in self.saved.items():
            run_xinput(["set-button-map", str(xid)] + [str(x) for x in mapping])


class Clicker:
    def __init__(self, interval, jitter=0.0, name="back-rightclick-virtual", info=None):
        self.interval = interval
        self.jitter = jitter
        self.held = threading.Event()
        cap = {
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
            e.EV_REL: [e.REL_X, e.REL_Y],
        }
        kwargs = {}
        if info is not None:  # copy vendor/product IDs of the real mouse
            kwargs = dict(vendor=info.vendor, product=info.product,
                          version=info.version, bustype=info.bustype)
        self.ui = UInput(cap, name=name, **kwargs)
        threading.Thread(target=self.loop, daemon=True).start()

    def wait(self, fraction):
        """Sleep for a share of the interval, randomized by +/- jitter."""
        base = self.interval * fraction
        time.sleep(max(0.001, base * (1 + random.uniform(-self.jitter, self.jitter))))

    def loop(self):
        while True:
            self.held.wait()
            while self.held.is_set():
                self.ui.write(e.EV_KEY, e.BTN_RIGHT, 1)
                self.ui.syn()
                self.wait(0.3)   # how long the button stays down
                self.ui.write(e.EV_KEY, e.BTN_RIGHT, 0)
                self.ui.syn()
                self.wait(0.7)   # gap before the next click


def watch(path, trigger, clicker):
    dev = evdev.InputDevice(path)
    try:
        for ev in dev.read_loop():
            if ev.type == e.EV_KEY and ev.code == trigger:
                if ev.value == 1:
                    clicker.held.set()
                elif ev.value == 0:
                    clicker.held.clear()
    except OSError:
        pass
    finally:
        clicker.held.clear()


def find_mice(trigger):
    mice = []
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        keys = d.capabilities().get(e.EV_KEY, [])
        if trigger in keys and e.BTN_LEFT in keys and "back-rightclick" not in d.name:
            mice.append(d)
    return mice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cps", type=float, default=20.0)
    ap.add_argument("--button", choices=["side", "extra"], default="side")
    ap.add_argument("--keep-back", action="store_true")
    ap.add_argument("--jitter", type=float, default=0.0,
                    help="randomize click timing by +/- this fraction, e.g. 0.3")
    ap.add_argument("--mimic", action="store_true",
                    help="give the virtual device your real mouse's name and USB IDs")
    args = ap.parse_args()

    trigger = e.BTN_SIDE if args.button == "side" else e.BTN_EXTRA
    x_button = 8 if args.button == "side" else 9
    interval = 1.0 / max(args.cps, 1.0)

    mice = find_mice(trigger)
    if not mice:
        raise SystemExit("No mouse with a back button found (run with sudo?).")

    if args.mimic:
        clicker = Clicker(interval, args.jitter, name=mice[0].name, info=mice[0].info)
    else:
        clicker = Clicker(interval, args.jitter)
    mutes = []
    for d in mice:
        print(f"Watching: {d.name} ({d.path})")
        if not args.keep_back:
            mutes.append(BackButtonMute(d.name, x_button))
        threading.Thread(target=watch, args=(d.path, trigger, clicker), daemon=True).start()

    print("Hold the back button to spam right click. Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for m in mutes:
            m.restore()


if __name__ == "__main__":
    main()