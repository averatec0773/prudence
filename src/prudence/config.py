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

# The model block's defaults. They are named here rather than imported from
# `prudence.model` so that reading the config never loads a backend, and so that
# `config.py` keeps its one dependency (`tomllib`).
BACKENDS = ("anthropic", "none")
DEFAULT_BACKEND = "anthropic"
DEFAULT_MODEL_ID = "claude-sonnet-5"
DEFAULT_KEY_ENV = "ANTHROPIC_API_KEY"
DEFAULT_MAX_TOKENS = 1024

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


@dataclass(frozen=True)
class ModelSettings:
    """Which model writes the optional prose, if any. Defaults to writing none.

    The key itself is never here: `api_key_env` names the environment variable to read,
    so a config file can be copied, printed or committed without carrying a secret. A
    user who wants the default only has to leave this block out.
    """

    backend: str = DEFAULT_BACKEND
    model_id: str = DEFAULT_MODEL_ID
    api_key_env: str = DEFAULT_KEY_ENV
    max_tokens: int = DEFAULT_MAX_TOKENS


@dataclass(frozen=True)
class ReviewSettings:
    """Standing choices for `prudence review`. `explain` is `--explain` without the flag."""

    explain: bool = False


@dataclass
class Config:
    path: Path
    version: int = CONFIG_VERSION
    repositories: dict[str, RepoConfig] = field(default_factory=dict)
    model: ModelSettings = field(default_factory=ModelSettings)
    review: ReviewSettings = field(default_factory=ReviewSettings)

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
    return Config(
        path=target,
        version=version,
        repositories=repositories,
        model=_model_settings(raw.get("model")),
        review=_review_settings(raw.get("review")),
    )


def _model_settings(block: object) -> ModelSettings:
    """The `[model]` block, with every unreadable field falling back to its default.

    A typo in a setting must not stop an ingest: an unknown backend name is kept as it
    was written so that `select_model` can say which name it does not know, but a
    non-string or a missing field is simply the default (architecture rule 3).
    """
    if not isinstance(block, dict):
        return ModelSettings()
    backend = block.get("backend")
    model_id = block.get("model_id")
    key_env = block.get("api_key_env")
    max_tokens = block.get("max_tokens")
    return ModelSettings(
        backend=backend if isinstance(backend, str) and backend else DEFAULT_BACKEND,
        model_id=model_id if isinstance(model_id, str) and model_id else DEFAULT_MODEL_ID,
        api_key_env=key_env if isinstance(key_env, str) and key_env else DEFAULT_KEY_ENV,
        max_tokens=(
            max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else DEFAULT_MAX_TOKENS
        ),
    )


def _review_settings(block: object) -> ReviewSettings:
    if not isinstance(block, dict):
        return ReviewSettings()
    explain = block.get("explain")
    return ReviewSettings(explain=explain if isinstance(explain, bool) else False)


def save(config: Config) -> None:
    """Write the config atomically, so an interrupted write never loses the consent record."""
    config.path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.path.with_suffix(config.path.suffix + ".tmp")
    temporary.write_text(dumps(config), encoding="utf-8")
    os.replace(temporary, config.path)


def dumps(config: Config) -> str:
    """Serialise the config. Only the value shapes used above are supported, on purpose."""
    lines = [HEADER, f"version = {config.version}", ""]
    if config.model != ModelSettings():
        lines.append("[model]")
        lines.append(f"backend = {_string(config.model.backend)}")
        lines.append(f"model_id = {_string(config.model.model_id)}")
        lines.append(f"api_key_env = {_string(config.model.api_key_env)}")
        lines.append(f"max_tokens = {config.model.max_tokens}")
        lines.append("")
    if config.review != ReviewSettings():
        lines.append("[review]")
        lines.append(f"explain = {'true' if config.review.explain else 'false'}")
        lines.append("")
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
