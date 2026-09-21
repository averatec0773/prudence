#!/usr/bin/env python3
"""Photograph one of the app's own windows, over the app's own backdrop.

Every batch's acceptance is a picture held beside the Swift app's, so the tool that makes
one exists from batch 1 rather than from batch 9. Batch 9 grows it into the full
inventory, the contact sheet and the label audit.

Three things it is careful about, each one a mistake already made once:

* **It keeps the PID it launched and kills that PID.** Never `pkill` by name or path: the
  founder's own `Prudence.app` has the same name, and on 2026-09-21 a `pkill` by path quit
  it out from under them.
* **It puts a backdrop under the window** (`PRUDENCE_BACKDROP=1`, a plain full-screen
  window of the app's own). A frosted surface photographed over whatever happened to be on
  the screen is neither reproducible nor the founder's to publish.
* **It captures a screen region, not the window's own buffer.** `screencapture -l` copies a
  window's surface, and a window whose material is composited by the window server from
  what is behind it does not carry that composite in its own surface. The region is the
  window's bounds, read from the window list, and the backdrop covers everything else.
* **It refuses to fire unless our window is the thing on top of that region.** Capturing a
  region is capturing whatever is there, and on 2026-09-21 the first run of this script
  photographed the founder's browser because the app was not frontmost. The app is
  activated by PID and the window order is checked; if the check fails, nothing is
  written.

    python3 Scripts/shot.py --name window-light --window main --appearance light
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import AppKit
import Quartz

APP = Path(__file__).resolve().parent.parent
BINARY = APP / "src-tauri/target/release/bundle/macos/Prudence.app/Contents/MacOS/Prudence"
DEBUG_BINARY = APP / "src-tauri/target/debug/bundle/macos/Prudence.app/Contents/MacOS/Prudence"

# The window this shot is of, and how to recognise it in the window list. Widths are
# logical points; the panel is 360 by design and the window's floor is 900.
# The backdrop is the app's own window too and is the biggest thing on the screen, so the
# title has to be part of the rule and not only the size.
BACKDROP_TITLE = "Prudence backdrop"

TARGETS = {
    "panel": {"min_width": 200, "max_width": 500, "env": {"PRUDENCE_PANEL_OPEN": "1"}},
    "main": {"min_width": 880, "max_width": 4000, "env": {"PRUDENCE_WINDOW_OPEN": "1"}},
}


def on_screen() -> list[dict]:
    """Every on-screen window, front to back, which is the order this list comes in."""
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    out = []
    for entry in info or []:
        bounds = entry.get("kCGWindowBounds") or {}
        out.append(
            {
                "id": entry.get("kCGWindowNumber"),
                "pid": entry.get("kCGWindowOwnerPID"),
                "owner": entry.get("kCGWindowOwnerName") or "",
                "name": entry.get("kCGWindowName") or "",
                "layer": entry.get("kCGWindowLayer", 0),
                "x": bounds.get("X", 0.0),
                "y": bounds.get("Y", 0.0),
                "w": bounds.get("Width", 0.0),
                "h": bounds.get("Height", 0.0),
            }
        )
    return out


def windows_of(pid: int) -> list[dict]:
    """The given process's on-screen windows, biggest first."""
    mine = [w for w in on_screen() if w["pid"] == pid]
    return sorted(mine, key=lambda w: w["w"] * w["h"], reverse=True)


def overlaps(a: dict, b: dict) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"]
        or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"]
        or b["y"] + b["h"] <= a["y"]
    )


def is_on_top(pid: int, window: dict) -> tuple[bool, str]:
    """Is our window the frontmost ordinary window over its own rectangle?

    Anything at a layer above zero is the menu bar, the Dock or a status window, and none
    of those is in the region. Anything of ours is fine: the panel may legitimately sit in
    front of the backdrop while the window is being photographed.
    """
    for other in on_screen():
        if other["id"] == window["id"]:
            return True, ""
        if other["layer"] != 0 or other["pid"] == pid:
            continue
        if overlaps(other, window):
            return False, f"{other['owner']!r} window {other['name']!r} is in front"
    return False, "our window is not on screen"


def activate(pid: int) -> None:
    """Bring the process we launched to the front, and nothing else."""
    app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is not None:
        app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)


def pick(windows: list[dict], target: str) -> dict | None:
    rule = TARGETS[target]
    for window in windows:
        if window["name"] == BACKDROP_TITLE:
            continue
        if rule["min_width"] <= window["w"] <= rule["max_width"]:
            return window
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="output file stem")
    parser.add_argument("--window", choices=sorted(TARGETS), default="panel")
    parser.add_argument("--appearance", choices=["light", "dark"], default="light")
    parser.add_argument("--language", choices=["en", "zh-Hans"], default="en")
    parser.add_argument("--out", default=str(APP / "shots"))
    parser.add_argument("--store", required=True, help="a COPY of a store, never the real one")
    parser.add_argument("--wait", type=float, default=7.0)
    parser.add_argument("--debug-build", action="store_true")
    parser.add_argument("--no-backdrop", action="store_true")
    args = parser.parse_args()

    binary = DEBUG_BINARY if args.debug_build else BINARY
    if not binary.exists():
        print(f"no bundle at {binary}; run `pnpm tauri build` first", file=sys.stderr)
        return 2

    store = Path(args.store).expanduser().resolve()
    if not (store / "prudence.db").exists():
        print(f"no prudence.db in {store}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update(
        {
            "PRUDENCE_DATA_DIR": str(store),
            "PRUDENCE_CONFIG_DIR": str(store),
            "PRUDENCE_FORCE_APPEARANCE": args.appearance,
            "PRUDENCE_FORCE_LANGUAGE": args.language,
            # A shot is of the state the caller asked for, not of whatever the machine
            # last left behind.
            "PRUDENCE_UI_MEMORY": "off",
        }
    )
    env.update(TARGETS[args.window]["env"])
    if not args.no_backdrop:
        env["PRUDENCE_BACKDROP"] = "1"

    log = out / f"{args.name}.log"
    with log.open("w") as handle:
        process = subprocess.Popen([str(binary)], env=env, stdout=handle, stderr=handle)

    try:
        time.sleep(args.wait)
        window = pick(windows_of(process.pid), args.window)
        if window is None:
            names = [(w["name"], w["w"], w["h"]) for w in windows_of(process.pid)]
            print(f"no {args.window} window for pid {process.pid}; saw {names}", file=sys.stderr)
            return 1

        # Three tries at getting our own window in front of its own rectangle, then give
        # up. Never capture a region we are not sure we own.
        reason = ""
        for _ in range(3):
            activate(process.pid)
            time.sleep(0.8)
            window = pick(windows_of(process.pid), args.window) or window
            ok, reason = is_on_top(process.pid, window)
            if ok:
                break
        else:
            print(f"refusing to capture: {reason}", file=sys.stderr)
            return 1

        target = out / f"{args.name}.png"
        region = f"{int(window['x'])},{int(window['y'])},{int(window['w'])},{int(window['h'])}"
        subprocess.run(["screencapture", "-x", "-R", region, str(target)], check=True)
        print(f"{target}  window {window['id']}  {region}")
        return 0
    finally:
        # The PID this script started, and no other.
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
