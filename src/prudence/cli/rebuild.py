"""`prudence rebuild`: throw the derived tables away and build them again.

This is the command that makes the parser safe to change. It reads the archive and the
repositories, never the agent's files, so it can be run after any code change. The
commit harvest runs again too, because a repository's history moves under us: rebases
and squashes rewrite hashes, and a commit that was harvested yesterday may not exist
today.
"""

from __future__ import annotations

import click

from prudence import config as config_module
from prudence.cli.ingest import progress_sink, report, workers_option
from prudence.store import db, derived, pipeline


@click.command()
@click.option(
    "--progress",
    "show_progress",
    is_flag=True,
    help="Write one JSON progress line per step to stderr while the rebuild runs.",
)
@workers_option
def rebuild(show_progress: bool, workers: int) -> None:
    """Rebuild every derived table from the archive, and harvest the commits again."""
    config = config_module.load()
    try:
        with db.ingest_lock():
            connection = db.connect()
            try:
                result = pipeline.run(
                    connection,
                    config,
                    with_archive=False,
                    progress=progress_sink(show_progress),
                    workers=workers,
                )
            finally:
                connection.close()
    except db.Locked as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Rebuilt at parser version {derived.PARSER_VERSION}.")
    for line in report(result):
        click.echo(line)
