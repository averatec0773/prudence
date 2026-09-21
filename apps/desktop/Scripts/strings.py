#!/usr/bin/env python3
"""Turn the Swift String Catalog into the per-locale JSON this app reads.

    python3 Scripts/strings.py            # write the files
    python3 Scripts/strings.py --check    # fail if they are stale

**This script is a migration, and it dies with `apps/mac/`.** The lead's ruling on
2026-09-21: generate once, and `src/design/strings.*.json` become the source of truth. The
generator and the `--check` test exist only so that the two dictionaries cannot drift
while both apps are in the repository; when the Swift app is deleted, both go with it and
nothing generates the JSON any more.

**The desktop may diverge, and says where.** The Swift app is frozen, so a string the
desktop needs and the catalog does not have cannot be added to the catalog, and a string
the catalog gets wrong cannot be fixed there. Both are listed below in `DESKTOP_ONLY` and
`DESKTOP_OVERRIDES`, and the generator carries them into the output. Anything not in those
two lists must still match the catalog exactly, which is what stops silent drift while
both apps exist.

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
    "by apps/desktop/Scripts/strings.py, plus that script's DESKTOP_ONLY and "
    "DESKTOP_OVERRIDES. Do not edit by hand while apps/mac/ exists: add to those lists and "
    "run the script. When the Swift app is deleted, the script goes with it and this file "
    "becomes the source of truth."
)


# Keys the desktop added after the Swift app was frozen. Nothing in `apps/mac/` uses them.
DESKTOP_ONLY = {
    # The Overview's hover line, its heat-cell label and its chart caption, each composed
    # as one sentence per language rather than assembled from fragments in JavaScript.
    "overview.weekReading": {"en": "%1$@: %2$@. %3$@", "zh-Hans": "%1$@：%2$@。%3$@"},
    "overview.dayHours": {"en": "%1$@: %2$@", "zh-Hans": "%1$@：%2$@"},
    "chart.pointReading": {
        "en": "%1$@ %2$@ %3$@ of %4$@ lines",
        "zh-Hans": "%1$@ %2$@ %3$@，基于 %4$@ 行",
    },
}

# Keys the catalog has wrong. Each one needs a reason, and each one is a divergence from
# the Swift app that somebody has to carry back if that app is ever unfrozen.
DESKTOP_OVERRIDES = {
    # The catalog says "%1$@ 个会话" - "%1$@ sessions". The number is a count of **lines**
    # in both places it is used (`measured_30d` and `lines` are both over `line_fate`), so
    # the Chinese claimed a unit the figure does not have, on the one caption whose job is
    # to make a share checkable. English was unit-free and is now explicit too.
    "chart.sampleSize": {"en": "n=%1$@ lines", "zh-Hans": "n=%1$@ 行"},
}


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
        for key, values in DESKTOP_OVERRIDES.items():
            if key not in table:
                raise KeyError(f"{key} is an override for a key the catalog does not have")
            table[key] = values[language]
        for key, values in DESKTOP_ONLY.items():
            if key in table:
                raise KeyError(f"{key} is listed as desktop-only but the catalog has it")
            table[key] = values[language]
        out[language] = {
            "note": NOTE,
            "language": language,
            "strings": dict(sorted(table.items())),
        }
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
