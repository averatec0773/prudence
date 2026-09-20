"""How many records this session replayed: the trace a resumed session leaves behind.

`session.replayed_records` (parser version 4) is a count `store/derived.py` already
computed to fold a resumed transcript's duplicate records into the first session that
claimed them, previously visible only inside the free-text `notes` column. This fact
exposes it directly: a resumed or replayed session has a nonzero count, a session
started fresh has zero, which is a real measurement, not an absence.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1


def compute(connection: sqlite3.Connection, session_id: str) -> int | None:
    row = connection.execute(
        "SELECT replayed_records FROM session WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return None
    return row["replayed_records"]


CASES = (
    Case(
        name="a resumed session replayed some records",
        session_id="s1",
        expected=4,
        rows={"session": [{"session_id": "s1", "replayed_records": 4}]},
    ),
    Case(
        name="a fresh session replayed nothing: a real zero",
        session_id="s2",
        expected=0,
        rows={"session": [{"session_id": "s2", "replayed_records": 0}]},
    ),
)

FACT = Fact(
    name="context_resets", version=FACT_VERSION, trust="medium", compute=compute, cases=CASES
)
