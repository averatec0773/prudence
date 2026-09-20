"""How many times the developer sat down: a gap over an hour starts a new one.

The same rule `store/views.py` uses for `prudence sessions`' sitting column, computed
here independently so a fact never depends on a presentation module. A session with no
timestamped record has done nothing recordable, so the fact is absent, not one.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from prudence.facts.base import Case, Fact

FACT_VERSION = 1
GAP = timedelta(minutes=60)


def compute(connection: sqlite3.Connection, session_id: str) -> int | None:
    count = 0
    previous: datetime | None = None
    for (timestamp,) in connection.execute(
        "SELECT timestamp FROM record WHERE session_id = ? AND timestamp IS NOT NULL"
        " ORDER BY timestamp",
        (session_id,),
    ):
        try:
            moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if previous is None or moment - previous > GAP:
            count += 1
        previous = moment
    return count or None


CASES = (
    Case(
        name="two records close together are one sitting",
        session_id="s1",
        expected=1,
        rows={
            "record": [
                {"record_id": "r1", "session_id": "s1", "timestamp": "2026-09-15T09:00:00Z"},
                {"record_id": "r2", "session_id": "s1", "timestamp": "2026-09-15T09:10:00Z"},
            ]
        },
    ),
    Case(
        name="a gap over an hour starts a second sitting",
        session_id="s2",
        expected=2,
        rows={
            "record": [
                {"record_id": "r1", "session_id": "s2", "timestamp": "2026-09-15T09:00:00Z"},
                {"record_id": "r2", "session_id": "s2", "timestamp": "2026-09-15T10:30:00Z"},
            ]
        },
    ),
    Case(
        name="no timestamped record: absent, not one",
        session_id="s3",
        expected=None,
        rows={"record": [{"record_id": "r1", "session_id": "s3", "timestamp": None}]},
    ),
)

FACT = Fact(name="sittings", version=FACT_VERSION, trust="high", compute=compute, cases=CASES)
