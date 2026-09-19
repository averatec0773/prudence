"""The capture hook itself, run the way Claude Code runs it: JSON on stdin, event as argv.

There is no fake `claude` to drive, so the script is exercised directly. Everything it
touches is a temporary directory: its own data directory, its enabled list and a git
repository built for the test. The developer's `~/.claude` is never read or written.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from conftest import Workspace, git

from prudence import hooks as hooks_module


def _installed(lab: Workspace, roots: list[str]) -> tuple[Path, Path]:
    """The script and the enabled list, in a data directory of our own."""
    data = lab.root / "hookdata"
    script = hooks_module.install_script(data / "hooks" / "prudence-hook.sh")
    hooks_module.write_enabled(roots, data / "hooks" / "enabled.txt")
    return script, data


def _payload(cwd: str) -> str:
    """A hook input of the shape the spike recorded, quotes in the tool input included."""
    return json.dumps(
        {
            "session_id": "abcd1234-0000-4000-8000-000000000001",
            "transcript_path": "/somewhere/transcript.jsonl",
            "cwd": cwd,
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": 'echo "hello world" && sed -i s/a/b/ x.txt'},
            "tool_use_id": "toolu_01ABCdef",
            "prompt_id": "prompt_0099",
        }
    )


def _run(script: Path, data: Path, payload: str, event: str, **env: str) -> subprocess.Popen:
    environment = dict(os.environ)
    environment["PRUDENCE_DATA_DIR"] = str(data)
    environment.update(env)
    return subprocess.run(
        ["/bin/sh", str(script), event],
        input=payload,
        capture_output=True,
        text=True,
        env=environment,
    )


def _spool(data: Path) -> list[dict]:
    path = data / "spool.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_the_hook_writes_one_line_of_git_state_for_an_enabled_repository(
    lab: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    (lab.repo / "dirty.txt").write_text("not committed yet\n")
    head = git(lab.repo, "rev-parse", "HEAD")
    script, data = _installed(lab, [str(lab.repo)])

    result = _run(script, data, _payload(str(lab.repo)), "PostToolUse")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "", "a hook that prints is a hook that talks back to the model"

    lines = _spool(data)
    assert len(lines) == 1
    line = lines[0]
    assert set(line) == {
        "event",
        "ts",
        "session_id",
        "prompt_id",
        "tool_use_id",
        "cwd",
        "head",
        "branch",
        "dirty_fingerprint",
        "dirty_count",
        "elapsed_ms",
    }
    assert line["event"] == "PostToolUse"
    assert line["session_id"] == "abcd1234-0000-4000-8000-000000000001"
    assert line["prompt_id"] == "prompt_0099"
    assert line["tool_use_id"] == "toolu_01ABCdef"
    assert line["cwd"] == str(lab.repo)
    assert line["head"] == head
    assert line["dirty_count"] == 1, "one untracked file"
    assert len(line["dirty_fingerprint"]) == 16
    assert line["ts"].endswith("Z") and line["ts"][19] == "."
    assert isinstance(line["elapsed_ms"], int) and line["elapsed_ms"] >= 0
    assert "hello world" not in json.dumps(line), "no command text, ever"

    with capsys.disabled():
        print(f"\n  hook elapsed_ms (informational): {line['elapsed_ms']}")


def test_the_hook_records_nothing_outside_an_enabled_repository(lab: Workspace) -> None:
    stranger = lab.root / "elsewhere"
    stranger.mkdir()
    script, data = _installed(lab, [str(lab.repo)])

    result = _run(script, data, _payload(str(stranger)), "Stop")
    assert result.returncode == 0
    assert _spool(data) == [], "a directory nobody enabled leaves no trace at all"


def test_prudence_internal_short_circuits_the_hook(lab: Workspace) -> None:
    script, data = _installed(lab, [str(lab.repo)])
    result = _run(script, data, _payload(str(lab.repo)), "Stop", PRUDENCE_INTERNAL="1")
    assert result.returncode == 0
    assert _spool(data) == [], "Prudence's own model calls never record themselves"


def test_the_hook_survives_input_it_cannot_understand(lab: Workspace) -> None:
    script, data = _installed(lab, [str(lab.repo)])
    for payload in ("", "not json at all", "[]", '{"cwd": ' + json.dumps(str(lab.repo)) + "}"):
        result = _run(script, data, payload, "SessionStart")
        assert result.returncode == 0, f"never fails, even on {payload!r}"
    lines = _spool(data)
    assert len(lines) == 1, "only the one payload that named an enabled directory"
    assert lines[0]["event"] == "SessionStart" and lines[0]["session_id"] == ""


def test_a_missing_enabled_list_means_no_recording(lab: Workspace) -> None:
    data = lab.root / "hookdata"
    script = hooks_module.install_script(data / "hooks" / "prudence-hook.sh")
    result = _run(script, data, _payload(str(lab.repo)), "SessionStart")
    assert result.returncode == 0
    assert _spool(data) == [], "nothing is enabled until the list says so"
