#!/usr/bin/env python3
"""Ask whether the compositor holds, and answer from pixels rather than from the page.

Wry issue 1848 reports the macOS 26 WKWebView compositor intermittently ceasing to present
new frames while the DOM keeps updating. Every check that asks the page how it is would
pass during that failure, so this script ends by reading a colour out of a screenshot:
the shell tells the page to fill its content area with a known colour, and the script
looks at the pixels. A stale compositor keeps the old ones.

    python3 Scripts/stress.py --rounds 400 --store /tmp/prudence-copy --out shots
    python3 Scripts/stress.py --rounds 400 --idle 600 --store ... --out ...

`--idle N` asks the same question again after N seconds of the app doing nothing at all,
because nothing in the issue says the stall needs activity.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import io

from PIL import Image, ImageCms

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot import BINARY, activate, is_on_top, pick, windows_of  # noqa: E402

# Must match `probe()` in `src-tauri/src/stress.rs`.
EXPECTED = {"after-stress": (214, 45, 130), "after-idle": (36, 168, 92)}
TOLERANCE = 6


def wait_for(log: Path, marker: str, timeout: float) -> str | None:
    """Wait for a line containing `marker` to appear in the shell's own output."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log.exists():
            for line in log.read_text(errors="replace").splitlines():
                if marker in line:
                    return line
        time.sleep(0.5)
    return None


def capture(pid: int, name: str, out: Path) -> Path | None:
    window = pick(windows_of(pid), "main")
    if window is None:
        print(f"{name}: no window to photograph", file=sys.stderr)
        return None
    for _ in range(3):
        activate(pid)
        time.sleep(0.6)
        window = pick(windows_of(pid), "main") or window
        ok, reason = is_on_top(pid, window)
        if ok:
            break
    else:
        print(f"{name}: refusing to capture, {reason}", file=sys.stderr)
        return None

    target = out / f"{name}.png"
    region = f"{int(window['x'])},{int(window['y'])},{int(window['w'])},{int(window['h'])}"
    subprocess.run(["screencapture", "-x", "-R", region, str(target)], check=True)
    return target


def sample(image: Path) -> tuple[int, int, int]:
    """The colour in the middle of the content area, which the probe fills whole.

    `screencapture` writes the display's own profile and does not convert, so on a P3
    display a CSS `rgb(214,45,130)` lands in the file as `(197,62,128)`. Reading the raw
    numbers would have reported a perfectly healthy compositor as stale. The embedded
    profile is used to convert back to sRGB, which is the space the CSS was written in.
    """
    with Image.open(image) as picture:
        rgb = picture.convert("RGB")
        profile = picture.info.get("icc_profile")
        if profile:
            rgb = ImageCms.profileToProfile(
                rgb,
                ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile("sRGB"),
                outputMode="RGB",
            )
        # Right of the sidebar and below the toolbar, in the middle of the screen area.
        return rgb.getpixel((int(rgb.width * 0.7), int(rgb.height * 0.6)))


def close_enough(got: tuple[int, int, int], want: tuple[int, int, int]) -> bool:
    return all(abs(a - b) <= TOLERANCE for a, b in zip(got, want))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=400)
    parser.add_argument("--idle", type=int, default=0, help="seconds of idleness before the second probe")
    parser.add_argument("--store", required=True, help="a COPY of a store, never the real one")
    parser.add_argument("--out", required=True)
    parser.add_argument("--appearance", choices=["light", "dark"], default="light")
    parser.add_argument(
        "--no-backdrop",
        action="store_true",
        help="skip the full-screen backdrop. Use it for a long idle run: the probe fills "
        "the window's own content area, so the measurement does not need one, and ten "
        "minutes of a full-screen window is ten minutes of the founder's screen.",
    )
    args = parser.parse_args()

    if not BINARY.exists():
        print(f"no bundle at {BINARY}", file=sys.stderr)
        return 2
    store = Path(args.store).expanduser().resolve()
    if not (store / "prudence.db").exists():
        print(f"no prudence.db in {store}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "stress.log"

    env = dict(os.environ)
    env.update(
        {
            "PRUDENCE_DATA_DIR": str(store),
            "PRUDENCE_CONFIG_DIR": str(store),
            "PRUDENCE_FORCE_APPEARANCE": args.appearance,
            "PRUDENCE_UI_MEMORY": "off",
            "PRUDENCE_WINDOW_OPEN": "1",
            "PRUDENCE_STRESS": f"screens:{args.rounds}",
        }
    )
    if not args.no_backdrop:
        env["PRUDENCE_BACKDROP"] = "1"
    if args.idle:
        env["PRUDENCE_STRESS_IDLE"] = str(args.idle)

    with log.open("w") as handle:
        process = subprocess.Popen([str(BINARY)], env=env, stdout=handle, stderr=handle)

    failures = []
    try:
        budget = 60 + args.rounds * 0.5
        if wait_for(log, "[stress] settled", budget) is None:
            print(f"the run never settled within {budget:.0f} s", file=sys.stderr)
            return 1
        print("settled; photographing the window")
        if capture(process.pid, "stress-settled", out) is None:
            failures.append("could not photograph the settled window")

        for label, wait_seconds in [("after-stress", 60), ("after-idle", args.idle + 120)]:
            if label == "after-idle" and not args.idle:
                continue
            line = wait_for(log, f"[probe] {label}", wait_seconds)
            if line is None:
                failures.append(f"{label}: the probe never ran")
                continue
            picture = capture(process.pid, f"probe-{label}", out)
            if picture is None:
                failures.append(f"{label}: could not photograph the probe")
                continue
            got = sample(picture)
            want = EXPECTED[label]
            verdict = "painted" if close_enough(got, want) else "STALE"
            print(f"{label}: wanted rgb{want}, screen shows rgb{got} -> {verdict}")
            if verdict == "STALE":
                failures.append(f"{label}: wanted rgb{want}, screen shows rgb{got}")
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"\n{args.rounds} rounds, every probe painted. Log: {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
