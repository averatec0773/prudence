"""How many shell calls this session classified as a formatter.

A plain count over `command.command_class`, which `store/edits.py` already classifies
from the command text with no ambiguity, at any capture level. A session that ran no
commands at all is a real zero, not an absence.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1


def compute(connection: sqlite3.Connection, session_id: str) -> int:
    (count,) = connection.execute(
        "SELECT COUNT(*) FROM command WHERE session_id = ? AND command_class = 'formatter'",
        (session_id,),
    ).fetchone()
    return count


def _command(session_id: str, tool_use_id: str, command_class: str) -> dict:
    return {"tool_use_id": tool_use_id, "session_id": session_id, "command_class": command_class}


CASES = (
    Case(
        name="two formatter calls among other commands",
        session_id="s1",
        expected=2,
        rows={
            "command": [
                _command("s1", "c1", "formatter"),
                _command("s1", "c2", "formatter"),
                _command("s1", "c3", "test"),
            ]
        },
    ),
    Case(name="no commands at all: a real zero", session_id="s2", expected=0, rows={}),
)

FACT = Fact(name="formatter_runs", version=FACT_VERSION, trust="high", compute=compute, cases=CASES)
