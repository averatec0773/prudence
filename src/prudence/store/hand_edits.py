"""Hand changes between turns: the gap the transcript can never see, from the hooks.

`hook_event` carries a tree fingerprint at every `UserPromptSubmit` and `Stop`, keyed by
`prompt_id`. This module folds that into two tables, purely by reading `hook_event`
(itself a derived table; nothing here touches the archive):

`turn_tree` is one row per turn (`prompt_id`): the fingerprint at the turn's own
`UserPromptSubmit` (start) and at its last `Stop` (end), plus how many shell calls
(`PreToolUse` for Bash, or Codex's shell tools) happened in between. `hook_event.tool_name`
tells a shell call from an `apply_patch`; a row with no tool name is from an older hook
that only matched Bash.

`hand_edit` is one row per gap between two consecutive turns where the tree changed with
no shell call in between: the end fingerprint of turn N differs from the start
fingerprint of turn N+1, and no shell call landed between them. The dirty-count delta
between the two moments is stored as an estimate of how many files were touched, never
a path. A gap during which another recorded session or hook was active in the same
repository is not a hand edit: another agent may have changed the tree, so the turn's
`hand_edit_coverage` is 0 and the gap is left unknown rather than blamed on the user.

Both `UserPromptSubmit` and `Stop` can fire more than once for the same `prompt_id` (the
hooks spike measured both, around a subagent invocation). The start is the earliest
`UserPromptSubmit` for a `prompt_id`, because that is the first known state before any of
the turn's tool calls ran; the end is the latest `Stop` for that `prompt_id` that still
lands before the next turn's start, so a stray duplicate cannot be mistaken for a later
turn's boundary.

A session with no `hook_event` rows at all produces no `turn_tree` and no `hand_edit`
rows, which is exactly how `facts.hand_edits_between_turns` tells "never captured" apart
from "captured, no gaps found".
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from prudence.store import progress as progress_module

PARSER_VERSION = 2

TURN_TREE_TABLE = "turn_tree"
HAND_EDIT_TABLE = "hand_edit"

TURN_TREE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {name}(
    session_id TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    start_head TEXT,
    start_fingerprint TEXT,
    start_dirty INTEGER,
    end_head TEXT,
    end_fingerprint TEXT,
    end_dirty INTEGER,
    bash_calls_between INTEGER NOT NULL DEFAULT 0,
    parser_version INTEGER NOT NULL,
    hand_edit_coverage INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(session_id, prompt_id)
) WITHOUT ROWID
"""

HAND_EDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS {name}(
    session_id TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    prev_prompt_id TEXT NOT NULL,
    files_changed_delta INTEGER,
    parser_version INTEGER NOT NULL,
    PRIMARY KEY(session_id, prompt_id)
)
"""

INDEXES = (
    "CREATE INDEX IF NOT EXISTS turn_tree_session ON turn_tree(session_id)",
    "CREATE INDEX IF NOT EXISTS hand_edit_session ON hand_edit(session_id)",
)

SCHEMA = TURN_TREE_SCHEMA.format(name=TURN_TREE_TABLE) + HAND_EDIT_SCHEMA.format(
    name=HAND_EDIT_TABLE
)


@dataclass
class BuildStats:
    sessions: int = 0
    turns: int = 0
    hand_edits: int = 0
    elapsed: float = 0.0


@dataclass
class _Turn:
    prompt_id: str
    start_ts: str | None = None
    start_head: str | None = None
    start_fingerprint: str | None = None
    start_dirty: int | None = None
    end_ts: str | None = None
    end_head: str | None = None
    end_fingerprint: str | None = None
    end_dirty: int | None = None
    bash_calls: int = 0
    hand_edit_coverage: bool = True


def build(
    connection: sqlite3.Connection, progress: progress_module.Step | None = None
) -> BuildStats:
    """Rebuild `turn_tree` and `hand_edit` from `hook_event` alone. Idempotent."""
    started = time.monotonic()
    stats = BuildStats()
    progress = progress or progress_module.silent()
    connection.execute(f"DROP TABLE IF EXISTS {TURN_TREE_TABLE}__new")
    connection.execute(TURN_TREE_SCHEMA.format(name=f"{TURN_TREE_TABLE}__new"))
    connection.execute(f"DROP TABLE IF EXISTS {HAND_EDIT_TABLE}__new")
    connection.execute(HAND_EDIT_SCHEMA.format(name=f"{HAND_EDIT_TABLE}__new"))

    turn_rows: list[tuple] = []
    hand_rows: list[tuple] = []
    try:
        sessions = [
            row[0]
            for row in connection.execute("SELECT DISTINCT session_id FROM hook_event ORDER BY 1")
        ]
    except sqlite3.OperationalError:
        sessions = []
    stats.sessions = len(sessions)

    progress.start(len(sessions), "sessions")
    for session_id in sessions:
        progress.advance()
        events = connection.execute(
            "SELECT event, ts, prompt_id, head, dirty_fingerprint, dirty_count,"
            " cwd, repo_key, tool_name"
            " FROM hook_event"
            " WHERE session_id = ? ORDER BY ts, event",
            (session_id,),
        ).fetchall()
        turns = _turns(events)
        for previous, current in zip(turns, turns[1:], strict=False):
            if not previous.end_ts or not current.start_ts:
                current.hand_edit_coverage = False
                continue
            current.hand_edit_coverage = not _other_agent_in_gap(
                connection, session_id, events, previous.end_ts, current.start_ts
            )
        for turn in turns:
            turn_rows.append(
                (
                    session_id,
                    turn.prompt_id,
                    turn.start_head,
                    turn.start_fingerprint,
                    turn.start_dirty,
                    turn.end_head,
                    turn.end_fingerprint,
                    turn.end_dirty,
                    turn.bash_calls,
                    PARSER_VERSION,
                    int(turn.hand_edit_coverage),
                )
            )
        hand_rows.extend(_hand_edits(session_id, turns, events))

    connection.executemany(
        f"INSERT OR REPLACE INTO {TURN_TREE_TABLE}__new VALUES (?,?,?,?,?,?,?,?,?,?,?)", turn_rows
    )
    connection.executemany(
        f"INSERT OR REPLACE INTO {HAND_EDIT_TABLE}__new VALUES (?,?,?,?,?)", hand_rows
    )
    stats.turns = len(turn_rows)
    stats.hand_edits = len(hand_rows)
    _swap(connection)
    stats.elapsed = time.monotonic() - started
    return stats


def _turns(events: list[sqlite3.Row]) -> list[_Turn]:
    """One `_Turn` per `prompt_id`, in the order its first `UserPromptSubmit` appeared.

    `events` is already ordered by `ts`. The start is the earliest `UserPromptSubmit` for
    a `prompt_id`; the end is the latest `Stop` for that `prompt_id` whose `ts` still
    falls before the next turn's start, which is how a duplicate `Stop` is tolerated
    without letting it wander into the wrong turn.
    """
    order: list[str] = []
    starts: dict[str, sqlite3.Row] = {}
    stops: dict[str, list[sqlite3.Row]] = {}
    for row in events:
        prompt_id = row["prompt_id"] or ""
        if not prompt_id:
            continue
        if row["event"] == "UserPromptSubmit":
            if prompt_id not in starts:
                starts[prompt_id] = row
                order.append(prompt_id)
        elif row["event"] == "Stop":
            stops.setdefault(prompt_id, []).append(row)

    turns = [
        _Turn(
            prompt_id=prompt_id,
            start_ts=starts[prompt_id]["ts"],
            start_head=starts[prompt_id]["head"] or None,
            start_fingerprint=starts[prompt_id]["dirty_fingerprint"] or None,
            start_dirty=starts[prompt_id]["dirty_count"],
        )
        for prompt_id in order
    ]

    for index, turn in enumerate(turns):
        upper = turns[index + 1].start_ts if index + 1 < len(turns) else None
        candidates = [
            row for row in stops.get(turn.prompt_id, ()) if upper is None or row["ts"] < upper
        ]
        if candidates:
            last = max(candidates, key=lambda row: row["ts"])
            turn.end_ts = last["ts"]
            turn.end_head = last["head"] or None
            turn.end_fingerprint = last["dirty_fingerprint"] or None
            turn.end_dirty = last["dirty_count"]
        turn.bash_calls = sum(
            1
            for row in events
            if row["event"] == "PreToolUse"
            and row["tool_name"] in (None, "", "Bash", "bash", "exec_command", "shell")
            and turn.start_ts is not None
            and row["ts"] >= turn.start_ts
            and (turn.end_ts is None or row["ts"] <= turn.end_ts)
        )
    return turns


def _hand_edits(session_id: str, turns: list[_Turn], events: list[sqlite3.Row]) -> list[tuple]:
    """A row per consecutive pair whose tree moved with no Bash call to explain it."""
    rows: list[tuple] = []
    for previous, current in zip(turns, turns[1:], strict=False):
        if not current.hand_edit_coverage:
            continue
        if previous.end_fingerprint is None or current.start_fingerprint is None:
            continue
        if previous.end_fingerprint == current.start_fingerprint:
            continue
        between = sum(
            1
            for row in events
            if row["event"] == "PreToolUse"
            and previous.end_ts is not None
            and row["ts"] > previous.end_ts
            and row["ts"] < current.start_ts
        )
        if between:
            continue
        delta = None
        if previous.end_dirty is not None and current.start_dirty is not None:
            delta = abs(current.start_dirty - previous.end_dirty)
        rows.append((session_id, current.prompt_id, previous.prompt_id, delta, PARSER_VERSION))
    return rows


def _other_agent_in_gap(connection, session_id, events, start, end) -> bool:
    repositories = {row["repo_key"] for row in events if row["repo_key"]}
    directories = {row["cwd"] for row in events if row["cwd"]}
    for row in connection.execute(
        "SELECT repo_key, cwd FROM hook_event WHERE session_id != ? AND ts >= ? AND ts <= ?",
        (session_id, start, end),
    ):
        if row["repo_key"] in repositories or row["cwd"] in directories:
            return True
    for row in connection.execute(
        "SELECT repo_key, cwd FROM session WHERE session_id != ? AND first_at <= ?"
        " AND last_at >= ?",
        (session_id, end, start),
    ):
        if row["repo_key"] in repositories or row["cwd"] in directories:
            return True
    return False


def _swap(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        for table in (TURN_TREE_TABLE, HAND_EDIT_TABLE):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    for statement in INDEXES:
        connection.execute(statement)


def counts(connection: sqlite3.Connection) -> tuple[int, int]:
    """Turns folded, and hand edits found, over the whole store."""
    try:
        turns = connection.execute(f"SELECT COUNT(*) FROM {TURN_TREE_TABLE}").fetchone()[0]
        edits = connection.execute(f"SELECT COUNT(*) FROM {HAND_EDIT_TABLE}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0, 0
    return turns, edits
