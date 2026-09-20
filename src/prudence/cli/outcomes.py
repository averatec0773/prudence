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

import sqlite3

import click

from prudence import config as config_module
from prudence.paths import database_file
from prudence.store import db, views
from prudence.store import outcomes as outcomes_module

DEFAULT_WINDOW = "90d"


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
def outcomes(window: str, project: str | None) -> None:
    """Show survival and rework per session, with the coverage behind each figure."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = _repo_key(connection, project)
        click.echo(render(connection, window, repo_key))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def render(connection: sqlite3.Connection, window: str, repo_key: str | None) -> str:
    """The per-session table, the per-repository totals, and what the words mean."""
    since = views.resolve_date(window)
    query = "SELECT session_id, repo_key, first_at FROM session WHERE first_at >= ?"
    parameters: list[str] = [since]
    if repo_key is not None:
        query += " AND repo_key = ?"
        parameters.append(repo_key)
    rows = list(connection.execute(query + " ORDER BY first_at", parameters))
    if not rows:
        return f"No session in the last {window}."

    ids = [row["session_id"] for row in rows]
    fates = views.outcomes_map(connection, ids)
    credited = views.credited_map(connection, ids)
    names = views.repository_names(connection)
    suppressed = views.suppressed_repositories(connection)

    withheld = sorted(suppressed & {row["repo_key"] for row in rows})
    lines = []
    for key in withheld:
        lines.append(
            f"{names.get(key, key)}: no outcome facts, because more than "
            f"{outcomes_module.OTHER_AUTHOR_SHARE * 100:.0f}% of that repository's commits in "
            "the window carry an author email hash other than the majority's. Survival there "
            "would be about somebody else's code as much as yours."
        )
    if withheld:
        lines.append("")
    lines.append(_header())
    shown = 0
    for row in rows:
        totals = fates.get(row["session_id"])
        if not totals:
            continue
        shown += 1
        lines.append(
            _row(
                row["session_id"][:8],
                names.get(row["repo_key"], row["repo_key"] or "unassigned"),
                totals,
                credited.get(row["session_id"], {}),
            )
        )
    if not shown:
        lines.append("  no session in this window is credited with a line that could be followed")

    lines.append("")
    lines.append("per repository")
    lines.append(_header())
    per_repo = views.outcomes_by_repository(connection, ids)
    for key, totals in sorted(per_repo.items(), key=lambda item: names.get(item[0], item[0])):
        lines.append(_row("", names.get(key, key), totals, totals))
    for key in withheld:
        lines.append(f"  {names.get(key, key):<16} suppressed, see the note above")
    lines.append("")
    lines.extend(_footer(shown, len(rows), window))
    return "\n".join(lines)


def _header() -> str:
    return (
        f"{'session':<9} {'repository':<16} {'lines':>7} {'alive 7d':>14} {'alive 30d':>14} "
        f"{'alive 90d':>14} {'alive head':>14} {'rework':>7} {'coverage':>9}  method"
    )


def _row(session: str, repository: str, totals: dict[str, int], counted: dict) -> str:
    return (
        f"{session:<9} {repository[:16]:<16} {totals['lines']:>7} "
        f"{_cell(totals['alive_7d'], totals['measured_7d']):>14} "
        f"{_cell(totals['alive_30d'], totals['measured_30d']):>14} "
        f"{_cell(totals['alive_90d'], totals['measured_90d']):>14} "
        f"{_cell(totals['alive_head'], totals['lines']):>14} "
        f"{_percent(views.share(totals['reworked'], totals['lines'])):>7} "
        f"{_percent(counted.get('coverage')):>9}  {_method(counted)}"
    )


def _cell(alive: int, measured: int) -> str:
    """`82% (1204)`: the share and the lines it is over. A dash means not measured yet."""
    if not measured:
        return "-"
    return f"{alive / measured * 100:.0f}% ({measured})"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def _method(counted: dict) -> str:
    if not counted:
        return ""
    return f"{counted.get('fact', 0)} fact, {counted.get('inferred', 0)} inferred"


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
        "Rework means a later commit within ninety days, carrying the same author email hash "
        "as the original, removed that line from that path.",
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
