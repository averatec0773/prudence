"""One session at a time: the rows, counts and files `prudence show --session` needs."""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from typing import Any

from prudence.store.views.common import SITTING_GAP


def session_row(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    """The one row from `session` this id names, or None when there isn't one."""
    return connection.execute(
        "SELECT * FROM session WHERE session_id = ?", (session_id,)
    ).fetchone()


def repository_names(connection: sqlite3.Connection) -> dict[str, str]:
    return {row["repo_key"]: row["name"] for row in connection.execute("SELECT * FROM repository")}


def sittings(connection: sqlite3.Connection, session_id: str) -> int:
    """How many times the developer sat down: a gap over an hour starts a new one."""
    count = 0
    previous: datetime | None = None
    for row in connection.execute(
        "SELECT timestamp FROM record WHERE session_id = ? AND timestamp IS NOT NULL"
        " ORDER BY timestamp",
        (session_id,),
    ):
        try:
            moment = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if previous is None or moment - previous > SITTING_GAP:
            count += 1
        previous = moment
    return max(count, 1)


def record_turn_toolcall_counts(connection: sqlite3.Connection, session_id: str) -> dict[str, int]:
    return {
        "records": _scalar(
            connection, "SELECT COUNT(*) FROM record WHERE session_id = ?", session_id
        ),
        "turns": _scalar(connection, "SELECT COUNT(*) FROM turn WHERE session_id = ?", session_id),
        "tool_calls": _scalar(
            connection, "SELECT COUNT(*) FROM tool_call WHERE session_id = ?", session_id
        ),
    }


def _scalar(connection: sqlite3.Connection, query: str, session_id: str) -> int:
    return connection.execute(query, (session_id,)).fetchone()[0]


def tool_calls_by_name(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT COALESCE(tool_name, '?') AS name, COUNT(*) AS n FROM tool_call"
        " WHERE session_id = ? GROUP BY name ORDER BY n DESC, name",
        (session_id,),
    ).fetchall()


def edit_totals(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row:
    return connection.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(lines_added), 0) AS added,"
        " COALESCE(SUM(lines_removed), 0) AS removed FROM edit WHERE session_id = ?",
        (session_id,),
    ).fetchone()


def commands_by_class(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT command_class, COUNT(*) AS n FROM command WHERE session_id = ?"
        " GROUP BY command_class ORDER BY n DESC, command_class",
        (session_id,),
    ).fetchall()


def edited_files(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    """Files this session edited. Callers withhold this at `metadata-only`, not this query."""
    return connection.execute(
        "SELECT COALESCE(rel_path, file_path, '?') AS path, COUNT(*) AS n,"
        " SUM(lines_added) AS added, SUM(lines_removed) AS removed FROM edit"
        " WHERE session_id = ? GROUP BY path ORDER BY added DESC, path",
        (session_id,),
    ).fetchall()


def attributed_commits(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT a.commit_hash, a.method, a.method_note, a.confidence, a.rank, a.lines_matched,"
        " a.coverage, c.added_lines, c.committer_at FROM attribution a"
        ' LEFT JOIN "commit" c ON c.commit_hash = a.commit_hash'
        " WHERE a.session_id = ? ORDER BY c.committer_at, a.method, a.rank",
        (session_id,),
    ).fetchall()


def session_facts(connection: sqlite3.Connection, session_id: str) -> dict[str, dict[str, Any]]:
    """This session's behaviour facts, keyed by name. Empty before `session_fact` exists
    (`prudence rebuild` was never run) and for a fact that did not apply to this session.
    """
    try:
        rows = connection.execute(
            "SELECT fact, value, trust, fact_version FROM session_fact WHERE session_id = ?"
            " ORDER BY fact",
            (session_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {
        row["fact"]: {
            "value": row["value"],
            "trust": row["trust"],
            "fact_version": row["fact_version"],
        }
        for row in rows
    }


def hook_timeline(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    """Empty before `hook_event` exists (`prudence hooks install` was never run)."""
    try:
        return connection.execute(
            "SELECT event, ts, prompt_id, head, dirty_count FROM hook_event"
            " WHERE session_id = ? ORDER BY ts, event",
            (session_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def turn_ordinals(connection: sqlite3.Connection, session_id: str) -> dict[str, int]:
    """1-based turn number, chronological, for every `prompt_id` this session's `turn_tree`
    covers. `turn` carries `started_at` under the same key (`turn_id` is `promptId` when
    Claude Code writes one), which is what orders turns the hooks never timestamped
    directly (`turn_tree` stores no timestamp of its own)."""
    try:
        rows = connection.execute(
            "SELECT tt.prompt_id AS prompt_id FROM turn_tree tt"
            " LEFT JOIN turn t ON t.turn_id = tt.prompt_id"
            " WHERE tt.session_id = ? ORDER BY COALESCE(t.started_at, ''), tt.prompt_id",
            (session_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row["prompt_id"]: index + 1 for index, row in enumerate(rows)}


def hand_edits(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]] | None:
    """Gaps where the tree changed by hand between two turns, or None: no hook data at all.

    None means this session predates `prudence hooks install`, or the tables have not
    been built (`prudence rebuild` was never run); an empty list means hook data exists
    and no gap was found, which is a real answer, not an absence.
    """
    try:
        has_hooks = connection.execute(
            "SELECT EXISTS(SELECT 1 FROM hook_event WHERE session_id = ?)", (session_id,)
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return None
    if not has_hooks:
        return None
    if connection.execute(
        "SELECT 1 FROM turn_tree WHERE session_id = ? AND hand_edit_coverage = 0 LIMIT 1",
        (session_id,),
    ).fetchone():
        return None
    ordinals = turn_ordinals(connection, session_id)
    try:
        rows = connection.execute(
            "SELECT prompt_id, prev_prompt_id, files_changed_delta FROM hand_edit"
            " WHERE session_id = ? ORDER BY rowid",
            (session_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    return [
        {
            "before_turn": ordinals.get(row["prev_prompt_id"]),
            "after_turn": ordinals.get(row["prompt_id"]),
            "files_changed_delta": row["files_changed_delta"],
        }
        for row in rows
    ]


def archived_files(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT path, source, size, generation FROM archive_file WHERE session_id = ?"
        " ORDER BY source, path",
        (session_id,),
    ).fetchall()


def session_summary(
    connection: sqlite3.Connection, session_id: str, list_files: bool = False
) -> dict[str, Any] | None:
    """Everything `prudence show --session` prints, as JSON. None when the id is unknown.

    No message text anywhere: identity, counts, file paths (full capture only) and
    commit hashes, the same facts the text form shows and nothing more.
    """
    # Imported here, not at the top: `outcomes` and `usage` both read this module, and
    # this is the one function that reads them back.
    from prudence.store.views import outcomes as outcomes_views
    from prudence.store.views import usage as usage_views

    row = session_row(connection, session_id)
    if row is None:
        return None
    names = repository_names(connection)
    full = row["capture_level"] == "full"

    edit = edit_totals(connection, session_id)
    file_rows = edited_files(connection, session_id) if full else []
    archive_rows = archived_files(connection, session_id)
    counted = outcomes_views.credited(connection, session_id)

    by_source: Counter[str] = Counter()
    archive_total = 0
    for archived in archive_rows:
        archive_total += archived["size"]
        by_source[archived["source"]] += 1

    return {
        "session_id": session_id,
        "identity": {
            "repository": names.get(row["repo_key"], row["repo_key"]),
            "repo_key": row["repo_key"],
            "capture_level": row["capture_level"],
            "source": row["source"],
            "entrypoint": row["entrypoint"],
            "cwd": row["cwd"] if full else None,
            "first_at": row["first_at"],
            "last_at": row["last_at"],
            "sittings": sittings(connection, session_id),
            "notes": row["notes"],
            "parser_version": row["parser_version"],
        },
        "purpose": usage_views.purpose_of(connection, session_id),
        "purpose_rule_version": usage_views.purpose_rule_version(connection),
        "counts": {
            **record_turn_toolcall_counts(connection, session_id),
            "tool_calls_by_name": {
                r["name"]: r["n"] for r in tool_calls_by_name(connection, session_id)
            },
            "edits": edit["n"],
            "lines_added": edit["added"],
            "lines_removed": edit["removed"],
            "commands_by_class": {
                r["command_class"]: r["n"] for r in commands_by_class(connection, session_id)
            },
        },
        "files": {
            "withheld": not full,
            "edits": [
                {
                    "path": r["path"],
                    "edits": r["n"],
                    "lines_added": r["added"] or 0,
                    "lines_removed": r["removed"] or 0,
                }
                for r in file_rows
            ],
        },
        "usage": usage_views.usage_of_session(connection, session_id),
        "commits": [
            {
                "commit_hash": r["commit_hash"],
                "committer_at": r["committer_at"],
                "method": r["method"],
                "method_note": r["method_note"],
                "confidence": r["confidence"],
                "rank": r["rank"],
                "lines_matched": r["lines_matched"],
                "added_lines": r["added_lines"],
                "coverage": r["coverage"],
            }
            for r in attributed_commits(connection, session_id)
        ],
        "commits_fact": counted["fact"],
        "commits_inferred": counted["inferred"],
        "commits_uncertain": counted["uncertain"],
        "coverage": counted["coverage"],
        "outcomes": outcomes_views.outcome_shares(
            outcomes_views.outcomes_of(connection, session_id)
        ),
        "outcomes_suppressed": row["repo_key"]
        in outcomes_views.suppressed_repositories(connection),
        "outcomes_suppressed_reason": outcomes_views.suppression_notes(connection).get(
            row["repo_key"]
        ),
        "behaviour_facts": session_facts(connection, session_id),
        "hooks": _hook_turns(hook_timeline(connection, session_id)),
        "hand_edits": hand_edits(connection, session_id),
        "archive": {
            "files": len(archive_rows),
            "bytes": archive_total,
            "by_source": dict(by_source),
            "rows": (
                [
                    {
                        "path": r["path"],
                        "source": r["source"],
                        "size": r["size"],
                        "generation": r["generation"],
                    }
                    for r in archive_rows
                ]
                if list_files
                else None
            ),
        },
    }


def _hook_turns(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    turns: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        turns.setdefault(row["prompt_id"] or "", []).append(row)
    result = []
    for turn_id, events in turns.items():
        first, last = events[0], events[-1]
        result.append(
            {
                "turn_id": turn_id or None,
                "events": len(events),
                "first_ts": first["ts"],
                "head_before": first["head"],
                "head_after": last["head"],
                "dirty_count": last["dirty_count"],
            }
        )
    return result
