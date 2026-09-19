"""`prudence status`: everything recorded, and where it is.

Decision P5 says the user can always see what was recorded, so this command shows the
paths as well as the counts, and it lists the record types the parser did not
recognise: a format change is visible here before it matters anywhere else.
"""

from __future__ import annotations

import sqlite3

import click

from prudence import __version__
from prudence import config as config_module
from prudence.cli.render import size
from prudence.paths import database_file
from prudence.store import archive, db, derived


@click.command()
def status() -> None:
    """Show what Prudence has recorded so far."""
    config = config_module.load()
    lines = [f"prudence {__version__}", f"config: {config.path}", f"data:   {database_file()}", ""]
    if not config.repositories:
        lines.append("No repository is enabled. Run `prudence init` to choose what is recorded.")
        click.echo("\n".join(lines))
        return

    database_exists = database_file().exists()
    connection = db.connect() if database_exists else None
    try:
        lines.append(f"{'repository':<32} {'level':<14} {'files':>7} {'archived':>10}")
        for repo in sorted(config.repositories.values(), key=lambda r: r.name):
            files, archived = _per_repo(connection, repo.key)
            lines.append(f"{repo.name[:32]:<32} {repo.level:<14} {files:>7} {size(archived):>10}")
        lines.append("")
        if connection is None:
            lines.append("Nothing ingested yet. Run `prudence ingest`.")
        else:
            lines.extend(_store_lines(connection))
    finally:
        if connection is not None:
            connection.close()
    click.echo("\n".join(lines))


def _per_repo(connection: sqlite3.Connection | None, repo_key: str) -> tuple[int, int]:
    if connection is None:
        return 0, 0
    row = connection.execute(
        "SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS size FROM archive_file"
        " WHERE repo_key = ?",
        (repo_key,),
    ).fetchone()
    return row["files"], row["size"]


def _store_lines(connection: sqlite3.Connection) -> list[str]:
    files, original, stored = archive.archive_totals(connection)
    counts = derived.counts(connection)
    lines = [
        f"archive: {files} files, {size(original)} of agent data, {size(stored)} stored compressed",
    ]
    if counts["session"] < 0:
        lines.append("derived tables: not built yet. Run `prudence ingest` or `prudence rebuild`.")
        return lines
    lines.append(
        f"derived: {counts['session']} sessions, {counts['record']} records, "
        f"{counts['turn']} turns, {counts['tool_call']} tool calls "
        f"(parser version {derived.PARSER_VERSION})"
    )
    resumed = connection.execute(
        "SELECT COUNT(*) FROM session WHERE notes LIKE '%resumed%'"
    ).fetchone()[0]
    if resumed:
        lines.append(f"resumed sessions noted: {resumed}")
    unknown = connection.execute(
        "SELECT type, claude_version, count FROM unknown_record_type ORDER BY count DESC, type"
    ).fetchall()
    if not unknown:
        lines.append("unknown record types: none")
        return lines
    lines.append(f"unknown record types ({len(unknown)} type and version pairs):")
    for row in unknown:
        lines.append(f"  {row['type']:<28} {row['claude_version'] or '?':<12} {row['count']}")
    return lines
