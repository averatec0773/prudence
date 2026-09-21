"""The evidence one question gets: sessions, what they cost, what became of them.

Nothing here is computed. Every figure was already produced by `store/views` for a
command the user can run themselves, which is what makes an answer checkable: the model
is handed the same rows `prudence sessions`, `prudence usage` and `prudence observations`
print, and the user can re-derive any figure in the answer from one of those commands.

Three limits, all constants rather than judgements made at the call site:

- `MAX_SESSIONS` caps how many sessions are evidence, because a question over a year
  would otherwise send a year.
- `MAX_BYTES` caps the whole payload, and the trim happens from the oldest session
  forward so the answer is about recent work when it cannot be about all of it.
- `MAX_EXCERPTS` caps `--with-content`, which is off unless asked for and is refused
  outright for a project recorded at `metadata-only` (there is nothing to excerpt).

Transcript text is never read unless `--with-content` is passed and every candidate
project is `full`. That is principle 1 in code rather than in a promise: the default
path of this module cannot reach a message.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from prudence.ask.parse import Question
from prudence.store import views

MAX_SESSIONS = 12
MAX_OBSERVATIONS = 8
MAX_BYTES = 24 * 1024
MAX_EXCERPTS = 6
EXCERPT_CHARS = 200


@dataclass
class Evidence:
    """Everything the model is given, and everything `--no-model` prints."""

    question: Question
    sessions: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    totals: dict[str, Any] = field(default_factory=dict)
    observations: list[dict[str, Any]] = field(default_factory=list)
    excerpts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    total_found: int = 0
    trimmed: int = 0

    @property
    def session_ids(self) -> list[str]:
        return [row["session_id"] for row in self.sessions]

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question.as_dict(),
            "sessions": self.sessions,
            "usage": self.usage,
            "totals": self.totals,
            "observations": self.observations,
            "excerpts": self.excerpts,
            "notes": self.notes,
            "sessions_found": self.total_found,
            "sessions_dropped": self.trimmed,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @property
    def empty(self) -> bool:
        return not self.sessions and not self.observations


def retrieve(
    connection: sqlite3.Connection,
    question: Question,
    with_content: bool = False,
    levels: dict[str, str] | None = None,
) -> Evidence:
    """The rows this question is answered from. Reads only; computes nothing."""
    evidence = Evidence(question=question)
    found = views.search_sessions(
        connection,
        query=question.search,
        repo_key=question.project,
        since=question.since,
        until=question.until,
        limit=MAX_SESSIONS,
    )
    results = list(found.get("results", []))
    evidence.total_found = int(found.get("total", len(results)))

    # A term that matches nothing is worse than no term: it turns a question about a
    # period into an empty answer. Fall back to the range alone and say so.
    if not results and question.search:
        wider = views.search_sessions(
            connection,
            query="",
            repo_key=question.project,
            since=question.since,
            until=question.until,
            limit=MAX_SESSIONS,
        )
        results = list(wider.get("results", []))
        evidence.total_found = int(wider.get("total", len(results)))
        if results:
            evidence.notes.append(
                f"Nothing matched {question.search!r} in a file path or a command class, "
                "so this is every session in the range instead."
            )

    evidence.sessions = results
    evidence.usage = views.usage_summary(
        connection,
        since=question.since,
        until=question.until,
        repo_key=question.project,
    )
    evidence.totals = totals_of(evidence.usage)
    evidence.observations = views.observations(connection, question.project)[:MAX_OBSERVATIONS]

    if question.since or question.until:
        evidence.notes.append(
            f"Range: {(question.since or 'the beginning')[:10]} to "
            f"{(question.until or 'now')[:10]}"
            + (f" ({question.range_label})." if question.range_label else ".")
        )
    if evidence.total_found > len(evidence.sessions):
        evidence.notes.append(
            f"{evidence.total_found} sessions matched; the {len(evidence.sessions)} most "
            "recent are the evidence."
        )

    if with_content:
        evidence.excerpts, note = excerpts(connection, evidence, levels or {})
        if note:
            evidence.notes.append(note)

    _trim(evidence)
    return evidence


def totals_of(usage: dict[str, Any] | None) -> dict[str, Any]:
    """The sums and shares a reader of the usage table would work out themselves.

    They exist because the first live run of `ask` showed a model adding four session
    token counts together and dividing them, and the number guard refusing the answer
    for it. The guard was right: principle 2 says every figure is computed before the
    model sees it. So the engine computes them, here, once, and the model quotes them.
    """
    if not usage or not usage.get("sessions"):
        return {}
    by_purpose = usage["by_purpose"]
    per_purpose = {
        label: sum(cell.get(column, 0) for column in views.TOKEN_COLUMNS)
        for label, cell in by_purpose.items()
    }
    measured = any(cell.get("measured") for cell in by_purpose.values())
    total = sum(per_purpose.values())
    return {
        "sessions": usage["sessions"],
        "tokens": total if measured else None,
        "tokens_thousands": _thousands(total) if measured else "-",
        "active_hours": round(sum(cell["hours"] for cell in by_purpose.values()), 1),
        "by_purpose": {
            label: {
                "sessions": by_purpose[label]["sessions"],
                "tokens": tokens,
                "tokens_thousands": _thousands(tokens),
                "share_of_tokens": f"{tokens / total * 100:.0f}%" if total else "-",
                "active_hours": round(by_purpose[label]["hours"], 1),
            }
            for label, tokens in sorted(per_purpose.items(), key=lambda item: -item[1])
        },
    }


def excerpts(
    connection: sqlite3.Connection, evidence: Evidence, levels: dict[str, str]
) -> tuple[list[dict[str, Any]], str | None]:
    """Short archive excerpts around the question's terms, for `full` projects only.

    This is the one function in the package that opens the archive. It is reached only
    when the user passed `--with-content`, it refuses any session whose project is not
    recorded at `full`, and it caps both the number of excerpts and their length, so
    that "the user asked for content" never becomes "the whole transcript left".
    """
    from prudence.store import archive

    terms = [term for term in ([*evidence.question.quoted, *evidence.question.terms]) if term]
    if not terms:
        return [], "No search term to excerpt around, so no transcript content was read."

    allowed = [
        row
        for row in evidence.sessions
        if levels.get(_repo_key(connection, row["session_id"]), "full") == "full"
    ]
    refused = len(evidence.sessions) - len(allowed)
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.I)

    found: list[dict[str, Any]] = []
    for row in allowed:
        if len(found) >= MAX_EXCERPTS:
            break
        for file_row in views.archived_files(connection, row["session_id"]):
            if len(found) >= MAX_EXCERPTS:
                break
            for _, line in archive.iter_lines(connection, file_row["path"]):
                text = line.decode("utf-8", "replace")
                match = pattern.search(text)
                if match is None:
                    continue
                start = max(0, match.start() - EXCERPT_CHARS // 2)
                found.append(
                    {
                        "session_id": row["session_id"],
                        "text": text[start : start + EXCERPT_CHARS],
                    }
                )
                break
    note = (
        f"{len(found)} transcript excerpts of at most {EXCERPT_CHARS} characters were "
        "included because --with-content was passed."
    )
    if refused:
        note += f" {refused} sessions were skipped: their project is not recorded at full."
    return found, note


def _repo_key(connection: sqlite3.Connection, session_id: str) -> str | None:
    row = views.session_row(connection, session_id)
    return row["repo_key"] if row is not None else None


def _trim(evidence: Evidence) -> None:
    """Drop the oldest sessions until the payload fits. Says how many went."""
    while len(evidence.as_json().encode()) > MAX_BYTES and len(evidence.sessions) > 1:
        evidence.sessions.pop()
        evidence.trimmed += 1
    if evidence.trimmed:
        evidence.notes.append(
            f"{evidence.trimmed} older sessions were left out to keep what was sent under "
            f"{MAX_BYTES // 1024} KB."
        )


def tables(evidence: Evidence, names: dict[str, str] | None = None) -> str:
    """The evidence as text: what `--no-model` prints, and what a reader checks against."""
    lines: list[str] = []
    question = evidence.question
    lines.append(f"Question: {question.text}")
    scope = (names or {}).get(question.project or "", question.project) or "every project"
    lines.append(f"Scope: {scope}")
    if question.matched:
        lines.append(f"Read from the question: {', '.join(question.matched)}")
    lines.append("")

    if evidence.sessions:
        lines.append(
            f"{'session':<10} {'repository':<16} {'started':<17} {'purpose':<12} "
            f"{'tokens':>8} {'commits':>8} {'rework':>8}"
        )
        for row in evidence.sessions:
            outcomes = row.get("outcomes") or {}
            rework = outcomes.get("reworked_share")
            lines.append(
                f"{row['session_id'][:8]:<10} {str(row['repository'])[:16]:<16} "
                f"{str(row['started_at'])[:17]:<17} {str(row.get('purpose') or '-')[:12]:<12} "
                f"{_thousands(row.get('tokens')):>8} {row.get('commits_attributed', 0):>8} "
                f"{_percent(rework):>8}"
            )
    else:
        lines.append("No session matched this question.")

    if evidence.totals:
        lines.append("")
        lines.append("tokens by purpose in the range")
        for label, cell in evidence.totals["by_purpose"].items():
            lines.append(
                f"  {label:<14} {cell['sessions']:>4} sessions  "
                f"{cell['tokens_thousands']:>8}  {cell['share_of_tokens']:>5}  "
                f"{cell['active_hours']} active h"
            )
        lines.append(
            f"  {'all purposes':<14} {evidence.totals['sessions']:>4} sessions  "
            f"{evidence.totals['tokens_thousands']:>8}         "
            f"{evidence.totals['active_hours']} active h"
        )

    if evidence.observations:
        lines.append("")
        lines.append("observations that apply")
        from prudence.store import observations as observations_module

        for row in evidence.observations:
            name = (names or {}).get(row["repo_key"])
            lines.append(f"  {observations_module.sentence(row, name)}")
            lines.append(f"    {observations_module.caveat(row)}")

    if evidence.excerpts:
        lines.append("")
        lines.append(f"{len(evidence.excerpts)} transcript excerpts (--with-content)")

    if evidence.notes:
        lines.append("")
        lines.extend(evidence.notes)
    return "\n".join(lines)


def _thousands(count: int | None) -> str:
    if count is None:
        return "-"
    return str(count) if count < 1000 else f"{count / 1000:.0f}k"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"
