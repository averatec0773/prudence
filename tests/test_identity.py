from __future__ import annotations

import subprocess
from pathlib import Path

from prudence.store.identity import identify, normalise_remote


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_identify_uses_root_commit_and_survives_a_move(tmp_path: Path) -> None:
    repo = tmp_path / "one"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "root",
    )
    _git(repo, "remote", "add", "origin", "git@github.com:someone/one.git")
    before = identify(str(repo))
    assert before is not None
    assert before.key.startswith("root:")
    assert before.remote_url == "https://github.com/someone/one"
    assert before.display_name == "one"

    moved = tmp_path / "renamed"
    repo.rename(moved)
    identify.cache_clear()
    after = identify(str(moved))
    assert after is not None
    assert after.key == before.key, "moving the directory must not change the identity"


def test_identify_returns_none_outside_git_and_for_missing_dirs(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert identify(str(plain)) is None
    assert identify(str(tmp_path / "missing")) is None


def test_normalise_remote_equates_ssh_and_https() -> None:
    assert normalise_remote("git@github.com:A/B.git") == normalise_remote("https://github.com/a/b")
    assert normalise_remote("ssh://git@github.com/a/b.git") == "https://github.com/a/b"
