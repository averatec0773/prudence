"""One model call over retrieved evidence, with the same number guard the review uses.

Journey decision D2 in one function. `ask(...)` is written so that the CLI, and later the
MCP tool, call exactly the same thing and get exactly the same text: the surfaces differ
in how they print an `Answer`, never in how one is produced.

The guard is the same as the review's, for the same reason (principle 2). The allowed
list here is every number in the evidence payload rather than a curated inventory,
because the evidence *is* the computation: each figure came out of a view a command
prints. A number in the answer that is in no row is a number the model made up, and the
answer is refused rather than stored.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from prudence.ask import schema
from prudence.ask.parse import Question, parse
from prudence.ask.retrieve import Evidence, retrieve, tables
from prudence.model import Model, Request, Sent
from prudence.model.guard import Verdict, complete_checked
from prudence.model.numbers import numbers_in
from prudence.model.recorded import input_hash

# Bumped whenever SYSTEM changes. 2: the rule against grading, after the segment's first
# live run graded the work; `tone.check_tone` enforces it on this side too.
ASK_PROMPT_VERSION = 2

DEFAULT_MAX_TOKENS = 700
MAX_WORDS = 250

SYSTEM = f"""\
You answer one question about a developer's own recorded work, using only the evidence
below. The evidence is rows computed from their own sessions and commits; it is all you
know, and you know nothing about any other person.

Write at most {MAX_WORDS} words in plain prose. Rules, all of them hard:
- Answer from the evidence only. Every number you write must appear in it. Never
  estimate, extrapolate or round differently, and never introduce a figure of your own.
- Do no arithmetic. Do not add numbers together, and do not work out a total, an
  average, a difference, a ratio or a percentage of your own. The evidence carries a
  `totals` block with the sums and shares already computed; quote those. If a figure you
  want is in neither the rows nor `totals`, say it is not in the record.
- Cite session ids, using the first eight characters exactly as the evidence prints
  them, so the reader can run `prudence show --session <id>`.
- Say plainly what the evidence cannot tell. If the rows do not answer the question, the
  correct answer is which part is unanswerable and what would answer it.
- Coverage is part of every outcome figure. When you quote one, say what it covers.
- Describe; never grade. No scores, no rankings, and no word that judges the work: not
  solid, good, strong, healthy, impressive, poor, weak, concerning, worrying,
  substantial or dramatic, and nothing else of that kind. "92% coverage" is a fact;
  "92% coverage, which is solid" is a verdict, and a verdict is not yours to give.
- No praise and no criticism, and do not dramatise or soften a number by the words you
  put around it.
- Never compare this developer with other people or with an average; you have no data
  about anyone else.
- No headings, no bullet lists. Short paragraphs of plain prose.
"""


@dataclass(frozen=True)
class Answer:
    """One answer, the evidence it stood on, and what the guards made of it.

    `text` is present whether or not the guards passed, because `store` and the surface
    both need to know there was one. Neither prints it when `ok` is false: a refused
    answer is an impression with figures nobody computed, and it goes no further than
    this object.
    """

    question: Question
    evidence: Evidence
    text: str | None
    model: str | None
    prompt_version: int
    evidence_hash: str
    input_hash: str | None
    verdict: Verdict

    @property
    def invented(self) -> list[str]:
        return self.verdict.invented

    @property
    def ok(self) -> bool:
        return self.verdict.ok

    def as_dict(self) -> dict[str, Any]:
        """The JSON form. A refused answer carries its verdict and not its words."""
        return {
            "answer": self.text if self.ok else None,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "evidence_hash": self.evidence_hash,
            "refused_numbers": self.verdict.invented,
            "refused_words": self.verdict.graded,
            "evidence": self.evidence.as_dict(),
        }


def build_request(evidence: Evidence, max_tokens: int = DEFAULT_MAX_TOKENS) -> Request:
    """The whole call, with the receipt the surface prints before making it."""
    user = (
        f"Question: {evidence.question.text}\n\n"
        f"Evidence (computed from the developer's own record):\n{evidence.as_json()}\n"
    )
    sections = ["sessions"]
    if evidence.usage:
        sections.append("usage")
    if evidence.totals:
        sections.append("totals")
    if evidence.observations:
        sections.append("observations")
    if evidence.excerpts:
        sections.append("excerpts")
    return Request(
        system=SYSTEM,
        user=user,
        max_tokens=max_tokens,
        sent=Sent(
            sections=tuple(sections),
            numbers=len(allowed_numbers(evidence)),
            content=bool(evidence.excerpts),
            excerpts=len(evidence.excerpts),
            bytes=len(SYSTEM.encode()) + len(user.encode()),
        ),
    )


def allowed_numbers(evidence: Evidence) -> list[str]:
    """Every number in the evidence, which is every number the answer may use."""
    return numbers_in(evidence.as_json())


def ask(
    connection: sqlite3.Connection,
    text: str,
    model: Model | None = None,
    project: str | None = None,
    with_content: bool = False,
    levels: dict[str, str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    now: Any = None,
    call: Any = None,
) -> Answer:
    """Parse, retrieve and (unless `model` is None) answer. The one entry point.

    `call` is how a surface injects its own "print the receipt, then complete" wrapper:
    the CLI passes `cli.modelio.run` so the user sees the line before the call, and a
    caller that wants no printing passes nothing and gets `model.complete`.
    """
    from prudence.store import views

    names = views.repository_names(connection)
    question = parse(text, now=now, projects=names)
    if project:
        resolved = views.repo_key_for(connection, project)
        if resolved is None:
            raise LookupError(f"no recorded repository is called {project!r}")
        question.project = resolved
        if "project" not in question.matched:
            question.matched.append("project")

    evidence = retrieve(connection, question, with_content=with_content, levels=levels)
    digest = schema.evidence_hash(evidence.as_json())

    if model is None:
        return Answer(
            question=question,
            evidence=evidence,
            text=None,
            model=None,
            prompt_version=ASK_PROMPT_VERSION,
            evidence_hash=digest,
            input_hash=None,
            verdict=Verdict(),
        )

    request = build_request(evidence, max_tokens=max_tokens)
    completion, verdict = complete_checked(model, request, allowed_numbers(evidence), call=call)
    return Answer(
        question=question,
        evidence=evidence,
        text=completion.text.strip(),
        model=completion.model,
        prompt_version=ASK_PROMPT_VERSION,
        evidence_hash=digest,
        input_hash=input_hash(request),
        verdict=verdict,
    )


def store(connection: sqlite3.Connection, answer: Answer, asked_at: str) -> int:
    """Keep the question. A refused answer is stored as no answer and a note of why.

    The row is written either way, so that asking is part of the record even when the
    answer was not kept, and so that a run of refusals is visible rather than invisible.
    The words themselves are never written down.
    """
    return schema.insert(
        connection,
        asked_at=asked_at,
        question=answer.question.text,
        project=answer.question.project,
        evidence_hash=answer.evidence_hash,
        model=answer.model,
        answer=answer.text if answer.ok else None,
        refused_numbers=None if answer.ok else (answer.verdict.as_note() or None),
    )


def render(
    answer: Answer,
    names: dict[str, str] | None = None,
    evidence_first: bool = True,
    include_answer: bool = True,
) -> str:
    """The text a surface prints: the evidence, then the answer, then where it came from."""
    parts: list[str] = []
    if evidence_first:
        parts.append(tables(answer.evidence, names))
    if answer.text and answer.ok and include_answer:
        parts.append("")
        parts.append("## Answer")
        parts.append("")
        parts.append(answer.text)
        parts.append("")
        parts.append(
            f"Written by {answer.model} from the evidence above; every number checked "
            "against it. Run `prudence show --session <id>` on any session it cites."
        )
    return "\n".join(parts)
