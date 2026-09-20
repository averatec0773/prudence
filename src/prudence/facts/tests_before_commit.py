"""The share of this session's `git commit` calls a test run preceded.

"Preceded" means in the same turn or the previous one, per the plan: a test run three
turns before a commit says little about whether the commit that followed was checked,
but a test run in the commit's own turn or the one just before it does. Turns are
ordered by `turn.started_at`, the same clock every other fact reads.

A session that made no in-session `git commit` at all has nothing this fact can be
about, so it is absent rather than a fabricated zero or a fabricated one.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1


def compute(connection: sqlite3.Connection, session_id: str) -> float | None:
    turns = [
        row["turn_id"]
        for row in connection.execute(
            "SELECT turn_id FROM turn WHERE session_id = ? ORDER BY started_at, turn_id",
            (session_id,),
        )
    ]
    index = {turn_id: position for position, turn_id in enumerate(turns)}
    test_positions = {
        index[row["turn_id"]]
        for row in connection.execute(
            "SELECT turn_id FROM command WHERE session_id = ? AND command_class = 'test'",
            (session_id,),
        )
        if row["turn_id"] in index
    }
    commit_turns = [
        row["turn_id"]
        for row in connection.execute(
            "SELECT turn_id FROM command WHERE session_id = ? AND command_class = 'git_commit'",
            (session_id,),
        )
    ]
    if not commit_turns:
        return None
    satisfied = 0
    for turn_id in commit_turns:
        position = index.get(turn_id)
        if position is not None and (position in test_positions or position - 1 in test_positions):
            satisfied += 1
    return satisfied / len(commit_turns)


def _turn(session_id: str, turn_id: str, started_at: str) -> dict:
    return {"turn_id": turn_id, "session_id": session_id, "started_at": started_at}


def _command(session_id: str, tool_use_id: str, turn_id: str, command_class: str) -> dict:
    return {
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "command_class": command_class,
    }


CASES = (
    Case(
        name="test and commit in the same turn",
        session_id="s1",
        expected=1.0,
        rows={
            "turn": [_turn("s1", "t1", "2026-09-15T09:00:00Z")],
            "command": [
                _command("s1", "c1", "t1", "test"),
                _command("s1", "c2", "t1", "git_commit"),
            ],
        },
    ),
    Case(
        name="test in the previous turn",
        session_id="s2",
        expected=1.0,
        rows={
            "turn": [
                _turn("s2", "t1", "2026-09-15T09:00:00Z"),
                _turn("s2", "t2", "2026-09-15T09:05:00Z"),
            ],
            "command": [
                _command("s2", "c1", "t1", "test"),
                _command("s2", "c2", "t2", "git_commit"),
            ],
        },
    ),
    Case(
        name="a commit with no preceding test at all",
        session_id="s3",
        expected=0.0,
        rows={
            "turn": [_turn("s3", "t1", "2026-09-15T09:00:00Z")],
            "command": [_command("s3", "c1", "t1", "git_commit")],
        },
    ),
    Case(
        name="two commits, one preceded by a test",
        session_id="s4",
        expected=0.5,
        rows={
            "turn": [
                _turn("s4", "t1", "2026-09-15T09:00:00Z"),
                _turn("s4", "t2", "2026-09-15T09:05:00Z"),
                _turn("s4", "t3", "2026-09-15T09:10:00Z"),
            ],
            "command": [
                _command("s4", "c1", "t1", "test"),
                _command("s4", "c2", "t2", "git_commit"),
                _command("s4", "c3", "t3", "git_commit"),
            ],
        },
    ),
    Case(name="no in-session commit at all: absent", session_id="s5", expected=None, rows={}),
)

FACT = Fact(
    name="tests_before_commit", version=FACT_VERSION, trust="medium", compute=compute, cases=CASES
)
