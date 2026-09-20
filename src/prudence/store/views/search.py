"""Searching across sessions, the data `prudence sessions` and `search_sessions` need."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from prudence.store.views.common import SITTING_GAP, _batched
from prudence.store.views.outcomes import (
    credited_map,
    outcome_shares,
    outcomes_map,
    suppressed_repositories,
)
from prudence.store.views.sessions import repository_names
from prudence.store.views.usage import purpose_map, usage_map

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def repo_key_for(connection: sqlite3.Connection, token: str) -> str | None:
    """A repository name or key resolved to its key, or None when nothing matches."""
    for row in connection.execute("SELECT repo_key, name FROM repository"):
        if token in (row["repo_key"], row["name"]):
            return row["repo_key"]
    return None


def resolve_date(value: str, now: datetime | None = None) -> str:
    """An ISO date, or `7d`/`30d`/`90d` shorthand for "that far back from now"."""
    import re

    window = re.match(r"^(\d+)([dhw])$", value.strip().lower())
    if window:
        units = {"h": "hours", "d": "days", "w": "weeks"}
        delta = timedelta(**{units[window.group(2)]: int(window.group(1))})
        return ((now or datetime.now(UTC)) - delta).strftime("%Y-%m-%dT%H:%M:%S")
    text = value.strip()
    return f"{text}T00:00:00" if len(text) == 10 else text


def search_sessions(
    connection: sqlite3.Connection,
    query: str = "",
    repo_key: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Sessions matching `query`, newest first, capped at `MAX_LIMIT` regardless of `limit`.

    `query` matches full-capture edited file paths (`edit.rel_path`) and command classes
    (`command.command_class`); it never matches message text, because none is stored.
    Returns `{"results": [...], "total": N, "truncated": bool}`.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    clauses: list[str] = []
    params: list[str] = []
    if repo_key:
        clauses.append("session.repo_key = ?")
        params.append(repo_key)
    if since:
        clauses.append("session.first_at >= ?")
        params.append(resolve_date(since))
    if until:
        clauses.append("session.first_at <= ?")
        params.append(resolve_date(until))
    if query:
        clauses.append(
            "session.session_id IN ("
            "SELECT session_id FROM edit WHERE rel_path LIKE ?"
            " UNION SELECT session_id FROM command WHERE command_class LIKE ?"
            ")"
        )
        like = f"%{query}%"
        params.extend([like, like])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"SELECT session_id, repo_key, first_at, capture_level, notes FROM session{where}"
        " ORDER BY first_at DESC",
        params,
    ).fetchall()
    total = len(rows)
    page = rows[:limit]
    names = repository_names(connection)
    ids = [row["session_id"] for row in page]
    turns = _counted_map(connection, "SELECT session_id, COUNT(*) FROM turn", ids)
    edits = _counted_map(connection, "SELECT session_id, COUNT(*) FROM edit", ids)
    counted = credited_map(connection, ids)
    tokens = usage_map(connection, ids)
    sat = _sittings_map(connection, ids)
    fates = outcomes_map(connection, ids)
    suppressed = suppressed_repositories(connection)
    purposes = purpose_map(connection, ids)
    empty = {"fact": 0, "inferred": 0, "uncertain": 0, "commits": 0, "coverage": None}
    results = [
        {
            "session_id": row["session_id"],
            "repository": names.get(row["repo_key"], row["repo_key"]),
            "started_at": row["first_at"],
            "purpose": purposes.get(row["session_id"]),
            "sittings": sat.get(row["session_id"], 1),
            "prompts": turns.get(row["session_id"], 0),
            "edits": edits.get(row["session_id"], 0),
            "tokens": tokens.get(row["session_id"]),
            "commits_attributed": counted.get(row["session_id"], empty)["commits"],
            "commits_fact": counted.get(row["session_id"], empty)["fact"],
            "commits_inferred": counted.get(row["session_id"], empty)["inferred"],
            "commits_uncertain": counted.get(row["session_id"], empty)["uncertain"],
            "coverage": counted.get(row["session_id"], empty)["coverage"],
            "outcomes": outcome_shares(fates.get(row["session_id"])),
            "outcomes_suppressed": row["repo_key"] in suppressed,
            "capture_notes": row["notes"],
        }
        for row in page
    ]
    return {"results": results, "total": total, "truncated": total > limit}


def _sittings_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    previous: dict[str, datetime] = {}
    for row in _batched(
        connection,
        "SELECT session_id, timestamp FROM record WHERE timestamp IS NOT NULL",
        ids,
        " ORDER BY session_id, timestamp",
    ):
        try:
            moment = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        last = previous.get(row["session_id"])
        if last is None:
            result[row["session_id"]] = 1
        elif moment - last > SITTING_GAP:
            result[row["session_id"]] = result.get(row["session_id"], 1) + 1
        previous[row["session_id"]] = moment
    return result


def _counted_map(connection: sqlite3.Connection, query: str, ids: list[str]) -> dict[str, int]:
    return {row[0]: row[1] for row in _batched(connection, query, ids, " GROUP BY session_id")}
