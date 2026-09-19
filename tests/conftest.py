"""A machine of our own: a real git repository, synthetic transcripts, private dirs.

Tests never read `~/.claude` and never write to a real config or data directory; every
path Prudence uses is redirected with the environment variables `paths.py` reads.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from prudence.store.identity import identify

FIXTURES = Path(__file__).parent / "fixtures" / "claude_code"
CWD_PLACEHOLDER = "__CWD__"


def git(repo: Path, *args: str, at: str | None = None) -> str:
    """One git command. `at` fixes both dates, so a test can place a commit in time."""
    environment = dict(os.environ)
    if at is not None:
        environment["GIT_AUTHOR_DATE"] = at
        environment["GIT_COMMITTER_DATE"] = at
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    ).stdout.strip()


def commit(repo: Path, at: str, message: str = "change") -> str:
    """Commit whatever is in the tree at a fixed moment; returns the full hash."""
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        message,
        at=at,
    )
    return git(repo, "rev-parse", "HEAD")


def tool_call(
    session_id: str,
    cwd: str,
    tool_use_id: str,
    tool_name: str,
    payload: dict,
    result: dict | None = None,
    at: str = "2026-09-15T09:00:00.000Z",
    is_error: bool = False,
) -> list[dict]:
    """The two records a tool call really is: the use, and the result some lines later."""
    common = {
        "sessionId": session_id,
        "cwd": cwd,
        "gitBranch": "master",
        "version": "2.1.278",
        "isSidechain": False,
    }
    use = {
        **common,
        "type": "assistant",
        "uuid": f"{tool_use_id}-use",
        "parentUuid": None,
        "timestamp": at,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": payload}
            ],
        },
    }
    answer = {
        **common,
        "type": "user",
        "uuid": f"{tool_use_id}-result",
        "parentUuid": f"{tool_use_id}-use",
        "timestamp": at,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "is_error": is_error}],
        },
    }
    if result is not None:
        answer["toolUseResult"] = result
    return [use, answer]


def prompt(session_id: str, cwd: str, text: str, at: str = "2026-09-15T08:59:00.000Z") -> dict:
    return {
        "type": "user",
        "uuid": f"{session_id}-prompt-{at}",
        "parentUuid": None,
        "sessionId": session_id,
        "cwd": cwd,
        "gitBranch": "master",
        "version": "2.1.278",
        "isSidechain": False,
        "entrypoint": "cli",
        "timestamp": at,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def write_transcript(project: Path, session_id: str, records: list[dict]) -> Path:
    project.mkdir(parents=True, exist_ok=True)
    path = project / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


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


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    repo = make_repo(tmp_path / "alpha")
    claude = tmp_path / "claude"
    project = claude / "projects" / "-alpha"
    project.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(tmp_path / "data"))
    return Workspace(root=tmp_path, repo=repo, claude=claude, project=project)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    """The recorded fixtures, one per observed transcript format, against a real repository."""
    space = _prepare(tmp_path, monkeypatch)
    for source in sorted(FIXTURES.rglob("*")):
        if not source.is_file():
            continue
        target = space.project / source.relative_to(FIXTURES)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text().replace(CWD_PLACEHOLDER, str(space.repo)))
    identify.cache_clear()
    yield space
    identify.cache_clear()


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    """The same machine with no transcripts yet, for tests that build their own scenario."""
    space = _prepare(tmp_path, monkeypatch)
    identify.cache_clear()
    yield space
    identify.cache_clear()
