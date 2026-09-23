"""`prudence hooks`: install, remove and inspect the capture hooks.

The hooks are the only thing Prudence writes into the user's world, so this command
shows its work: the backup it took, the unified diff of what changed in the settings
file, and the exact command it wired up. Nothing is installed until the user runs this.
Installing and removing are recorded in the run log (`cli/recording.py`), once the user
has said yes.
"""

from __future__ import annotations

import time

import click

from prudence import config as config_module
from prudence import hooks as hooks_module
from prudence.cli.recording import recorded
from prudence.cli.render import size
from prudence.paths import claude_settings_file, database_file, spool_file
from prudence.store import db, spool


@click.group()
def hooks() -> None:
    """Install, remove or inspect the hooks that record git state during a session."""


@hooks.command("install")
@click.option("--yes", is_flag=True, help="Do not ask before editing the settings file.")
def install(yes: bool) -> None:
    """Add Prudence's hook entries to Claude Code's settings file.

    Six synchronous entries: SessionStart, UserPromptSubmit, Stop, SubagentStop, and a
    PreToolUse/PostToolUse pair on Bash. The Bash pair is the one that earns its cost:
    the hooks spike measured a turn that rewrote four files and made a commit while the
    working tree looked identical at the turn's two boundaries.
    """
    config = config_module.load()
    if not config.repositories:
        raise click.UsageError(
            "No repository is enabled, so the hooks would record nothing. Run `prudence init`."
        )
    settings = claude_settings_file()
    if not yes:
        click.echo(f"This edits {settings} (a backup is written first).")
        click.confirm("Install the Prudence hooks?", abort=True)

    with recorded() as run:
        started = time.monotonic()
        connection = db.connect()
        try:
            result = hooks_module.install(connection)
        except hooks_module.SettingsProblem as error:
            raise click.ClickException(str(error)) from error
        finally:
            connection.close()
        run.step(
            "install",
            time.monotonic() - started,
            {
                "added": len(result.added),
                "already": len(result.already),
                "enabled_roots": result.enabled_roots,
                "backup": result.backup is not None,
            },
        )

    click.echo(f"Hook script: {result.script_path}")
    click.echo(f"Enabled roots: {result.enabled_roots} in {result.enabled_path}")
    if result.already:
        click.echo(f"Already installed: {', '.join(result.already)}")
    if not result.added:
        click.echo(f"Nothing to change in {result.settings_path}.")
        return
    click.echo(f"Installed: {', '.join(result.added)}")
    click.echo(f"Backup: {result.backup}" if result.backup else "No backup: the file was new.")
    click.echo("")
    click.echo(result.diff or "(no textual change)")


@hooks.command("uninstall")
@click.option("--yes", is_flag=True, help="Do not ask before editing the settings file.")
def uninstall(yes: bool) -> None:
    """Remove Prudence's hook entries, restoring the backup when nothing else changed."""
    settings = claude_settings_file()
    if not yes:
        click.echo(f"This edits {settings}.")
        click.confirm("Remove the Prudence hooks?", abort=True)
    with recorded() as run:
        started = time.monotonic()
        try:
            result = hooks_module.uninstall()
        except hooks_module.SettingsProblem as error:
            raise click.ClickException(str(error)) from error
        run.step(
            "uninstall",
            time.monotonic() - started,
            {
                "removed": len(result.removed),
                "restored": result.restored_from is not None,
                "changed_since_backup": result.changed_since_backup,
            },
        )
    if not result.removed:
        click.echo(f"No Prudence hook entries in {result.settings_path}.")
        return
    click.echo(f"Removed: {', '.join(sorted(set(result.removed)))}")
    if result.restored_from is not None:
        click.echo(f"Restored byte for byte from {result.restored_from}.")
    elif result.changed_since_backup:
        click.echo(
            "The settings file changed after our backup was taken, so only our entries "
            "were removed and the backup was left alone."
        )
    click.echo("")
    click.echo(result.diff or "(no textual change)")


@hooks.command("status")
def status() -> None:
    """Show which hook entries are present and how large the spool has grown."""
    wired = hooks_module.present()
    click.echo(f"settings: {claude_settings_file()}")
    click.echo(
        f"script:   {hooks_module.script_source().name} -> {hooks_module.hook_script_file()}"
    )
    click.echo(f"enabled:  {hooks_module.enabled_list_file()}")
    expected = [event if m is None else f"{event}({m})" for event, m in hooks_module.EVENTS]
    click.echo(f"installed: {', '.join(wired) if wired else 'none'}")
    missing = [name for name in expected if name not in wired]
    if missing:
        click.echo(f"missing:   {', '.join(missing)}")
    backup = hooks_module.latest_backup()
    click.echo(f"backup:    {backup if backup else 'none'}")
    click.echo(f"spool:     {spool_file()} ({size(hooks_module.spool_size())})")
    if not database_file().exists():
        return
    connection = db.connect()
    try:
        events, sessions = spool.counts(connection)
    finally:
        connection.close()
    click.echo(f"recorded:  {events} hook events over {sessions} sessions")
