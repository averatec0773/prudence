"""Token usage as the archive reported it, by bucket and by purpose, and the active time."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from prudence.store import tokens
from prudence.store.buckets import BUCKETS
from prudence.store.views.common import SITTING_GAP, _batched
from prudence.store.views.sessions import repository_names

TOKEN_COLUMNS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


def session_usage(connection: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    """One row per model this session used, with its requests and its four token counts."""
    return connection.execute(
        "SELECT COALESCE(model, '?') AS model, COUNT(*) AS requests,"
        " SUM(input_tokens) AS input_tokens,"
        " SUM(output_tokens) AS output_tokens,"
        " SUM(cache_read_tokens) AS cache_read_tokens,"
        " SUM(cache_creation_tokens) AS cache_creation_tokens,"
        f" SUM({tokens.total_sql()}) AS total_tokens"
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
    totals = {column: tokens.sum_nullable(row[column] for row in rows) for column in TOKEN_COLUMNS}
    return {
        "requests": sum(row["requests"] for row in rows),
        **totals,
        "total_tokens": sum(row["total_tokens"] for row in rows),
        "by_model": {
            row["model"]: {
                "requests": row["requests"],
                **{column: row[column] for column in TOKEN_COLUMNS},
                "total_tokens": row["total_tokens"],
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
            f"SELECT session_id, SUM({tokens.total_sql()}) AS total FROM usage",
            ids,
            " GROUP BY session_id",
        )
    }


def usage_by_kind_map(
    connection: sqlite3.Connection, ids: list[str]
) -> dict[str, dict[str, int | None]]:
    """The four token counts per session, absent for a session whose records carried none."""
    columns = ", ".join(f"SUM({column}) AS {column}" for column in TOKEN_COLUMNS)
    columns += f", SUM({tokens.total_sql()}) AS total_tokens"
    return {
        row["session_id"]: {
            **{column: row[column] for column in TOKEN_COLUMNS},
            "total_tokens": row["total_tokens"] or 0,
        }
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
    return {
        "sessions": 0,
        "hours": 0.0,
        "measured": 0,
        "total_tokens": 0,
        **dict.fromkeys(TOKEN_COLUMNS, None),
    }


def _accumulate_usage(
    cell: dict[str, Any], counted: dict[str, int | None] | None, hours: float
) -> None:
    cell["sessions"] += 1
    cell["hours"] += hours
    if counted:
        cell["measured"] += 1
        for column in TOKEN_COLUMNS:
            if counted[column] is not None:
                cell[column] = (cell[column] or 0) + counted[column]
        cell["total_tokens"] += counted["total_tokens"] or 0


def usage_totals(connection: sqlite3.Connection) -> dict[str, Any]:
    """Every token the store recorded, in total and per model. Empty before parser 3."""
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS requests, COUNT(DISTINCT session_id) AS sessions,"
            " SUM(input_tokens) AS input_tokens,"
            " SUM(output_tokens) AS output_tokens,"
            " SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cache_creation_tokens) AS cache_creation_tokens,"
            f" SUM({tokens.total_sql()}) AS total_tokens FROM usage"
        ).fetchone()
        models = connection.execute(
            "SELECT COALESCE(model, '?') AS model, COUNT(*) AS requests FROM usage"
            " GROUP BY model ORDER BY requests DESC, model"
        ).fetchall()
    except sqlite3.OperationalError:
        return {"requests": 0, "sessions": 0, "total_tokens": 0, "by_model": {}}
    totals = {column: (0 if row["requests"] == 0 else row[column]) for column in TOKEN_COLUMNS}
    return {
        "requests": row["requests"],
        "sessions": row["sessions"],
        **totals,
        "total_tokens": row["total_tokens"] or 0,
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


# --- buckets: what each reply did, summed ----------------------------------------------


def bucket_usage(
    connection: sqlite3.Connection,
    since: str,
    until: str | None = None,
    repo_key: str | None = None,
) -> list[sqlite3.Row]:
    """The replies that began in a window, summed per project, bucket and UTC day.

    One row per (`repo_key`, `bucket`, `day`) from the `response` table: `responses`,
    `measured` (the replies that reported usage at all), the four token counts, and
    `heuristic_tokens` (the part whose bucket rests on the name heuristic). A reply with
    no bucket, whose record could not be read, comes back under `bucket` None: it is the
    coverage gap, never a fifth bucket. Empty before parser version 6.
    """
    columns = ", ".join(f"SUM(p.{column}) AS {column}" for column in TOKEN_COLUMNS)
    total = tokens.total_sql("p")
    query, parameters = _window(
        f"SELECT s.repo_key AS repo_key, p.bucket AS bucket, substr(p.started_at, 1, 10) AS day,"
        f" COUNT(*) AS responses, COUNT(COALESCE(p.total_input_tokens, p.input_tokens))"
        f" AS measured, {columns}, SUM({total}) AS total_tokens,"
        f" SUM(CASE WHEN p.heuristic = 1 THEN {total} ELSE 0 END) AS heuristic_tokens"
        " FROM response p JOIN session s ON s.session_id = p.session_id",
        since,
        until,
        repo_key,
    )
    try:
        return connection.execute(
            query + " GROUP BY s.repo_key, p.bucket, day ORDER BY day", parameters
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def bucket_sessions(
    connection: sqlite3.Connection,
    since: str,
    until: str | None = None,
    repo_key: str | None = None,
) -> int:
    """How many sessions had at least one reply in the window `bucket_usage` sums."""
    query, parameters = _window(
        "SELECT COUNT(DISTINCT p.session_id) FROM response p"
        " JOIN session s ON s.session_id = p.session_id",
        since,
        until,
        repo_key,
    )
    try:
        return connection.execute(query, parameters).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _window(
    query: str, since: str, until: str | None, repo_key: str | None
) -> tuple[str, list[str]]:
    """The WHERE clause both bucket queries share: replies begun in a window, one project."""
    query += " WHERE p.started_at >= ?"
    parameters = [since]
    if until is not None:
        query += " AND p.started_at < ?"
        parameters.append(until)
    if repo_key is not None:
        query += " AND s.repo_key = ?"
        parameters.append(repo_key)
    return query, parameters


def bucket_totals(connection: sqlite3.Connection) -> dict[str, Any]:
    """Every reply in the store, by bucket, with the rule version and the doubts beside it.

    `heuristic_tokens` rest on a guess from a tool's name; `coverage_gap_tokens` are in
    replies no bucket could be given at all; `subagent_tokens` are subagents' replies and
    `subagent_unlinked_tokens` the part of them no turn was found for.
    """
    total = tokens.total_sql()
    empty: dict[str, Any] = {
        "responses": 0,
        "total_tokens": 0,
        "by_bucket": {},
        "rule_version": None,
        "heuristic_tokens": 0,
        "coverage_gap_tokens": 0,
        "subagent_tokens": 0,
        "subagent_unlinked_tokens": 0,
    }
    try:
        rows = connection.execute(
            f"SELECT bucket, COUNT(*) AS responses, SUM({total}) AS tokens,"
            f" SUM(CASE WHEN heuristic = 1 THEN {total} ELSE 0 END) AS heuristic,"
            f" SUM(CASE WHEN agent_id IS NOT NULL THEN {total} ELSE 0 END) AS subagent,"
            f" SUM(CASE WHEN agent_id IS NOT NULL AND turn_id IS NULL THEN {total} ELSE 0 END)"
            " AS unlinked, MAX(bucket_rule_version) AS version FROM response GROUP BY bucket"
        ).fetchall()
    except sqlite3.OperationalError:
        return empty
    if not rows:
        return empty
    return {
        "responses": sum(row["responses"] for row in rows),
        "total_tokens": sum(row["tokens"] for row in rows),
        "by_bucket": {
            row["bucket"]: {"responses": row["responses"], "total_tokens": row["tokens"]}
            for row in rows
            if row["bucket"] is not None
        },
        "rule_version": max(row["version"] for row in rows),
        "heuristic_tokens": sum(row["heuristic"] for row in rows),
        "coverage_gap_tokens": sum(row["tokens"] for row in rows if row["bucket"] is None),
        "subagent_tokens": sum(row["subagent"] for row in rows),
        "subagent_unlinked_tokens": sum(row["unlinked"] for row in rows),
    }


def bucket_shares_map(
    connection: sqlite3.Connection, ids: list[str]
) -> dict[str, dict[str, float]]:
    """Each session's bucketed tokens as four shares. Absent: no reply with tokens."""
    total = tokens.total_sql()
    found: dict[str, dict[str, int]] = {}
    for row in _batched(
        connection,
        f"SELECT session_id, bucket, SUM({total}) AS tokens FROM response WHERE bucket IS NOT NULL",
        ids,
        " GROUP BY session_id, bucket",
    ):
        found.setdefault(row["session_id"], {})[row["bucket"]] = row["tokens"] or 0
    shares: dict[str, dict[str, float]] = {}
    for session_id, by_bucket in found.items():
        grand = sum(by_bucket.values())
        if grand:
            shares[session_id] = {bucket: by_bucket.get(bucket, 0) / grand for bucket in BUCKETS}
    return shares


# --- where the tokens went: the waste facts, summed -------------------------------------

# The facts `waste_totals` sums, as `session_fact` names them.
WASTE_FACTS = (
    "test_fix_loops",
    "test_fix_loop_tokens",
    "reread_files",
    "giant_turns",
    "giant_turn_tokens",
    "changes_after_compaction",
)


def waste_totals(connection: sqlite3.Connection, ids: list[str]) -> dict[str, Any]:
    """The waste facts of the sessions asked about, summed, beside their tokens.

    `tokens` is the total `usage_map` gives for the same sessions, so
    `test_fix_loop_tokens / tokens` is a share of exactly the set it was summed over; a
    session that reported no usage adds to neither side. A fact no session of the set has
    (all of them at `metadata-only` capture, for `reread_files`) is None, not zero.
    """
    found: dict[str, float | None] = dict.fromkeys(WASTE_FACTS)
    names = ", ".join(f"'{name}'" for name in WASTE_FACTS)
    query = f"SELECT fact, SUM(value) AS total FROM session_fact WHERE fact IN ({names})"
    try:
        for row in _batched(connection, query, ids, " GROUP BY fact"):
            found[row["fact"]] = (found[row["fact"]] or 0) + row["total"]
    except sqlite3.OperationalError:
        pass
    tokens = usage_map(connection, ids)
    return {
        "sessions": len(ids),
        "measured": len(tokens),
        "tokens": sum(tokens.values()),
        **found,
    }
