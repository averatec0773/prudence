"""`prudence forget`: remove a session or a repository from the store for good.

The other half of decision P5. Seeing what was recorded is worth little without being
able to take it back, so this command deletes the derived rows, the harvested rows and
the archived bytes together, and prints what it removed rather than a reassurance.

`--project` also disables the repository in the config, because forgetting a project
and then having the next `ingest` record it again from the agent's own directory would
be the opposite of what the user asked for.
"""

from __future__ import annotations

import click

from prudence import config as config_module
from prudence.cli.render import size
from prudence.paths import database_file
from prudence.store import db, erase


@click.command()
@click.option("--session", "session_token", metavar="ID", help="One session, by id or prefix.")
@click.option("--project", "project_token", metavar="NAME", help="One repository, by name or key.")
@click.option("--vacuum", "run_vacuum", is_flag=True, help="Shrink the database file. Slow.")
@click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
def forget(
    session_token: str | None, project_token: str | None, run_vacuum: bool, yes: bool
) -> None:
    """Delete a session or a repository from the store, archive included.

    `VACUUM` is not run afterwards. It rewrites the whole database file, which on a
    store of several gigabytes takes minutes, and the pages a delete frees are reused
    by the next ingest anyway. Run `prudence forget --vacuum` when you want the file on
    disk to shrink now.
    """
    chosen = [flag for flag in (session_token, project_token) if flag]
    if len(chosen) > 1:
        raise click.UsageError("Choose one of --session or --project, not both.")
    if not chosen and not run_vacuum:
        raise click.UsageError("Nothing to forget. Pass --session, --project or --vacuum.")
    if not database_file().exists():
        raise click.ClickException("Nothing recorded yet; there is nothing to forget.")

    connection = db.connect()
    try:
        if session_token:
            _forget_session(connection, session_token, yes)
        elif project_token:
            _forget_project(connection, project_token, yes)
        if run_vacuum:
            click.echo("Vacuuming; this rewrites the whole database file.")
            click.echo(f"Freed {size(erase.vacuum(connection))} on disk.")
    finally:
        connection.close()


def _forget_session(connection, token: str, yes: bool) -> None:
    from prudence.cli.show import resolve

    session_id = resolve(connection, token)
    if not yes:
        click.confirm(
            f"Delete every row and every archived byte of session {session_id}?", abort=True
        )
    _report(erase.forget_sessions(connection, [session_id]), f"session {session_id}")


def _forget_project(connection, token: str, yes: bool) -> None:
    repo_key, name = _repository(connection, token)
    session_ids = erase.sessions_of(connection, repo_key)
    if not yes:
        click.confirm(
            f"Delete {len(session_ids)} sessions, their commits and their archived bytes "
            f"for {name}, and stop recording it?",
            abort=True,
        )
    removal = erase.forget_project(connection, repo_key)
    _report(removal, f"repository {name} ({repo_key})")

    config = config_module.load()
    if config_module.disable(config, repo_key) is not None:
        config_module.save(config)
        click.echo(f"Disabled {name} in {config.path}. Nothing more will be recorded for it.")
    else:
        click.echo(f"{name} was not enabled in the config; nothing to disable.")


def _repository(connection, token: str) -> tuple[str, str]:
    for row in connection.execute("SELECT repo_key, name FROM repository"):
        if token in (row["repo_key"], row["name"]):
            return row["repo_key"], row["name"]
    repo = config_module.load().find(token)
    if repo is None:
        raise click.UsageError(f"No recorded or enabled repository called {token!r}.")
    return repo.key, repo.name


def _report(removal: erase.Removal, subject: str) -> None:
    click.echo(f"Forgot {subject}.")
    detail = ", ".join(f"{count} {table}" for table, count in sorted(removal.rows.items()) if count)
    click.echo(f"Rows deleted: {removal.total_rows} ({detail or 'none'}).")
    click.echo(
        f"Archive: {removal.archive_files} files, {size(removal.archive_bytes)} of agent "
        f"bytes, {size(removal.stored_bytes)} of compressed chunks."
    )
    click.echo(
        "The database file is not smaller yet: VACUUM rewrites it whole and is slow, so "
        "it is not automatic. Run `prudence forget --vacuum` to reclaim the space now."
    )
