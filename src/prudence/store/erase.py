"""Forgetting: taking a session or a repository back out of the store for good.

The counterpart of decision P5. A user who can see everything that was recorded must
also be able to remove it, and removal has to be complete: the derived rows, the
harvested rows, and the archived bytes those rows were built from. Deleting only the
derived tables would leave the transcript sitting in the archive and the next `ingest`
would build it all again.

Two things are deliberately not done here. Nothing is deleted from Claude Code's own
directory: the user's agent history is theirs, and `forget` is about Prudence's copy.
And `VACUUM` is not run, because it rewrites the whole database file and on a store of
a few gigabytes that takes minutes; the space is reused by the next ingest anyway, and
`prudence forget --vacuum` is there for a user who wants the file to shrink now.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

# Every derived and harvested table that holds a session id, with the column it uses.
SESSION_TABLES = (
    ("attribution", "session_id"),
    ("command", "session_id"),
    ("commit_alias", "session_id"),
    ("usage", "session_id"),
    ("edit", "session_id"),
    ("hook_event", "session_id"),
    ("record", "session_id"),
    ("session", "session_id"),
    ("tool_call", "session_id"),
    ("turn", "session_id"),
)


@dataclass
class Removal:
    """What a `forget` actually removed, counted so the user can be told."""

    sessions: int = 0
    archive_files: int = 0
    archive_bytes: int = 0
    stored_bytes: int = 0
    commits: int = 0
    repositories: int = 0
    rows: Counter[str] = field(default_factory=Counter)

    @property
    def total_rows(self) -> int:
        return sum(self.rows.values())


def sessions_of(connection: sqlite3.Connection, repo_key: str) -> list[str]:
    """Every session id recorded for one repository, from the derived table and the archive."""
    found = {
        row[0]
        for row in _safe(connection, "SELECT session_id FROM session WHERE repo_key = ?", repo_key)
    }
    found.update(
        row[0]
        for row in _safe(
            connection,
            "SELECT DISTINCT session_id FROM archive_file WHERE repo_key = ? AND session_id"
            " IS NOT NULL",
            repo_key,
        )
    )
    return sorted(found)


def forget_sessions(connection: sqlite3.Connection, session_ids: list[str]) -> Removal:
    """Delete these sessions from every table, and the archived bytes behind them."""
    removal = Removal(sessions=len(session_ids))
    if not session_ids:
        return removal
    for batch in _batches(session_ids):
        marks = ", ".join("?" * len(batch))
        _count_archive(connection, f"session_id IN ({marks})", batch, removal)
        removal.rows["edit_line"] += _execute(
            connection,
            "DELETE FROM edit_line WHERE tool_use_id IN"
            f" (SELECT tool_use_id FROM edit WHERE session_id IN ({marks}))",
            batch,
        )
        for table, column in SESSION_TABLES:
            removal.rows[table] += _execute(
                connection, f"DELETE FROM {table} WHERE {column} IN ({marks})", batch
            )
        _delete_archive(connection, f"session_id IN ({marks})", batch)
    return removal


def forget_project(connection: sqlite3.Connection, repo_key: str) -> Removal:
    """Delete a whole repository: its sessions, its commits and its own row."""
    removal = forget_sessions(connection, sessions_of(connection, repo_key))
    key = [repo_key]
    _count_archive(connection, "repo_key = ?", key, removal)
    removal.rows["commit_line"] += _execute(
        connection,
        'DELETE FROM commit_line WHERE commit_hash IN (SELECT commit_hash FROM "commit"'
        " WHERE repo_key = ?)",
        key,
    )
    removal.rows["attribution"] += _execute(
        connection,
        'DELETE FROM attribution WHERE commit_hash IN (SELECT commit_hash FROM "commit"'
        " WHERE repo_key = ?)",
        key,
    )
    removal.rows["commit_alias"] += _execute(
        connection,
        'DELETE FROM commit_alias WHERE commit_hash IN (SELECT commit_hash FROM "commit"'
        " WHERE repo_key = ?)",
        key,
    )
    removal.rows["line_fate"] += _execute(
        connection,
        'DELETE FROM line_fate WHERE commit_hash IN (SELECT commit_hash FROM "commit"'
        " WHERE repo_key = ?)",
        key,
    )
    removal.commits = _execute(connection, 'DELETE FROM "commit" WHERE repo_key = ?', key)
    removal.rows["commit"] += removal.commits
    removal.rows["hook_event"] += _execute(
        connection, "DELETE FROM hook_event WHERE repo_key = ?", key
    )
    removal.repositories = _execute(connection, "DELETE FROM repository WHERE repo_key = ?", key)
    removal.rows["repository"] += removal.repositories
    _delete_archive(connection, "repo_key = ?", key)
    return removal


def vacuum(connection: sqlite3.Connection) -> int:
    """Rewrite the database so the freed pages return to the file system. Slow on purpose."""
    before = connection.execute("PRAGMA page_count").fetchone()[0]
    page = connection.execute("PRAGMA page_size").fetchone()[0]
    connection.execute("VACUUM")
    after = connection.execute("PRAGMA page_count").fetchone()[0]
    return max(0, (before - after) * page)


def _count_archive(
    connection: sqlite3.Connection, where: str, parameters: list[str], removal: Removal
) -> None:
    row = connection.execute(
        f"SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS size FROM archive_file WHERE {where}",
        parameters,
    ).fetchone()
    stored = connection.execute(
        "SELECT COALESCE(SUM(LENGTH(data)), 0) AS stored FROM archive_chunk WHERE path IN"
        f" (SELECT path FROM archive_file WHERE {where})",
        parameters,
    ).fetchone()
    removal.archive_files += row["files"]
    removal.archive_bytes += row["size"]
    removal.stored_bytes += stored["stored"]


def _delete_archive(connection: sqlite3.Connection, where: str, parameters: list[str]) -> None:
    connection.execute(
        f"DELETE FROM archive_chunk WHERE path IN (SELECT path FROM archive_file WHERE {where})",
        parameters,
    )
    connection.execute(f"DELETE FROM archive_file WHERE {where}", parameters)


def _execute(connection: sqlite3.Connection, statement: str, parameters: list[str]) -> int:
    """Run a delete, treating a table that was never built as nothing to delete."""
    try:
        return connection.execute(statement, parameters).rowcount
    except sqlite3.OperationalError:
        return 0


def _safe(connection: sqlite3.Connection, query: str, *parameters: str) -> list[tuple]:
    try:
        return [tuple(row) for row in connection.execute(query, parameters)]
    except sqlite3.OperationalError:
        return []


def _batches(values: list[str], width: int = 400) -> list[list[str]]:
    return [values[start : start + width] for start in range(0, len(values), width)]
