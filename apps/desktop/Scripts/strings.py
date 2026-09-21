#!/usr/bin/env python3
"""Turn the Swift String Catalog into the per-locale JSON this app reads.

    python3 Scripts/strings.py            # write the files
    python3 Scripts/strings.py --check    # fail if they are stale

**This script is a migration, and it dies with `apps/mac/`.** The lead's ruling on
2026-09-21: generate once, and `src/design/strings.*.json` become the source of truth. The
generator and the `--check` test exist only so that the two dictionaries cannot drift
while both apps are in the repository; when the Swift app is deleted, both go with it and
nothing generates the JSON any more.

What it carries across, unchanged:

* every key, in `en` and `zh-Hans`;
* `%n$@` placeholders, in **each language's own order**, which is the whole reason they
  are numbered;
* the plural entries, as `{one, other}` for English and `{other}` for Chinese, with
  `%n$lld` left where it is so the runtime can put a localised number in it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
CATALOG = APP / "../mac/PrudenceKit/Sources/PrudenceUI/Resources/Localizable.xcstrings"
OUT = APP / "src/text"
LANGUAGES = ("en", "zh-Hans")

NOTE = (
    "Generated from apps/mac/PrudenceKit/Sources/PrudenceUI/Resources/Localizable.xcstrings "
    "by apps/desktop/Scripts/strings.py. Do not edit by hand while apps/mac/ exists: run the "
    "script. When the Swift app is deleted, the script goes with it and this file becomes "
    "the source of truth."
)


def localisation(entry: dict, language: str, key: str):
    """One key in one language: a string, or a table of plural forms."""
    localisations = entry.get("localizations", {})
    if language not in localisations:
        raise KeyError(f"{key} has no {language}")
    node = localisations[language]

    if "stringUnit" in node:
        return node["stringUnit"]["value"]

    variations = node.get("variations", {}).get("plural")
    if not variations:
        raise KeyError(f"{key} in {language} is neither a string nor a plural")
    return {form: body["stringUnit"]["value"] for form, body in sorted(variations.items())}


def build() -> dict[str, dict]:
    catalog = json.loads(CATALOG.read_text())
    strings = catalog["strings"]
    out = {}
    for language in LANGUAGES:
        table = {key: localisation(entry, language, key) for key, entry in sorted(strings.items())}
        out[language] = {"note": NOTE, "language": language, "strings": table}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the files are stale")
    args = parser.parse_args()

    if not CATALOG.exists():
        # The Swift app is gone. That is the end state, not an error: the JSON is the
        # source now and there is nothing left to generate it from.
        print(f"no catalog at {CATALOG.resolve()}; the JSON is the source now")
        return 0

    built = build()
    stale = []
    for language, payload in built.items():
        target = OUT / f"strings.{language}.json"
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
        if args.check:
            if not target.exists() or target.read_text() != text:
                stale.append(target.name)
        else:
            target.write_text(text)
            print(f"{target.relative_to(APP)}  {len(payload['strings'])} keys")

    if stale:
        print(f"stale, rerun Scripts/strings.py: {', '.join(stale)}", file=sys.stderr)
        return 1
    if args.check:
        print(f"{', '.join(LANGUAGES)} match the catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
