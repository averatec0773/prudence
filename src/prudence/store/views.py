"""Read-only queries over the derived tables, shared by `prudence show` and the MCP server.

Both surfaces need the same facts about a session: `cli/show.py` renders them as text,
`prudence/mcp/server.py` returns them as JSON. This module is the one place the SQL is
written, so the two never drift. Nothing here formats anything; that stays with the
caller. No function returns message text, because none is stored anywhere it could be
read from (architecture rule: no code leaves the archive).
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from prudence.store import attribution as attribution_module

SITTING_GAP = timedelta(minutes=60)
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

TOKEN_COLUMNS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


# --- one session, the data `prudence show --session` and `show_session` both need -----


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


# --- token usage, as the archive reported it per API response -------------------------


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


# --- commits per session, counted by the confidence rule ------------------------------


def credited_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Commits per session split by confidence, and the mean coverage over the counted ones.

    One commit can carry two rows for the same session (it ran `git commit` and it wrote
    the lines), so each commit is counted once, at its best label. `uncertain` is
    reported and never added to `commits`, which is what principle 3 asks for.
    """
    order = {label: index for index, label in enumerate(attribution_module.CONFIDENCES)}
    best: dict[str, dict[str, tuple[str, float | None]]] = defaultdict(dict)
    for row in _batched(
        connection,
        "SELECT session_id, commit_hash, confidence, coverage FROM attribution",
        ids,
        "",
    ):
        seen = best[row["session_id"]].get(row["commit_hash"])
        if seen is None or order[row["confidence"]] < order[seen[0]]:
            best[row["session_id"]][row["commit_hash"]] = (row["confidence"], row["coverage"])

    result: dict[str, dict[str, Any]] = {}
    for session_id, commits in best.items():
        counted = Counter(label for label, _ in commits.values())
        coverages = [
            coverage
            for label, coverage in commits.values()
            if label in attribution_module.COUNTED and coverage is not None
        ]
        result[session_id] = {
            "fact": counted[attribution_module.FACT],
            "inferred": counted[attribution_module.INFERRED],
            "uncertain": counted[attribution_module.UNCERTAIN],
            "commits": counted[attribution_module.FACT] + counted[attribution_module.INFERRED],
            "coverage": (sum(coverages) / len(coverages)) if coverages else None,
        }
    return result


def credited(connection: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    """The same counts for one session, zeroed when it is credited with nothing."""
    return credited_map(connection, [session_id]).get(
        session_id, {"fact": 0, "inferred": 0, "uncertain": 0, "commits": 0, "coverage": None}
    )


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
    row = session_row(connection, session_id)
    if row is None:
        return None
    names = repository_names(connection)
    full = row["capture_level"] == "full"

    edit = edit_totals(connection, session_id)
    file_rows = edited_files(connection, session_id) if full else []
    archive_rows = archived_files(connection, session_id)
    counted = credited(connection, session_id)

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
        "usage": usage_of_session(connection, session_id),
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
        "behaviour_facts": session_facts(connection, session_id),
        "hooks": _hook_turns(hook_timeline(connection, session_id)),
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


# --- searching across sessions, the data `search_sessions` needs ----------------------


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
    empty = {"fact": 0, "inferred": 0, "uncertain": 0, "commits": 0, "coverage": None}
    results = [
        {
            "session_id": row["session_id"],
            "repository": names.get(row["repo_key"], row["repo_key"]),
            "started_at": row["first_at"],
            "sittings": sat.get(row["session_id"], 1),
            "prompts": turns.get(row["session_id"], 0),
            "edits": edits.get(row["session_id"], 0),
            "tokens": tokens.get(row["session_id"]),
            "commits_attributed": counted.get(row["session_id"], empty)["commits"],
            "commits_fact": counted.get(row["session_id"], empty)["fact"],
            "commits_inferred": counted.get(row["session_id"], empty)["inferred"],
            "commits_uncertain": counted.get(row["session_id"], empty)["uncertain"],
            "coverage": counted.get(row["session_id"], empty)["coverage"],
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


def _batched(
    connection: sqlite3.Connection, query: str, ids: list[str], suffix: str
) -> list[sqlite3.Row]:
    """Run a query over a list of sessions, in batches SQLite will accept as parameters."""
    rows: list[sqlite3.Row] = []
    joiner = " AND " if " WHERE " in query else " WHERE "
    for start in range(0, len(ids), 400):
        batch = ids[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        rows.extend(
            connection.execute(f"{query}{joiner}session_id IN ({placeholders}){suffix}", batch)
        )
    return rows


def _scalar(connection: sqlite3.Connection, query: str, session_id: str) -> int:
    return connection.execute(query, (session_id,)).fetchone()[0]


# --- `prudence status`, as JSON --------------------------------------------------------


def status_summary(connection: sqlite3.Connection | None) -> dict[str, Any]:
    """What `prudence status` prints, as JSON. Ids, counts and versions only."""
    from prudence import config as config_module
    from prudence.store import archive, attribution, commits, derived, rewritten, spool

    config = config_module.load()
    repositories = []
    for repo in sorted(config.repositories.values(), key=lambda r: r.name):
        files, archived_bytes = 0, 0
        counted = {"sessions": 0, "edits": 0, "commits": 0}
        if connection is not None:
            row = connection.execute(
                "SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS size FROM archive_file"
                " WHERE repo_key = ?",
                (repo.key,),
            ).fetchone()
            files, archived_bytes = row["files"], row["size"]
            for name, statement in (
                ("sessions", "SELECT COUNT(*) FROM session WHERE repo_key = ?"),
                ("edits", "SELECT COUNT(*) FROM edit WHERE repo_key = ?"),
                ("commits", 'SELECT COUNT(*) FROM "commit" WHERE repo_key = ?'),
            ):
                try:
                    counted[name] = connection.execute(statement, (repo.key,)).fetchone()[0]
                except sqlite3.OperationalError:
                    counted[name] = 0
        repositories.append(
            {
                "repo_key": repo.key,
                "name": repo.name,
                "level": repo.level,
                "files": files,
                "archived_bytes": archived_bytes,
                **counted,
            }
        )

    result: dict[str, Any] = {
        "repositories": repositories,
        "database_built": connection is not None,
    }
    if connection is None:
        return result

    files, original, stored = archive.archive_totals(connection)
    result["archive"] = {"files": files, "original_bytes": original, "stored_bytes": stored}
    counts = derived.counts(connection)
    result["built"] = counts["session"] >= 0
    if not result["built"]:
        return result
    result["derived"] = {**counts, "parser_version": derived.PARSER_VERSION}
    result["usage"] = usage_totals(connection)

    harvested, commit_lines = commits.counts(connection)
    result["commits"] = {
        "harvested": harvested,
        "added_lines_hashed": commit_lines,
        "fact_version": commits.FACT_VERSION,
        "by_method": attribution.counts(connection),
        "by_confidence": attribution.confidence_counts(connection),
        "printed_hashes": rewritten.resolution(connection),
        "attribution_fact_version": attribution.FACT_VERSION,
        "commit_alias_fact_version": rewritten.FACT_VERSION,
    }
    events, hook_sessions = spool.counts(connection)
    result["hook_events"] = {
        "events": events,
        "sessions": hook_sessions,
        "fact_version": spool.FACT_VERSION,
    }
    result["unassigned_sessions"] = connection.execute(
        "SELECT COUNT(*) FROM session WHERE repo_key IS NULL"
    ).fetchone()[0]
    result["unknown_record_types"] = [
        dict(row)
        for row in connection.execute(
            "SELECT type, claude_version, count FROM unknown_record_type ORDER BY count DESC, type"
        )
    ]
    return result
