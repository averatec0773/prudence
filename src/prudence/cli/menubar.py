"""`prudence menubar`: a signpost to the native app that replaced it.

The `rumps` prototype is gone (M3 task 7). The command is not, because someone has it in
their shell history and a command that vanishes is a worse answer than a command that
says where the thing went. It prints one line and exits 0: nothing failed, the menu bar
simply lives somewhere else now.
"""

from __future__ import annotations

import click

REPLACED = (
    "The Python menu-bar prototype was replaced by the native Prudence app "
    "(apps/mac in the repository; a signed build is published with each release). "
    "See apps/mac/README.md."
)


@click.command()
def menubar() -> None:
    """Say where the menu bar went: the native app in apps/mac."""
    click.echo(REPLACED)
