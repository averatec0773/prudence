"""How many times the tree changed by hand between two turns the hooks saw.

`store/hand_edits.py` folds `hook_event` into `hand_edit`: one row per gap where the
working tree moved between the end of one turn and the start of the next with no Bash
call in between, which is the signature of a hand edit rather than a shell command. This
fact is the count of that table for one session.

It reads `hook_event` and `hand_edit` rather than the seven tables most facts are built
from, because it is the one fact whose only source is the capture hooks (M2 plan, task
9): a session recorded before `prudence hooks install` was ever run has no `hook_event`
row at all, and that absence is what tells "never captured" apart from "captured, zero
hand edits found". A session with hook data but no gap is a real zero.
"""

from __future__ import annotations

import sqlite3

from prudence.facts.base import Case, Fact

FACT_VERSION = 2


def compute(connection: sqlite3.Connection, session_id: str) -> int | None:
    (has_hooks,) = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM hook_event WHERE session_id = ?)", (session_id,)
    ).fetchone()
    if not has_hooks:
        return None
    if connection.execute(
        "SELECT 1 FROM turn_tree WHERE session_id = ? AND hand_edit_coverage = 0 LIMIT 1",
        (session_id,),
    ).fetchone():
        return None
    (count,) = connection.execute(
        "SELECT COUNT(*) FROM hand_edit WHERE session_id = ?", (session_id,)
    ).fetchone()
    return count


CASES = (
    Case(
        name="no hook events at all: not captured",
        session_id="s1",
        expected=None,
        rows={},
    ),
    Case(
        name="hook data present, no hand edit found: a real zero",
        session_id="s2",
        expected=0,
        rows={
            "hook_event": [
                {
                    "event_id": "e1",
                    "event": "UserPromptSubmit",
                    "session_id": "s2",
                    "prompt_id": "p1",
                }
            ]
        },
    ),
    Case(
        name="two hand edits recorded between turns",
        session_id="s3",
        expected=2,
        rows={
            "hook_event": [
                {
                    "event_id": "e1",
                    "event": "UserPromptSubmit",
                    "session_id": "s3",
                    "prompt_id": "p1",
                }
            ],
            "hand_edit": [
                {
                    "session_id": "s3",
                    "prompt_id": "p2",
                    "prev_prompt_id": "p1",
                    "files_changed_delta": 1,
                },
                {
                    "session_id": "s3",
                    "prompt_id": "p3",
                    "prev_prompt_id": "p2",
                    "files_changed_delta": 2,
                },
            ],
        },
    ),
)

FACT = Fact(
    name="hand_edits_between_turns",
    version=FACT_VERSION,
    trust="medium",
    compute=compute,
    cases=CASES,
)
