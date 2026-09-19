"""Command line: one file per command, all registered here. Commands stay thin and call
the engine (`prudence.scan`, later `prudence.store` and `prudence.facts`)."""

from __future__ import annotations

import click

from prudence import __version__
from prudence.cli.init import init
from prudence.cli.status import status


@click.group()
@click.version_option(__version__, prog_name="prudence")
def main() -> None:
    """Prudence: a local-first growth coach for developers who build with AI agents."""


main.add_command(init)
main.add_command(status)
