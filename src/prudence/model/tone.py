"""The words a report about a person's own work may not use. Principle 3, as a check.

Principle 3 says: report what happened and what it was connected to, in counts the user
can check; never grade. A number is easy to guard (`numbers.check_numbers`); the grading
usually arrives as an adjective instead. "92% coverage, which is solid" adds no fact and
one verdict, and a verdict is the thing the principle rules out.

So this is the adjective half of the same guard. It is a short list of obvious words,
kept as data with its own version, and it is deliberately not a style checker: it catches
praise, blame and drama, and leaves everything else to the prompt. A word that turns out
to be a false alarm is removed from the list and the version is bumped; the list is not
grown to cover every way a sentence could be evaluative, because at that point it would
be censoring prose rather than guarding a principle.

The live run this was written for produced "which is solid", "a substantial shift" and
"clear movement" in one segment of three paragraphs, which is why it exists.

**One list per language.** A segment written in Chinese breaks the same principle with
different words, so the lists are data keyed by language code (`WORDS_BY_LANGUAGE`) and
every check also runs the English list, because a Chinese paragraph still quotes the
page's English labels. Adding a language here is one entry and a version bump; nothing
else in this module knows a language exists.
"""

from __future__ import annotations

import re

from prudence.model.language import DEFAULT

# Bumped whenever a list in WORDS_BY_LANGUAGE changes, so a stored text can be read
# against the list that passed it rather than against today's.
# 2: the zh-Hans list, for the segments M4 writes in Chinese.
TONE_VERSION = 2

# Praise, blame and drama. One list, alphabetical inside each group, short on purpose.
PRAISE = (
    "admirable",
    "commendable",
    "encouraging",
    "excellent",
    "good",
    "great",
    "healthy",
    "impressive",
    "nice work",
    "outstanding",
    "remarkable",
    "solid",
    "strong",
    "well done",
)
BLAME = (
    "alarming",
    "bad",
    "concerning",
    "disappointing",
    "poor",
    "terrible",
    "weak",
    "worrying",
)
DRAMA = (
    "clear movement",
    "dramatic",
    "dramatically",
    "striking",
    "substantial",
    "substantially",
)

WORDS: tuple[str, ...] = tuple(sorted({*PRAISE, *BLAME, *DRAMA}))

# Simplified Chinese: the same three groups, and just as short. 差 is the one most likely
# to be a false alarm, because it is a character inside ordinary words (误差, 差异); the
# rule in the docstring applies to it like any other, and it comes off the list and the
# version is bumped the first time it catches a sentence that only described.
ZH_HANS_PRAISE = ("优秀", "出色", "健康", "很棒", "良好", "稳健")
ZH_HANS_BLAME = ("差", "糟糕")
ZH_HANS_DRAMA = ("大幅", "显著")
ZH_HANS: tuple[str, ...] = tuple(sorted({*ZH_HANS_PRAISE, *ZH_HANS_BLAME, *ZH_HANS_DRAMA}))

# The list a check uses is the language's own plus English, always: a Chinese paragraph
# quotes the page's English labels and can grade in either language.
WORDS_BY_LANGUAGE: dict[str, tuple[str, ...]] = {
    "en": WORDS,
    "zh-Hans": tuple(sorted({*WORDS, *ZH_HANS})),
}


def _pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    """One matcher over a word list. `\\b` only helps the half of it that is ASCII.

    A word boundary is defined between a word character and a non-word one, and CJK is
    word characters all the way through, so `\\b优秀\\b` never matches inside a sentence
    that has no spaces in it. The two halves are matched by their own alternation.
    """
    spaced = [re.escape(word).replace(r"\ ", r"\s+") for word in words if word.isascii()]
    other = [re.escape(word) for word in words if not word.isascii()]
    parts = []
    if spaced:
        parts.append(r"\b(?:" + "|".join(spaced) + r")\b")
    if other:
        parts.append("(?:" + "|".join(sorted(other, key=len, reverse=True)) + ")")
    return re.compile("|".join(parts), re.I)


_PATTERNS: dict[str, re.Pattern[str]] = {
    code: _pattern(words) for code, words in WORDS_BY_LANGUAGE.items()
}
_PATTERN = _PATTERNS[DEFAULT]


def check_tone(text: str, language: str = DEFAULT) -> list[str]:
    """Every graded word in `text`, as written, in order. Empty means it only described.

    Duplicates are collapsed: a caller uses this to tell the model which words to drop,
    and naming "solid" three times helps nobody.
    """
    pattern = _PATTERNS.get(language, _PATTERN)
    found: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        word = match.group(0)
        key = word.lower()
        if key not in seen:
            seen.add(key)
            found.append(word)
    return found
