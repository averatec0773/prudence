"""`prudence rebuild`: throw the derived tables away and build them again.

This is the command that makes the parser safe to change. It reads only the archive,
so it can be run after any code change, and it never touches the agent's files.
"""

from __future__ import annotations

import click

from prudence import config as config_module
from prudence.store import db, derived


@click.command()
def rebuild() -> None:
    """Rebuild every derived table from the archive."""
    config = config_module.load()
    try:
        with db.ingest_lock():
            connection = db.connect()
            try:
                stats = derived.build(connection, config.levels)
            finally:
                connection.close()
    except db.Locked as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        f"Rebuilt at parser version {derived.PARSER_VERSION}: {stats.sessions} sessions, "
        f"{stats.records} records, {stats.turns} turns, {stats.tool_calls} tool calls, "
        f"{stats.unknown_types} unknown record types, {stats.elapsed:.1f} s."
    )
