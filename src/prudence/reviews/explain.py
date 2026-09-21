"""The "what this means" segment: the one place a model is allowed to write in a review.

Design-for-change rule 10 states the contract this module keeps: **model output is a
segment, never the review.** The page above it is complete and correct without a model;
this adds a paragraph that says which of the figures already on the page stand out and
one thing the user may try, and it is stored beside the exact list of numbers it was
given so that the claim "it invented nothing" is a test rather than an assurance.

What is sent is a compressed form of the stored row and nothing else: section titles,
their rows and notes, and the numbers inventory. No transcript text, no message text, no
file contents, at any capture level. `sent_summary` builds the receipt the CLI prints
before the call, so the user sees the shape of what leaves before it leaves.

What comes back is checked before it is stored. `check_numbers` reads every number-like
token in the text; any that is not in the list the model was given makes the segment
refused, unstored and reported, because a segment with a number nobody computed is worse
than no segment (principle 2).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from prudence.model import Model, Request, Sent
from prudence.model import language as language_module
from prudence.model.guard import Verdict, complete_checked
from prudence.model.numbers import check_numbers, numbers_in
from prudence.model.recorded import input_hash
from prudence.reviews import schema

# Bumped whenever the system prompt changes. A stored segment carries the version that
# wrote it, so two segments written months apart can be told apart without guessing from
# their prose.
# 2: the first live run graded the work ("which is solid", "a substantial shift"), so the
# rule against grading moved from implicit to stated, and `tone.check_tone` now enforces it.
# 3: the last line names the output language, in that language (`model/language.py`).
EXPLAIN_PROMPT_VERSION = 3

MAX_WORDS = 180
DEFAULT_MAX_TOKENS = 600

RULES = f"""\
You are writing one short segment at the end of a developer's own work review. The
review is already written and every figure in it was computed from that developer's own
recorded sessions and commits before you were called.

You are given two things: the review's sections as JSON, and a list of every number that
appears on the page.

Write at most {MAX_WORDS} words in plain language, covering two things:
1. What stands out in these numbers, in the developer's own terms.
2. One thing they may want to try, phrased as a suggestion they are free to ignore.

Rules, all of them hard:
- Use only numbers that appear in the list you were given. Never estimate, extrapolate,
  round differently, or introduce a figure of your own. If a number would help and it is
  not in the list, say what the record does not show instead.
- Do no arithmetic. Do not add figures together and do not work out a total, an average,
  a difference, a ratio or a percentage of your own.
- Cite session ids exactly as they are written where a section carries them.
- Describe; never grade. Say what the numbers are and what they are connected to, and
  stop there. No scores, no rankings, no percentiles, no streaks, and no word that
  judges the work: not solid, good, strong, healthy, impressive, poor, weak, concerning,
  worrying, substantial or dramatic, and nothing else of that kind. "92% coverage" is a
  fact; "92% coverage, which is solid" is a verdict, and a verdict is not yours to give.
- No praise and no criticism. Do not tell the developer they did well or badly, and do
  not soften or dramatise a number by the words you put around it.
- Never compare this developer with other people, with an average, or with "most
  developers". You have no data about anyone else and any such sentence would be made up.
- Do not repeat the tables. The reader has just read them.
- No headings and no bullet lists. Two or three short paragraphs of plain prose.
"""


def system(language: str = language_module.DEFAULT) -> str:
    """The rules, and then one line naming the language to answer in, in that language.

    The language line is last and on its own, so the rules above it are byte-identical
    across languages: the long half of the prompt is the cached half, and a user who
    switches language keeps every rule they had.
    """
    return f"{RULES}\n{language_module.instruction(language)}\n"


# The English rendering, which is what a caller that says nothing gets.
SYSTEM = system()


@dataclass(frozen=True)
class Segment:
    """One model-written segment and everything needed to judge it later.

    A segment that did not pass carries its verdict and its text is never printed or
    stored: the caller reads `verdict`, says what was wrong, and drops the rest.
    """

    text: str
    model: str
    prompt_version: int
    input_hash: str
    numbers: list[dict[str, Any]]
    verdict: Verdict
    language: str = language_module.DEFAULT

    @property
    def invented(self) -> list[str]:
        return self.verdict.invented

    @property
    def ok(self) -> bool:
        return self.verdict.ok

    def credit(self) -> str:
        """The line printed under the segment, naming the model and the check it passed."""
        return (
            f"Written by {self.model}; every number checked against the review's "
            f"{len(self.numbers)} numbers."
        )


def numbers_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The review's numbers inventory: what the model may use, and what is stored."""
    numbers = payload.get("numbers")
    return [item for item in numbers if isinstance(item, dict)] if isinstance(numbers, list) else []


def allowed_numbers(payload: dict[str, Any]) -> list[str]:
    """Every figure the model was shown, which is the inventory plus the section prose.

    The inventory is the page's arithmetic. The sections also carry sentences with
    numbers in them ("commits whose 7-day mark fell inside this range", "fact version
    2"), and those were in the prompt too, so quoting one is not an invention. Both go
    into the check; only the inventory is stored and counted in the credit line.
    """
    allowed = [str(item.get("text", "")) for item in numbers_of(payload)]
    for section in payload.get("sections", []):
        if not isinstance(section, dict):
            continue
        for note in section.get("notes") or []:
            allowed.extend(numbers_in(str(note)))
        for row in section.get("rows") or []:
            for cell in row:
                allowed.extend(numbers_in(str(cell)))
    return [item for item in allowed if item]


def section_names(payload: dict[str, Any]) -> tuple[str, ...]:
    """The keys of the sections that carried something, for the "what was sent" line."""
    names: list[str] = []
    for section in payload.get("sections", []):
        if isinstance(section, dict) and section.get("key"):
            names.append(str(section["key"]))
    return tuple(names)


def prompt_body(payload: dict[str, Any]) -> str:
    """The user half of the call: the sections, then the numbers list, as JSON.

    Built from the stored row and nothing else, so it can be rebuilt from a review a
    year later and hashed to the same value.
    """
    sections = [
        {
            "key": section.get("key"),
            "title": section.get("title"),
            "headers": section.get("headers"),
            "rows": section.get("rows"),
            "notes": section.get("notes"),
            "empty": section.get("empty"),
        }
        for section in payload.get("sections", [])
        if isinstance(section, dict)
    ]
    body = {
        "scope": payload.get("project_name") or "every project",
        "window": payload.get("window"),
        "sections": sections,
        "numbers": [
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "text": item.get("text"),
                "coverage": item.get("coverage"),
            }
            for item in numbers_of(payload)
        ],
    }
    return json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True)


def build_request(
    payload: dict[str, Any],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    language: str = language_module.DEFAULT,
) -> Request:
    """The whole call, with the receipt the surface prints before making it."""
    user = prompt_body(payload)
    prompt = system(language)
    return Request(
        system=prompt,
        user=user,
        max_tokens=max_tokens,
        sent=Sent(
            sections=section_names(payload),
            numbers=len(numbers_of(payload)),
            content=False,
            bytes=len(prompt.encode()) + len(user.encode()),
            language=language,
        ),
    )


def explain(
    payload: dict[str, Any],
    model: Model,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    call: Any = None,
    language: str = language_module.DEFAULT,
) -> Segment:
    """Make the call and check the answer. Storing it is the caller's decision.

    `call` is how a surface injects its own "print the receipt, then complete": the CLI
    passes `cli.modelio.run` so the user reads what is being sent before it is sent, and
    a caller that wants no printing passes nothing.

    A draft that breaks either guard is sent back once with its offending tokens named
    (`model/guard.py`); only what comes out of that is returned, verdict and all. The
    `input_hash` stored is the first request's, because that is the identity of the
    prompt the segment answers, not of the argument it took to get there.
    """
    request = build_request(payload, max_tokens=max_tokens, language=language)
    completion, verdict = complete_checked(
        model, request, allowed_numbers(payload), call=call, language=language
    )
    return Segment(
        text=completion.text.strip(),
        model=completion.model,
        prompt_version=EXPLAIN_PROMPT_VERSION,
        input_hash=input_hash(request),
        numbers=numbers_of(payload),
        verdict=verdict,
        language=language,
    )


def store(
    connection: sqlite3.Connection, review_id: int, segment: Segment, created_at: str
) -> None:
    """Write a checked segment onto its review row. Refuses one that did not pass."""
    if not segment.ok:
        raise ValueError("; ".join(segment.verdict.reasons()))
    schema.store_segment(
        connection,
        review_id,
        text=segment.text,
        prompt_version=segment.prompt_version,
        model=segment.model,
        input_hash=segment.input_hash,
        numbers=segment.numbers,
        created_at=created_at,
        language=segment.language,
    )


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "EXPLAIN_PROMPT_VERSION",
    "MAX_WORDS",
    "RULES",
    "SYSTEM",
    "Segment",
    "allowed_numbers",
    "build_request",
    "check_numbers",
    "explain",
    "numbers_of",
    "prompt_body",
    "section_names",
    "store",
    "system",
]
