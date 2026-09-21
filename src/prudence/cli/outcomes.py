"""`prudence outcomes`: what became of the code each session is credited with.

This is the first surface that answers the question the product exists for, so it is
built to be checkable rather than impressive. Every survival figure is printed as a
percentage and the denominator it is over, because the denominators genuinely differ:
a commit made three weeks ago has a 7-day mark and a 30-day mark but no 90-day mark,
and counting its lines as dead at 90 days would be a lie about young work. A dash is a
measurement that does not exist yet, never a zero.

Coverage and the method mix sit on the same line as the survival figures, because a
session credited with three commits it explains four lines of has not written three
commits, and a number whose confidence is a column away is a number read without it.

A repository where other people commit prints no outcome row at all; it prints why.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import click

from prudence import config as config_module

# The submodule by its full name, never `from prudence.cli import observations`: the
# package binds that name to the command function, not to the module.
from prudence.cli.observations import block as observation_block
from prudence.paths import database_file
from prudence.store import db, views
from prudence.store import observations as observations_module
from prudence.store import outcomes as outcomes_module

DEFAULT_WINDOW = "90d"

# The share keys `views.outcome_shares` adds, all None for a row it declines to compute.
_NO_SHARES = dict.fromkeys(
    (
        "survival_7d",
        "survival_30d",
        "survival_90d",
        "survival_head",
        "survival_head_anywhere",
        "blame_head",
        "reworked_share",
        "fact_version",
    )
)


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
def outcomes(window: str, project: str | None, as_json: bool) -> None:
    """Show survival and rework per session, with the coverage behind each figure."""
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
    """Everything the page is made of, before any of it is laid out.

    `render` below draws it and `--json` prints it as it is, so a surface reading the
    JSON sees the same rows the table does, including the withheld repositories, which
    are part of the answer and not a footnote.
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
            "credited_sessions": 0,
            "withheld": [],
            "by_session": [],
            "by_project": [],
            "observations": [],
            "notes": [],
        }

    ids = [row["session_id"] for row in rows]
    fates = views.outcomes_map(connection, ids)
    credited = views.credited_map(connection, ids)
    names = views.repository_names(connection)
    notes = views.suppression_notes(connection)

    withheld = sorted(set(notes) & {row["repo_key"] for row in rows})
    by_session = [
        {
            "session_id": row["session_id"],
            "project": names.get(row["repo_key"], row["repo_key"] or "unassigned"),
            **_counts(fates[row["session_id"]], credited.get(row["session_id"], {})),
        }
        for row in rows
        if fates.get(row["session_id"])
    ]
    per_repo = views.outcomes_by_repository(connection, ids)
    by_project = [
        {"repo_key": key, "project": names.get(key, key), **_counts(totals, totals)}
        for key, totals in sorted(per_repo.items(), key=lambda item: names.get(item[0], item[0]))
    ]
    return {
        **head,
        "sessions": len(rows),
        "credited_sessions": len(by_session),
        "withheld": [
            {"repo_key": key, "project": names.get(key, key), "note": notes[key]}
            for key in withheld
        ],
        "by_session": by_session,
        "by_project": by_project,
        "observations": _observations(
            connection, repo_key, {row["repo_key"] for row in rows}, names
        ),
        "notes": _footer(len(by_session), len(rows), window),
    }


def render(data: dict[str, Any]) -> str:
    """The per-session table, the per-repository totals, and what the words mean."""
    if not data["sessions"]:
        return f"No session in the last {data['window']}."

    lines = []
    for held in data["withheld"]:
        lines.append(
            f"{held['project']}: no outcome facts, because {held['note']}. Survival there "
            "would be about somebody else's code as much as yours. An identity is yours when "
            "it committed inside one of your sessions, or is a repository's majority author."
        )
    if data["withheld"]:
        lines.append("")
    lines.append(_header())
    for cell in data["by_session"]:
        lines.append(_row(cell["session_id"][:8], cell["project"], cell))
    if not data["by_session"]:
        lines.append("  no session in this window is credited with a line that could be followed")

    lines.append("")
    lines.append("per repository")
    lines.append(_header())
    for cell in data["by_project"]:
        lines.append(_row("", cell["project"], cell))
    for held in data["withheld"]:
        lines.append(f"  {held['project']:<16} suppressed, see the note above")
    lines.append("")
    lines.extend(data["notes"])
    lines.append("")
    lines.append("observations")
    rows = data["observations"]
    lines.extend(observation_block(rows, {row["repo_key"]: row["project"] for row in rows}))
    return "\n".join(lines)


def _counts(totals: dict[str, int], counted: dict) -> dict[str, Any]:
    """One row's fate counters, the shares they make, and the credit behind them.

    The same shape `views.outcome_shares` gives the MCP server, so a surface reading
    either sees one vocabulary. A row with nothing measured keeps the keys and answers
    None, because a mark that has not arrived is not a zero.
    """
    fate = {key: totals.get(key, 0) for key in views.FATE_KEYS}
    shares = views.outcome_shares(fate) or {**views.empty_fate(), **_NO_SHARES}
    return {
        **shares,
        "coverage": counted.get("coverage"),
        "commits_fact": counted.get("fact", 0),
        "commits_inferred": counted.get("inferred", 0),
    }


def _observations(
    connection: sqlite3.Connection,
    repo_key: str | None,
    keys: set[str],
    names: dict[str, str],
) -> list[dict[str, Any]]:
    """The join, for the repositories this table speaks about.

    The observation rows are over the whole store rather than over the window, because a
    split needs more sessions than a short window holds; the window filters which
    projects are shown, never which sessions an observation was computed from.
    """
    if repo_key is not None:
        rows = views.observations(connection, repo_key)
    else:
        rows = [
            row
            for row in views.observations(connection)
            if row["repo_key"] in keys or row["repo_key"] == observations_module.POOLED
        ]
    return [{**row, "project": names.get(row["repo_key"])} for row in rows]


def _header() -> str:
    return (
        f"{'session':<9} {'repository':<16} {'lines':>7} {'alive 7d':>14} {'alive 30d':>14} "
        f"{'alive 90d':>14} {'alive head':>14} {'rework':>7} {'coverage':>9}  method"
    )


def _row(session: str, repository: str, cell: dict[str, Any]) -> str:
    return (
        f"{session:<9} {repository[:16]:<16} {cell['lines']:>7} "
        f"{_cell(cell['alive_7d'], cell['measured_7d']):>14} "
        f"{_cell(cell['alive_30d'], cell['measured_30d']):>14} "
        f"{_cell(cell['alive_90d'], cell['measured_90d']):>14} "
        f"{_cell(cell['alive_head'], cell['lines']):>14} "
        f"{_percent(cell['reworked_share']):>7} "
        f"{_percent(cell['coverage']):>9}  {_method(cell)}"
    )


def _cell(alive: int, measured: int) -> str:
    """`82% (1204)`: the share and the lines it is over. A dash means not measured yet."""
    if not measured:
        return "-"
    return f"{alive / measured * 100:.0f}% ({measured})"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def _method(cell: dict[str, Any]) -> str:
    return f"{cell['commits_fact']} fact, {cell['commits_inferred']} inferred"


def _footer(shown: int, total: int, window: str) -> list[str]:
    return [
        f"{shown} of {total} sessions in the last {window} are credited with lines that could "
        "be followed; the rest are credited with nothing, or only with attributions the "
        "confidence rule calls uncertain, which enter no statistic.",
        "A line is one distinct added line of a commit a session is credited with at fact or "
        "inferred confidence, hashed the same way on both sides.",
        "Alive at 7, 30 or 90 days means the line was still in the same file in the tree the "
        "branch stood at that many days after the commit; a mark still in the future is a dash, "
        "not a death.",
        "Alive at head means the line is still in the same file now; the store also holds "
        "whether it is anywhere at head, which is how a line that moved to another file reads "
        "as moved rather than dead.",
        "Rework means a later commit within ninety days, by one of your own identities, "
        "removed that line from that path (line_fate fact version "
        f"{outcomes_module.FACT_VERSION}).",
        "Coverage is the mean share of a counted commit's added lines that the session itself "
        "wrote, and the method column says how many of those commits are known rather than "
        "inferred.",
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
