"""Read Codex rollout files without depending on the Prudence store."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime
from pathlib import Path

from prudence.paths import codex_home
from prudence.sources.base import AgentLog, CompanionFile, Event, FileHead, SessionFile
from prudence.sources.codex import events as reader

KIND = "codex"
HEAD_BYTES = 64 * 1024
TAIL_BYTES = 64 * 1024


def _home(home: Path | None) -> Path:
    return home.expanduser() if home is not None else codex_home()


def _record(line: bytes) -> dict | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Codex:
    kind = KIND

    def __init__(self, home: Path | None = None):
        self.home = _home(home)

    def session_files(self) -> list[SessionFile]:
        files = []
        for directory in (self.home / "sessions", self.home / "archived_sessions"):
            if directory.is_dir():
                files.extend(directory.rglob("*.jsonl"))
        return [self._session(path) for path in sorted(files) if path.is_file()]

    def _session(self, path: Path) -> SessionFile:
        cwd = native_id = None
        first = last = None
        size = path.stat().st_size
        with path.open("rb") as stream:
            head = stream.read(HEAD_BYTES)
            stream.seek(max(0, size - TAIL_BYTES))
            tail = stream.read(TAIL_BYTES)
            for line in head.splitlines():
                record = _record(line)
                if record is None:
                    continue
                stamp = _time(record.get("timestamp"))
                first = first or stamp
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if record.get("type") == "session_meta":
                    native_id = native_id or payload.get("id") or payload.get("session_id")
                    cwd = cwd or payload.get("cwd")
                elif record.get("type") == "turn_context":
                    cwd = cwd or payload.get("cwd")
            for line in reversed(tail.splitlines()):
                record = _record(line)
                if record is not None:
                    last = _time(record.get("timestamp"))
                    if last is not None:
                        break
        native_id = native_id if isinstance(native_id, str) and native_id else path.stem
        return SessionFile(
            path,
            reader.session_id(native_id),
            cwd if isinstance(cwd, str) else None,
            first,
            last or first,
            size,
            None,
        )

    def companion_files(self, session: SessionFile) -> list[CompanionFile]:
        return []

    def head(self, lines: Iterable[bytes]) -> FileHead:
        return reader.head(lines)

    def agent_logs(self, paths: Sequence[str]) -> list[AgentLog]:
        return []

    def events(
        self,
        lines: Iterable[tuple[int, bytes]],
        path: str,
        file_session_id: str,
        agent_id: str | None,
        sidecar: bytes | None = None,
    ) -> Iterator[Event]:
        return reader.events(lines, path, file_session_id, agent_id, sidecar)


SOURCE = Codex()
