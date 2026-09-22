#!/usr/bin/env python3
"""The one version number, everywhere it is written.

The engine (`prudence-core`), the desktop app and the Claude Code plugin share one
version, and a release is one tag. The number is written in several files because each
tool reads its own; this script is the only thing that should edit them.

    python3 scripts/version.py             # print the version and every place it is written
    python3 scripts/version.py --check     # exit 1 if any two disagree (CI runs this)
    python3 scripts/version.py --set 0.2.0 # write it everywhere, then run `uv lock`

`uv.lock` and `Cargo.lock` carry the package's own version; `--set` rewrites those two
entries in place, which is exactly what `uv lock` and a build would do, so CI's
`uv sync --locked` stays satisfied without a resolver run. No other line of either lock
file is touched.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?"

# (path, pattern with one capture group around the version). The rest of each pattern is
# what makes the match unambiguous inside that file, and nothing else in the file matches.
PLACES: list[tuple[str, str]] = [
    ("pyproject.toml", rf'^version = "({SEMVER})"$'),
    ("src/prudence/__init__.py", rf'^__version__ = "({SEMVER})"$'),
    ("uv.lock", rf'^name = "prudence-core"\nversion = "({SEMVER})"$'),
    ("apps/desktop/src-tauri/tauri.conf.json", rf'^  "version": "({SEMVER})",$'),
    ("apps/desktop/src-tauri/Cargo.toml", rf'^version = "({SEMVER})"$'),
    ("apps/desktop/src-tauri/Cargo.lock", rf'^name = "prudence-desktop"\nversion = "({SEMVER})"$'),
    ("apps/desktop/package.json", rf'^  "version": "({SEMVER})",$'),
    ("plugin/.claude-plugin/plugin.json", rf'^  "version": "({SEMVER})",$'),
]


def read_all() -> list[tuple[str, str]]:
    """Every (path, version) the patterns find; a path that does not match is an error."""
    found = []
    for relative, pattern in PLACES:
        text = (ROOT / relative).read_text()
        matches = re.findall(pattern, text, flags=re.MULTILINE)
        if len(matches) != 1:
            sys.exit(f"{relative}: expected exactly one version line, found {len(matches)}")
        found.append((relative, matches[0]))
    return found


def check() -> int:
    found = read_all()
    versions = {version for _, version in found}
    width = max(len(path) for path, _ in found)
    for path, version in found:
        print(f"{path:<{width}}  {version}")
    if len(versions) > 1:
        print(f"\n{len(versions)} different versions; run scripts/version.py --set X.Y.Z")
        return 1
    return 0


def set_version(version: str) -> None:
    if not re.fullmatch(SEMVER, version):
        sys.exit(f"not a version: {version}")
    for relative, pattern in PLACES:
        path = ROOT / relative
        text = path.read_text()

        def replace(match: re.Match[str]) -> str:
            whole = match.group(0)
            start = match.start(1) - match.start()
            end = match.end(1) - match.start()
            return whole[:start] + version + whole[end:]

        new, count = re.subn(pattern, replace, text, flags=re.MULTILINE)
        if count != 1:
            sys.exit(f"{relative}: expected exactly one version line, found {count}")
        path.write_text(new)
        print(f"{relative}: {version}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the versions disagree")
    parser.add_argument("--set", metavar="X.Y.Z", help="write this version everywhere")
    args = parser.parse_args()
    if args.set:
        set_version(args.set)
        return check()
    return check()


if __name__ == "__main__":
    sys.exit(main())
