"""Check what came back, ask once for a correction, and refuse in silence if it persists.

Both places a model writes (a review's segment, an answer to a question) have the same
two rules and the same three outcomes, so the loop lives here once rather than twice.

**The rules.** Every number must be one the model was given (principle 2), and no word
may grade the person (principle 3). `numbers.check_numbers` and `tone.check_tone` say
which tokens broke which rule.

**The retry.** A first draft that used a figure it worked out, or called a number solid,
is usually one instruction away from a good one, and the instruction can name the exact
offending tokens. So a failed check appends that instruction and calls once more. This
costs a second call, which is why the surface prints a receipt for it like any other.

**The refusal is silent about the text.** If the second draft fails too, the caller is
given the verdict and the text is thrown away unprinted and unstored. That is the part
worth being deliberate about: a rejected draft is a model's impression carrying figures
nobody computed, and showing it under a "here is what it said, ignore the numbers"
heading puts those figures in front of the reader anyway. A person reading a review
remembers "about 40%" long after they have forgotten the disclaimer over it. The user
gets the evidence, the list of what was wrong, and the price of the attempt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from prudence.model.base import Completion, Model, Request
from prudence.model.language import DEFAULT as DEFAULT_LANGUAGE
from prudence.model.numbers import check_numbers
from prudence.model.tone import TONE_VERSION, check_tone

# Bumped when the correction sentence changes, so a retry's prompt can be identified.
CORRECTION_VERSION = 1
RETRIES = 1


@dataclass(frozen=True)
class Verdict:
    """What the two guards found. Empty on both counts is the only way to be stored."""

    invented: list[str] = field(default_factory=list)
    graded: list[str] = field(default_factory=list)
    tone_version: int = TONE_VERSION

    @property
    def ok(self) -> bool:
        return not self.invented and not self.graded

    def reasons(self) -> list[str]:
        """One sentence per broken rule, for the message the user reads."""
        said: list[str] = []
        if self.invented:
            said.append(
                "it used numbers that are in none of the rows it was given ("
                + ", ".join(self.invented)
                + "); every figure has to be computed before the model sees it"
            )
        if self.graded:
            said.append(
                "it graded the work rather than describing it ("
                + ", ".join(self.graded)
                + "); Prudence reports what happened, never how good it was"
            )
        return said

    def as_note(self) -> str:
        """The short form stored on a row instead of the refused text."""
        parts = []
        if self.invented:
            parts.append("numbers: " + ", ".join(self.invented))
        if self.graded:
            parts.append("graded: " + ", ".join(self.graded))
        return "; ".join(parts)


def judge(text: str, allowed: Any, language: str = DEFAULT_LANGUAGE) -> Verdict:
    """Both guards over one piece of model text, in the language it was asked for."""
    return Verdict(invented=check_numbers(text, allowed), graded=check_tone(text, language))


def correction(verdict: Verdict) -> str:
    """The instruction appended for the second attempt, naming what to drop."""
    lines = ["", "Your previous answer was rejected. Write it again, and this time:"]
    if verdict.invented:
        lines.append(
            "- Do not use " + ", ".join(verdict.invented) + ". None of these appear in the "
            "numbers above. Use only the figures listed, exactly as they are written, and "
            "do no arithmetic of your own."
        )
    if verdict.graded:
        lines.append(
            "- Do not use the words " + ", ".join(verdict.graded) + ", or any other word "
            "that grades the work. Say what the numbers are and what they are connected "
            "to. No praise, no criticism, no adjectives about how the period went."
        )
    lines.append("Keep everything else about the answer the same.")
    return "\n".join(lines)


def corrected(request: Request, verdict: Verdict) -> Request:
    """The same request with the correction appended. A new prompt, so a new hash."""
    return Request(
        system=request.system,
        user=request.user + "\n" + correction(verdict),
        max_tokens=request.max_tokens,
        sent=request.sent,
    )


def complete_checked(
    model: Model,
    request: Request,
    allowed: Any,
    call: Callable[[Model, Request], Completion] | None = None,
    retries: int = RETRIES,
    language: str = DEFAULT_LANGUAGE,
) -> tuple[Completion, Verdict]:
    """Call, check, and on a failure call once more with the offending tokens named.

    Returns the last completion and its verdict. A caller stores the text only when the
    verdict is `ok`, and prints nothing of it otherwise.

    The correction sentence stays English whatever the answer's language: it is an
    instruction to the model rather than prose for the reader, and naming the offending
    tokens is what it is for.
    """
    make = call if call is not None else (lambda chosen, sent: chosen.complete(sent))
    attempt = request
    completion = make(model, attempt)
    verdict = judge(completion.text, allowed, language)
    for _ in range(retries):
        if verdict.ok:
            break
        attempt = corrected(attempt, verdict)
        completion = make(model, attempt)
        verdict = judge(completion.text, allowed, language)
    return completion, verdict
