"""`prudence init`: see what history exists, then choose what is recorded.

Nothing is enabled until the user says so, one repository at a time, which is the
whole point of the command: an employed developer must never find their employer's
code in a personal store because a tool defaulted to "all".

Both forms exist for the same reason: the interactive prompt is how a person does it,
and the `--enable` form is how a test or a script does it.
"""

from __future__ import annotations

import sys

import click

from prudence import config as config_module
from prudence.cli.render import date, size
from prudence.scan import NO_REPOSITORY, ProjectGroup, ScanResult, scan


@click.command()
@click.option("--scan", "scan_only", is_flag=True, help="List the history found; change nothing.")
@click.option(
    "--enable",
    "enable_tokens",
    multiple=True,
    metavar="NAME",
    help="Enable a repository by display name or identity key. Repeatable.",
)
@click.option(
    "--disable",
    "disable_tokens",
    multiple=True,
    metavar="NAME",
    help="Stop recording a repository. Already recorded data is kept; use `forget` to remove it.",
)
@click.option(
    "--level",
    type=click.Choice(config_module.LEVELS),
    default="full",
    show_default=True,
    help="How much to derive from an enabled repository.",
)
def init(
    scan_only: bool, enable_tokens: tuple[str, ...], disable_tokens: tuple[str, ...], level: str
) -> None:
    """Choose which repositories Prudence records. Nothing is enabled until you say so."""
    config = config_module.load()
    if enable_tokens or disable_tokens:
        _apply(config, enable_tokens, disable_tokens, level)
        return
    result = scan()
    click.echo(render(result, config))
    if scan_only:
        return
    if not sys.stdin.isatty():
        click.echo(
            "\nRun `prudence init --enable <repository> --level full|metadata-only` to enable one."
        )
        return
    _interactive(result, config)


def render(result: ScanResult, config: config_module.Config | None = None) -> str:
    enabled = config.levels if config else {}
    lines = [
        f"Claude Code history in {result.projects_dir}: "
        f"{result.total_sessions} sessions, {size(result.total_bytes)}.",
        "",
        f"{'repository':<32} {'sessions':>8} {'first':>10} {'last':>10} {'size':>9}  capture",
    ]
    for group in result.groups:
        name = group.name
        if group.key == NO_REPOSITORY:
            name = f"{NO_REPOSITORY} ({len(group.directories)} directories)"
        lines.append(
            f"{name[:32]:<32} {group.sessions:>8} {date(group.first_at):>10} "
            f"{date(group.last_at):>10} {size(group.size_bytes):>9}  "
            f"{enabled.get(group.key, 'off')}"
        )
    lines.append("")
    lines.append(
        f"Claude Code deletes transcripts after {result.cleanup_period_days} days "
        f"(cleanupPeriodDays). History on this machine goes back to {date(result.oldest)}. "
        "Prudence keeps its own copy from the day a repository is enabled."
    )
    if enabled:
        lines.append(f"{len(enabled)} repositories enabled. Config: {config.path}")
    else:
        lines.append("Nothing is enabled yet. Nothing was written.")
    return "\n".join(lines)


def _apply(
    config: config_module.Config,
    enable_tokens: tuple[str, ...],
    disable_tokens: tuple[str, ...],
    level: str,
) -> None:
    changed = False
    for token in disable_tokens:
        repo = config_module.disable(config, token)
        if repo is None:
            raise click.UsageError(f"{token!r} is not enabled.")
        changed = True
        click.echo(f"Disabled {repo.name} ({repo.key}). Recorded data is kept until you forget it.")
    if enable_tokens:
        result = scan()
        for token in enable_tokens:
            group = _resolve(result, token)
            _enable_group(config, group, level)
            changed = True
    if changed:
        config_module.save(config)
        click.echo(f"Config: {config.path}")


def _enable_group(config: config_module.Config, group: ProjectGroup, level: str) -> None:
    identity = group.identity
    config_module.enable(
        config,
        key=group.key,
        name=group.name,
        level=level,
        root_commits=identity.root_commits if identity else (),
        remote=identity.remote_url if identity else None,
        common_dir=identity.common_dir if identity else None,
    )
    click.echo(f"Enabled {group.name} at level {level} ({group.sessions} sessions).")


def _resolve(result: ScanResult, token: str) -> ProjectGroup:
    for group in result.groups:
        if group.key == token:
            return group
    matches = [g for g in result.groups if g.name == token and g.key != NO_REPOSITORY]
    if not matches:
        raise click.UsageError(f"No repository called {token!r} in the scan.")
    if len(matches) > 1:
        keys = ", ".join(g.key for g in matches)
        raise click.UsageError(f"{token!r} matches several repositories; use a key: {keys}")
    return matches[0]


def _interactive(result: ScanResult, config: config_module.Config) -> None:
    click.echo("")
    click.echo("Enable repositories one at a time. Press Enter on an empty line to finish.")
    changed = False
    while True:
        token = click.prompt("Repository", default="", show_default=False).strip()
        if not token:
            break
        try:
            group = _resolve(result, token)
        except click.UsageError as error:
            click.echo(str(error))
            continue
        level = click.prompt(
            "Capture level",
            type=click.Choice(config_module.LEVELS),
            default="full",
        )
        _enable_group(config, group, level)
        changed = True
    if changed:
        config_module.save(config)
        click.echo(f"Config: {config.path}")
        click.echo("Run `prudence ingest` to record them.")
    else:
        click.echo("Nothing was enabled. Nothing was written.")
