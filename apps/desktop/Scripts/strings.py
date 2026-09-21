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
    # The method line under each chart, rewritten for a reader. The view and column names
    # moved into `*.method`, which the page puts behind a disclosure: principle 3 asks for
    # the method stated, and a caption that opens with `alive_30d / measured_30d` states
    # it to whoever wrote the query, not to whoever is reading the chart.
    "overview.tokensByPurpose.note2": {
        "en": "What each week's tokens went on. A session counts on the day it started; a week nothing was recorded in is left empty rather than drawn as zero.",
        "zh-Hans": "每一周的 token 花在了什么上。一个会话计在它开始的那天；没有任何记录的那一周留空，而不是画成零。",
    },
    "overview.tokensByPurpose.method": {
        "en": "Summed from the app_usage_by_purpose_day view into the ISO week each local day falls in, over total_tokens.",
        "zh-Hans": "由 app_usage_by_purpose_day 视图按本地日期所属的 ISO 周汇总 total_tokens。",
    },
    "overview.whatBecame.note2": {
        "en": "Of the lines written in a week, how many were still in the code thirty days later, and how many had been rewritten. The pale band behind them is how much of that week's committed work the sessions themselves wrote. A week whose thirty days are not up yet is a gap, never a zero.",
        "zh-Hans": "某一周写下的代码，三十天后还有多少留在代码里，又有多少被改写。它们背后那条浅色的带子，是那一周提交的工作里由会话本人写下的比例。三十天还没到的那一周是断口，不是零。",
    },
    "overview.whatBecame.method": {
        "en": "alive_30d / measured_30d and reworked / lines, both from the app_outcomes_by_week view; the band is that view's coverage.",
        "zh-Hans": "alive_30d / measured_30d 与 reworked / lines，都来自 app_outcomes_by_week 视图；带子是该视图的 coverage。",
    },
    "overview.whereTime.note2": {
        "en": "Which days the work happened on. A darker square is a longer day; a day with no session at all is left blank rather than shaded as zero.",
        "zh-Hans": "工作发生在哪些日子。颜色越深，那天越长；完全没有会话的日子留白，而不是按零着色。",
    },
    "overview.whereTime.method": {
        "en": "Active minutes per local day, summed from the app_usage_by_purpose_day view.",
        "zh-Hans": "按本地日期汇总 app_usage_by_purpose_day 视图的 active_minutes。",
    },
    "chart.method": {"en": "How this is measured", "zh-Hans": "这张图是怎么算出来的"},
    # The honest placeholder, in place of forty fake rows. A screen that is not written
    # should say so rather than imitate one that is.
    "screen.notBuilt.title": {"en": "Not built yet", "zh-Hans": "这个页面还没写"},
    "screen.notBuilt.detail": {
        "en": "This screen arrives in the next delivery. Nothing is wrong with your store.",
        "zh-Hans": "这个页面会在下一次交付里出现。你的库没有问题。",
    },
    # Two line charts stacked in one card with identical furniture. The legend said which
    # stroke meant what, which was no use when they are separate pictures.
    "overview.stillAlive": {"en": "Still there after 30 days", "zh-Hans": "三十天后仍然还在"},
    "overview.reworkedLater": {"en": "Rewritten later", "zh-Hans": "后来被改写"},
    # Fewer than two measured weeks is not an empty chart, it is a chart that cannot be
    # drawn yet, and it should say so in words rather than leave one dot in a wide card.
    "overview.tooFewWeeks.title": {
        "en": "Not enough weeks to draw a line yet",
        "zh-Hans": "还不够画出一条线",
    },
    "overview.tooFewWeeks.detail": {
        "en": "A trend needs two measured weeks. %1$@ so far; the table below has it in full.",
        "zh-Hans": "一条趋势线至少需要两个有测量的周。目前有 %1$@；下面的表格里是完整的数字。",
    },
    "unit.measuredWeeks": {
        "en": {"one": "%1$lld measured week", "other": "%1$lld measured weeks"},
        "zh-Hans": {"other": "%1$lld 个有测量的周"},
    },
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
