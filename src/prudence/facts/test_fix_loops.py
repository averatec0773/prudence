"""How many test-fix loops this session went through, and the tokens spent inside them.

A loop is a reply that ran tests, then a reply that changed a file, then another reply
that ran tests, all in one turn and one context: the main conversation, or one subagent,
since a subagent's replies are charged to the turn that dispatched it but are not part of
the main conversation's sequence. A reply "ran tests" when its bucket is `run` and one of
its shell calls is of `command_class = 'test'`; a reply that edits and tests at once is a
`change` and so is the change of the next loop, not a run. Each closing run is also the
opening run of the next loop, so three test runs with a change between each are two
loops. `test_fix_loop_tokens` is the sum of every reply from a loop's opening run to its
closing run, each reply once however many loops it sits in.

This is the headline form of the demo's `test_fix_loop` (docs/reference/usage-buckets.md,
"Waste signatures"), which closed a loop on a rerun of any command of the same class. That
variant stays available as `loops(..., same_class=True)` for comparison and is not
stored, because the engine's five command classes put every unrecognised command in one
`other` class and a rerun of "some other command" is not a loop anyone would name.

The honest limit is the link between a shell call and its reply: `tool_call` carries no
reply id, so a call belongs to the latest reply in its turn and context that had begun
when the call was written. Within one context replies follow each other, and a call is
always written before the result the next reply waits for, so the link is exact on every
transcript seen so far; two replies stamped with the same instant would be ordered by id.
A count of loops is a fact about cost, not a judgement: some loops are the work.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field

from prudence.facts.base import Case, Fact
from prudence.store import buckets

FACT_VERSION = 1

# The command class whose rerun after a change closes a loop.
LOOP_CLASS = "test"

# Sorts after every reply id, so a reply begun at the call's own instant counts as begun.
_AFTER_ANY_ID = "\U0010ffff"

_TOKENS = (
    "COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)"
    " + COALESCE(cache_read_tokens, 0) + COALESCE(cache_creation_tokens, 0)"
)


@dataclass
class _Reply:
    bucket: str | None
    tokens: int
    classes: set[str] = field(default_factory=set)


def loops(
    connection: sqlite3.Connection, session_id: str, same_class: bool = False
) -> tuple[int, int]:
    """(loops, tokens in them) for one session.

    `same_class` closes a loop on a rerun of any class: a shell call's command class, or
    the name of a run tool that is not the shell (the demo's definition).
    """
    contexts = _contexts(connection, session_id, same_class)
    count = 0
    tokens = 0
    for replies in contexts.values():
        opened: dict[str, int] = {}
        changed: dict[str, bool] = {}
        inside: set[int] = set()
        for index, reply in enumerate(replies):
            if reply.bucket == buckets.CHANGE:
                for name in changed:
                    changed[name] = True
            if reply.bucket != buckets.RUN:
                continue
            for name in sorted(reply.classes):
                if name in opened and changed[name]:
                    count += 1
                    inside.update(range(opened[name], index + 1))
                opened[name] = index
                changed[name] = False
        tokens += sum(replies[index].tokens for index in inside)
    return count, tokens


def _contexts(
    connection: sqlite3.Connection, session_id: str, same_class: bool
) -> dict[tuple[str, str | None], list[_Reply]]:
    """Each (turn, agent) context's replies in order, with the classes each one ran."""
    replies: dict[tuple[str, str | None], list[_Reply]] = defaultdict(list)
    starts: dict[tuple[str, str | None], list[tuple[str, str]]] = defaultdict(list)
    for row in connection.execute(
        f"SELECT response_id, turn_id, agent_id, started_at, bucket, {_TOKENS} AS tokens"
        " FROM response WHERE session_id = ? AND turn_id IS NOT NULL"
        " AND started_at IS NOT NULL ORDER BY turn_id, agent_id, started_at, response_id",
        (session_id,),
    ):
        key = (row["turn_id"], row["agent_id"])
        replies[key].append(_Reply(row["bucket"], row["tokens"]))
        starts[key].append((row["started_at"], row["response_id"]))

    for call in connection.execute(
        "SELECT t.turn_id, r.agent_id, t.started_at, t.tool_name, c.command_class"
        " FROM tool_call t LEFT JOIN command c ON c.tool_use_id = t.tool_use_id"
        " LEFT JOIN record r ON r.record_id = t.record_id"
        " WHERE t.session_id = ? AND t.turn_id IS NOT NULL AND t.started_at IS NOT NULL",
        (session_id,),
    ):
        name = _class_of(call["tool_name"], call["command_class"], same_class)
        if name is None:
            continue
        key = (call["turn_id"], call["agent_id"])
        # The latest reply begun by the time the call was written.
        index = bisect_right(starts.get(key, []), (call["started_at"], _AFTER_ANY_ID)) - 1
        if index >= 0:
            replies[key][index].classes.add(name)
    return replies


def _class_of(tool_name: str | None, command_class: str | None, same_class: bool) -> str | None:
    if command_class is not None:
        return command_class if same_class or command_class == LOOP_CLASS else None
    if not same_class or tool_name in buckets.SHELL_TOOLS:
        return None
    kind, _ = buckets.call_kind(tool_name)
    return (tool_name or "").rsplit("__", 1)[-1] if kind == buckets.RUN else None


def compute(connection: sqlite3.Connection, session_id: str) -> int:
    return loops(connection, session_id)[0]


def compute_tokens(connection: sqlite3.Connection, session_id: str) -> int | None:
    """The loops' tokens, absent for a session whose replies reported no usage at all."""
    (measured,) = connection.execute(
        "SELECT COUNT(input_tokens) FROM response WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not measured:
        return None
    return loops(connection, session_id)[1]


# --- cases -----------------------------------------------------------------------------


def _reply(
    session_id: str,
    reply_id: str,
    turn_id: str,
    started_at: str,
    bucket: str,
    tokens: int = 100,
    agent_id: str | None = None,
) -> dict:
    return {
        "response_id": reply_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_id": agent_id,
        "started_at": started_at,
        "bucket": bucket,
        "bucket_rule_version": 1,
        "input_tokens": tokens,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }


def _shell(
    session_id: str,
    call_id: str,
    turn_id: str,
    started_at: str,
    command_class: str,
    record_id: str | None = None,
) -> list[tuple[str, dict]]:
    """One shell call: its `tool_call` row and its `command` row."""
    return [
        (
            "tool_call",
            {
                "tool_use_id": call_id,
                "session_id": session_id,
                "record_id": record_id,
                "turn_id": turn_id,
                "tool_name": "Bash",
                "started_at": started_at,
            },
        ),
        (
            "command",
            {
                "tool_use_id": call_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "command_class": command_class,
            },
        ),
    ]


def _rows(replies: list[dict], calls: list[list[tuple[str, dict]]], **extra) -> dict:
    rows: dict[str, list[dict]] = {"response": replies, **extra}
    for call in calls:
        for table, row in call:
            rows.setdefault(table, []).append(row)
    return rows


_T = "2026-09-15T09:00:0{}.000Z"

# Test, change, test: one loop over the three replies.
_ONE_LOOP = _rows(
    [
        _reply("s1", "m1", "p1", _T.format(1), "run", 100),
        _reply("s1", "m2", "p1", _T.format(2), "change", 200),
        _reply("s1", "m3", "p1", _T.format(3), "run", 300),
        _reply("s1", "m4", "p1", _T.format(4), "talk", 1000),
    ],
    [
        _shell("s1", "c1", "p1", _T.format(1), "test"),
        _shell("s1", "c3", "p1", "2026-09-15T09:00:03.500Z", "test"),
    ],
)

# The same three replies, but the closing run is in the person's next turn.
_TWO_TURNS = _rows(
    [
        _reply("s3", "m1", "p1", _T.format(1), "run"),
        _reply("s3", "m2", "p1", _T.format(2), "change"),
        _reply("s3", "m3", "p2", _T.format(3), "run"),
    ],
    [
        _shell("s3", "c1", "p1", _T.format(1), "test"),
        _shell("s3", "c3", "p2", _T.format(3), "test"),
    ],
)

# Test, change, test, change, test: two loops, the middle run shared, tokens once each.
_TWO_LOOPS = _rows(
    [
        _reply("s4", "m1", "p1", _T.format(1), "run", 1),
        _reply("s4", "m2", "p1", _T.format(2), "change", 10),
        _reply("s4", "m3", "p1", _T.format(3), "run", 100),
        _reply("s4", "m4", "p1", _T.format(4), "change", 1000),
        _reply("s4", "m5", "p1", _T.format(5), "run", 10000),
    ],
    [
        _shell("s4", "c1", "p1", _T.format(1), "test"),
        _shell("s4", "c3", "p1", _T.format(3), "test"),
        _shell("s4", "c5", "p1", _T.format(5), "test"),
    ],
)

# The main conversation tests, a subagent in the same turn changes, the main tests
# again: the change is in another context, so no loop in either.
_SPLIT_CONTEXTS = _rows(
    [
        _reply("s5", "m1", "p1", _T.format(1), "run"),
        _reply("s5", "a1", "p1", _T.format(2), "change", agent_id="ag"),
        _reply("s5", "m3", "p1", _T.format(3), "run"),
    ],
    [
        _shell("s5", "c1", "p1", _T.format(1), "test", record_id="r1"),
        _shell("s5", "c3", "p1", _T.format(3), "test", record_id="r3"),
    ],
    record=[
        {"record_id": "r1", "session_id": "s5", "agent_id": None},
        {"record_id": "r3", "session_id": "s5", "agent_id": None},
    ],
)

CASES = (
    Case(
        name="test, change, test in one turn: one loop", session_id="s1", expected=1, rows=_ONE_LOOP
    ),
    Case(
        name="a build rerun after a change is not a test-fix loop",
        session_id="s2",
        expected=0,
        rows=_rows(
            [
                _reply("s2", "m1", "p1", _T.format(1), "run"),
                _reply("s2", "m2", "p1", _T.format(2), "change"),
                _reply("s2", "m3", "p1", _T.format(3), "run"),
            ],
            [
                _shell("s2", "c1", "p1", _T.format(1), "other"),
                _shell("s2", "c3", "p1", _T.format(3), "other"),
            ],
        ),
    ),
    Case(
        name="the rerun is in the next turn: no loop (the old `<session>:0` collapse made one)",
        session_id="s3",
        expected=0,
        rows=_TWO_TURNS,
    ),
    Case(
        name="three test runs with changes between: two loops",
        session_id="s4",
        expected=2,
        rows=_TWO_LOOPS,
    ),
    Case(
        name="the change was a subagent's: no loop",
        session_id="s5",
        expected=0,
        rows=_SPLIT_CONTEXTS,
    ),
    Case(name="no replies at all: a real zero", session_id="s6", expected=0, rows={}),
)

TOKEN_CASES = (
    Case(
        name="the loop's three replies, not the talk after it",
        session_id="s1",
        expected=600,
        rows=_ONE_LOOP,
    ),
    Case(
        name="two loops sharing a run: every reply once",
        session_id="s4",
        expected=11111,
        rows=_TWO_LOOPS,
    ),
    Case(
        name="replies that reported no usage: absent, not zero",
        session_id="s7",
        expected=None,
        rows={
            "response": [
                {**_reply("s7", "m1", "p1", _T.format(1), "run"), "input_tokens": None},
            ]
        },
    ),
)

FACT = Fact(
    name="test_fix_loops", version=FACT_VERSION, trust="medium", compute=compute, cases=CASES
)
TOKENS_FACT = Fact(
    name="test_fix_loop_tokens",
    version=FACT_VERSION,
    trust="medium",
    compute=compute_tokens,
    cases=TOKEN_CASES,
)
