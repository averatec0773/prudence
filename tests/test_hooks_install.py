"""`prudence hooks`: editing Claude Code's settings file, and undoing it exactly.

Every test here points CLAUDE_CONFIG_DIR at a temporary directory holding a copy of a
settings file. Nothing in this suite may ever open the developer's own `~/.claude`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import Workspace, record_one_session

from prudence import hooks as hooks_module
from prudence.cli import main

# A settings file with something of the user's own in it, including a hook of their own
# on an event we also use, so removal has to be surgical rather than wholesale.
EXISTING = {
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"]},
    "hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "/usr/local/bin/mine.sh"}]}],
        "PostToolUse": [
            {"matcher": "Write", "hooks": [{"type": "command", "command": "echo written"}]}
        ],
    },
}


def _settings(lab: Workspace, monkeypatch: pytest.MonkeyPatch, body: dict | None = None) -> Path:
    """A copy of a settings file in a directory of our own, never the real one."""
    directory = lab.root / "claude-settings"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "settings.json"
    path.write_text(json.dumps(body if body is not None else EXISTING, indent=2) + "\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(directory))
    return path


def test_install_adds_our_entries_shows_a_diff_and_is_idempotent(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    settings = _settings(lab, monkeypatch)
    original = settings.read_text()
    runner = CliRunner()

    first = runner.invoke(main, ["hooks", "install", "--yes"])
    assert first.exit_code == 0, first.output
    for event in ("SessionStart", "UserPromptSubmit", "Stop", "SubagentStop"):
        assert event in first.output
    assert "PreToolUse(Bash)" in first.output and "PostToolUse(Bash)" in first.output
    assert "--- " in first.output and "+++ " in first.output, "a unified diff is printed"
    assert "Backup:" in first.output

    backups = sorted(settings.parent.glob("settings.json.prudence-backup-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == original, "the backup is the file as it was"

    written = json.loads(settings.read_text())
    assert written["model"] == "opus", "nothing of the user's own was touched"
    assert written["permissions"] == EXISTING["permissions"]
    commands = [entry["command"] for entry in written["hooks"]["Stop"][0]["hooks"]]
    assert "/usr/local/bin/mine.sh" in commands, "their Stop hook is still first"
    assert any("prudence-hook.sh Stop" in command for command in commands)
    assert all(entry.get("timeout") == 10 for entry in written["hooks"]["PreToolUse"][0]["hooks"])
    assert written["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
    assert "async" not in json.dumps(written), "the spike showed async loses Stop and SessionEnd"

    after_first = settings.read_text()
    second = runner.invoke(main, ["hooks", "install", "--yes"])
    assert second.exit_code == 0, second.output
    assert "Already installed" in second.output
    assert "Nothing to change" in second.output
    assert settings.read_text() == after_first, "a second install writes nothing"
    assert len(sorted(settings.parent.glob("settings.json.prudence-backup-*"))) == 1


def test_uninstall_restores_the_backup_byte_for_byte(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    settings = _settings(lab, monkeypatch)
    original = settings.read_text()
    runner = CliRunner()
    assert runner.invoke(main, ["hooks", "install", "--yes"]).exit_code == 0
    assert settings.read_text() != original

    result = runner.invoke(main, ["hooks", "uninstall", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Restored byte for byte" in result.output
    assert settings.read_text() == original

    again = runner.invoke(main, ["hooks", "uninstall", "--yes"])
    assert "No Prudence hook entries" in again.output


def test_uninstall_keeps_a_later_edit_and_says_the_backup_no_longer_fits(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    settings = _settings(lab, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(main, ["hooks", "install", "--yes"]).exit_code == 0

    changed = json.loads(settings.read_text())
    changed["statusLine"] = {"type": "command", "command": "mine"}
    settings.write_text(json.dumps(changed, indent=2) + "\n")

    result = runner.invoke(main, ["hooks", "uninstall", "--yes"])
    assert result.exit_code == 0, result.output
    assert "changed after our backup" in result.output
    written = json.loads(settings.read_text())
    assert written["statusLine"] == {"type": "command", "command": "mine"}
    assert "prudence-hook.sh" not in json.dumps(written)
    assert written["hooks"]["Stop"][0]["hooks"][0]["command"] == "/usr/local/bin/mine.sh"
    assert written["hooks"]["PostToolUse"][0]["matcher"] == "Write", "their matcher group stays"


def test_install_writes_the_script_and_the_enabled_list(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    _settings(lab, monkeypatch, body={})
    result = CliRunner().invoke(main, ["hooks", "install", "--yes"])
    assert result.exit_code == 0, result.output

    script = hooks_module.hook_script_file()
    assert script.is_file() and script.stat().st_mode & 0o111, "the copy is executable"
    assert script.read_bytes() == hooks_module.script_source().read_bytes()

    listed = hooks_module.enabled_list_file().read_text()
    assert str(lab.repo) in listed, "the enabled worktree root, for the shell to compare against"

    status = CliRunner().invoke(main, ["hooks", "status"])
    assert status.exit_code == 0, status.output
    assert "installed: SessionStart" in status.output
    assert "missing" not in status.output


def test_a_settings_file_that_is_not_json_is_refused_untouched(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    directory = lab.root / "claude-settings"
    directory.mkdir(parents=True, exist_ok=True)
    settings = directory / "settings.json"
    settings.write_text("{ this is not json\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(directory))

    result = CliRunner().invoke(main, ["hooks", "install", "--yes"])
    assert result.exit_code != 0
    assert "nothing was written" in result.output
    assert settings.read_text() == "{ this is not json\n"


def test_install_quotes_a_script_path_with_a_space(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """macOS keeps the data dir under `Application Support`; the command must survive it."""
    from prudence import hooks as hooks_module
    from prudence.store import db

    record_one_session(lab)
    settings = _settings(lab, monkeypatch)
    script = tmp_path / "Application Support" / "prudence-hook.sh"
    connection = db.connect()
    try:
        result = hooks_module.install(connection, settings_path=settings, script_path=script)
        assert result.added
        written = json.loads(settings.read_text())
        commands = [
            entry["command"]
            for groups in written["hooks"].values()
            for group in groups
            for entry in group["hooks"]
            if "prudence-hook.sh" in entry.get("command", "")
        ]
        assert len(commands) == 6
        assert all(cmd.startswith("'") and "Application Support" in cmd for cmd in commands)
        again = hooks_module.install(connection, settings_path=settings, script_path=script)
        assert not again.added, "quoted entries are recognised as already present"
    finally:
        connection.close()
    gone = hooks_module.uninstall(settings_path=settings, script_path=script)
    assert len(gone.removed) == 6
