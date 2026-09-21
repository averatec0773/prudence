"""`prudence usage`: where the tokens and the hours went, by purpose and by project.

This is the founder's own question from the first conversation, and principle 3 names it
as welcome: factual feedback on the data, including usage broken down by purpose. So the
table is a breakdown and nothing else. No budget, no target, no judgement about which
purpose deserves the tokens, and no total across purposes pretending to be a score.

Three things are kept honest here.

The four token counts are printed separately, because they are not interchangeable: a
cache read is cheap and a cache write is not, and a single total hides which of them a
week was made of. They are shown in thousands, which is the unit the numbers live at.

Active hours are the sum of a session's sittings, not the clock between its first and
last record: a session left open overnight did not take fourteen hours. A session whose
records are a single instant contributes no time at all.

A dash is not a zero. A session whose Claude Code version wrote no usage fields has no
token rows, and its purpose still appears with its hours.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any

import click

from prudence import config as config_module
from prudence.cli.render import thousands
from prudence.facts import purpose as purpose_module
from prudence.paths import database_file
from prudence.store import db, views

DEFAULT_WINDOW = "30d"

# The order the purposes are printed in when they have the same total, so that two runs
# of the same store never disagree about the order of two equal rows.
ORDER = purpose_module.PURPOSES

TOKEN_COLUMNS = views.TOKEN_COLUMNS


@click.command()
@click.option(
    "--last",
    "window",
    default=DEFAULT_WINDOW,
    show_default=True,
    metavar="7d|30d|90d",
    help="How far back to look, by the session's first record.",
)
@click.option("--project", "project", metavar="NAME", help="One repository, by name or key.")
@click.option("--json", "as_json", is_flag=True, help="Print the same numbers as JSON.")
def usage(window: str, project: str | None, as_json: bool) -> None:
    """Show tokens and active hours by session purpose, by project and by week."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = _repo_key(connection, project)
        data = summary(connection, window, repo_key)
        click.echo(json.dumps(data, indent=2) if as_json else render(data))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def summary(connection: sqlite3.Connection, window: str, repo_key: str | None) -> dict[str, Any]:
    """The numbers the three tables are made of, before anything is formatted.

    `render` below turns this into the page and `--json` prints it as it is, so the two
    cannot disagree: there is one query and one set of sums. Token counts stay raw and
    `measured` travels with them, because a group no session of which recorded usage is
    a dash rather than a zero and only the caller knows how to draw a dash.
    """
    since = views.resolve_date(window)
    query = "SELECT session_id, repo_key, first_at FROM session WHERE first_at >= ?"
    parameters: list[str] = [since]
    if repo_key is not None:
        query += " AND repo_key = ?"
        parameters.append(repo_key)
    rows = list(connection.execute(query + " ORDER BY first_at", parameters))
    head = {"window": window, "since": since, "repo_key": repo_key}
    if not rows:
        return {
            **head,
            "sessions": 0,
            "total": _cell(_empty(), _empty()),
            "by_purpose": [],
            "by_project": [],
            "by_week": [],
            "purpose_rule_version": views.purpose_rule_version(connection),
            "notes": [],
        }

    ids = [row["session_id"] for row in rows]
    purposes = views.purpose_map(connection, ids)
    tokens = _tokens(connection, ids)
    active = views.active_seconds_map(connection, ids)
    names = views.repository_names(connection)

    by_purpose: dict[str, dict[str, float]] = defaultdict(_empty)
    by_project: dict[tuple[str, str], dict[str, float]] = defaultdict(_empty)
    by_week: dict[tuple[str, str], dict[str, float]] = defaultdict(_empty)
    for row in rows:
        session_id = row["session_id"]
        label = purposes.get(session_id, purpose_module.UNKNOWN)
        project = names.get(row["repo_key"], row["repo_key"] or "unassigned")
        counted = tokens.get(session_id)
        cell = {
            "sessions": 1.0,
            "hours": active.get(session_id, 0.0) / 3600,
            "measured": 1.0 if counted else 0.0,
            **{column: float((counted or {}).get(column, 0)) for column in TOKEN_COLUMNS},
        }
        _add(by_purpose[label], cell)
        _add(by_project[(project, label)], cell)
        _add(by_week[(_week(row["first_at"]), label)], cell)

    total = _empty()
    for cell in by_purpose.values():
        _add(total, cell)

    return {
        **head,
        "sessions": len(rows),
        "total": _cell(total, total),
        "by_purpose": [
            {"purpose": label, **_cell(cell, total)} for label, cell in _sorted(by_purpose)
        ],
        "by_project": [
            {"project": project, "purpose": label, **_cell(cell, total)}
            for (project, label), cell in sorted(
                by_project.items(), key=lambda item: (item[0][0], ORDER.index(item[0][1]))
            )
        ],
        "by_week": [
            {"week": week, "purpose": label, **_cell(cell, total)}
            for (week, label), cell in sorted(
                by_week.items(), key=lambda item: (item[0][0], ORDER.index(item[0][1]))
            )
        ],
        "purpose_rule_version": views.purpose_rule_version(connection),
        "notes": _footer(connection, len(rows), window),
    }


def render(data: dict[str, Any]) -> str:
    """The three tables and the footer, from `summary` and nothing else."""
    window = data["window"]
    if not data["sessions"]:
        return f"No session in the last {window}."

    lines = [f"tokens and active hours by purpose, last {window}", _header("purpose")]
    for cell in data["by_purpose"]:
        lines.append(_row(cell["purpose"], cell))
    lines.append(_row("all purposes", data["total"]))

    lines.append("")
    lines.append("by project")
    lines.append(f"{'project':<22} " + _header("purpose"))
    for cell in data["by_project"]:
        lines.append(f"{cell['project'][:22]:<22} " + _row(cell["purpose"], cell))

    lines.append("")
    lines.append("by week")
    lines.append(f"{'week':<10} {'purpose':<14} {'tokens':>9} {'sessions':>9} {'active h':>9}")
    for cell in data["by_week"]:
        lines.append(
            f"{cell['week']:<10} {cell['purpose']:<14} {_total_tokens(cell):>9} "
            f"{cell['sessions']:>9} {cell['hours']:>9.1f}"
        )

    lines.append("")
    lines.extend(data["notes"])
    return "\n".join(lines)


def _cell(cell: dict[str, float], total: dict[str, float]) -> dict[str, Any]:
    """One group's numbers, with the share of the page's total it is."""
    grand = _sum(total)
    return {
        "sessions": int(cell["sessions"]),
        "measured": int(cell["measured"]),
        "hours": cell["hours"],
        **{column: int(cell[column]) for column in TOKEN_COLUMNS},
        "total_tokens": int(_sum(cell)),
        "share": (_sum(cell) / grand) if grand else None,
    }


def _empty() -> dict[str, float]:
    return {
        "sessions": 0.0,
        "hours": 0.0,
        "measured": 0.0,
        **dict.fromkeys(TOKEN_COLUMNS, 0.0),
    }


def _add(totals: dict[str, float], cell: dict[str, float]) -> None:
    for key, value in cell.items():
        totals[key] += value


def _sorted(by_purpose: dict[str, dict[str, float]]) -> list[tuple[str, dict[str, float]]]:
    """Most tokens first, ties broken by the fixed purpose order rather than by chance."""
    return sorted(
        by_purpose.items(),
        key=lambda item: (-_sum(item[1]), ORDER.index(item[0])),
    )


def _sum(cell: dict[str, float]) -> float:
    return sum(cell[column] for column in TOKEN_COLUMNS)


def _header(first: str) -> str:
    return (
        f"{first:<14} {'sessions':>8} {'input':>8} {'output':>8} {'cache rd':>9} {'cache wr':>9} "
        f"{'total':>9} {'share':>6} {'active h':>9}"
    )


def _row(label: str, cell: dict[str, Any]) -> str:
    """One row. A group no session of which recorded usage is dashes, not zeroes."""
    share = "-" if cell["share"] is None else f"{cell['share'] * 100:.0f}%"
    measured = bool(cell["measured"])
    return (
        f"{label:<14} {cell['sessions']:>8} "
        + " ".join(
            f"{(_k(cell[column]) if measured else '-'):>{width}}"
            for column, width in zip(TOKEN_COLUMNS, (8, 8, 9, 9), strict=True)
        )
        + f" {_total_tokens(cell):>9} {share:>6} {cell['hours']:>9.1f}"
    )


def _total_tokens(cell: dict[str, Any]) -> str:
    return _k(cell["total_tokens"]) if cell["measured"] else "-"


def _k(value: float) -> str:
    """A token count in thousands. A real zero is printed as zero, not as a dash."""
    return thousands(int(round(value)))


def _week(first_at: str | None) -> str:
    """The ISO week the session started in, as `2026-W38`."""
    if not first_at:
        return "?"
    try:
        moment = datetime.fromisoformat(first_at.replace("Z", "+00:00"))
    except ValueError:
        return "?"
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


def _tokens(connection: sqlite3.Connection, ids: list[str]) -> dict[str, dict[str, int]]:
    """The four counts per session, absent for a session whose records carried none."""
    found: dict[str, dict[str, int]] = {}
    columns = ", ".join(f"SUM(COALESCE({column}, 0)) AS {column}" for column in TOKEN_COLUMNS)
    for start in range(0, len(ids), 400):
        batch = ids[start : start + 400]
        placeholders = ", ".join("?" * len(batch))
        for row in connection.execute(
            f"SELECT session_id, {columns} FROM usage WHERE session_id IN ({placeholders})"
            " GROUP BY session_id",
            batch,
        ):
            found[row["session_id"]] = {column: row[column] or 0 for column in TOKEN_COLUMNS}
    return found


def _footer(connection: sqlite3.Connection, sessions: int, window: str) -> list[str]:
    version = views.purpose_rule_version(connection) or purpose_module.RULE_VERSION
    return [
        f"{sessions} sessions in the last {window}. Token counts are in thousands, split into "
        "input, output, cache read and cache write because they do not cost the same; a dash "
        "means that Claude Code version wrote no usage fields, which is not zero tokens.",
        "Active hours are the sum of a session's sittings, counting a gap of more than an hour "
        "as a break, not the clock between its first and last record.",
        f"The purpose label comes from rules over the session's tool mix (purpose rule version "
        f"{version}): counts of reads, searches, edits, test runs, repeated errors and commits. "
        "Nothing in the conversation is read to produce it.",
    ]


def _repo_key(connection: sqlite3.Connection, project: str | None) -> str | None:
    if project is None:
        return None
    resolved = views.repo_key_for(connection, project)
    if resolved is not None:
        return resolved
    repo = config_module.load().find(project)
    if repo is None:
        raise click.UsageError(f"No enabled repository called {project!r}.")
    return repo.key
