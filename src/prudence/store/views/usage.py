"""Token usage as the archive reported it, the purpose label, and the active time it is over."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from prudence.store.views.common import SITTING_GAP, _batched
from prudence.store.views.sessions import repository_names

TOKEN_COLUMNS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


def session_usage(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    """One row per model this session used, with its requests and its four token counts."""
    return connection.execute(
        "SELECT COALESCE(model, '?') AS model, COUNT(*) AS requests,"
        " SUM(COALESCE(input_tokens, 0)) AS input_tokens,"
        " SUM(COALESCE(output_tokens, 0)) AS output_tokens,"
        " SUM(COALESCE(cache_read_tokens, 0)) AS cache_read_tokens,"
        " SUM(COALESCE(cache_creation_tokens, 0)) AS cache_creation_tokens"
        " FROM usage WHERE session_id = ? GROUP BY model ORDER BY model",
        (session_id,),
    ).fetchall()


def usage_of_session(connection: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    """This session's usage, per model and in total, or None when no record carried any.

    None is the honest answer for a Claude Code version that wrote no usage fields, and
    for a session that made no API call at all. It is not zero.
    """
    rows = session_usage(connection, session_id)
    if not rows:
        return None
    totals = {column: sum(row[column] for row in rows) for column in TOKEN_COLUMNS}
    return {
        "requests": sum(row["requests"] for row in rows),
        **totals,
        "total_tokens": sum(totals.values()),
        "by_model": {
            row["model"]: {
                "requests": row["requests"],
                **{column: row[column] for column in TOKEN_COLUMNS},
                "total_tokens": sum(row[column] for column in TOKEN_COLUMNS),
            }
            for row in rows
        },
    }


def usage_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, int]:
    """Total tokens per session, for the sessions asked about. Absent means no usage row."""
    return {
        row["session_id"]: row["total"]
        for row in _batched(
            connection,
            "SELECT session_id, SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)"
            " + COALESCE(cache_read_tokens, 0) + COALESCE(cache_creation_tokens, 0)) AS total"
            " FROM usage",
            ids,
            " GROUP BY session_id",
        )
    }


def usage_by_kind_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, int]]:
    """The four token counts per session, absent for a session whose records carried none."""
    columns = ", ".join(f"SUM(COALESCE({column}, 0)) AS {column}" for column in TOKEN_COLUMNS)
    return {
        row["session_id"]: {column: row[column] or 0 for column in TOKEN_COLUMNS}
        for row in _batched(
            connection, f"SELECT session_id, {columns} FROM usage", ids, " GROUP BY session_id"
        )
    }


def usage_summary(
    connection: sqlite3.Connection,
    since: str,
    until: str | None = None,
    repo_key: str | None = None,
) -> dict[str, Any]:
    """Tokens by kind and active hours, summed by purpose and by project.

    The same sessions and the same sums `prudence usage` (`cli/usage.py`) prints, as
    raw numbers rather than formatted strings, so a surface (the MCP server, the menu
    bar) can present them however it needs to. `until` narrows the window to a fixed
    span, such as one ISO week, in addition to `since`. Empty before `prudence ingest`
    has ever run.
    """
    query = "SELECT session_id, repo_key, first_at FROM session WHERE first_at >= ?"
    parameters: list[str] = [since]
    if until is not None:
        query += " AND first_at < ?"
        parameters.append(until)
    if repo_key is not None:
        query += " AND repo_key = ?"
        parameters.append(repo_key)
    empty = {"sessions": 0, "by_purpose": {}, "by_project": {}, "purpose_rule_version": None}
    try:
        rows = connection.execute(query, parameters).fetchall()
    except sqlite3.OperationalError:
        return empty
    if not rows:
        return {**empty, "purpose_rule_version": purpose_rule_version(connection)}

    from prudence.facts import purpose as purpose_module

    ids = [row["session_id"] for row in rows]
    purposes = purpose_map(connection, ids)
    tokens = usage_by_kind_map(connection, ids)
    active = active_seconds_map(connection, ids)
    names = repository_names(connection)

    by_purpose: dict[str, dict[str, Any]] = {}
    by_project: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        session_id = row["session_id"]
        label = purposes.get(session_id, purpose_module.UNKNOWN)
        project = names.get(row["repo_key"], row["repo_key"] or "unassigned")
        counted = tokens.get(session_id)
        hours = active.get(session_id, 0.0) / 3600
        _accumulate_usage(by_purpose.setdefault(label, _empty_usage_cell()), counted, hours)
        _accumulate_usage(
            by_project.setdefault(project, {}).setdefault(label, _empty_usage_cell()),
            counted,
            hours,
        )

    return {
        "sessions": len(rows),
        "by_purpose": by_purpose,
        "by_project": by_project,
        "purpose_rule_version": purpose_rule_version(connection),
    }


def _empty_usage_cell() -> dict[str, Any]:
    return {"sessions": 0, "hours": 0.0, "measured": 0, **dict.fromkeys(TOKEN_COLUMNS, 0)}


def _accumulate_usage(cell: dict[str, Any], counted: dict[str, int] | None, hours: float) -> None:
    cell["sessions"] += 1
    cell["hours"] += hours
    if counted:
        cell["measured"] += 1
        for column in TOKEN_COLUMNS:
            cell[column] += counted[column]


def usage_totals(connection: sqlite3.Connection) -> dict[str, Any]:
    """Every token the store recorded, in total and per model. Empty before parser 3."""
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS requests, COUNT(DISTINCT session_id) AS sessions,"
            " SUM(COALESCE(input_tokens, 0)) AS input_tokens,"
            " SUM(COALESCE(output_tokens, 0)) AS output_tokens,"
            " SUM(COALESCE(cache_read_tokens, 0)) AS cache_read_tokens,"
            " SUM(COALESCE(cache_creation_tokens, 0)) AS cache_creation_tokens FROM usage"
        ).fetchone()
        models = connection.execute(
            "SELECT COALESCE(model, '?') AS model, COUNT(*) AS requests FROM usage"
            " GROUP BY model ORDER BY requests DESC, model"
        ).fetchall()
    except sqlite3.OperationalError:
        return {"requests": 0, "sessions": 0, "total_tokens": 0, "by_model": {}}
    totals = {column: row[column] or 0 for column in TOKEN_COLUMNS}
    return {
        "requests": row["requests"],
        "sessions": row["sessions"],
        **totals,
        "total_tokens": sum(totals.values()),
        "by_model": {model["model"]: model["requests"] for model in models},
    }


# --- labels: what a session was for, and the active time a usage table divides by -----


def purpose_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, str]:
    """The purpose label of each session asked about. Absent before `session_label` exists."""
    try:
        return {
            row["session_id"]: row["label"]
            for row in _batched(
                connection,
                "SELECT session_id, label FROM session_label WHERE name = 'purpose'",
                ids,
                "",
            )
        }
    except sqlite3.OperationalError:
        return {}


def purpose_of(connection: sqlite3.Connection, session_id: str) -> str | None:
    """One session's purpose, or None when the labels have not been built yet."""
    return purpose_map(connection, [session_id]).get(session_id)


def purpose_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """How many sessions carry each purpose, over the whole store."""
    try:
        return {
            row["label"]: row["n"]
            for row in connection.execute(
                "SELECT label, COUNT(*) AS n FROM session_label WHERE name = 'purpose'"
                " GROUP BY label ORDER BY n DESC, label"
            )
        }
    except sqlite3.OperationalError:
        return {}


def purpose_rule_version(connection: sqlite3.Connection) -> int | None:
    """The rule version the stored labels were produced by, or None when there are none."""
    try:
        row = connection.execute(
            "SELECT MAX(rule_version) AS version FROM session_label WHERE name = 'purpose'"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["version"] if row is not None else None


def active_seconds_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, float]:
    """Active time per session: the sum of its sittings, not the wall clock between them.

    The same 60-minute gap rule `sittings` uses, so a session left open overnight
    contributes the bursts somebody actually sat through and not the night between them.
    A single-record burst has no duration and adds nothing.
    """
    totals: dict[str, float] = {}
    starts: dict[str, datetime] = {}
    previous: dict[str, datetime] = {}
    for row in _batched(
        connection,
        "SELECT session_id, timestamp FROM record WHERE timestamp IS NOT NULL",
        ids,
        " ORDER BY session_id, timestamp",
    ):
        session_id = row["session_id"]
        try:
            moment = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        last = previous.get(session_id)
        if last is None:
            starts[session_id] = moment
        elif moment - last > SITTING_GAP:
            totals[session_id] = (
                totals.get(session_id, 0.0) + (last - starts[session_id]).total_seconds()
            )
            starts[session_id] = moment
        previous[session_id] = moment
    for session_id, last in previous.items():
        totals[session_id] = (
            totals.get(session_id, 0.0) + (last - starts[session_id]).total_seconds()
        )
    return totals
