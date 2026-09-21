"""`prudence sessions`: one line per session, with what it did and what it is credited with.

This is the table the whole record exists to print, so it shows its own weaknesses on
the same line as its numbers. Coverage sits beside the commit count because a session
credited with three commits it explains four lines of has not written three commits.
The commits column separates what is known from what is inferred and prints the
uncertain attributions beside both, because a count that quietly absorbs its own doubt
is the kind of number this project exists not to print. The notes column carries the
capture level and how the session found its repository, because a row derived through a
fallback should not look like a row read straight off the working directory.

Tokens are the four counts of an API response added together (input, output, cache read
and cache creation), in thousands. A dash means no usage was recorded at all, which is
what a Claude Code version older than the usage fields leaves behind; it is not a zero.

Sittings, not sessions, are how long someone actually sat there: a Desktop session can
stay open for days, so a gap of more than an hour is counted as a new sitting.

The purpose column is a label, not a measurement: rules over the session's tool mix
(`facts/purpose.py`), never a reading of the conversation. It is printed as one word
with no share and no rank beside it, because that is all it is.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

import click

from prudence import config as config_module
from prudence.cli.render import thousands
from prudence.paths import database_file
from prudence.store import db, views

SITTING_GAP = timedelta(minutes=60)
DEFAULT_WINDOW = "7d"
EMPTY = {"fact": 0, "inferred": 0, "uncertain": 0, "commits": 0, "coverage": None}
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
@click.option("--json", "as_json", is_flag=True, help="Print the same rows as JSON.")
def sessions(window: str, project: str | None, as_json: bool) -> None:
    """List recent sessions with their edits, commands and attributed commits."""
    since = _since(window)
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = _repo_key(connection, project)
        data = summary(connection, since, repo_key, window)
        click.echo(json.dumps(data, indent=2) if as_json else render(data))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def summary(
    connection: sqlite3.Connection, since: str, repo_key: str | None, window: str
) -> dict[str, Any]:
    """One dictionary per session, from the derived tables alone.

    `render` lays these out as the table and `--json` prints them as they are. A count
    that does not exist is None rather than 0 here as well: no usage row means no token
    number, and a thirty-day mark still in the future is not a death.
    """
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
    head = {"window": window, "since": since, "repo_key": repo_key}
    if not rows:
        return {**head, "sessions": [], "notes": []}

    ids = [row["session_id"] for row in rows]
    sittings = _sittings(connection, ids)
    turns = _count(connection, "SELECT session_id, COUNT(*) FROM turn", ids)
    edits = _count(connection, "SELECT session_id, COUNT(*) FROM edit", ids)
    commands = _count(connection, "SELECT session_id, COUNT(*) FROM command", ids)
    credited = views.credited_map(connection, ids)
    tokens = views.usage_map(connection, ids)
    fates = views.outcomes_map(connection, ids)
    purposes = views.purpose_map(connection, ids)

    listed = []
    for row in rows:
        session_id = row["session_id"]
        counted = credited.get(session_id, EMPTY)
        totals = fates.get(session_id)
        listed.append(
            {
                "session_id": session_id,
                "repo_key": row["repo_key"],
                "project": names.get(row["repo_key"], row["repo_key"] or "unassigned"),
                "started_at": row["first_at"],
                "purpose": purposes.get(session_id),
                "sittings": sittings.get(session_id, 1),
                "prompts": turns.get(session_id, 0),
                "edits": edits.get(session_id, 0),
                "commands": commands.get(session_id, 0),
                "tokens": tokens.get(session_id),
                "commits_fact": counted["fact"],
                "commits_inferred": counted["inferred"],
                "commits_uncertain": counted["uncertain"],
                "coverage": counted["coverage"],
                "survival_30d": (
                    views.share(totals["alive_30d"], totals["measured_30d"]) if totals else None
                ),
                "capture_level": row["capture_level"],
                "capture_notes": row["notes"],
            }
        )
    return {**head, "sessions": listed, "notes": _footer(len(rows), window)}


def render(data: dict[str, Any]) -> str:
    """The table, from `summary` and nothing else."""
    if not data["sessions"]:
        return f"No session in the last {data['window']}."
    lines = [
        f"{'session':<10} {'repository':<20} {'started':<16} {'purpose':<13} {'sit':>4} "
        f"{'prompts':>8} {'edits':>6} {'bash':>5} {'tokens':>7} {'commits':>13} "
        f"{'coverage':>9} {'alive 30d':>10}  notes"
    ]
    for cell in data["sessions"]:
        lines.append(
            f"{cell['session_id'][:8]:<10} {cell['project'][:20]:<20} "
            f"{(cell['started_at'] or '')[:16]:<16} "
            f"{(cell['purpose'] or '-'):<13} "
            f"{cell['sittings']:>4} {cell['prompts']:>8} "
            f"{cell['edits']:>6} {cell['commands']:>5} "
            f"{thousands(cell['tokens']):>7} {_commits(cell):>13} "
            f"{_percent(cell['coverage']):>9} {_percent(cell['survival_30d']):>10}  "
            f"{_notes(cell)}"
        )
    lines.append("")
    lines.extend(data["notes"])
    return "\n".join(lines)


def _footer(count: int, window: str) -> list[str]:
    return [
        f"{count} sessions in the last {window}. Commits are counted as "
        "fact (+inferred), with (?N) uncertain attributions beside them, which enter no "
        "statistic; coverage is the mean share of a counted commit's added lines that "
        "session wrote. Tokens are input, output and cache tokens together, in thousands. "
        "Alive 30d is the share of the session's counted lines still in the same file "
        "thirty days after the commit; a dash means that mark has not happened yet. "
        "`prudence outcomes` prints the rest.",
        "Purpose is a label from rules over the session's tool mix, not from reading the "
        "conversation; `prudence usage` groups the tokens and the hours by it.",
    ]


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


def _commits(cell: dict[str, Any]) -> str:
    """`7 (+2) (?1)`: seven known, two inferred, one uncertain that is counted nowhere."""
    text = str(cell["commits_fact"])
    if cell["commits_inferred"]:
        text += f" (+{cell['commits_inferred']})"
    if cell["commits_uncertain"]:
        text += f" (?{cell['commits_uncertain']})"
    return text


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


def _notes(cell: dict[str, Any]) -> str:
    notes = [cell["capture_notes"]] if cell["capture_notes"] else []
    if cell["capture_level"] and cell["capture_level"] != "full":
        notes.insert(0, cell["capture_level"])
    return "; ".join(notes)


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"
