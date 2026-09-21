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
"""

from __future__ import annotations

import re

# Bumped whenever WORDS changes, so a stored text can be read against the list that
# passed it rather than against today's.
TONE_VERSION = 1

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

_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(word).replace(r"\ ", r"\s+") for word in WORDS) + r")\b",
    re.I,
)


def check_tone(text: str) -> list[str]:
    """Every graded word in `text`, as written, in order. Empty means it only described.

    Duplicates are collapsed: a caller uses this to tell the model which words to drop,
    and naming "solid" three times helps nobody.
    """
    found: list[str] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text):
        word = match.group(0)
        key = word.lower()
        if key not in seen:
            seen.add(key)
            found.append(word)
    return found
