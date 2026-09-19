"""A machine of our own: a real git repository, synthetic transcripts, private dirs.

Tests never read `~/.claude` and never write to a real config or data directory; every
path Prudence uses is redirected with the environment variables `paths.py` reads.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from prudence.store.identity import identify

FIXTURES = Path(__file__).parent / "fixtures" / "claude_code"
CWD_PLACEHOLDER = "__CWD__"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def make_repo(path: Path) -> Path:
    """A repository whose root commit is unique to it, so its identity key is unique."""
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(
        path,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        f"root of {path.name}",
    )
    return path


@dataclass
class Workspace:
    root: Path
    repo: Path
    claude: Path
    project: Path

    @property
    def transcripts(self) -> list[Path]:
        return sorted(self.project.glob("*.jsonl"))

    def repo_key(self) -> str:
        identity = identify(str(self.repo))
        assert identity is not None
        return identity.key


@pytest.fixture(autouse=True)
def isolated_paths(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No test may see the developer's own config, data or Claude Code history."""
    base = tmp_path_factory.mktemp("elsewhere")
    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(base / "config"))
    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(base / "data"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(base / "claude"))


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    repo = make_repo(tmp_path / "alpha")
    claude = tmp_path / "claude"
    project = claude / "projects" / "-alpha"
    project.mkdir(parents=True)
    for source in sorted(FIXTURES.rglob("*")):
        if not source.is_file():
            continue
        target = project / source.relative_to(FIXTURES)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text().replace(CWD_PLACEHOLDER, str(repo)))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(tmp_path / "data"))
    identify.cache_clear()
    yield Workspace(root=tmp_path, repo=repo, claude=claude, project=project)
    identify.cache_clear()
