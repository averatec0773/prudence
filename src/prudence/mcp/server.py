"""The MCP server: three read-only tools over the store, for Claude Code and other agents.

Same promise as every other surface, stated once here because an agent reading this
code is exactly the audience: no message text ever leaves the store, at any capture
level. A tool returns ids, dates, counts, repository names, full file paths (never at
`metadata-only`) and commit hashes, and nothing else. Rule 7 in ARCHITECTURE.md applies
here as much as anywhere: a tool reports numbers already computed; it does not compute
new ones and it never writes prose about them.

The rest of Prudence never imports the `mcp` package. This module is the one place that
does, and it fails at import time with an actionable message rather than a bare
`ModuleNotFoundError` if the optional dependency is missing.
"""

from __future__ import annotations

import sqlite3
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as error:  # pragma: no cover - exercised only when `mcp` is absent
    raise ImportError(
        "The mcp package is not installed. Install with: uv tool install 'prudence-dev[mcp]'"
    ) from error

from prudence.paths import database_file
from prudence.store import db, views

NOT_INGESTED = "Nothing ingested yet. Run `prudence ingest`."

mcp = FastMCP("prudence")


def _connect() -> sqlite3.Connection | None:
    """Open the store, or None when `prudence ingest` has never run.

    `db.connect()` creates the file the moment it is called, so the existence check has
    to come first or every tool would quietly manufacture an empty database.
    """
    if not database_file().exists():
        return None
    return db.connect()


def _resolve_session(connection: sqlite3.Connection, token: str) -> str | None:
    """A session id from an id or an unambiguous prefix; None otherwise, never a guess."""
    rows = [
        row["session_id"]
        for row in connection.execute(
            "SELECT session_id FROM session WHERE session_id LIKE ? ORDER BY session_id",
            (f"{token}%",),
        )
    ]
    return rows[0] if len(rows) == 1 else None


@mcp.tool()
def search_sessions(
    query: str = "",
    repo: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search recorded sessions, newest first.

    `query` matches full-capture edited file paths (repository-relative) and Bash
    command classes (`git_commit`, `test`, and so on); it never matches message text,
    because none is stored at any capture level. `repo` filters by repository name or
    key. `since`/`until` accept an ISO date (`2026-09-01`) or `7d`/`30d`/`90d` shorthand.
    `limit` defaults to 20 and is capped at 100 no matter what is asked for.

    Returns `{"results": [...], "total": N, "truncated": bool}`, or `{"message": "..."}`
    when nothing has been ingested yet. Each result carries only: session_id,
    repository, started_at, sittings, prompts, edits, tokens (input, output and cache
    tokens together, null when the Claude Code version recorded none), commits_fact,
    commits_inferred, commits_uncertain, commits_attributed (fact plus inferred, never
    uncertain), coverage and capture_notes. No message text is ever included.
    """
    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        repo_key = None
        if repo:
            repo_key = views.repo_key_for(connection, repo)
            if repo_key is None:
                return {"results": [], "total": 0, "truncated": False}
        return views.search_sessions(
            connection, query=query, repo_key=repo_key, since=since, until=until, limit=limit
        )
    finally:
        connection.close()


@mcp.tool()
def show_session(session_id: str) -> dict[str, Any]:
    """Everything `prudence show --session` prints, as structured JSON.

    `session_id` may be a full id or an unambiguous prefix. Returns identity (repository,
    capture level, timestamps, sittings), counts (records, turns, tool calls, edits,
    commands), token usage per model (null when the Claude Code version recorded none),
    edited files at full capture only (withheld at `metadata-only`), attributed commits
    with their method, confidence, rank and coverage, and the commits_fact,
    commits_inferred and commits_uncertain counts. Returns `{"message": "..."}` when
    nothing has been ingested yet or when the id does not match exactly one session.
    No message text at any capture level, because none is stored.
    """
    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        resolved = _resolve_session(connection, session_id)
        if resolved is None:
            return {"message": f"No single recorded session matches {session_id!r}."}
        summary = views.session_summary(connection, resolved)
        assert summary is not None  # resolved id came straight from the session table
        return summary
    finally:
        connection.close()


@mcp.tool()
def status() -> dict[str, Any]:
    """What `prudence status` prints, as JSON.

    Per-repository counts (files, archived bytes, sessions, edits, commits) and
    store-wide totals (archive size, derived table counts, token usage, commits by
    attribution method and by confidence, what became of every commit hash a session
    printed, hook events, unassigned sessions, unknown record types). No message text.
    """
    connection = _connect()
    try:
        return views.status_summary(connection)
    finally:
        if connection is not None:
            connection.close()


def run() -> None:
    """Start the server on stdio. The entry point `prudence mcp` calls."""
    mcp.run()
