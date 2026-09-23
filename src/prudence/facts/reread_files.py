"""How many times, in this session, one file was read three times or more within one turn.

Counted as (turn, context, file) triples: a `Read` of the same `tool_call.file_path`
`REREAD_THRESHOLD` times or more in one turn and one context, where a context is the
main conversation or one subagent, since two agents each reading a file once have not
reread it. A file read in slices (an offset and a limit each time) counts like any other
read; the call's input is not kept, so the two cannot be told apart, which is the honest
limit of this count.

File paths are kept at `full` capture only, so a `metadata-only` session is absent here
rather than a false zero, exactly as it is from `files_edited_unread`.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1

# Reads of one file in one turn and context at which it counts as reread.
REREAD_THRESHOLD = 3


def compute(connection: sqlite3.Connection, session_id: str) -> int | None:
    row = connection.execute(
        "SELECT capture_level FROM session WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None or row["capture_level"] != "full":
        return None
    (count,) = connection.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM tool_call t"
        " LEFT JOIN record r ON r.record_id = t.record_id"
        " WHERE t.session_id = ? AND t.tool_name = 'Read' AND t.file_path IS NOT NULL"
        " AND t.turn_id IS NOT NULL"
        " GROUP BY t.turn_id, r.agent_id, t.file_path HAVING COUNT(*) >= ?)",
        (session_id, REREAD_THRESHOLD),
    ).fetchone()
    return count


def _read(
    session_id: str, call_id: str, turn_id: str, path: str, record_id: str | None = None
) -> dict:
    return {
        "tool_use_id": call_id,
        "session_id": session_id,
        "record_id": record_id,
        "turn_id": turn_id,
        "tool_name": "Read",
        "file_path": path,
    }


def _full(session_id: str) -> dict:
    return {"session_id": session_id, "capture_level": "full"}


CASES = (
    Case(
        name="one file read three times in one turn: one",
        session_id="s1",
        expected=1,
        rows={
            "session": [_full("s1")],
            "tool_call": [
                _read("s1", "t1", "p1", "a.py"),
                _read("s1", "t2", "p1", "a.py"),
                _read("s1", "t3", "p1", "a.py"),
                _read("s1", "t4", "p1", "b.py"),
            ],
        },
    ),
    Case(
        name="the same three reads over two turns: none (the old `<session>:0` collapse made one)",
        session_id="s2",
        expected=0,
        rows={
            "session": [_full("s2")],
            "tool_call": [
                _read("s2", "t1", "p1", "a.py"),
                _read("s2", "t2", "p1", "a.py"),
                _read("s2", "t3", "p2", "a.py"),
            ],
        },
    ),
    Case(
        name="two reads by the main conversation and one by a subagent: none",
        session_id="s3",
        expected=0,
        rows={
            "session": [_full("s3")],
            "record": [
                {"record_id": "r1", "session_id": "s3", "agent_id": None},
                {"record_id": "r2", "session_id": "s3", "agent_id": None},
                {"record_id": "r3", "session_id": "s3", "agent_id": "ag"},
            ],
            "tool_call": [
                _read("s3", "t1", "p1", "a.py", "r1"),
                _read("s3", "t2", "p1", "a.py", "r2"),
                _read("s3", "t3", "p1", "a.py", "r3"),
            ],
        },
    ),
    Case(
        name="metadata-only capture: absent, paths are withheld",
        session_id="s4",
        expected=None,
        rows={"session": [{"session_id": "s4", "capture_level": "metadata-only"}]},
    ),
)

FACT = Fact(name="reread_files", version=FACT_VERSION, trust="high", compute=compute, cases=CASES)
