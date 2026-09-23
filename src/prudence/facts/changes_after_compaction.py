"""How many replies changed a file after a compaction, before the next turn began.

A compaction is the `system` record with `subtype = 'compact_boundary'` that
`compactions` counts. From that marker on, the main conversation works from a summary
rather than from what it had read. This fact counts the main conversation's `change`
replies from the marker until the next turn of the session begins: the rest of the turn
the compaction happened in, which is where Claude Code carries on from its own summary
with no new word from the person. A subagent's replies are not counted, because a
subagent starts from a fresh context of its own.

The window closes at the next turn because the derived tables cannot tell who opened a
turn. That is the honest limit, and it is not small. The 2026-09-22 demo read the text
and kept the window open until the person typed a prompt of their own, so a scheduled
`/loop` tick or a slash command did not close it; on the founder's store 53 of the demo's
56 changes were in `/loop` ticks after a compaction, and this fact counts none of them.
Two of the five it does count were made on a prompt the person typed together with
`/compact`, which shares that command's turn. Following the demo exactly needs the parser
to record what opened each turn (a typed prompt, a command, a scheduled tick), without
its text.

The demo's note that "a compact summary starts a turn of its own" did not hold on the
founder's store: in all 43 compactions the summary carries the prompt id of the turn it
compacted. A session that never compacted is a real zero.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1

# Sorts after every ISO timestamp: the end of a window no later turn closes.
_OPEN = "9999"


def compute(connection: sqlite3.Connection, session_id: str) -> int:
    markers = [
        row["timestamp"]
        for row in connection.execute(
            "SELECT timestamp FROM record WHERE session_id = ? AND type = 'system'"
            " AND subtype = 'compact_boundary' AND agent_id IS NULL"
            " AND timestamp IS NOT NULL ORDER BY timestamp",
            (session_id,),
        )
    ]
    count = 0
    for marker in markers:
        (closed,) = connection.execute(
            "SELECT MIN(started_at) FROM turn WHERE session_id = ? AND started_at > ?",
            (session_id, marker),
        ).fetchone()
        (changes,) = connection.execute(
            "SELECT COUNT(*) FROM response WHERE session_id = ? AND agent_id IS NULL"
            " AND bucket = 'change' AND started_at > ? AND started_at < ?",
            (session_id, marker, closed or _OPEN),
        ).fetchone()
        count += changes
    return count


def _marker(session_id: str, record_id: str, at: str, agent_id: str | None = None) -> dict:
    return {
        "record_id": record_id,
        "session_id": session_id,
        "type": "system",
        "subtype": "compact_boundary",
        "timestamp": at,
        "agent_id": agent_id,
    }


def _turn(session_id: str, turn_id: str, at: str) -> dict:
    return {"turn_id": turn_id, "session_id": session_id, "started_at": at}


def _change(
    session_id: str, reply_id: str, turn_id: str, at: str, agent_id: str | None = None
) -> dict:
    return {
        "response_id": reply_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_id": agent_id,
        "started_at": at,
        "bucket": "change",
        "bucket_rule_version": 1,
    }


_AT = "2026-09-15T09:{:02d}:00.000Z"

CASES = (
    Case(
        name="compacted mid-turn: the rest of that turn counts, the next turn does not",
        session_id="s1",
        expected=2,
        rows={
            "record": [_marker("s1", "b1", _AT.format(10))],
            "turn": [_turn("s1", "p1", _AT.format(0)), _turn("s1", "p2", _AT.format(30))],
            "response": [
                _change("s1", "m1", "p1", _AT.format(5)),
                _change("s1", "m2", "p1", _AT.format(12)),
                _change("s1", "m3", "p1", _AT.format(15)),
                _change("s1", "m4", "p2", _AT.format(31)),
            ],
        },
    ),
    Case(
        name="the last turn of the session compacted: counted to the end",
        session_id="s2",
        expected=1,
        rows={
            "record": [_marker("s2", "b1", _AT.format(10))],
            "turn": [_turn("s2", "p1", _AT.format(0))],
            "response": [_change("s2", "m1", "p1", _AT.format(40))],
        },
    ),
    Case(
        name="a subagent's change in the window, and a subagent's own compaction: neither",
        session_id="s3",
        expected=1,
        rows={
            "record": [
                _marker("s3", "b1", _AT.format(10)),
                _marker("s3", "b2", _AT.format(40), agent_id="ag"),
            ],
            "turn": [_turn("s3", "p1", _AT.format(0)), _turn("s3", "p2", _AT.format(20))],
            "response": [
                _change("s3", "m1", "p1", _AT.format(12)),
                _change("s3", "a1", "p1", _AT.format(13), agent_id="ag"),
                _change("s3", "m2", "p2", _AT.format(41)),
            ],
        },
    ),
    Case(name="never compacted: a real zero", session_id="s4", expected=0, rows={}),
)

FACT = Fact(
    name="changes_after_compaction",
    version=FACT_VERSION,
    trust="medium",
    compute=compute,
    cases=CASES,
)
