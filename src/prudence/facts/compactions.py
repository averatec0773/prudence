"""How many times this session's context was compacted.

Claude Code writes a `system` record with `subtype = "compact_boundary"` at the moment
it compacts, which the parser already keeps in `record.type`/`record.subtype` (verified
against the founder's own store: no fixture carried one, so this was checked directly
against real transcripts rather than guessed). A plain count, unambiguous, at any
capture level.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1


def compute(connection: sqlite3.Connection, session_id: str) -> int:
    (count,) = connection.execute(
        "SELECT COUNT(*) FROM record WHERE session_id = ? AND type = 'system'"
        " AND subtype = 'compact_boundary'",
        (session_id,),
    ).fetchone()
    return count


def _record(session_id: str, record_id: str, record_type: str, subtype: str | None) -> dict:
    return {
        "record_id": record_id,
        "session_id": session_id,
        "type": record_type,
        "subtype": subtype,
    }


CASES = (
    Case(
        name="two compaction boundaries",
        session_id="s1",
        expected=2,
        rows={
            "record": [
                _record("s1", "r1", "system", "compact_boundary"),
                _record("s1", "r2", "system", "compact_boundary"),
                _record("s1", "r3", "system", "turn_duration"),
            ]
        },
    ),
    Case(name="no compaction: a real zero", session_id="s2", expected=0, rows={}),
)

FACT = Fact(name="compactions", version=FACT_VERSION, trust="high", compute=compute, cases=CASES)
