"""`prudence menubar`: the macOS menu-bar prototype.

The rest of Prudence never imports `rumps`, so this command is the one place that
checks it is even available before reaching for it.
"""

from __future__ import annotations

import sys

import click


@click.command()
def menubar() -> None:
    """Run the menu-bar prototype (macOS only, needs the `menubar` extra)."""
    if sys.platform != "darwin":
        click.echo("The menu bar is macOS only.")
        return
    try:
        import rumps  # noqa: F401
    except ImportError:
        click.echo(
            "rumps is not installed. Install with: uv tool install 'prudence-dev[menubar]'"
        )
        return

    from prudence.menubar.app import run

    run()
