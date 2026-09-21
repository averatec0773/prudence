"""Sources: where Prudence sees the developer's work, and the registry of them.

One package per agent. A source finds the agent's local data and turns it into the
events `sources/base.py` defines; it never writes to the agent's files and never
touches the Prudence store directly. The store asks here for an adapter and never
names an agent itself.

There is one adapter today, so `source()` answers with it. A second agent needs one
more thing before this can become a real lookup: the archive has to record which agent
wrote each file, because `store/derived.py` reads files out of the archive long after
the machine they came from was scanned. That is an `archive_file` column behind an
`ARCHIVE_SCHEMA_VERSION` bump, and it belongs to the commit that adds the second
adapter rather than to this one.
"""

from __future__ import annotations

from prudence.sources import claude_code
from prudence.sources.base import Source

SOURCES: dict[str, Source] = {claude_code.KIND: claude_code.SOURCE}
DEFAULT_KIND = claude_code.KIND


def source(kind: str = DEFAULT_KIND) -> Source:
    """The adapter for one agent. Unknown kinds are a programming error, not input."""
    return SOURCES[kind]
