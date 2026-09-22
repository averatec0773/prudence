#!/usr/bin/env python3
"""Photograph the real menu bar with our status item in it.

`shot.py` photographs one of the app's own windows over the app's own backdrop, and its
guarantees all rest on that: the subject is ours, so the picture is ours. The menu bar is
not ours. It belongs to the machine, and the whole point of the shot is to show our glyph
**between the neighbours it has to live with**, so there is no backdrop to hide behind.

What replaces those guarantees:

* **The strip is found, not guessed.** On macOS 26 a status item is hosted by Control
  Center, so our process owns no window in the menu bar and no outside script can find our
  item in the window list. The app reports its own anchor instead (a harness-only line, so
  it is not in a release build) and the capture runs from a fixed margin left of it to the
  right edge of the screen. The left half of the menu bar, where the frontmost application
  puts its menu titles, is never in frame.
* **It refuses an implausible anchor.** On 2026-09-21 the app reported an unplaced status
  item at x = 18, the left margin collapsed to zero, and this script photographed the whole
  menu bar with the app menus in it. The app no longer reports an unplaced item
  (`platform::macos::in_the_menu_bar`); this is the second lock on the same door.
* **It kills the PID it launched.** Never `pkill` by name: the founder's own `Prudence.app`
  has the same name.

Two things it deliberately does not do.

It does not photograph a light menu bar and a dark one. **On macOS 26 the menu bar takes
its tint from the desktop picture, not from the appearance setting**: switching the system
to light and back changed nothing in the strip, so the switch was pure machine mutation
and is gone. A light menu bar needs a light wallpaper, which is the founder's to set.

The backdrop is up, but it does not neutralise the bar: the menu bar samples the desktop
picture, not the windows in front of it. What it does is keep everything below the bar out
of the frame, which is most of what the strip's bottom edge would otherwise catch.

    python3 Scripts/menubar.py --name glyph --store /tmp/copy-of-a-store
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import Quartz

APP = Path(__file__).resolve().parent.parent
DEBUG_BINARY = APP / "src-tauri/target/debug/bundle/macos/Prudence.app/Contents/MacOS/Prudence"
BINARY = APP / "src-tauri/target/release/bundle/macos/Prudence.app/Contents/MacOS/Prudence"

# How much of the menu bar to keep to the left of our own item. Enough to show the
# neighbours the founder is judging it against, not enough to reach the app menus.
MARGIN = 260.0
# The menu bar is 33 points on macOS 26; take a little more so the shot shows the bar's
# own lower edge rather than cropping at it.
STRIP = 36.0

ANCHOR = re.compile(
    r"\[harness\] status item at "
    r"center_x=([\d.-]+) bottom=([\d.-]+) min_x=([\d.-]+) max_x=([\d.-]+)"
)
BACKDROP_TITLE = "Prudence backdrop"


def anchor_from(log: Path) -> dict | None:
    """Where the app says its own status item is. See the note above on why we ask it."""
    found = ANCHOR.search(log.read_text(errors="replace")) if log.exists() else None
    if not found:
        return None
    center_x, bottom, min_x, max_x = (float(v) for v in found.groups())
    return {"center_x": center_x, "bottom": bottom, "min_x": min_x, "max_x": max_x}


def backdrop_is_up(pid: int) -> bool:
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
    )
    return any(
        entry.get("kCGWindowOwnerPID") == pid and entry.get("kCGWindowName") == BACKDROP_TITLE
        for entry in info or []
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="output file stem")
    parser.add_argument("--store", required=True, help="a COPY of a store, never the real one")
    parser.add_argument("--out", default=str(APP / "shots"))
    parser.add_argument("--wait", type=float, default=6.0)
    parser.add_argument("--release-build", action="store_true")
    args = parser.parse_args()

    binary = BINARY if args.release_build else DEBUG_BINARY
    if not binary.exists():
        print(f"no binary at {binary}", file=sys.stderr)
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
            "PRUDENCE_UI_MEMORY": "off",
            "PRUDENCE_BACKDROP": "1",
        }
    )

    log = out / f"{args.name}.log"
    with log.open("w") as handle:
        process = subprocess.Popen([str(binary)], env=env, stdout=handle, stderr=handle)

    try:
        time.sleep(args.wait)
        if process.poll() is not None:
            print(f"the app exited with {process.returncode}; see {log}", file=sys.stderr)
            return 1

        if not backdrop_is_up(process.pid):
            print("the backdrop did not appear; refusing to capture", file=sys.stderr)
            return 1

        item = anchor_from(log)
        if item is None:
            print(f"the app never reported a status item; see {log}", file=sys.stderr)
            return 1
        if not (item["min_x"] <= item["center_x"] <= item["max_x"] and 0 < item["bottom"] <= 60):
            print(f"implausible anchor {item}; refusing to capture", file=sys.stderr)
            return 1
        print(f"status item centred at x={item['center_x']:.1f}, bottom {item['bottom']:.1f}")

        left = max(item["min_x"], item["center_x"] - MARGIN)
        rect = f"{int(left)},0,{int(item['max_x'] - left)},{int(STRIP)}"
        path = out / f"{args.name}.png"
        subprocess.run(["screencapture", "-x", "-R", rect, str(path)], check=True)
        print(f"wrote {path}")
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
