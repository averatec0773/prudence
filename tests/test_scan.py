"""Scan groups synthetic transcripts by repository without reading any content."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from prudence.cli import main
from prudence.scan import NO_REPOSITORY, scan
from prudence.sources.claude_code import cleanup_period_days, read_session_file


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def make_repo(path: Path) -> Path:
    """A repository whose root commit is unique to it (message = its name)."""
    path.mkdir()
    _git(path, "init", "-q")
    _git(
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


def write_session(
    projects: Path, project_slug: str, name: str, cwd: str, stamps: list[str]
) -> Path:
    project_dir = projects / project_slug
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / f"{name}.jsonl"
    records = [
        {
            "type": "user",
            "cwd": cwd,
            "timestamp": stamps[0],
            "entrypoint": "cli",
            "message": {"role": "user", "content": "hidden"},
        }
    ]
    records += [
        {"type": "assistant", "timestamp": s, "message": {"content": "hidden"}} for s in stamps[1:]
    ]
    records.append({"type": "bookkeeping-of-unknown-kind"})  # no timestamp: must be tolerated
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def test_read_session_file_reads_head_and_tail_only(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    path = write_session(
        projects, "p", "s1", "/somewhere", ["2026-09-01T10:00:00Z", "2026-09-01T11:30:00Z"]
    )
    session = read_session_file(path)
    assert session.session_id == "s1"
    assert session.cwd == "/somewhere"
    assert session.first_at is not None and session.first_at.hour == 10
    assert session.last_at is not None and session.last_at.hour == 11
    assert session.entrypoint == "cli"
    assert session.size_bytes == path.stat().st_size


def test_scan_groups_worktrees_of_one_repo_and_isolates_unknown_dirs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "alpha")
    worktree = tmp_path / "alpha-wt"
    _git(repo, "worktree", "add", "-q", str(worktree), "-b", "feature")
    other = make_repo(tmp_path / "beta")
    projects = tmp_path / "projects"
    write_session(projects, "a", "s1", str(repo), ["2026-09-01T10:00:00Z"])
    write_session(projects, "a-wt", "s2", str(worktree), ["2026-09-02T10:00:00Z"])
    write_session(projects, "b", "s3", str(other), ["2026-09-03T10:00:00Z"])
    write_session(projects, "gone", "s4", str(tmp_path / "deleted"), ["2026-09-04T10:00:00Z"])

    result = scan(projects_dir=projects, settings_file=tmp_path / "missing.json")

    by_name = {g.name: g for g in result.groups}
    assert by_name["alpha"].sessions == 2, "a linked worktree belongs to the same repository"
    assert by_name["alpha"].first_at.day == 1 and by_name["alpha"].last_at.day == 2
    assert by_name["beta"].sessions == 1
    assert by_name[NO_REPOSITORY].sessions == 1
    assert result.groups[-1].key == NO_REPOSITORY, "unknown directories are listed last"
    assert result.total_sessions == 4
    assert result.cleanup_period_days == 30, "missing settings fall back to the default"
    assert result.oldest.day == 1


def test_cleanup_period_days_reads_settings(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"cleanupPeriodDays": 365}))
    assert cleanup_period_days(settings) == 365
    settings.write_text("{not json")
    assert cleanup_period_days(settings) == 30


def test_init_scan_command_renders_a_table(tmp_path: Path, monkeypatch) -> None:
    repo = make_repo(tmp_path / "gamma")
    config = tmp_path / "claude"
    write_session(config / "projects", "g", "s1", str(repo), ["2026-09-05T10:00:00Z"])
    (config / "settings.json").write_text(json.dumps({"cleanupPeriodDays": 90}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    out = CliRunner().invoke(main, ["init", "--scan"])

    assert out.exit_code == 0, out.output
    assert "gamma" in out.output
    assert "1 sessions" in out.output
    assert "after 90 days" in out.output
    assert "Nothing was written" in out.output
