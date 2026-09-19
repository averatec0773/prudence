"""`prudence ingest`: copy new bytes into the archive, then rebuild what they mean.

Archiving and parsing are one command because they are one promise: after `ingest`,
what the agent wrote is in the archive and the tables agree with it. They are two
functions because only the first is irreversible.
"""

from __future__ import annotations

import click

from prudence import config as config_module
from prudence.cli.render import size
from prudence.store import archive, db, derived


@click.command()
def ingest() -> None:
    """Record everything new from the enabled repositories."""
    config = config_module.load()
    if not config.repositories:
        raise click.UsageError(
            "No repository is enabled. Run `prudence init` to choose what is recorded."
        )
    try:
        with db.ingest_lock():
            _run(config)
    except db.Locked as error:
        raise click.ClickException(str(error)) from error


def _run(config: config_module.Config) -> None:
    connection = db.connect()
    try:
        targets = archive.collect_targets(set(config.repositories))
        stats = archive.archive(connection, targets)
        click.echo(
            f"Archived: {stats.files_seen} files seen, {stats.new_files} new, "
            f"{stats.rearchived_files} rewritten, {stats.unchanged_files} unchanged, "
            f"{size(stats.new_bytes)} new ({stats.new_bytes} bytes), "
            f"{stats.elapsed:.1f} s."
        )
        if stats.missing_files:
            click.echo(f"{stats.missing_files} files disappeared while reading; skipped.")
        built = derived.build(connection, config.levels)
        click.echo(
            f"Parsed: {built.sessions} sessions, {built.records} records, "
            f"{built.turns} turns, {built.tool_calls} tool calls, "
            f"{built.unknown_types} unknown record types, {built.elapsed:.1f} s."
        )
    finally:
        connection.close()
