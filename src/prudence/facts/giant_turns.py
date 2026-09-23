"""How many of this session's turns spent more than five million tokens, and how many.

A turn's tokens are the sum of every reply linked to it in `response`, its subagents'
replies included, because parser version 6 charges a subagent's replies to the turn that
dispatched it. `GIANT_TURN_TOKENS` is the line the 2026-09-22 demo drew on the founder's
store, where turns above it were a fifth of all turns and four fifths of all tokens
(docs/reference/usage-buckets.md, "Waste signatures"). `giant_turn_tokens` is the sum of
those turns' tokens.

The honest limit: almost all of a large turn's tokens are cache reads, the same context
read again by each reply, so a giant turn is a long turn as much as an expensive one. A
subagent reply no dispatching call was found for has no turn and is in no turn's sum. A
session whose replies reported no usage at all is absent from both facts, not zero.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 1

# A turn above this many tokens, subagents included, is a giant turn.
GIANT_TURN_TOKENS = 5_000_000

_TOKENS = (
    "COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)"
    " + COALESCE(cache_read_tokens, 0) + COALESCE(cache_creation_tokens, 0)"
)


def giant(connection: sqlite3.Connection, session_id: str) -> tuple[int, int] | None:
    """(giant turns, their tokens), or None when no reply of the session reported usage."""
    rows = connection.execute(
        f"SELECT SUM({_TOKENS}) AS tokens, COUNT(input_tokens) AS measured FROM response"
        " WHERE session_id = ? AND turn_id IS NOT NULL GROUP BY turn_id",
        (session_id,),
    ).fetchall()
    if not any(row["measured"] for row in rows):
        return None
    over = [row["tokens"] for row in rows if row["tokens"] > GIANT_TURN_TOKENS]
    return len(over), sum(over)


def compute(connection: sqlite3.Connection, session_id: str) -> int | None:
    found = giant(connection, session_id)
    return None if found is None else found[0]


def compute_tokens(connection: sqlite3.Connection, session_id: str) -> int | None:
    found = giant(connection, session_id)
    return None if found is None else found[1]


def _reply(
    session_id: str,
    reply_id: str,
    turn_id: str | None,
    cache_read: int | None,
    agent_id: str | None = None,
) -> dict:
    return {
        "response_id": reply_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_id": agent_id,
        "bucket_rule_version": 1,
        "input_tokens": None if cache_read is None else 10,
        "output_tokens": None if cache_read is None else 0,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": None if cache_read is None else 0,
    }


# One turn over the line only because of its subagent, one just under it, and a
# subagent reply that has no turn at all.
_MIXED = {
    "response": [
        _reply("s1", "m1", "p1", 3_000_000),
        _reply("s1", "a1", "p1", 2_500_000, agent_id="ag"),
        _reply("s1", "m2", "p2", 4_999_980),
        _reply("s1", "a2", None, 9_000_000, agent_id="lost"),
    ]
}

CASES = (
    Case(
        name="a turn over the line with its subagent's replies: one",
        session_id="s1",
        expected=1,
        rows=_MIXED,
    ),
    Case(
        name="two turns under the line: a real zero",
        session_id="s2",
        expected=0,
        rows={
            "response": [
                _reply("s2", "m1", "p1", 3_000_000),
                _reply("s2", "m2", "p2", 3_000_000),
            ]
        },
    ),
    Case(
        name="no reply reported usage: absent",
        session_id="s3",
        expected=None,
        rows={"response": [_reply("s3", "m1", "p1", None)]},
    ),
)

TOKEN_CASES = (
    Case(
        name="the giant turn's own and its subagent's tokens, nothing else",
        session_id="s1",
        expected=5_500_020,
        rows=_MIXED,
    ),
    Case(
        name="no reply reported usage: absent",
        session_id="s3",
        expected=None,
        rows={"response": [_reply("s3", "m1", "p1", None)]},
    ),
)

FACT = Fact(name="giant_turns", version=FACT_VERSION, trust="high", compute=compute, cases=CASES)
TOKENS_FACT = Fact(
    name="giant_turn_tokens",
    version=FACT_VERSION,
    trust="high",
    compute=compute_tokens,
    cases=TOKEN_CASES,
)
