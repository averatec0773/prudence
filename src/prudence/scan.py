"""Scan: what agent history exists on this machine, grouped by repository.

Read-only. This is what `prudence init --scan` shows before anything is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from prudence import config as config_module
from prudence import sources
from prudence.sources import claude_code
from prudence.sources.base import SessionFile
from prudence.store.identity import RepoIdentity, identify

NO_REPOSITORY = "no repository"


@dataclass
class ProjectGroup:
    key: str
    name: str
    identity: RepoIdentity | None
    sessions: int = 0
    size_bytes: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None
    directories: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    source_ids: set[str] = field(default_factory=set)

    def add(self, session: SessionFile) -> None:
        self.sessions += 1
        self.size_bytes += session.size_bytes
        if session.cwd:
            self.directories.add(session.cwd)
        if session.first_at and (self.first_at is None or session.first_at < self.first_at):
            self.first_at = session.first_at
        if session.last_at and (self.last_at is None or session.last_at > self.last_at):
            self.last_at = session.last_at


@dataclass
class ScanResult:
    projects_dir: Path
    groups: list[ProjectGroup]
    cleanup_period_days: int
    total_sessions: int
    total_bytes: int

    @property
    def oldest(self) -> datetime | None:
        stamps = [g.first_at for g in self.groups if g.first_at]
        return min(stamps) if stamps else None


def scan(
    projects_dir: Path | None = None,
    settings_file: Path | None = None,
    config: config_module.Config | None = None,
) -> ScanResult:
    root = projects_dir or claude_code.claude_projects_dir()
    groups: dict[str, ProjectGroup] = {}
    total_sessions = 0
    total_bytes = 0
    if projects_dir is not None:
        locations = [
            config_module.SourceConfig(
                "claude", "claude_code", "Claude Code", str(projects_dir.parent)
            )
        ]
        sessions = [
            (locations[0], claude_code.read_session_file(p))
            for p in claude_code.list_session_files(root)
        ]
    else:
        locations = list((config or config_module.load()).sources.values())
        sessions = [
            (location, session)
            for location in locations
            if location.enabled
            for session in sources.source(location.kind, Path(location.home)).session_files()
        ]
    seen = set()
    for location, session in sessions:
        identity = identify(session.cwd) if session.cwd else None
        if identity is None:
            key, name = NO_REPOSITORY, NO_REPOSITORY
        else:
            key, name = identity.key, identity.display_name
        group = groups.get(key)
        if group is None:
            group = groups[key] = ProjectGroup(key=key, name=name, identity=identity)
        group.sources.add(location.kind)
        group.source_ids.add(location.id)
        identity_key = (location.kind, session.session_id)
        if identity_key in seen:
            continue
        seen.add(identity_key)
        total_sessions += 1
        total_bytes += session.size_bytes
        group.add(session)
    ordered = sorted(groups.values(), key=lambda g: (g.key == NO_REPOSITORY, -g.sessions, g.name))
    return ScanResult(
        projects_dir=root,
        groups=ordered,
        cleanup_period_days=claude_code.cleanup_period_days(settings_file),
        total_sessions=total_sessions,
        total_bytes=total_bytes,
    )
