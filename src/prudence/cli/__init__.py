"""Command line: one file per command, all registered here. Commands stay thin and call
the engine (`prudence.scan`, later `prudence.store` and `prudence.facts`)."""

from __future__ import annotations

import click

from prudence import __version__
from prudence.cli.ask import ask
from prudence.cli.classify import classify
from prudence.cli.explain import explain
from prudence.cli.export import export, import_bundle
from prudence.cli.facts import facts
from prudence.cli.forget import forget
from prudence.cli.hooks import hooks
from prudence.cli.ingest import ingest
from prudence.cli.init import init
from prudence.cli.mcp import mcp
from prudence.cli.menubar import menubar
from prudence.cli.observations import observations
from prudence.cli.outcomes import outcomes
from prudence.cli.rebuild import rebuild
from prudence.cli.review import review
from prudence.cli.sample import sample
from prudence.cli.sessions import sessions
from prudence.cli.settings import config
from prudence.cli.show import show
from prudence.cli.status import status
from prudence.cli.suggestions import suggestions
from prudence.cli.usage import usage


@click.group()
@click.version_option(__version__, prog_name="prudence")
def main() -> None:
    """Prudence: a growth coach for developers who build with AI coding agents."""


main.add_command(init)
main.add_command(ingest)
main.add_command(rebuild)
main.add_command(sample)
main.add_command(sessions)
main.add_command(outcomes)
main.add_command(observations)
main.add_command(review)
main.add_command(explain)
main.add_command(ask)
main.add_command(suggestions)
main.add_command(config)
main.add_command(usage)
main.add_command(facts)
main.add_command(classify)
main.add_command(show)
main.add_command(status)
main.add_command(forget)
main.add_command(export)
main.add_command(import_bundle)
main.add_command(hooks)
main.add_command(menubar)
main.add_command(mcp)
