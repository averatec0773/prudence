"""Hand edits between turns: `turn_tree` and `hand_edit`, folded from `hook_event`.

Four scenarios, as the M2 plan asks for task 9: a tree that changed between two turns
with no Bash call in between (detected), the same change with a Bash call in between
(not counted, because the shell command could have made it), a duplicate `Stop` for one
turn (tolerated rather than mistaken for a second turn), and a session with no hook data
at all (`NULL`, "not captured", never a fabricated zero).
"""

from __future__ import annotations

import json

from click.testing import CliRunner
from conftest import SAMPLE_SESSION, Workspace, record_one_session

from prudence.cli import main
from prudence.paths import spool_file
from prudence.store import db


def _line(
    lab: Workspace,
    event: str,
    ts: str,
    prompt_id: str,
    fingerprint: str,
    dirty: int,
    tool_use_id: str = "",
    head: str = "a" * 40,
) -> str:
    return json.dumps(
        {
            "event": event,
            "ts": ts,
            "session_id": SAMPLE_SESSION,
            "prompt_id": prompt_id,
            "tool_use_id": tool_use_id,
            "cwd": str(lab.repo),
            "head": head,
            "branch": "master",
            "dirty_fingerprint": fingerprint,
            "dirty_count": dirty,
            "elapsed_ms": 40,
        }
    )


def _append(*lines: str) -> None:
    path = spool_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        for line in lines:
            handle.write(line + "\n")


def _ingest() -> None:
    result = CliRunner().invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output


def _rows(query: str) -> list[tuple]:
    connection = db.connect()
    try:
        return [tuple(row) for row in connection.execute(query)]
    finally:
        connection.close()


def _fact_value() -> float | None:
    rows = _rows(
        "SELECT value FROM session_fact WHERE session_id = "
        f"'{SAMPLE_SESSION}' AND fact = 'hand_edits_between_turns'"
    )
    return rows[0][0] if rows else None


FP_A = "aaaaaaaaaaaaaaaa"
FP_B = "bbbbbbbbbbbbbbbb"
FP_C = "cccccccccccccccc"


def test_a_hand_edit_between_two_turns_is_detected_and_a_duplicate_stop_is_tolerated(
    lab: Workspace,
) -> None:
    record_one_session(lab)
    _append(
        _line(lab, "UserPromptSubmit", "2026-09-15T14:00:00.000Z", "turn-1", FP_A, 0),
        # Two Stops for the same turn: the hooks spike measured this around a subagent.
        # The later one, still before the next turn's start, is the one that counts.
        _line(lab, "Stop", "2026-09-15T14:01:00.000Z", "turn-1", FP_A, 0),
        _line(lab, "Stop", "2026-09-15T14:01:30.000Z", "turn-1", FP_A, 0),
        # The tree moved between the two turns, and no Bash call explains it: a hand edit.
        _line(lab, "UserPromptSubmit", "2026-09-15T14:05:00.000Z", "turn-2", FP_B, 2),
        _line(lab, "Stop", "2026-09-15T14:06:00.000Z", "turn-2", FP_C, 5),
    )
    _ingest()

    turns = _rows(
        "SELECT prompt_id, start_fingerprint, end_fingerprint FROM turn_tree"
        f" WHERE session_id = '{SAMPLE_SESSION}' ORDER BY prompt_id"
    )
    assert turns == [
        ("turn-1", FP_A, FP_A),
        ("turn-2", FP_B, FP_C),
    ], "the later duplicate Stop won, not the earlier one"

    gaps = _rows(
        "SELECT prompt_id, prev_prompt_id, files_changed_delta FROM hand_edit"
        f" WHERE session_id = '{SAMPLE_SESSION}'"
    )
    assert gaps == [("turn-2", "turn-1", 2)], "dirty count went from 0 to 2: an estimate of 2 files"

    assert _fact_value() == 1

    shown = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION])
    assert shown.exit_code == 0, shown.output
    assert "hand edits" in shown.output
    assert "files changed by hand" in shown.output
    assert "not captured" not in shown.output


def test_a_bash_call_between_two_turns_rules_out_a_hand_edit(lab: Workspace) -> None:
    record_one_session(lab)
    _append(
        _line(lab, "UserPromptSubmit", "2026-09-15T15:00:00.000Z", "turn-1", FP_A, 0),
        _line(lab, "Stop", "2026-09-15T15:01:00.000Z", "turn-1", FP_A, 0),
        # A Bash call lands between the two turns: it, not a hand, could have moved the
        # tree, so this gap must not be counted even though the fingerprint changed.
        _line(
            lab,
            "PreToolUse",
            "2026-09-15T15:02:00.000Z",
            "turn-1",
            FP_A,
            0,
            tool_use_id="toolu_between",
        ),
        _line(lab, "UserPromptSubmit", "2026-09-15T15:05:00.000Z", "turn-2", FP_B, 3),
        _line(lab, "Stop", "2026-09-15T15:06:00.000Z", "turn-2", FP_B, 3),
    )
    _ingest()

    gaps = _rows(f"SELECT * FROM hand_edit WHERE session_id = '{SAMPLE_SESSION}'")
    assert gaps == [], "a Bash call between the turns explains the change; not a hand edit"
    assert _fact_value() == 0, "hook data exists, but no gap was found: a real zero"

    shown = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION])
    assert shown.exit_code == 0, shown.output
    assert "none: the tree matched at every turn boundary the hooks saw" in shown.output


def test_no_hook_data_is_not_captured_rather_than_zero(lab: Workspace) -> None:
    record_one_session(lab)
    _ingest()

    assert _rows(f"SELECT * FROM hook_event WHERE session_id = '{SAMPLE_SESSION}'") == []
    assert _fact_value() is None, "no hook_event rows at all: absent, not zero"

    shown = CliRunner().invoke(main, ["show", "--session", SAMPLE_SESSION])
    assert shown.exit_code == 0, shown.output
    assert "hand edits" in shown.output
    assert "not captured (no hook data)" in shown.output

    facts_output = CliRunner().invoke(main, ["facts", "--last", "30d"]).output
    assert "handedit" in facts_output


def test_other_agent_activity_makes_hand_edit_gap_unknown(lab):
    record_one_session(lab)
    other = json.loads(_line(lab, "PreToolUse", "2026-09-15T15:02:00.000Z", "cx-turn", FP_B, 1))
    other.update(session_id="codex:other", source="codex", tool_name="apply_patch")
    _append(
        _line(lab, "UserPromptSubmit", "2026-09-15T15:00:00.000Z", "turn-1", FP_A, 0),
        _line(lab, "Stop", "2026-09-15T15:01:00.000Z", "turn-1", FP_A, 0),
        json.dumps(other),
        _line(lab, "UserPromptSubmit", "2026-09-15T15:05:00.000Z", "turn-2", FP_B, 1),
        _line(lab, "Stop", "2026-09-15T15:06:00.000Z", "turn-2", FP_B, 1),
    )
    _ingest()
    assert not _rows(f"SELECT * FROM hand_edit WHERE session_id = '{SAMPLE_SESSION}'")
    assert _fact_value() is None, "other agents may explain the change; zero would claim coverage"
