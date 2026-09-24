"""Named agent history locations. Pausing collection never deletes its history."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import click

from prudence import config as config_module


def _show(config: config_module.Config, as_json: bool) -> None:
    rows = [
        {**asdict(item), "exists": Path(item.home).is_dir()} for item in config.sources.values()
    ]
    if as_json:
        click.echo(json.dumps(rows, indent=2))
    else:
        for row in rows:
            state = "on" if row["enabled"] else "paused"
            click.echo(f"{row['id']}  {row['label']} ({row['kind']}, {state})  {row['home']}")


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def sources(ctx: click.Context, as_json: bool) -> None:
    """List collection locations, add one, or pause collection without deleting history."""
    if ctx.invoked_subcommand is None:
        _show(config_module.load(), as_json)


@sources.command("add")
@click.option("--kind", type=click.Choice(config_module.SOURCE_KINDS), required=True)
@click.option("--name", required=True)
@click.option("--home", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--json", "as_json", is_flag=True)
def add(kind: str, name: str, home: Path, as_json: bool) -> None:
    """Add an extra location with an explicit agent type."""
    config = config_module.load()
    try:
        config_module.add_source(config, kind, name, home)
    except ValueError as error:
        raise click.UsageError(str(error)) from error
    config_module.save(config)
    from prudence.hooks import write_enabled_sources

    write_enabled_sources(config)
    _show(config, as_json)


@sources.command("set")
@click.argument("source_id")
@click.option("--enabled/--paused", default=None)
@click.option("--name")
@click.option("--home", type=click.Path(path_type=Path, file_okay=False))
@click.option("--json", "as_json", is_flag=True)
def set_source(
    source_id: str, enabled: bool | None, name: str | None, home: Path | None, as_json: bool
) -> None:
    """Change a location by its stable id. Existing records keep their origin."""
    config = config_module.load()
    item = config.sources.get(source_id)
    if item is None:
        raise click.UsageError(f"Unknown source {source_id!r}.")
    if name is not None and not name.strip():
        raise click.UsageError("A source needs a name.")
    if home is not None:
        home = home.expanduser().resolve()
        if any(
            s.id != source_id and Path(s.home).resolve() == home for s in config.sources.values()
        ):
            raise click.UsageError("This source directory is already configured.")
    config.sources[source_id] = replace(
        item,
        enabled=item.enabled if enabled is None else enabled,
        label=item.label if name is None else name.strip(),
        home=item.home if home is None else str(home),
    )
    config_module.save(config)
    from prudence.hooks import write_enabled_sources

    write_enabled_sources(config)
    _show(config, as_json)
