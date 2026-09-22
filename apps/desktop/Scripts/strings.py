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
    # --- the Review screen ------------------------------------------------------------
    # A stored review's own titles, notes and empty sentences are the engine's English
    # and the screen prints them as stored: they are the record of what the user was
    # told, and rewriting them would make the page disagree with the Markdown report.
    # Everything below is the screen's own furniture, which is the reader's language.
    # The catalog was written for the Swift app's shorter review sheet, so it has the
    # tags, the empty state and the segment line, and no section titles.
    "review.section.did": {"en": "What you did", "zh-Hans": "你做了什么"},
    "review.section.became": {
        "en": "What became of earlier work",
        "zh-Hans": "更早的工作后来怎么样了",
    },
    "review.section.compared": {
        "en": "Compared with the previous period",
        "zh-Hans": "与上一期相比",
    },
    "review.section.suggestions": {"en": "Last time's suggestions", "zh-Hans": "上次留下的建议"},
    # One caption per card: principle 3 asks for the method stated to a reader. The
    # engine's own notes name the views and the fact versions and go behind the
    # disclosure, exactly as the Overview's charts do.
    "review.did.note": {
        "en": "The sessions of the period, grouped by the purpose their tool mix was labelled with, and the commits credited to them. A dash is a session that recorded no usage fields at all, which is not zero tokens.",
        "zh-Hans": "这一时段的会话，按工具组合判定出的用途分组，以及计入这些会话的提交。短横线表示那个会话根本没有记录用量字段，而不是零 token。",
    },
    "review.became.note": {
        "en": "Of the lines written by the commits in the outcome window, how many were still there later and how many you rewrote. Every share carries the number of lines it is over, and the pale underlay behind each bar is how much of that work the sessions themselves wrote.",
        "zh-Hans": "在结果窗口内的提交所写下的代码行中，后来还有多少留着，又有多少被你自己改写。每个比例都标出了它所基于的行数；每根条形背后的浅色底衬，是这些工作里由会话自己写下的比例。",
    },
    "review.observations.note": {
        "en": "Each row splits your own sessions in two at one threshold and takes each side's median. They describe what happened; they are not advice, and neither side is the better one.",
        "zh-Hans": "每一行都把你自己的会话按某个阈值分成两边，各取中位数。它们描述已经发生的事，不是建议，也无所谓哪一边更好。",
    },
    "review.compared.note": {
        "en": "The same figures over the period of the same length immediately before this one. A period that measured nothing is a dash, never a zero.",
        "zh-Hans": "把同样的数字放到紧挨着的、等长的上一期旁边看。某一期没有测到的，写成短横线，而不是零。",
    },
    "review.suggestions.note": {
        "en": "What became of the suggestions an earlier review left open.",
        "zh-Hans": "更早的回顾留下、还没有处理的建议，后来怎么样了。",
    },
    # The two ranges are different windows and the screen must not let them read as one:
    # outcomes are measured over commits old enough to have been followed, which is a
    # window behind the activity window. How far behind is the engine's own constant and
    # is left to the engine's note rather than restated here, where it would go stale in
    # silence.
    "review.rangeLine": {
        "en": "Period reviewed: %1$@ to %2$@. Outcomes are measured over a different window: the commits made between %3$@ and %4$@.",
        "zh-Hans": "回顾的时段：%1$@到%2$@。成果部分用的是另一个窗口：%3$@到%4$@之间的提交。",
    },
    "review.picker": {"en": "Earlier reviews", "zh-Hans": "更早的回顾"},
    # The button is drawn now and wired when the engine wiring lands. It says which, so
    # that a reader who presses it is not left wondering whether it failed.
    "review.notWired": {
        "en": "Review now runs the engine, and that wiring arrives with the next delivery. Until then, `prudence review` in a terminal writes one.",
        "zh-Hans": "「立即回顾」需要调用引擎，这部分接线会在下一次交付里完成。在那之前，可以在终端里运行 `prudence review` 写一份。",
    },
    "review.segment.none": {
        "en": "No model segment was written for this review. `prudence review --explain` writes one, and every figure in it has to be one of the review's own numbers.",
        "zh-Hans": "这份回顾没有模型写的段落。`prudence review --explain` 可以写一段；其中出现的每个数字，都必须是这份回顾自己算出的数字。",
    },
    # The list is scoped by the project picker above the screen, so an empty list there
    # means something different from an empty store and has to say which.
    "review.emptyForProject.title": {
        "en": "No review of %1$@ yet",
        "zh-Hans": "还没有关于 %1$@ 的回顾",
    },
    "review.emptyForProject.detail": {
        "en": "Your other projects' reviews are still there: choose All projects above. `prudence review --project %1$@` writes one for this project.",
        "zh-Hans": "其他项目的回顾还在：在上方选择「全部项目」就能看到。要给这个项目写一份，运行 `prudence review --project %1$@`。",
    },
    # Not the Overview's "Commits in range". A review counts the commits **credited to
    # the sessions of its period**, which is a different question from the commits made
    # on the days of that period: over the founder's own review 1 the two are 18 and 32.
    # Two measures under one caption is the defect this key exists to keep out.
    "review.did.commits": {"en": "Commits", "zh-Hans": "提交"},
    "review.did.commitsFoot": {
        "en": "credited to these sessions",
        "zh-Hans": "计入这些会话的提交",
    },
    # Short enough to sit under a figure. It said "over the commits in the outcome
    # window", which is a different commit set: `did.coverage` is the engine's "mean
    # coverage of those commits", and "those commits" is `did.commits`, the ones credited
    # to the sessions that started inside the **period reviewed**. Only `became.coverage`
    # is over the outcome window. On the founder's own review the page contradicted
    # itself: 92% over a commit set the card below described as empty.
    "review.did.coverageFoot": {
        "en": "over the commits credited to these sessions",
        "zh-Hans": "基于计入这些会话的那些提交",
    },
    # And the sentence behind the disclosure, for the same reason. The catalogue's
    # `review.coverageHelp` names the outcome window and is right where it came from, on
    # the outcomes card; it is wrong on this one.
    "review.did.coverageHelp": {
        "en": "The mean share of a counted commit's added lines the session itself wrote, over the commits credited to the sessions of the period reviewed.",
        "zh-Hans": "在计入本期各个会话的提交里，由会话本人写下的新增代码行所占比例的平均值。",
    },
    # Design rule 3: the sentence is composed in the reader's language from the review's
    # own numbers, and the engine's English stays beside it as the thing to check it
    # against. This is the disclosure that English lives behind.
    "review.observations.stored": {
        "en": "The sentences as the review stored them",
        "zh-Hans": "这些句子在回顾中存储时的原文",
    },
    # The Observations screen. The catalog's `observations.empty.pooled.*` is written for
    # the Swift window, which showed only the pooled rows under "All projects" and could
    # therefore tell the reader to pick a project. This screen shows every row there is,
    # so an empty list means the engine found nothing anywhere, and the detail has to say
    # which floors were not cleared rather than send the reader to a picker that would
    # show the same nothing.
    # Not `menu.noObservation`: the panel shows one row and says "No observation yet" in
    # the singular, which is a different statement from a whole screen finding none. The
    # Chinese has no plural to carry that difference, so it carries it with 任何.
    "observations.empty.all.title": {"en": "No observations yet", "zh-Hans": "还没有任何观察"},
    "observations.empty.all.detail": {
        # No numbers. The engine owns the two floors (`observations.MIN_SESSIONS` and
        # `MIN_GAP`) and publishes its own sentence naming them; this said "five" and
        # "ten points" from a second copy, so raising a floor in Python would leave the
        # app confidently telling the reader the old one. Describing the shape of the
        # rule cannot go stale.
        "en": "An observation needs enough sessions on both sides of a threshold, and a wide enough gap between the two medians. No behaviour in this store clears both floors yet. Nothing is wrong with your store.",
        "zh-Hans": "一条观察需要某个阈值两侧都有足够多的会话，并且两个中位数之间的差距足够大。这个库里还没有任何行为同时满足这两条。你的库没有问题。",
    },
    # The range picker sits above this screen and changes nothing on it: an observation is
    # computed over every session in the store, and there is no date window anywhere in
    # `store/observations.py`. Until the route table can ask for the project picker
    # without the range one, the screen says so, rather than let "8 weeks" above a figure
    # imply the figure is about eight weeks.
    "observations.allSessions": {
        "en": "Every row here is computed over every session on record, not over a date range.",
        "zh-Hans": "这里的每一行都是基于全部有记录的会话算出来的，不限定时间范围。",
    },
    # The sort rule, said out loud, with what it is not. A list ordered by size reads as a
    # ranking unless something says otherwise, and this product has no score in it.
    "observations.sortedByGap": {
        "en": "The behaviour whose two medians are furthest apart comes first. That is how the list is arranged, not a ranking of what matters.",
        "zh-Hans": "两个中位数相差最大的行为排在最前面。这只是列表的排列方式，不是重要性的排名。",
    },
    # Principle 3, the half that goes behind the disclosure: the view and the columns, for
    # a reader who wants to go and check. The card's own caption states the method in
    # words; this states where to go and look.
    "observations.method": {
        "en": "Both figures on a card are medians the engine took, one per side of the split, read from the app_observation view: with_value over with_n sessions and without_value over without_n sessions, with coverage, fact_commits and inferred_commits from the same row. The app prints them and derives nothing from them.",
        "zh-Hans": "卡片上的两个数字都是引擎取的中位数，分界的两边各一个，来自 app_observation 视图：with_value 基于 with_n 个会话，without_value 基于 without_n 个会话；coverage、fact_commits 和 inferred_commits 取自同一行。应用只把它们印出来，不在它们之上再算任何东西。",
    },
    # The interface words the threshold itself at contract 3 (threshold_op and
    # threshold_value), so the engine's own English clause is kept where a reader can
    # check the rewording against it. On an older store it is the only thing there is.
    "observations.method.threshold": {
        "en": "The engine's own words for this split: %1$@.",
        "zh-Hans": "引擎自己对这个分界的表述：%1$@。",
    },
    # The paired bars in words, for a screen reader and for the caption. One key, because
    # the two joins and the full stops belong to the language, not to JavaScript.
    "observations.pairReading": {
        "en": "%1$@: %2$@. %3$@: %4$@.",
        "zh-Hans": "%1$@：%2$@。%3$@：%4$@。",
    },
    # Which version of the engine's rules produced these rows, and which contract the app
    # read them under. Two rows that disagree across an upgrade should be explainable.
    "observations.version": {
        "en": "observation fact version %1$@, app contract %2$@",
        "zh-Hans": "观察事实版本 %1$@，应用契约 %2$@",
    },
    # --- the engine ------------------------------------------------------------------
    # The catalog has the dropdown's words for the engine (`menu.engineMissing`,
    # `menu.engineChecking`, `settings.enginePath` and its note) and the review's
    # readiness panel, because the Swift app had both. What it has nothing for is the
    # desktop's own engine block: a third way the executable can be found, the two
    # versions side by side, and a failure said in a word rather than a raw exit code.
    #
    # Where an executable came from. The catalog has "from Settings" and "found
    # automatically"; the login-shell probe is the third answer the search can give and a
    # reader should be told when it was needed, because it is the slow one.
    "engine.source.loginShell": {
        "en": "found through your login shell",
        "zh-Hans": "通过登录 shell 找到",
    },
    # The version and where the file came from, on one line. One key rather than two
    # joined with a comma in JavaScript: the order and the punctuation belong to the
    # language.
    "engine.versionAndSource": {
        "en": "version %1$@, %2$@",
        "zh-Hans": "版本 %1$@，%2$@",
    },
    # The CLI on this machine and the engine that wrote the store are two different
    # installations and can be two different versions. Said calmly: both are readable,
    # and the app supports more than one store contract, so this is worth knowing rather
    # than worth stopping for.
    "engine.versionMismatch": {
        "en": "The engine on this machine is version %1$@, and the store was last written by %2$@. Both still read; the next ingest will be written by %1$@.",
        "zh-Hans": "这台机器上的引擎是 %1$@ 版，而这个库上次是由 %2$@ 写入的。两者都还能读；下一次采集会由 %1$@ 写入。",
    },
    # Nothing was found. The title is the dropdown's `menu.engineMissing`; this is the
    # line under it, and it has to say what stops working and what to do about it.
    "engine.notFound.detail": {
        "en": "Nothing can be ingested or reviewed until it is found. Choose the file yourself if it is installed somewhere this search does not look.",
        "zh-Hans": "找不到它，就没法采集，也没法写回顾。如果它装在这些位置之外，可以自己选择那个文件。",
    },
    # After an ingest. `menu.ingestFinishedSessions` reads as "this run ingested N
    # sessions", which is not what the figure is: `parsed.sessions` is how many sessions
    # the store holds once the run is done. This says that instead of implying the other.
    "engine.ingestFinished.sessions": {
        "en": "Ingest finished. The store now holds %1$@.",
        "zh-Hans": "采集完成。这个库现在有 %1$@。",
    },
    # A run that failed. The title, then one line naming which kind of failure it was,
    # then the engine's own words underneath it. The engine's words are English, as the
    # store's own errors are.
    "engine.failed.title": {"en": "The engine did not finish", "zh-Hans": "引擎没有跑完"},
    "engine.error.launch": {
        "en": "It could not be started.",
        "zh-Hans": "它没能启动。",
    },
    "engine.error.failed": {
        "en": "It ran and stopped with an error.",
        "zh-Hans": "它跑起来了，但中途报错停下。",
    },
    # "not found" means two different things: nothing anywhere (which the dropdown's
    # `menu.engineMissing` already says) and "the file you chose is not something this
    # app can run". Only the second one needs words of its own.
    "engine.error.notExecutable": {
        "en": "That file is not something this app can run.",
        "zh-Hans": "那个文件不是这个应用能运行的程序。",
    },
    "engine.error.noVersion": {
        "en": "That file does not answer `--version` as the Prudence engine.",
        "zh-Hans": "那个文件对 `--version` 的回答不像是 Prudence 引擎。",
    },
    # Two surfaces can both ask for a run, and the engine takes an ingest lock of its
    # own, so the second one has to be told rather than queued behind the first.
    "engine.busy": {
        "en": "A run is already going. Wait for it to finish.",
        "zh-Hans": "已经有一次在跑了，等它跑完。",
    },
    # The picker, when what was chosen is not an engine. A chosen path is verified before
    # it is remembered, so this is what the user sees instead of a path that is kept and
    # then fails at every action.
    "engine.rejected": {
        "en": "That file was not kept: %1$@",
        "zh-Hans": "那个文件没有被采用：%1$@",
    },
}

# Keys the catalog has wrong. Each one needs a reason, and each one is a divergence from
# the Swift app that somebody has to carry back if that app is ever unfrozen.
DESKTOP_OVERRIDES = {
    # Six keys that put a literal space next to a placeholder the interface fills with a
    # **Chinese-formatted date**. A space between Latin or digits and Chinese is correct
    # and the catalogue is right to use it everywhere else; between two runs of Chinese it
    # is not, and `Fmt.day` in Chinese returns "2026年9月7日". So "%1$@ 当周" renders
    # "2026年9月7日 当周", which no Chinese writer would type. English is untouched: there
    # the placeholder is Latin and the space is required.
    #
    # Seen in the Chinese screenshot of the Overview against a copy of the real store,
    # 2026-09-21, and then swept for across the whole catalogue.
    "overview.weekOf": {"en": "Week of %1$@", "zh-Hans": "%1$@当周"},
    "overview.weekFilter": {
        "en": "The cards above are the week of %1$@: %2$@ tokens.",
        "zh-Hans": "上方的卡片只统计%1$@那一周：%2$@ tokens。",
    },
    "review.headline": {"en": "Review %1$@, %2$@ to %3$@", "zh-Hans": "回顾 %1$@，%2$@到%3$@"},
    "review.headline.project": {
        "en": "Review %1$@, %2$@ to %3$@, %4$@",
        "zh-Hans": "回顾 %1$@，%2$@到%3$@，%4$@",
    },
    "range.since": {"en": "Since %1$@", "zh-Hans": "自%1$@起"},
    # And an ASCII hyphen between a number and a Chinese date, which wants a Chinese comma.
    "review.option": {"en": "Review %1$@ - %2$@", "zh-Hans": "回顾 %1$@，%2$@"},
    # The catalog says "%1$@ 个会话" - "%1$@ sessions". The number is a count of **lines**
    # in both places it is used (`measured_30d` and `lines` are both over `line_fate`), so
    # the Chinese claimed a unit the figure does not have, on the one caption whose job is
    # to make a share checkable. English was unit-free and is now explicit too.
    "chart.sampleSize": {"en": "n=%1$@ lines", "zh-Hans": "n=%1$@ 行"},
    # The catalog says "%1$@ 做了，%2$@ 个没做". The first placeholder is filled with a
    # session phrase ("16 个会话"), so the space in front of 做了 puts a gap in the middle
    # of a Chinese clause: "16 个会话 做了". Chinese does not space its words, and the
    # space only looks deliberate because the English template has one.
    "observation.sessionsDidDidNot": {
        "en": "%1$@ did, %2$@ did not",
        "zh-Hans": "%1$@做了，%2$@ 个没做",
    },
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
