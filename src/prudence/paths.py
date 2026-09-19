"""Where things live on disk.

Every path Prudence reads or writes is resolved here, so a contributor can see the
whole footprint in one file and tests can redirect it with environment variables.

Configuration and data are separated because they have different lifetimes: the
config is small, hand-editable and worth backing up; the data is large, rebuildable
and private. On macOS both platform directories are the same folder, which is what
Apple's own layout prescribes, so the separation is logical rather than physical.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def claude_config_dir() -> Path:
    """Claude Code's configuration directory (`~/.claude` unless CLAUDE_CONFIG_DIR is set)."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override).expanduser() if override else Path.home() / ".claude"


def claude_projects_dir() -> Path:
    """Where Claude Code keeps session transcripts, one subdirectory per project path."""
    return claude_config_dir() / "projects"


def claude_file_history_dir() -> Path:
    """Pre-edit file snapshots Claude Code keeps for `/rewind`, one directory per session."""
    return claude_config_dir() / "file-history"


def claude_settings_file() -> Path:
    return claude_config_dir() / "settings.json"


def config_dir() -> Path:
    """Prudence's own configuration directory (PRUDENCE_CONFIG_DIR overrides)."""
    override = os.environ.get("PRUDENCE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "prudence"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".config") / "prudence"


def data_dir() -> Path:
    """Where the archive and the derived tables live (PRUDENCE_DATA_DIR overrides)."""
    override = os.environ.get("PRUDENCE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "prudence"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".local" / "share") / "prudence"


def config_file() -> Path:
    return config_dir() / "config.toml"


def database_file() -> Path:
    return data_dir() / "prudence.db"


def line_hash_key_file() -> Path:
    """The secret that keys every line hash, generated once per install.

    It sits beside the config rather than inside the database so that copying the
    database somewhere else does not carry the ability to test a guessed line
    against it, and so that deleting it is a one-line way to void every hash.
    """
    return config_dir() / "line-hash.key"


def lock_file() -> Path:
    """Advisory lock taken for the duration of an ingest, so two never overlap."""
    return data_dir() / "ingest.lock"


def reports_dir() -> Path:
    """Where a surface writes a Markdown report for the user to open, e.g. the menu bar."""
    return data_dir() / "reports"
