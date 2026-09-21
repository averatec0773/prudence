"""Claude Code as a source: everything that knows its file layout and its format.

`discovery.py` knows where the files are; `events.py` knows what a line of one means.
This module is the `sources.base.Source` the rest of Prudence sees, plus the two
discovery functions `scan.py` calls directly (a scan is an inventory of one agent's
history, not a read of the store, so it may ask this agent its own questions).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from prudence.paths import claude_projects_dir
from prudence.sources import base
from prudence.sources.claude_code import discovery
from prudence.sources.claude_code import events as reader
from prudence.sources.claude_code.discovery import (
    cleanup_period_days,
    list_session_files,
    read_session_file,
)

KIND = "claude_code"

__all__ = [
    "KIND",
    "SOURCE",
    "ClaudeCode",
    "claude_projects_dir",
    "cleanup_period_days",
    "list_session_files",
    "read_session_file",
]


class ClaudeCode:
    """The adapter. One instance, `SOURCE`, registered in `sources/__init__.py`."""

    kind = KIND

    def session_files(self) -> list[base.SessionFile]:
        return [read_session_file(path) for path in list_session_files()]

    def companion_files(self, session: base.SessionFile) -> list[base.CompanionFile]:
        return discovery.companion_files(session)

    def head(self, lines: Iterable[bytes]) -> base.FileHead:
        return reader.head(lines)

    def events(
        self,
        lines: Iterable[tuple[int, bytes]],
        path: str,
        file_session_id: str,
        agent_id: str | None,
    ) -> Iterator[base.Event]:
        return reader.events(lines, path, file_session_id, agent_id)


SOURCE = ClaudeCode()
