"""Where things live on disk.

Every path Prudence reads or writes is resolved here, so a contributor can see the
whole footprint in one file and tests can redirect it with environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path


def claude_config_dir() -> Path:
    """Claude Code's configuration directory (`~/.claude` unless CLAUDE_CONFIG_DIR is set)."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override).expanduser() if override else Path.home() / ".claude"


def claude_projects_dir() -> Path:
    """Where Claude Code keeps session transcripts, one subdirectory per project path."""
    return claude_config_dir() / "projects"


def claude_settings_file() -> Path:
    return claude_config_dir() / "settings.json"
