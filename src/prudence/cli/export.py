"""`prudence export` and `prudence import`: the store as one portable file.

Both live here because they are one promise read from two sides. Export exists so the
record is the user's, movable to another machine and readable without Prudence; import
exists so that promise is testable, and so a second machine can hold the first one's
history until sync is built.

Both are recorded in the run log (`cli/recording.py`), with the rows per table they moved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import click

from prudence.cli.recording import recorded
from prudence.cli.render import size
from prudence.paths import config_file, data_dir, database_file
from prudence.store import db, transfer


@click.command()
@click.option(
    "--out",
    "target",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Where to write the bundle. Defaults to prudence-export-<date>.tar.gz here.",
)
@click.option(
    "--archive",
    "with_archive",
    is_flag=True,
    help="Include the archived agent bytes. Much larger, and it carries the raw transcripts.",
)
def export(target: Path | None, with_archive: bool) -> None:
    """Write every recorded fact to one .tar.gz: a manifest, the config and a table per file."""
    with recorded() as run:
        if not database_file().exists():
            raise click.ClickException("Nothing recorded yet. Run `prudence ingest`.")
        destination = target or Path(
            f"prudence-export-{datetime.now(UTC).strftime('%Y%m%d')}.tar.gz"
        )
        connection = db.connect()
        try:
            stats = transfer.export(connection, destination, config_file(), with_archive)
        finally:
            connection.close()
        run.step("export", stats.elapsed, _moved(stats))
    detail = ", ".join(f"{table} {count}" for table, count in sorted(stats.tables.items()) if count)
    click.echo(f"Exported {stats.rows} rows to {destination} ({size(stats.bytes_written)}).")
    click.echo(f"Tables: {detail or 'none'}")
    click.echo(
        f"Archived bytes {'included' if with_archive else 'not included'}; {stats.elapsed:.1f} s."
    )


@click.command("import")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--merge", is_flag=True, help="Not implemented; refuses and explains why.")
def import_bundle(source: Path, merge: bool) -> None:
    """Restore an export into an empty data directory."""
    with recorded() as run:
        connection = db.connect()
        try:
            stats = transfer.import_bundle(connection, source, config_file(), merge)
        except transfer.Refused as error:
            raise click.ClickException(str(error)) from error
        finally:
            connection.close()
        run.step("import", stats.elapsed, _moved(stats))
    detail = ", ".join(f"{table} {count}" for table, count in sorted(stats.tables.items()) if count)
    click.echo(f"Imported {stats.rows} rows from {source} into {data_dir()}.")
    click.echo(f"Tables: {detail or 'none'}")
    if not stats.with_archive:
        click.echo(
            "The bundle carried no archived bytes, so `prudence rebuild` has nothing to "
            "rebuild from here. The derived rows are the whole record in this store."
        )
    click.echo(f"{stats.elapsed:.1f} s.")


def _moved(stats: transfer.TransferStats) -> dict:
    """What the run log keeps of a transfer: rows, bytes, and the rows of each table."""
    return {
        "rows": stats.rows,
        "bytes": stats.bytes_written,
        "with_archive": stats.with_archive,
        "tables": dict(stats.tables),
    }
