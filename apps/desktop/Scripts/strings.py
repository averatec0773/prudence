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
    # `panel()` puts this on every card, and not every card holds a chart: the Review
    # screen has cards of prose and the Settings screen has none at all. The Chinese said
    # "how this chart is computed", which read as a mistake on all of them.
    "chart.method": {"en": "How this is measured", "zh-Hans": "这是怎么算出来的"},
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
    # --- the Settings screen ----------------------------------------------------------
    # The catalogue already carries this screen's labels from the Swift app, and they are
    # reused (`settings.store`, `settings.databasePath`, `settings.language*`). Everything
    # below is what the Swift screen did not have. Two reasons it is this much prose:
    # the desktop screen is **read-only**, because no bridge command writes a setting, so
    # where the Swift app drew a switch this one has to say what is in force and where it
    # is changed; and this is the one place a user looks to find out what the tool knows
    # about them, so the record's own promise belongs here in full.
    "settings.recorded": {"en": "What is recorded", "zh-Hans": "记录了什么"},
    "settings.recorded.note": {
        "en": "Which repositories are on record, and how much of each was kept. Counted from the sessions in the store, so this is what was recorded rather than what is configured.",
        "zh-Hans": "哪些仓库在记录里，以及每个保留了多少。这是从存储里的会话数出来的，所以它是实际记录下来的东西，不是配置里写的东西。",
    },
    "settings.recorded.method": {
        "en": "capture_level from the app_session_list view, grouped by project. A session is one row of that view, so each figure is the number of rows in one group, and the groups add up to app_status.sessions.",
        "zh-Hans": "取 app_session_list 视图的 capture_level，按 project 分组。一个会话就是该视图的一行，所以每个数字是一组里的行数，各组相加等于 app_status.sessions。",
    },
    "settings.recorded.total": {"en": "%1$@ across %2$@.", "zh-Hans": "共 %1$@，来自 %2$@。"},
    "settings.recorded.readOnly": {
        "en": "This screen reads the store and changes nothing. A repository is enabled, and its level set, with `prudence enable <repository> --level full|metadata-only`; `prudence forget` removes what was already recorded, and `prudence status` prints where the configuration file is.",
        "zh-Hans": "这个页面只读取存储，不改动任何设置。启用一个仓库并设定它的级别要用 `prudence enable <repository> --level full|metadata-only`；`prudence forget` 会删掉已经记录下来的内容，`prudence status` 会打印配置文件的位置。",
    },
    "settings.recorded.empty.title": {
        "en": "Nothing is recorded yet",
        "zh-Hans": "还没有记录任何东西",
    },
    "settings.recorded.empty.detail": {
        "en": "No session is on record. Nothing is recorded until a repository is enabled: `prudence init` walks you through it, and `prudence enable <repository> --level full` enables one directly.",
        "zh-Hans": "存储里还没有任何会话。在启用一个仓库之前不会记录任何东西：`prudence init` 会带你走一遍，`prudence enable <repository> --level full` 直接启用一个。",
    },
    "settings.column.level": {"en": "Capture level", "zh-Hans": "记录级别"},
    "settings.column.sessions": {"en": "Sessions recorded", "zh-Hans": "已记录的会话"},
    # The two levels `config.LEVELS` has. A level this build has not heard of prints as
    # the engine's own token rather than as a blank, which is the same fallback the
    # Observations screen uses for a behaviour it does not know.
    "settings.level.full": {"en": "Full", "zh-Hans": "完整"},
    "settings.level.metadataOnly": {"en": "Metadata only", "zh-Hans": "仅元数据"},
    # The product's promise, in the README's own words. It is on this screen because this
    # is where somebody comes to ask what is kept about them, and because a promise that
    # lives only in a README is a promise the app never makes.
    "settings.never": {"en": "What is never recorded", "zh-Hans": "永远不会记录的东西"},
    "settings.never.note": {
        "en": "What the record holds and what it never holds, at any capture level.",
        "zh-Hans": "记录里有什么、以及在任何记录级别下都不会有什么。",
    },
    "settings.never.archive": {
        "en": "Your sessions' own files are archived unchanged, in a local store only your account can read.",
        "zh-Hans": "你的会话文件会原样归档在本地存储里，只有你自己的账户能读。",
    },
    "settings.never.derived": {
        "en": "The tables every figure in this app is computed from hold counts, classes and keyed line hashes. They never hold message text, at any capture level.",
        "zh-Hans": "这个 App 里的每个数字都算自派生表，那些表里只有计数、分类和加密的行哈希，任何记录级别下都不会有消息正文。",
    },
    "settings.never.metadataOnly": {
        "en": "A repository at metadata-only keeps no file paths, no working directory, no command text and no line hashes: shape and counts only.",
        "zh-Hans": "级别为 metadata-only 的仓库不保留文件路径、工作目录、命令文本和行哈希，只有形状和计数。",
    },
    "settings.never.upload": {
        "en": "Nothing is uploaded anywhere, and an observation compares you only with yourself.",
        "zh-Hans": "没有任何内容会被上传，观察只拿你和你自己比较。",
    },
    # The one exception, said out loud. `reviews/explain.py` sends a compressed form of a
    # stored review and its numbers inventory, never any text, and only when asked for.
    # A screen that printed "nothing is uploaded" and stopped there would be wrong.
    "settings.never.model": {
        "en": "The one exception is `prudence review --explain`, which you have to ask for: it sends a review's own figures to the model named in your configuration, and no session text.",
        "zh-Hans": "唯一的例外是需要你主动要求的 `prudence review --explain`：它会把一次回顾自己的数字发给你配置里指定的模型，不会发送任何会话文本。",
    },
    "settings.never.employer": {
        "en": "If you enable Prudence on a work repository, check your employer's policy first.",
        "zh-Hans": "如果你要在工作仓库上启用 Prudence，请先确认你雇主的政策。",
    },
    # Where the record is. The shell reports the one path it opened; it does not report
    # the configuration's directory, so this screen does not claim to know it.
    "settings.store.note": {
        "en": "Where the record is on this machine. The app opens it read-only and never writes to it.",
        "zh-Hans": "记录在这台机器上的位置。App 以只读方式打开它，从不写入。",
    },
    "settings.databasePath.resolved": {
        "en": "Found the way the engine finds it: PRUDENCE_DATA_DIR when that is set, and this system's standard location otherwise.",
        "zh-Hans": "查找方式和引擎一致：设置了 PRUDENCE_DATA_DIR 就用它，否则用本系统的标准位置。",
    },
    "settings.store.contract": {"en": "Contract", "zh-Hans": "契约"},
    "settings.store.contract.value": {
        "en": "%1$@ in this store; this build reads %2$@.",
        "zh-Hans": "这个存储是 %1$@；这个构建能读 %2$@。",
    },
    "settings.store.method": {
        "en": "last_ingest_at, sessions and the versions below are columns of the app_status view, printed as they are. The path is the file the shell opened.",
        "zh-Hans": "last_ingest_at、sessions 以及下面的各个版本号都是 app_status 视图的列，原样打印。路径是外壳实际打开的那个文件。",
    },
    # The fact versions. They are the provenance of every figure on the other three
    # screens: a number re-derived after one of these changes can differ from one
    # computed before it, and without this there is nowhere to see which is which.
    "settings.versions": {
        "en": "What produced these figures",
        "zh-Hans": "这些数字是由什么算出来的",
    },
    "settings.versions.note": {
        "en": "Every step of the engine carries a version. A figure re-derived after one of them changed can differ from one computed before it.",
        "zh-Hans": "引擎的每一步都带一个版本号。某一步变了之后重算出来的数字，可能和变之前算出来的不一样。",
    },
    "settings.versions.column.step": {"en": "Step", "zh-Hans": "步骤"},
    "settings.versions.column.version": {"en": "Version", "zh-Hans": "版本号"},
    "settings.version.parser": {"en": "Session parser", "zh-Hans": "会话解析"},
    "settings.version.purposeRule": {"en": "Purpose rule", "zh-Hans": "用途判定规则"},
    "settings.version.commit": {"en": "Commit facts", "zh-Hans": "提交事实"},
    "settings.version.attribution": {"en": "Commit attribution", "zh-Hans": "提交归因"},
    "settings.version.outcome": {"en": "Outcome facts", "zh-Hans": "结果事实"},
    "settings.version.observation": {"en": "Observation facts", "zh-Hans": "观察事实"},
    "settings.version.hook": {"en": "Hook facts", "zh-Hans": "钩子事实"},
    # Read-only for the same reason as the rest of the screen: `PRUDENCE_FORCE_LANGUAGE`
    # and `PRUDENCE_FORCE_APPEARANCE` are screenshot hooks rather than settings, and
    # there is no command that would persist a user's choice of either.
    "settings.languageAndAppearance": {
        "en": "Language and appearance",
        "zh-Hans": "语言与外观",
    },
    "settings.languageAndAppearance.note": {
        "en": "Both follow the system, and the app has no switch for either yet. This is what is in force and where it came from.",
        "zh-Hans": "两者都跟随系统，App 目前还没有任何开关。这里写的是当前生效的设置，以及它来自哪里。",
    },
    "settings.language.forced": {
        "en": "Forced by %1$@ for this launch.",
        "zh-Hans": "本次启动由 %1$@ 强制指定。",
    },
    "settings.language.fromSystem": {
        "en": "Followed from the system's language when the app started.",
        "zh-Hans": "App 启动时跟随了系统语言。",
    },
    "settings.appearance": {"en": "Appearance", "zh-Hans": "外观"},
    "settings.appearance.system": {"en": "Follows the system", "zh-Hans": "与系统一致"},
    "settings.appearance.note": {
        "en": "Light and dark come from the system appearance and change without a relaunch. The app has no override of its own.",
        "zh-Hans": "浅色和深色来自系统外观，切换时不需要重启 App。App 自己没有覆盖选项。",
    },
    "settings.about": {"en": "About", "zh-Hans": "关于"},
    "settings.about.note": {
        "en": "Which pieces are running, and where the project is.",
        "zh-Hans": "正在运行的是哪些部分，以及项目在哪里。",
    },
    "settings.about.app": {"en": "App version", "zh-Hans": "App 版本"},
    # Deliberately not "engine version": this is the version that last wrote to the
    # store, which is not necessarily the executable on the user's PATH today. The
    # executable and its own version belong to `ui/engine-section.js`.
    "settings.about.engine": {
        "en": "Engine that wrote this store",
        "zh-Hans": "写入该存储的引擎",
    },
    "settings.about.licence": {"en": "Licence", "zh-Hans": "许可协议"},
    "settings.about.project": {"en": "Project home", "zh-Hans": "项目主页"},
    "settings.about.platform": {"en": "Platform", "zh-Hans": "平台"},
    "settings.about.platform.note": {
        "en": "What the shell reports about this machine, in its own words. Worth quoting when something about the window looks wrong.",
        "zh-Hans": "外壳用它自己的说法报告的本机信息。窗口哪里看起来不对时，把这些一起贴出来会有帮助。",
    },
    "settings.about.method": {
        "en": "The app's version is this build's own. The engine's is app_status.engine_version, which is the version that last wrote to the store.",
        "zh-Hans": "App 版本是这个构建自己的版本。引擎版本取自 app_status.engine_version，也就是最后一次写入存储的那个版本。",
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
