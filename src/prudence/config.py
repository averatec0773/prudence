"""The user's choices: which repositories are recorded, and how much of each.

Nothing is recorded until a repository is enabled here, so this file is the whole
consent record. It is TOML because the user must be able to read and edit it without
Prudence: `tomllib` reads it, and the few lines below write it, which keeps the
dependency list at one package.

Each repository keeps all three identifiers from `store.identity` rather than only
the key in use, so the primary key can change later and a moved or re-cloned
repository can still be recognised.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from prudence.paths import config_file

LEVELS = ("full", "metadata-only")
CONFIG_VERSION = 1

HEADER = """\
# Prudence configuration.
# Nothing is recorded until a repository appears below. Delete a block to stop
# recording that repository; `prudence forget` removes what was already recorded.
"""


@dataclass(frozen=True)
class RepoConfig:
    """One enabled repository and the level of detail the user allowed for it."""

    key: str
    name: str
    level: str
    enabled_at: str
    root_commits: tuple[str, ...] = ()
    remote: str | None = None
    common_dir: str | None = None


@dataclass
class Config:
    path: Path
    version: int = CONFIG_VERSION
    repositories: dict[str, RepoConfig] = field(default_factory=dict)

    @property
    def levels(self) -> dict[str, str]:
        """Enabled repository key to capture level, the form ingest and parsing want."""
        return {key: repo.level for key, repo in self.repositories.items()}

    def level_of(self, repo_key: str) -> str:
        repo = self.repositories.get(repo_key)
        return repo.level if repo else "full"

    def find(self, token: str) -> RepoConfig | None:
        """Look a repository up by identity key or by display name."""
        if token in self.repositories:
            return self.repositories[token]
        matches = [r for r in self.repositories.values() if r.name == token]
        return matches[0] if len(matches) == 1 else None


def load(path: Path | None = None) -> Config:
    """Read the config, or return an empty one. A broken config is never silently reset."""
    target = path or config_file()
    if not target.exists():
        return Config(path=target)
    with target.open("rb") as fh:
        raw = tomllib.load(fh)
    repositories: dict[str, RepoConfig] = {}
    for block in raw.get("repository", []):
        key = block.get("key")
        if not isinstance(key, str) or not key:
            continue
        repositories[key] = RepoConfig(
            key=key,
            name=str(block.get("name", key)),
            level=block.get("level") if block.get("level") in LEVELS else "full",
            enabled_at=str(block.get("enabled_at", "")),
            root_commits=tuple(str(c) for c in block.get("root_commits", [])),
            remote=block.get("remote") or None,
            common_dir=block.get("common_dir") or None,
        )
    version = int(raw.get("version", CONFIG_VERSION))
    return Config(path=target, version=version, repositories=repositories)


def save(config: Config) -> None:
    """Write the config atomically, so an interrupted write never loses the consent record."""
    config.path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.path.with_suffix(config.path.suffix + ".tmp")
    temporary.write_text(dumps(config), encoding="utf-8")
    os.replace(temporary, config.path)


def dumps(config: Config) -> str:
    """Serialise the config. Only the value shapes used above are supported, on purpose."""
    lines = [HEADER, f"version = {config.version}", ""]
    for repo in sorted(config.repositories.values(), key=lambda r: (r.name, r.key)):
        lines.append("[[repository]]")
        lines.append(f"key = {_string(repo.key)}")
        lines.append(f"name = {_string(repo.name)}")
        lines.append(f"level = {_string(repo.level)}")
        lines.append(f"enabled_at = {_string(repo.enabled_at)}")
        lines.append("root_commits = [" + ", ".join(_string(c) for c in repo.root_commits) + "]")
        if repo.remote:
            lines.append(f"remote = {_string(repo.remote)}")
        if repo.common_dir:
            lines.append(f"common_dir = {_string(repo.common_dir)}")
        lines.append("")
    return "\n".join(lines)


def enable(
    config: Config,
    key: str,
    name: str,
    level: str,
    root_commits: tuple[str, ...] = (),
    remote: str | None = None,
    common_dir: str | None = None,
    today: date | None = None,
) -> RepoConfig:
    if level not in LEVELS:
        raise ValueError(f"unknown capture level {level!r}; use one of {', '.join(LEVELS)}")
    existing = config.repositories.get(key)
    repo = RepoConfig(
        key=key,
        name=name,
        level=level,
        enabled_at=existing.enabled_at if existing else (today or date.today()).isoformat(),
        root_commits=root_commits or (existing.root_commits if existing else ()),
        remote=remote or (existing.remote if existing else None),
        common_dir=common_dir or (existing.common_dir if existing else None),
    )
    config.repositories[key] = repo
    return repo


def disable(config: Config, token: str) -> RepoConfig | None:
    repo = config.find(token)
    if repo is None:
        return None
    del config.repositories[repo.key]
    return repo


def _string(value: str) -> str:
    """A TOML basic string. JSON's escapes are a subset of TOML's, so json rules apply."""
    out = ['"']
    for char in value:
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)
