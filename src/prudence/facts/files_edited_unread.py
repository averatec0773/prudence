"""Files this session edited before it had ever read them.

An edit tool call that touches a path the session never `Read` first is the strongest
of the coaching reference's tool-mix signals (part a: "pure tool-call counting, no
NLP"). File paths are only kept at `full` capture, so a `metadata-only` session cannot
answer this at all: the fact is absent, not zero, for exactly the sessions `tool_call`
withholds its `file_path` column for.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def compute(connection: sqlite3.Connection, session_id: str) -> int | None:
    row = connection.execute(
        "SELECT capture_level FROM session WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None or row["capture_level"] != "full":
        return None
    seen_read: set[str] = set()
    unread: set[str] = set()
    for call in connection.execute(
        "SELECT tool_name, file_path FROM tool_call WHERE session_id = ? AND file_path IS NOT NULL"
        " ORDER BY started_at, tool_use_id",
        (session_id,),
    ):
        path = call["file_path"]
        if call["tool_name"] == "Read":
            seen_read.add(path)
        elif call["tool_name"] in EDIT_TOOLS and path not in seen_read:
            unread.add(path)
    return len(unread)


def _call(session_id: str, tool_use_id: str, tool_name: str, path: str, started_at: str) -> dict:
    return {
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        "tool_name": tool_name,
        "file_path": path,
        "started_at": started_at,
    }


CASES = (
    Case(
        name="edited before it was ever read: counted",
        session_id="s1",
        expected=1,
        rows={
            "session": [{"session_id": "s1", "capture_level": "full"}],
            "tool_call": [
                _call("s1", "t1", "Write", "a.py", "2026-09-15T09:00:00Z"),
                _call("s1", "t2", "Read", "a.py", "2026-09-15T09:05:00Z"),
            ],
        },
    ),
    Case(
        name="read first, then edited: not counted",
        session_id="s2",
        expected=0,
        rows={
            "session": [{"session_id": "s2", "capture_level": "full"}],
            "tool_call": [
                _call("s2", "t1", "Read", "a.py", "2026-09-15T09:00:00Z"),
                _call("s2", "t2", "Write", "a.py", "2026-09-15T09:05:00Z"),
            ],
        },
    ),
    Case(
        name="edited and never read at all: counted",
        session_id="s3",
        expected=1,
        rows={
            "session": [{"session_id": "s3", "capture_level": "full"}],
            "tool_call": [_call("s3", "t1", "Write", "a.py", "2026-09-15T09:00:00Z")],
        },
    ),
    Case(
        name="metadata-only capture: absent, file paths are withheld",
        session_id="s4",
        expected=None,
        rows={
            "session": [{"session_id": "s4", "capture_level": "metadata-only"}],
            "tool_call": [_call("s4", "t1", "Write", "a.py", "2026-09-15T09:00:00Z")],
        },
    ),
)

FACT = Fact(
    name="files_edited_unread", version=FACT_VERSION, trust="high", compute=compute, cases=CASES
)
