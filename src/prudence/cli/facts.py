"""`prudence facts`: one row per session, one column per behaviour fact.

Reads `session_fact`, which `prudence ingest` and `prudence rebuild` both produce after
every other table: one row per session and fact the fact could compute. A blank cell
means the fact does not apply to that session, or the capture level it ran at withheld
what the fact needed, not zero (rule 10: an absent measurement is NULL, never a
fabricated zero). The footer names every column's trust level once, so the table itself
stays free of per-cell qualifiers.

The waste facts are compact on purpose: `loop_tok` is the share of the session's own
tokens spent inside test-fix loops rather than a raw count, and `giant_turn_tokens` is
left to `--json`, which carries every fact's raw value and the session's token total.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta

import click

from prudence import config as config_module
from prudence.facts import registry
from prudence.paths import database_file
from prudence.store import db, views

DEFAULT_WINDOW = "30d"
_WINDOW = re.compile(r"^(\d+)([dhw])$")
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}

# fact name -> short column header, in the order `prudence facts` prints its columns.
_HEADERS = {
    "sittings": "sit",
    "files_edited_unread": "unread",
    "formatter_runs": "fmt",
    "test_runs": "test",
    "tests_before_commit": "pretest",
    "commit_attempts_per_commit": "attempts",
    "repeated_errors": "rerr",
    "subagent_used": "subagt",
    "compactions": "compact",
    "context_resets": "ctxrst",
    "prompts_per_active_hour": "p/hr",
    "hand_edits_between_turns": "handedit",
    "test_fix_loops": "loops",
    "test_fix_loop_tokens": "loop_tok",
    "reread_files": "reread",
    "giant_turns": "giant",
    "changes_after_compaction": "chg_cmp",
}
_PERCENT = {"tests_before_commit"}
# Printed as a share of the session's own tokens, not as a count of tokens.
_SHARE_OF_TOKENS = {"test_fix_loop_tokens"}
# Left out of the table to keep it narrow; `--json` carries them.
_JSON_ONLY = {"giant_turn_tokens"}
_ONE_DECIMAL = {"commit_attempts_per_commit", "prompts_per_active_hour"}


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
@click.option("--json", "as_json", is_flag=True, help="Every fact's raw value, as JSON.")
def facts(window: str, project: str | None, as_json: bool) -> None:
    """List recent sessions with their behaviour facts."""
    since = _since(window)
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = _repo_key(connection, project)
        if as_json:
            click.echo(json.dumps(summary(connection, since, repo_key, window), indent=2))
        else:
            click.echo(render(connection, since, repo_key, window))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def summary(connection: sqlite3.Connection, since: str, repo_key: str | None, window: str) -> dict:
    """The same sessions as the table, with every fact's raw value and no formatting.

    A fact that does not apply to a session is absent from its `facts`, as it is absent
    from `session_fact`; `total_tokens` is None for a session that reported no usage.
    """
    names = {row["repo_key"]: row["name"] for row in connection.execute("SELECT * FROM repository")}
    rows = _sessions(connection, since, repo_key)
    ids = [row["session_id"] for row in rows]
    values = _values(connection, ids)
    tokens = views.usage_map(connection, ids)
    return {
        "window": window,
        "since": since,
        "repo_key": repo_key,
        "trust": {fact.name: fact.trust for fact in registry.FACTS},
        "sessions": [
            {
                "session_id": row["session_id"],
                "repo_key": row["repo_key"],
                "project": names.get(row["repo_key"], row["repo_key"]),
                "first_at": row["first_at"],
                "total_tokens": tokens.get(row["session_id"]),
                "facts": values.get(row["session_id"], {}),
            }
            for row in rows
        ],
    }


def _sessions(
    connection: sqlite3.Connection, since: str, repo_key: str | None
) -> list[sqlite3.Row]:
    query = "SELECT session_id, repo_key, first_at FROM session WHERE first_at >= ?"
    parameters: list[str] = [since]
    if repo_key is not None:
        query += " AND repo_key = ?"
        parameters.append(repo_key)
    return list(connection.execute(query + " ORDER BY first_at", parameters))


def render(connection: sqlite3.Connection, since: str, repo_key: str | None, window: str) -> str:
    """The table, built from `session` and `session_fact`, and `usage` for one share."""
    names = {row["repo_key"]: row["name"] for row in connection.execute("SELECT * FROM repository")}
    rows = _sessions(connection, since, repo_key)
    if not rows:
        return f"No session in the last {window}."

    ids = [row["session_id"] for row in rows]
    values = _values(connection, ids)
    tokens = views.usage_map(connection, ids)

    columns = [
        (fact.name, _HEADERS[fact.name]) for fact in registry.FACTS if fact.name not in _JSON_ONLY
    ]
    widths = {name: max(len(header), 6) for name, header in columns}

    lines = [
        f"{'session':<10} {'repository':<16} {'started':<11} "
        + " ".join(f"{header:>{widths[name]}}" for name, header in columns)
    ]
    for row in rows:
        session_id = row["session_id"]
        name = names.get(row["repo_key"], row["repo_key"] or "unassigned")
        found = values.get(session_id, {})
        cells = [
            f"{_format(name, found.get(name), tokens.get(session_id)):>{widths[name]}}"
            for name, _ in columns
        ]
        lines.append(
            f"{session_id[:8]:<10} {name[:16]:<16} {(row['first_at'] or '')[:10]:<11} "
            + " ".join(cells)
        )
    lines.append("")
    lines.append(
        f"{len(rows)} sessions in the last {window}. A dash means the fact does not apply to "
        "that session, or the capture level it ran at withheld what the fact needed."
    )
    lines.append(
        "loop_tok is the share of the session's tokens spent inside test-fix loops; "
        "`--json` has every raw value."
    )
    lines.append("trust: " + ", ".join(f"{header} {_trust(name)}" for name, header in columns))
    return "\n".join(lines)


def _values(connection: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for start in range(0, len(ids), 400):
        batch = ids[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        for row in connection.execute(
            "SELECT session_id, fact, value FROM session_fact"
            f" WHERE session_id IN ({placeholders})",
            batch,
        ):
            result.setdefault(row["session_id"], {})[row["fact"]] = row["value"]
    return result


def _trust(name: str) -> str:
    return next(fact.trust for fact in registry.FACTS if fact.name == name)


def _format(fact_name: str, value: float | None, session_tokens: int | None = None) -> str:
    if value is None:
        return "-"
    if fact_name in _SHARE_OF_TOKENS:
        return f"{value / session_tokens * 100:.0f}%" if session_tokens else "-"
    if fact_name in _PERCENT:
        return f"{value * 100:.0f}%"
    if fact_name in _ONE_DECIMAL:
        return f"{value:.1f}"
    return f"{value:.0f}"


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
