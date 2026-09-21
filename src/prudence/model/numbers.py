"""The guard that makes design-for-change rule 10 checkable rather than promised.

Principle 2 allows a model to quote, explain and compare the figures the engine computed
and forbids it to invent one. That is not a matter of prompt wording: it is a property of
the returned text, and this module is where the property is tested. Every number-like
token in the model's answer must appear in the list of numbers the model was given; the
ones that do not are handed back, and the caller refuses to store the text.

Three kinds of tolerance, because the alternative is a check that fails on correct
answers and is then switched off:

- **Presentation.** `1,204` is `1204`; `92 %` is `92%`; `26.0` is `26` when the list
  printed `26`. Rounding is compared at the coarser of the two precisions, so a model
  that writes `0.92` for a stored `0.9166` passes and one that writes `0.95` does not.
- **Dates and identifiers.** `2026-09-20` and a session id are not statistics. They are
  removed before tokenising, so citing a session (which the prompt asks for) is not a
  violation.
- **Units.** A suffix is part of the number: `713938k` matches `713938k` and not `713938`,
  and `92%` does not match `92`. A model that drops a unit has changed the claim.
- **Script.** A segment written in Chinese prints the same figures in different
  characters: `９２％` is `92%`, and `0.5万` is `5000`. `NORMALISATION` maps the
  full-width forms onto their ASCII ones and `MAGNITUDES` reads the Chinese
  ten-thousands the way the tokeniser already reads `k`, so the check neither misses an
  invented figure written in Chinese nor refuses a quoted one. The scaling is applied to
  both sides by `parse`, so `0.5万` passes against a given `5000` and fails against a
  given `5k`, which is right: a unit changed by arithmetic is a claim the model made up.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Removed before anything is tokenised: an ISO date, a session id (uuid-shaped or a long
# hex run), and a version-like dotted run that is not a measurement.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b")
# A date a person writes rather than a machine: "September 7 to 21, 2026", "7 Sep 2026".
# Without this the day numbers of a range the answer was asked to state read as invented
# statistics, which is the check failing on a correct answer.
_MONTH_NAMES = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
    "|january|february|march|april|june|july|august|september|october|november|december"
)
_WRITTEN_DATE = re.compile(
    rf"\b(?:{_MONTH_NAMES})\w*\.?\s+\d{{1,2}}(?:\s*(?:-|–|to|and)\s*\d{{1,2}})?"
    rf"(?:,?\s*\d{{4}})?\b|\b\d{{1,2}}\s+(?:{_MONTH_NAMES})\w*\.?(?:,?\s*\d{{4}})?\b",
    re.I,
)
# A four-digit year is never a measurement of the work. Allowed unconditionally rather
# than matched, because the evidence carries its years inside timestamps that the date
# rule above has already removed from the allowed side.
_YEAR = re.compile(r"\b(?:19[7-9]\d|20\d\d|21\d\d)\b")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# A hash, not a number: at least seven hex characters, one of which is a letter. The
# letter is what makes it a hash. Without that condition a seven-digit token count would
# be read as an identifier and dropped from the check, which would let a long invented
# figure through in the one place where the check is the whole point.
_HEX = re.compile(r"\b(?=[0-9a-fA-F]{7,}\b)[0-9a-fA-F]*[a-fA-F][0-9a-fA-F]*\b")

# Presentation, not meaning: the full-width characters a Chinese keyboard produces,
# mapped onto the ASCII the tokeniser below reads. Data, so a script that needs another
# row is one line here.
NORMALISATION = {
    **{chr(0xFF10 + digit): str(digit) for digit in range(10)},
    "％": "%",
    "，": ",",
    "．": ".",
    "。": ".",
    "＋": "+",
    "－": "-",
    "　": " ",
}
_NORMALISE = str.maketrans(NORMALISATION)

# A magnitude word is a multiplier, not a unit: 0.5万 is 5000, the same figure written
# another way. Applied on both sides by `parse`, so nothing is tolerated on one side and
# not the other.
MAGNITUDES = {"千": 1000.0, "万": 10000.0, "亿": 100000000.0}

# A number as a reader sees one: an optional sign, digits with optional thousands
# separators, an optional fraction, and an optional unit or magnitude word glued or
# spaced to the end.
_MAGNITUDE_CLASS = "".join(MAGNITUDES)
_TOKEN = re.compile(
    rf"[-+]?\d[\d,]*(?:\.\d+)?\s*(?:[{_MAGNITUDE_CLASS}]|%|[kKxX]\b|[kK](?=[^\w]|$))?"
)

SUFFIXES = {"%": "%", "k": "k", "x": "x"}


@dataclass(frozen=True)
class Figure:
    """One number as written: its value, its unit, and how precisely it was printed."""

    value: float
    suffix: str
    decimals: int

    def matches(self, other: Figure) -> bool:
        """True when the two would print the same at the coarser of the two precisions."""
        if self.suffix != other.suffix:
            return False
        places = min(self.decimals, other.decimals)
        return round(self.value, places) == round(other.value, places)


def normalise(text: str) -> str:
    """The same text with its full-width characters written as ASCII ones."""
    return text.translate(_NORMALISE)


def strip_identifiers(text: str) -> str:
    """Dates, session ids and commit hashes removed. They are names, not measurements."""
    for pattern in (_DATE, _WRITTEN_DATE, _UUID, _HEX, _YEAR):
        text = pattern.sub(" ", text)
    return text


def numbers_in(text: str) -> list[str]:
    """Every number-like token in a piece of text, as written, in ASCII presentation."""
    cleaned = strip_identifiers(normalise(text))
    return [match.group(0).strip() for match in _TOKEN.finditer(cleaned) if match.group(0).strip()]


def parse(token: str) -> Figure | None:
    """One written number as a `Figure`, or None when it is not one."""
    body = normalise(token).strip().replace(",", "").replace(" ", "")
    scale = 1.0
    if body and body[-1] in MAGNITUDES:
        scale = MAGNITUDES[body[-1]]
        body = body[:-1]
    suffix = ""
    if body and body[-1].lower() in SUFFIXES:
        suffix = SUFFIXES[body[-1].lower()]
        body = body[:-1]
    if not body or not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", body):
        return None
    decimals = len(body.split(".")[1]) if "." in body else 0
    if scale > 1:
        # 0.5万 is 5000 exactly: the decimals the magnitude absorbed are no longer a
        # statement about precision, and keeping them would compare 5000 against a given
        # 5000 at one decimal place for no reason.
        decimals = max(0, decimals - len(str(int(scale))) + 1)
    return Figure(value=float(body) * scale, suffix=suffix, decimals=decimals)


def allowed_figures(numbers: Iterable[object]) -> list[Figure]:
    """Every figure a model may use, read out of the list it was given.

    Each item may be a written number (`"92%"`), a bare value, or a mapping with `text`
    and `value` keys, which is the shape `reviews/build.numbers` stores.
    """
    figures: list[Figure] = []
    for item in numbers:
        for token in _candidates(item):
            figure = parse(token)
            if figure is not None:
                figures.append(figure)
    return figures


def check_numbers(text: str, numbers: Iterable[object]) -> list[str]:
    """Every number in `text` that is not in `numbers`, in the order they were written.

    An empty list means the text uses only figures it was given, which is what rule 10
    asks a stored segment to satisfy.
    """
    allowed = allowed_figures(numbers)
    invented: list[str] = []
    for token in numbers_in(text):
        figure = parse(token)
        if figure is None:
            continue
        if not any(figure.matches(known) for known in allowed):
            invented.append(token)
    return invented


def _candidates(item: object) -> list[str]:
    if isinstance(item, dict):
        # The printed text wins over the stored float. A raw 0.9166666 carries six
        # decimals, and matching at the coarser precision would then let `1` through as
        # a rounding of it; the text the model was shown (`92%`) has no such slack.
        raw = item.get("text")
        if isinstance(raw, str) and numbers_in(raw):
            return numbers_in(raw)
        value = item.get("value")
        if isinstance(value, int | float):
            return [_written(float(value))]
        return []
    if isinstance(item, int | float):
        return [_written(float(item))]
    return numbers_in(str(item))


def _written(value: float) -> str:
    """A stored float as a token. Trailing zeroes are dropped so `26.0` reads as `26`."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"
