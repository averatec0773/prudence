"""`prudence mcp`: run the MCP server (stdio) for Claude Code and other agents.

The rest of Prudence never imports the `mcp` package, so this command is the one place
that checks it is even available before reaching for it, the same pattern `menubar.py`
uses for `rumps`.
"""

from __future__ import annotations

import click


@click.command()
def mcp() -> None:
    """Run the MCP server: search_sessions, show_session and status, read-only, over stdio."""
    try:
        from prudence.mcp.server import run
    except ImportError:
        click.echo("mcp is not installed. Install with: uv tool install 'prudence-coach[mcp]'")
        return
    run()
