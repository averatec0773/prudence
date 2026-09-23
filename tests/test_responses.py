"""The `response` table: one row per reply of the model, in the turn that asked for it.

One synthetic session holds every shape the five bugs of 2026-09-22 were found on: a
reply split over several records, a subagent started by an `Agent` call and linked by the
file beside its log, a second one linked only by the parent's tool result, a `SendMessage`
that hands a running agent work from a later turn, and a resumed session that replays one
of the first session's replies under new record ids.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from click.testing import CliRunner
from conftest import Workspace, write_transcript

from prudence.cli import main
from prudence.store import buckets, db

MAIN = "aaaaaaaa-0000-4000-8000-000000000001"
RESUMED = "aaaaaaaa-0000-4000-8000-000000000002"
META_AGENT = "a1111111111111111"
RESULT_AGENT = "a2222222222222222"


def _record(kind: str, uuid: str, at: str, session: str, cwd: str, **extra: object) -> dict:
    return {
        "type": kind,
        "uuid": uuid,
        "parentUuid": None,
        "sessionId": session,
        "cwd": cwd,
        "gitBranch": "master",
        "version": "2.1.290",
        "timestamp": at,
        **extra,
    }


def _prompt(uuid: str, prompt_id: str, at: str, session: str, cwd: str) -> dict:
    return _record(
        "user",
        uuid,
        at,
        session,
        cwd,
        promptId=prompt_id,
        message={"role": "user", "content": [{"type": "text", "text": "Do the next thing."}]},
    )


def _reply(
    uuid: str,
    message_id: str,
    at: str,
    session: str,
    cwd: str,
    blocks: list[dict],
    output: int,
    **extra: object,
) -> dict:
    """One record of a reply. Several records of one reply share `message_id`."""
    return _record(
        "assistant",
        uuid,
        at,
        session,
        cwd,
        requestId=f"req-{message_id}",
        message={
            "id": message_id,
            "role": "assistant",
            "model": "claude-x",
            "content": blocks,
            "usage": {
                "input_tokens": 10,
                "output_tokens": output,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 100,
            },
        },
        **extra,
    )


def _use(call_id: str, name: str, **payload: object) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": payload}


def _result(
    uuid: str, call_id: str, at: str, session: str, cwd: str, text: str = "ok", **extra: object
) -> dict:
    return _record(
        "user",
        uuid,
        at,
        session,
        cwd,
        message={
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": call_id, "content": text}],
        },
        **extra,
    )


def _scenario(lab: Workspace) -> None:
    cwd = str(lab.repo)
    main_records = [
        _prompt("m-p1", "turn-1", "2026-09-20T10:00:00.000Z", MAIN, cwd),
        # One reply that starts two subagents.
        _reply(
            "m-r1",
            "msg-dispatch",
            "2026-09-20T10:00:05.000Z",
            MAIN,
            cwd,
            [
                _use("toolu_agent_meta", "Agent", prompt="look around"),
                _use("toolu_agent_result", "Agent", prompt="look elsewhere"),
            ],
            output=20,
        ),
        _result("m-t1", "toolu_agent_meta", "2026-09-20T10:05:00.000Z", MAIN, cwd),
        _result(
            "m-t2",
            "toolu_agent_result",
            "2026-09-20T10:05:01.000Z",
            MAIN,
            cwd,
            text=f"Done.\nagentId: {RESULT_AGENT} (for resuming)",
        ),
        _reply(
            "m-r2",
            "msg-edit",
            "2026-09-20T10:06:00.000Z",
            MAIN,
            cwd,
            [_use("toolu_edit", "Edit", file_path=f"{cwd}/a.py", old_string="a", new_string="b")],
            output=30,
        ),
        # The person types again while the first subagent is still running.
        _prompt("m-p2", "turn-2", "2026-09-20T10:10:00.000Z", MAIN, cwd),
        _reply(
            "m-r3",
            "msg-push",
            "2026-09-20T10:10:05.000Z",
            MAIN,
            cwd,
            [_use("toolu_push", "Bash", command="git push origin master")],
            output=40,
        ),
        _prompt("m-p3", "turn-3", "2026-09-20T10:20:00.000Z", MAIN, cwd),
        _reply(
            "m-r4",
            "msg-send",
            "2026-09-20T10:20:05.000Z",
            MAIN,
            cwd,
            [_use("toolu_send", "SendMessage", to=META_AGENT, message="one more thing")],
            output=50,
        ),
    ]
    write_transcript(lab.project, MAIN, main_records)

    subagents = lab.project / MAIN / "subagents"
    subagents.mkdir(parents=True)
    common = {"isSidechain": True}
    meta_agent = [
        # The subagent's own promptId names the turn the parent was in at the time,
        # which moved on to turn-2 before this reply was written.
        _prompt("s1-p", "turn-2", "2026-09-20T10:11:00.000Z", MAIN, cwd)
        | common
        | {"agentId": META_AGENT},
        # One reply over two records: the first carries a partial output count.
        _reply(
            "s1-r1a",
            "msg-sub-read",
            "2026-09-20T10:11:05.000Z",
            MAIN,
            cwd,
            [_use("toolu_sub_read", "Read", file_path=f"{cwd}/a.py")],
            output=3,
            agentId=META_AGENT,
            isSidechain=True,
        ),
        _reply(
            "s1-r1b",
            "msg-sub-read",
            "2026-09-20T10:11:06.000Z",
            MAIN,
            cwd,
            [_use("toolu_sub_grep", "Grep", pattern="x")],
            output=300,
            agentId=META_AGENT,
            isSidechain=True,
        ),
        # After the parent's SendMessage in turn-3.
        _reply(
            "s1-r2",
            "msg-sub-write",
            "2026-09-20T10:21:00.000Z",
            MAIN,
            cwd,
            [_use("toolu_sub_write", "Write", file_path=f"{cwd}/b.py", content="x = 1\n")],
            output=7,
            agentId=META_AGENT,
            isSidechain=True,
            promptId="turn-2",
        ),
    ]
    (subagents / f"agent-{META_AGENT}.jsonl").write_text(
        "\n".join(json.dumps(record) for record in meta_agent) + "\n"
    )
    (subagents / f"agent-{META_AGENT}.meta.json").write_text(
        json.dumps({"agentType": "general-purpose", "toolUseId": "toolu_agent_meta"})
    )
    result_agent = [
        _reply(
            "s2-r1",
            "msg-sub-run",
            "2026-09-20T10:12:00.000Z",
            MAIN,
            cwd,
            [_use("toolu_sub_test", "Bash", command="uv run pytest -q")],
            output=9,
            agentId=RESULT_AGENT,
            isSidechain=True,
            promptId="turn-2",
        ),
    ]
    (subagents / f"agent-{RESULT_AGENT}.jsonl").write_text(
        "\n".join(json.dumps(record) for record in result_agent) + "\n"
    )

    # A resume that replays the edit reply under new record ids and its own session id.
    write_transcript(
        lab.project,
        RESUMED,
        [
            _reply(
                "r-copy",
                "msg-edit",
                "2026-09-21T09:00:00.000Z",
                RESUMED,
                cwd,
                [
                    _use(
                        "toolu_edit_copy",
                        "Edit",
                        file_path=f"{cwd}/a.py",
                        old_string="a",
                        new_string="b",
                    )
                ],
                output=30,
            ),
            _prompt("r-p1", "turn-r1", "2026-09-21T09:01:00.000Z", RESUMED, cwd),
            _reply("r-r1", "msg-resumed", "2026-09-21T09:01:05.000Z", RESUMED, cwd, [], output=11),
        ],
    )


@pytest.fixture
def store(lab: Workspace) -> sqlite3.Connection:
    _scenario(lab)
    runner = CliRunner()
    assert runner.invoke(main, ["init", "--enable", "alpha", "--level", "full"]).exit_code == 0
    result = runner.invoke(main, ["ingest"])
    assert result.exit_code == 0, result.output
    connection = db.connect()
    yield connection
    connection.close()


def _responses(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {row["response_id"]: row for row in connection.execute("SELECT * FROM response")}


def test_a_reply_belongs_to_the_turn_its_prompt_opened(store: sqlite3.Connection) -> None:
    """Bug 1: records without a promptId used to fall to `<session>:0`."""
    rows = _responses(store)
    assert rows["msg-dispatch"]["turn_id"] == "turn-1"
    assert rows["msg-edit"]["turn_id"] == "turn-1"
    assert rows["msg-push"]["turn_id"] == "turn-2"
    usage_turns = {
        row["request_id"]: row["turn_id"]
        for row in store.execute("SELECT request_id, turn_id FROM usage")
    }
    assert usage_turns["req-msg-push"] == "turn-2"
    calls = dict(store.execute("SELECT tool_use_id, turn_id FROM tool_call").fetchall())
    assert calls["toolu_push"] == "turn-2"


def test_a_reply_over_several_records_counts_the_last_output(store: sqlite3.Connection) -> None:
    """Bug 2: the first streaming record carries a partial output count."""
    row = _responses(store)["msg-sub-read"]
    assert row["output_tokens"] == 300
    assert row["tool_calls"] == 2 and row["read_calls"] == 2
    usage = store.execute(
        "SELECT output_tokens FROM usage WHERE request_id = 'req-msg-sub-read'"
    ).fetchall()
    assert [r[0] for r in usage] == [300], "one usage row per reply, with its final count"


def test_a_subagent_reply_belongs_to_the_turn_that_dispatched_it(store: sqlite3.Connection) -> None:
    """Bug 3: the subagent's own promptId names the parent's turn at the time."""
    rows = _responses(store)
    assert rows["msg-sub-read"]["turn_id"] == "turn-1", "linked by the file beside the log"
    assert rows["msg-sub-read"]["agent_id"] == META_AGENT
    assert rows["msg-sub-run"]["turn_id"] == "turn-1", "linked by the parent's tool result"
    assert rows["msg-sub-write"]["turn_id"] == "turn-3", "a SendMessage re-homes later replies"


def test_a_replayed_reply_is_counted_once_by_the_session_that_declared_it(
    store: sqlite3.Connection,
) -> None:
    """Bug 4: a resume copies earlier replies under new record ids."""
    rows = _responses(store)
    assert rows["msg-edit"]["session_id"] == MAIN
    assert rows["msg-resumed"]["session_id"] == RESUMED
    counted = store.execute(
        "SELECT COUNT(*) FROM usage WHERE request_id = 'req-msg-edit'"
    ).fetchone()[0]
    assert counted == 1


def test_a_turn_total_includes_its_subagents(store: sqlite3.Connection) -> None:
    """Bug 5: per-turn totals come from the reply's own turn, not from the clock."""
    totals = dict(
        store.execute(
            "SELECT turn_id, SUM(input_tokens + output_tokens + cache_read_tokens"
            " + cache_creation_tokens) FROM response GROUP BY turn_id"
        ).fetchall()
    )
    per_reply = 10 + 1000 + 100
    # turn-1: its own two replies (20, 30) plus the read reply (300) and the test run (9).
    assert totals["turn-1"] == 4 * per_reply + 20 + 30 + 300 + 9
    assert totals["turn-3"] == 2 * per_reply + 50 + 7


def test_each_reply_carries_its_bucket(store: sqlite3.Connection) -> None:
    rows = _responses(store)
    assert {key: row["bucket"] for key, row in rows.items()} == {
        "msg-dispatch": "talk",
        "msg-edit": "change",
        "msg-push": "run",
        "msg-send": "talk",
        "msg-sub-read": "read",
        "msg-sub-write": "change",
        "msg-sub-run": "run",
        "msg-resumed": "talk",
    }
    assert {row["bucket_rule_version"] for row in rows.values()} == {buckets.BUCKET_RULE_VERSION}
    assert rows["msg-edit"]["files_changed"] == 1
    assert rows["msg-push"]["commands"] == 1
    assert all(row["heuristic"] == 0 for row in rows.values())


def test_the_file_beside_a_subagent_log_is_not_read_as_records(store: sqlite3.Connection) -> None:
    """A subagent's `.meta.json` used to be parsed as one record of type `unknown`."""
    unknown = [row[0] for row in store.execute("SELECT type FROM unknown_record_type")]
    assert "unknown" not in unknown
    agents = {row[0] for row in store.execute("SELECT DISTINCT agent_id FROM record")}
    assert agents == {None, META_AGENT, RESULT_AGENT}


def test_a_record_that_cannot_be_read_is_a_gap_and_not_a_bucket(lab: Workspace) -> None:
    cwd = str(lab.repo)
    path = write_transcript(
        lab.project,
        MAIN,
        [
            _prompt("g-p1", "turn-g", "2026-09-20T10:00:00.000Z", MAIN, cwd),
            _reply("g-r1", "msg-ok", "2026-09-20T10:00:05.000Z", MAIN, cwd, [], output=5),
        ],
    )
    with path.open("a") as handle:
        handle.write('{"type":"assistant","message":{"usage":{"input_tokens":4,"output_tokens":6\n')
    runner = CliRunner()
    assert runner.invoke(main, ["init", "--enable", "alpha", "--level", "full"]).exit_code == 0
    assert runner.invoke(main, ["ingest"]).exit_code == 0
    connection = db.connect()
    try:
        rows = connection.execute(
            "SELECT bucket, input_tokens + output_tokens FROM response ORDER BY response_id"
        ).fetchall()
        gap = connection.execute("SELECT coverage_gap_tokens FROM app_status").fetchone()[0]
        unknown = dict(connection.execute("SELECT type, count FROM unknown_record_type"))
    finally:
        connection.close()
    assert sorted((row[0] or "", row[1]) for row in rows) == [("", 10), ("talk", 15)]
    assert gap == 10
    assert unknown.get("unreadable") == 1, "counted like any record type the parser does not know"
