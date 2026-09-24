"""Sources: where Prudence sees the developer's work, and the registry of them.

One package per agent. A source finds the agent's local data and turns it into the
events `sources/base.py` defines; it never writes to the agent's files and never
touches the Prudence store directly. The store asks here for an adapter and never
names an agent itself.

"""

from __future__ import annotations

from pathlib import Path

from prudence.sources import claude_code
from prudence.sources.base import Source

SOURCES: dict[str, Source] = {claude_code.KIND: claude_code.SOURCE}
DEFAULT_KIND = claude_code.KIND


def source(kind: str = DEFAULT_KIND, home: Path | None = None) -> Source:
    """The adapter for one agent. Unknown kinds are a programming error, not input."""
    if kind == "codex":
        from prudence.sources.codex import Codex

        return Codex(home)
    if home is not None and kind == claude_code.KIND:
        return claude_code.ClaudeCode(home)
    return SOURCES[kind]
