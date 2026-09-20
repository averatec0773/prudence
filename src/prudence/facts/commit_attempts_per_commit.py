"""How many `git commit` calls it took per commit this session is credited with.

The denominator counts each commit once, at its best confidence, exactly as
`store/views.credited_map` does for `prudence sessions`' commit column, and only a
`fact` or `inferred` commit counts (principle 3: an `uncertain` attribution enters no
statistic). A session that attempted no commit, or whose attempts produced nothing this
session is credited with, has no ratio to report: NULL, not a fabricated zero or an
infinite one.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact
from prudence.store import attribution as attribution_module

FACT_VERSION = 1

_ORDER = {label: index for index, label in enumerate(attribution_module.CONFIDENCES)}


def compute(connection: sqlite3.Connection, session_id: str) -> float | None:
    (attempts,) = connection.execute(
        "SELECT COUNT(*) FROM command WHERE session_id = ? AND command_class = 'git_commit'",
        (session_id,),
    ).fetchone()
    best: dict[str, str] = {}
    for row in connection.execute(
        "SELECT commit_hash, confidence FROM attribution WHERE session_id = ?", (session_id,)
    ):
        current = best.get(row["commit_hash"])
        if current is None or _ORDER[row["confidence"]] < _ORDER[current]:
            best[row["commit_hash"]] = row["confidence"]
    counted = sum(1 for confidence in best.values() if confidence in attribution_module.COUNTED)
    if counted == 0:
        return None
    return attempts / counted


def _attempt(session_id: str, tool_use_id: str) -> dict:
    return {"tool_use_id": tool_use_id, "session_id": session_id, "command_class": "git_commit"}


def _attribution(session_id: str, commit_hash: str, method: str, confidence: str) -> dict:
    return {
        "commit_hash": commit_hash,
        "session_id": session_id,
        "method": method,
        "rank": 1,
        "confidence": confidence,
    }


CASES = (
    Case(
        name="three attempts, two commits counted: one and a half",
        session_id="s1",
        expected=1.5,
        rows={
            "command": [_attempt("s1", "c1"), _attempt("s1", "c2"), _attempt("s1", "c3")],
            "attribution": [
                _attribution("s1", "h1", "in_session", "fact"),
                _attribution("s1", "h2", "line_match", "inferred"),
            ],
        },
    ),
    Case(
        name="attempted, but nothing attributed: absent",
        session_id="s2",
        expected=None,
        rows={"command": [_attempt("s2", "c1")]},
    ),
    Case(
        name="only an uncertain attribution: not counted, absent",
        session_id="s3",
        expected=None,
        rows={
            "command": [_attempt("s3", "c1")],
            "attribution": [_attribution("s3", "h1", "line_match", "uncertain")],
        },
    ),
    Case(
        name="the same commit attributed twice keeps its best confidence",
        session_id="s4",
        expected=1.0,
        rows={
            "command": [_attempt("s4", "c1")],
            "attribution": [
                _attribution("s4", "h1", "line_match", "inferred"),
                _attribution("s4", "h1", "in_session", "fact"),
            ],
        },
    ),
)

FACT = Fact(
    name="commit_attempts_per_commit",
    version=FACT_VERSION,
    trust="medium",
    compute=compute,
    cases=CASES,
)
