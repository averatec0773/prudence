"""How many times this session dispatched a subagent, through the `Task` tool.

A plain count over `tool_call.tool_name`, unambiguous and available at any capture
level (tool names are never withheld, only file paths are). A session that never used
one is a real zero.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1


def compute(connection: sqlite3.Connection, session_id: str) -> int:
    (count,) = connection.execute(
        "SELECT COUNT(*) FROM tool_call WHERE session_id = ? AND tool_name = 'Task'",
        (session_id,),
    ).fetchone()
    return count


def _call(session_id: str, tool_use_id: str, tool_name: str) -> dict:
    return {"tool_use_id": tool_use_id, "session_id": session_id, "tool_name": tool_name}


CASES = (
    Case(
        name="two subagent dispatches",
        session_id="s1",
        expected=2,
        rows={
            "tool_call": [
                _call("s1", "t1", "Task"),
                _call("s1", "t2", "Task"),
                _call("s1", "t3", "Bash"),
            ]
        },
    ),
    Case(name="no subagent used: a real zero", session_id="s2", expected=0, rows={}),
)

FACT = Fact(name="subagent_used", version=FACT_VERSION, trust="high", compute=compute, cases=CASES)
