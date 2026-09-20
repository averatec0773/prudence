"""`prudence observations`: what the join found, in plain words with the numbers.

The analysis is entirely in `store/observations.py`; this file is layout and nothing
else. Two decisions live here, both of them presentation:

- a project's rows and the pooled rows are separate blocks, never one list, because a
  pooled row speaks for every project at once and principle 2 keeps a finding inside the
  project it came from;
- every sentence is followed by its coverage and method, indented under it, because an
  observation without its caveat is a number read without it.

There is no ordering by size here. Rows come back in a fixed order so that two runs of
the same store print the same page, and so that nothing on the page reads as a ranking.
"""

from __future__ import annotations

import sqlite3

import click

from prudence import config as config_module
from prudence.paths import database_file
from prudence.store import db, views
from prudence.store import observations as observations_module


@click.command()
@click.option("--project", "project", metavar="NAME", help="One repository, by name or key.")
def observations(project: str | None) -> None:
    """Show how your outcomes differ between sessions with and without each behaviour."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        repo_key = repo_key_for(connection, project)
        click.echo(render(connection, repo_key))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def render(connection: sqlite3.Connection, repo_key: str | None) -> str:
    """Every observation, the projects first and the pooled rows in their own block."""
    names = views.repository_names(connection)
    rows = views.observations(connection, repo_key)
    lines = block(rows, names)
    lines.append("")
    lines.extend(_footer(rows))
    return "\n".join(lines)


def block(rows: list[dict], names: dict[str, str]) -> list[str]:
    """The sentences, each with its caveat, projects first and pooled rows separately."""
    if not rows:
        return [observations_module.NOTHING]
    project = [row for row in rows if row["repo_key"] != observations_module.POOLED]
    pooled = [row for row in rows if row["repo_key"] == observations_module.POOLED]
    lines: list[str] = []
    for group in (project, pooled):
        if not group:
            continue
        if lines:
            lines.append("")
        for row in group:
            lines.append(observations_module.sentence(row, names.get(row["repo_key"])))
            lines.append(f"  {observations_module.caveat(row)}")
    return lines


def _footer(rows: list[dict]) -> list[str]:
    pooled = sum(1 for row in rows if row["repo_key"] == observations_module.POOLED)
    return [
        f"{len(rows)} observations, {pooled} of them pooled over every project.",
        "An observation splits your own sessions that are credited with lines that could be "
        "followed into two sides at one threshold, and takes the median of each side. It is "
        f"kept only when both sides hold at least {observations_module.MIN_SESSIONS} sessions "
        f"and the two medians are at least {observations_module.MIN_GAP * 100:.0f} points "
        "apart.",
        "A row that says across your projects pools every project and is computed only for a "
        "behaviour no single project had enough sessions to answer; it is not a finding about "
        "any one of them.",
        "Coverage is the mean share of a counted commit's added lines the session itself wrote, "
        "over the sessions on both sides, and the method says how many of those commits are "
        "known rather than inferred.",
        "These are descriptions, not advice: they say what the two sides did, not what to do "
        f"(observation fact version {observations_module.FACT_VERSION}).",
    ]


def repo_key_for(connection: sqlite3.Connection, project: str | None) -> str | None:
    """The repository key a `--project` names, from the store or from the config."""
    if project is None:
        return None
    resolved = views.repo_key_for(connection, project)
    if resolved is not None:
        return resolved
    repo = config_module.load().find(project)
    if repo is None:
        raise click.UsageError(f"No enabled repository called {project!r}.")
    return repo.key
