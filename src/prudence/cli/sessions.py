"""`prudence sessions`: one line per session, with what it did and what it is credited with.

This is the table the whole record exists to print, so it shows its own weaknesses on
the same line as its numbers. Coverage sits beside the commit count because a session
credited with three commits it explains four lines of has not written three commits.
The notes column carries the capture level and how the session found its repository,
because a row derived through a fallback should not look like a row read straight off
the working directory.

Sittings, not sessions, are how long someone actually sat there: a Desktop session can
stay open for days, so a gap of more than an hour is counted as a new sitting.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta

import click

from prudence import config as config_module
from prudence.paths import database_file
from prudence.store import db

SITTING_GAP = timedelta(minutes=60)
DEFAULT_WINDOW = "7d"
_WINDOW = re.compile(r"^(\d+)([dhw])$")
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}


@click.command()
@click.option(
    "--last",
    "window",
    default=DEFAULT_WINDOW,
    show_default=True,
    metavar="7d|30d|90d",
    help="How far back to look.",
)
@click.option("--project", "project", metavar="NAME", help="One repository, by name or key.")
def sessions(window: str, project: str | None) -> None:
    """List recent sessions with their edits, commands and attributed commits."""
    since = _since(window)
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = _repo_key(connection, project)
        click.echo(render(connection, since, repo_key, window))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def render(connection: sqlite3.Connection, since: str, repo_key: str | None, window: str) -> str:
    """The table, built from the derived tables alone."""
    names = {row["repo_key"]: row["name"] for row in connection.execute("SELECT * FROM repository")}
    query = (
        "SELECT session_id, repo_key, first_at, capture_level, notes FROM session"
        " WHERE first_at >= ?"
    )
    parameters: list[str] = [since]
    if repo_key is not None:
        query += " AND repo_key = ?"
        parameters.append(repo_key)
    rows = list(connection.execute(query + " ORDER BY first_at", parameters))
    if not rows:
        return f"No session in the last {window}."

    ids = [row["session_id"] for row in rows]
    sittings = _sittings(connection, ids)
    turns = _count(connection, "SELECT session_id, COUNT(*) FROM turn", ids)
    edits = _count(connection, "SELECT session_id, COUNT(*) FROM edit", ids)
    commands = _count(connection, "SELECT session_id, COUNT(*) FROM command", ids)
    credited = _credited(connection, ids)

    lines = [
        f"{'session':<10} {'repository':<20} {'started':<16} {'sit':>4} {'prompts':>8} "
        f"{'edits':>6} {'bash':>5} {'commits':>8} {'coverage':>9}  notes"
    ]
    for row in rows:
        session_id = row["session_id"]
        count, coverage = credited.get(session_id, (0, None))
        name = names.get(row["repo_key"], row["repo_key"] or "unassigned")
        lines.append(
            f"{session_id[:8]:<10} {name[:20]:<20} {(row['first_at'] or '')[:16]:<16} "
            f"{sittings.get(session_id, 1):>4} {turns.get(session_id, 0):>8} "
            f"{edits.get(session_id, 0):>6} {commands.get(session_id, 0):>5} "
            f"{count:>8} {_percent(coverage):>9}  {_notes(row)}"
        )
    lines.append("")
    lines.append(
        f"{len(rows)} sessions in the last {window}. Commits are those where the session "
        "committed in the session or won the line match; coverage is the mean share of a "
        "commit's added lines that session wrote."
    )
    return "\n".join(lines)


def _since(window: str) -> str:
    match = _WINDOW.match(window.strip().lower())
    if not match:
        raise click.UsageError(f"{window!r} is not a window like 7d, 30d or 90d.")
    delta = timedelta(**{_UNITS[match.group(2)]: int(match.group(1))})
    return (datetime.now(UTC) - delta).strftime("%Y-%m-%dT%H:%M:%S")


def _repo_key(connection: sqlite3.Connection, project: str | None) -> str | None:
    if project is None:
        return None
    for row in connection.execute("SELECT repo_key, name FROM repository"):
        if project in (row["repo_key"], row["name"]):
            return row["repo_key"]
    repo = config_module.load().find(project)
    if repo is None:
        raise click.UsageError(f"No enabled repository called {project!r}.")
    return repo.key


def _sittings(connection: sqlite3.Connection, ids: list[str]) -> dict[str, int]:
    """How many times the developer sat down, counting a gap over an hour as a new one."""
    result: dict[str, int] = {}
    previous: dict[str, datetime] = {}
    for row in _select(
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
            result[row["session_id"]] += 1
        previous[row["session_id"]] = moment
    return result


def _credited(
    connection: sqlite3.Connection, ids: list[str]
) -> dict[str, tuple[int, float | None]]:
    """Commits a session won, and the mean coverage over exactly those commits."""
    result: dict[str, tuple[int, float | None]] = {}
    for row in _select(
        connection,
        "SELECT session_id, COUNT(DISTINCT commit_hash) AS commits, AVG(coverage) AS coverage"
        " FROM attribution WHERE rank = 1 AND method IN ('in_session', 'line_match')",
        ids,
        " GROUP BY session_id",
    ):
        result[row["session_id"]] = (row["commits"], row["coverage"])
    return result


def _count(connection: sqlite3.Connection, query: str, ids: list[str]) -> dict[str, int]:
    return {row[0]: row[1] for row in _select(connection, query, ids, " GROUP BY session_id")}


def _select(
    connection: sqlite3.Connection, query: str, ids: list[str], suffix: str
) -> list[sqlite3.Row]:
    """Run a query over a list of sessions, in batches SQLite will accept."""
    rows: list[sqlite3.Row] = []
    joiner = " AND " if " WHERE " in query else " WHERE "
    for start in range(0, len(ids), 400):
        batch = ids[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        statement = f"{query}{joiner}session_id IN ({placeholders}){suffix}"
        rows.extend(connection.execute(statement, batch))
    return rows


def _notes(row: sqlite3.Row) -> str:
    notes = [row["notes"]] if row["notes"] else []
    if row["capture_level"] and row["capture_level"] != "full":
        notes.insert(0, row["capture_level"])
    return "; ".join(notes)


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"
