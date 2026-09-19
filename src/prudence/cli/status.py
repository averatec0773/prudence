from __future__ import annotations

import click

from prudence import __version__


@click.command()
def status() -> None:
    """Show what Prudence has recorded so far."""
    click.echo(
        f"prudence {__version__}: nothing recorded yet. "
        "Run `prudence init --scan` to see what history exists on this machine."
    )
