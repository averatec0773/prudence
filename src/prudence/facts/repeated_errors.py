"""How many distinct tool errors this session hit three times or more.

`tool_call.error_hash` (parser version 4) is a keyed digest of a failed result's
content, so this fact counts identical failures without a fact reading the error text
itself. It is only ever populated at `full` capture, so `metadata-only` sessions are
absent here rather than a false zero.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1
THRESHOLD = 3


def compute(connection: sqlite3.Connection, session_id: str) -> int | None:
    row = connection.execute(
        "SELECT capture_level FROM session WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None or row["capture_level"] != "full":
        return None
    groups = connection.execute(
        "SELECT COUNT(*) AS n FROM tool_call WHERE session_id = ? AND error_hash IS NOT NULL"
        " GROUP BY error_hash",
        (session_id,),
    ).fetchall()
    return sum(1 for group in groups if group["n"] >= THRESHOLD)


def _error(session_id: str, tool_use_id: str, error_hash: str) -> dict:
    return {
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        "is_error": 1,
        "error_hash": error_hash,
    }


CASES = (
    Case(
        name="the same error three times: one repeated pattern",
        session_id="s1",
        expected=1,
        rows={
            "session": [{"session_id": "s1", "capture_level": "full"}],
            "tool_call": [
                _error("s1", "t1", "h1"),
                _error("s1", "t2", "h1"),
                _error("s1", "t3", "h1"),
            ],
        },
    ),
    Case(
        name="two distinct errors, twice each: none repeated",
        session_id="s2",
        expected=0,
        rows={
            "session": [{"session_id": "s2", "capture_level": "full"}],
            "tool_call": [
                _error("s2", "t1", "h1"),
                _error("s2", "t2", "h1"),
                _error("s2", "t3", "h2"),
                _error("s2", "t4", "h2"),
            ],
        },
    ),
    Case(
        name="two errors each repeated three times: two patterns",
        session_id="s3",
        expected=2,
        rows={
            "session": [{"session_id": "s3", "capture_level": "full"}],
            "tool_call": [
                _error("s3", "t1", "h1"),
                _error("s3", "t2", "h1"),
                _error("s3", "t3", "h1"),
                _error("s3", "t4", "h2"),
                _error("s3", "t5", "h2"),
                _error("s3", "t6", "h2"),
            ],
        },
    ),
    Case(
        name="metadata-only capture: absent, error hashes are withheld",
        session_id="s4",
        expected=None,
        rows={
            "session": [{"session_id": "s4", "capture_level": "metadata-only"}],
            "tool_call": [
                _error("s4", "t1", "h1"),
                _error("s4", "t2", "h1"),
                _error("s4", "t3", "h1"),
            ],
        },
    ),
)

FACT = Fact(
    name="repeated_errors", version=FACT_VERSION, trust="medium", compute=compute, cases=CASES
)
