import click

from prudence import __version__


@click.group()
@click.version_option(__version__, prog_name="prudence")
def main() -> None:
    """Prudence: a local-first growth coach for developers who build with AI agents."""


@main.command()
def status() -> None:
    """Show what Prudence has recorded so far."""
    click.echo(
        f"prudence {__version__}: nothing recorded yet. "
        "Run `prudence init --scan` (coming in task 1)."
    )


if __name__ == "__main__":
    main()
