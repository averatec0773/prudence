"""The run log, its warnings and the self-checks: what a run leaves for later reading.

Three promises are tested here. A command that changes something leaves a record that
says what it did, even when it was killed halfway. What the parse could not fully read
is named by its shape (a key list, a file id and an offset, an agent id and a reason),
and nothing a transcript said is ever written: the scenario below plants one sentinel
string in every place a transcript can carry text and asserts it never reaches the log.
And the self-checks hold on a store the pipeline built, fail on one it did not, and turn
into exit code 3 under `--strict`.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import Workspace, prompt, record_one_session, tool_call, write_transcript

from prudence.cli import main, recording
from prudence.paths import runs_log_file
from prudence.store import checks, db, run_warnings, runlog

SENTINEL = "ZEBRA-SENTINEL-4417 the quick brown fox"
MAIN = "cccccccc-0000-4000-8000-000000000001"
LOST_AGENT = "a9999999999999999"


def _enable() -> None:
    result = CliRunner().invoke(main, ["init", "--enable", "alpha", "--level", "full"])
    assert result.exit_code == 0, result.output


def _records() -> list[dict]:
    records, unreadable = runlog.read()
    assert unreadable == 0
    return records


def _reply(uuid: str, message_id: str, at: str, cwd: str, blocks: list, **extra) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "parentUuid": None,
        "sessionId": MAIN,
        "cwd": cwd,
        "version": "2.1.290",
        "timestamp": at,
        "message": {
            "id": message_id,
            "role": "assistant",
            "model": "claude-x",
            "content": blocks,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_read_input_tokens": 300,
                "cache_creation_input_tokens": 40,
            },
        },
        **extra,
    }


def _scenario(lab: Workspace) -> None:
    """One session carrying the sentinel wherever a transcript can carry text.

    In the prompt, in a tool's input and result, in the value and in a key of a record
    of a type the parser does not know, in a line that is not a record at all, in a tool
    the bucket rule can only guess at, and in a subagent that nothing dispatched.
    """
    cwd = str(lab.repo)
    records = [
        prompt(MAIN, cwd, SENTINEL, at="2026-09-20T10:00:00.000Z") | {"promptId": "turn-1"},
        *tool_call(
            MAIN,
            cwd,
            "toolu_w1",
            "Write",
            {"file_path": f"{cwd}/note.py", "content": f"# {SENTINEL}\n"},
            result={"stdout": SENTINEL},
            at="2026-09-20T10:00:05.000Z",
        ),
        _reply(
            "r-guess",
            "msg-guess",
            "2026-09-20T10:00:10.000Z",
            cwd,
            [
                {
                    "type": "tool_use",
                    "id": "toolu_f1",
                    "name": "Frobnicate",
                    "input": {"q": SENTINEL},
                }
            ],
        ),
        {
            "type": "future-thing",
            "uuid": "u-future",
            "sessionId": MAIN,
            "timestamp": "2026-09-20T10:00:20.000Z",
            "payload": {"secretKey": SENTINEL, "nested": {"deeper": SENTINEL}},
            f"a key that says {SENTINEL}": 1,
        },
    ]
    path = write_transcript(lab.project, MAIN, records)
    with path.open("a") as handle:
        handle.write('{"type":"assistant","message":{"content":"' + SENTINEL + "\n")
    subagents = lab.project / MAIN / "subagents"
    subagents.mkdir(parents=True)
    (subagents / f"agent-{LOST_AGENT}.jsonl").write_text(
        json.dumps(
            _reply(
                "s-r1",
                "msg-lost",
                "2026-09-20T10:01:00.000Z",
                cwd,
                [{"type": "text", "text": SENTINEL}],
                agentId=LOST_AGENT,
                isSidechain=True,
                promptId="turn-1",
            )
        )
        + "\n"
    )


# What a string in a record may look like, wherever it is not free by design.
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
_WORDS = re.compile(r"^[a-z ]+$")


def _allowed(path: tuple[str, ...], value: str) -> bool:
    """Whether one string at one place in a record is a kind the log may hold.

    Free by design: the command line (what the person typed), the machine line, and an
    error's message and traceback (written by Prudence or a library). A parse's reason
    for reading everything is the engine's own sentence. Everything else is a timestamp
    or a name: an id, a version, a step, a kind, a key, a reason code or `<other>`.
    """
    if path[0] in ("command", "machine", "error") and path[-1] != "<key>":
        return "\n" not in value
    if path[-1] == "full_reason":
        return bool(_WORDS.match(value))
    return bool(_TIMESTAMP.match(value) or run_warnings.NAME.match(value)) or value in (
        run_warnings.OTHER,
    )


def _strings(value: object, path: tuple[str, ...] = ()):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield (*path, "<key>"), key
            yield from _strings(item, (*path, key))
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, (*path, "[]"))


def test_an_ingest_writes_a_start_line_and_an_end_line_that_fold_into_one_record(
    lab: Workspace,
) -> None:
    record_one_session(lab)
    lines = [json.loads(line) for line in runs_log_file().read_text().splitlines()]
    ingest_lines = [line for line in lines if line["command"][0] == "ingest"]
    assert len(ingest_lines) == 2, "one line when it starts and one when it ends"
    first, last = ingest_lines
    assert first["run_id"] == last["run_id"]
    assert first["ended_at"] is None and first["exit"] is None
    assert last["ended_at"] is not None and last["exit"] == 0

    record = next(record for record in _records() if record["command"][0] == "ingest")
    assert record == last
    for key in (
        "command",
        "started_at",
        "ended_at",
        "run_id",
        "engine_version",
        "parser_version",
        "bucket_rule_version",
        "app_contract_version",
        "machine",
        "store_bytes",
        "steps",
        "warnings",
        "checks",
        "error",
        "exit",
    ):
        assert key in record, key
    assert set(record["machine"]) == {"os", "arch", "python", "cores"}
    assert record["command"][:2] == ["ingest", "--workers"]
    names = [step["name"] for step in record["steps"]]
    assert names[:2] == ["repositories", "archive"] and names[-2:] == ["views", "checks"]
    parse = next(step for step in record["steps"] if step["name"] == "parse")
    assert parse["counts"]["files_parsed"] == 1 and parse["counts"]["sessions"] == 1
    assert [check["name"] for check in record["checks"]] == [
        check.__name__ for check in checks.CHECKS
    ]
    assert all(check["passed"] for check in record["checks"])
    assert record["store_bytes"] > 0
    assert oct(runs_log_file().stat().st_mode)[-3:] == "600"


def test_no_string_a_transcript_wrote_reaches_the_log(lab: Workspace) -> None:
    _scenario(lab)
    _enable()
    runner = CliRunner()
    assert runner.invoke(main, ["ingest"]).exit_code == 0
    assert runner.invoke(main, ["rebuild"]).exit_code == 0

    raw = runs_log_file().read_text()
    assert "ZEBRA" not in raw and "quick brown fox" not in raw
    records = _records()
    assert {record["command"][0] for record in records} >= {"init", "ingest", "rebuild"}
    for record in records:
        for path, value in _strings(record):
            assert _allowed(path, value), (path, value)


def test_warnings_name_what_the_parse_could_not_read_by_its_shape(lab: Workspace) -> None:
    _scenario(lab)
    _enable()
    assert CliRunner().invoke(main, ["ingest"]).exit_code == 0
    record = next(record for record in _records() if record["command"][0] == "ingest")
    warnings = {entry["kind"]: entry for entry in record["warnings"]}
    assert set(warnings) == {
        "unknown_record_type",
        "unreadable_line",
        "unattached_subagent",
        "heuristic_bucket",
    }

    (unknown,) = warnings["unknown_record_type"]["sample"]
    assert unknown["type"] == "future-thing" and unknown["count"] == 1
    assert unknown["first_seen"] == "2026-09-20T10:00:20.000Z"
    assert unknown["key_shape"] == [
        "<other>",
        "payload",
        "payload.nested",
        "payload.secretKey",
        "sessionId",
        "timestamp",
        "type",
        "uuid",
    ], "keys two levels deep, a key that is not a name written as <other>, no value"
    assert unknown["keys"] == 8

    (line,) = warnings["unreadable_line"]["sample"]
    connection = db.connect()
    try:
        path = connection.execute(
            "SELECT path FROM archive_file WHERE session_id = ? AND source = 'transcript'",
            (MAIN,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert line["file"] == run_warnings.file_id(path) and line["session"] == MAIN
    transcript = (lab.project / f"{MAIN}.jsonl").read_bytes()
    assert line["offset"] == transcript.rindex(b'{"type":"assistant","message":{"content"')

    assert warnings["unattached_subagent"]["sample"] == [
        {"agent": LOST_AGENT, "session": MAIN, "reason": "no_dispatching_call_named"}
    ]
    (guess,) = warnings["heuristic_bucket"]["sample"]
    assert guess == {"tool": "Frobnicate", "count": 1, "tokens": 370}


def test_a_second_ingest_that_reads_nothing_new_warns_about_nothing(lab: Workspace) -> None:
    _scenario(lab)
    _enable()
    runner = CliRunner()
    assert runner.invoke(main, ["ingest"]).exit_code == 0
    assert runner.invoke(main, ["ingest"]).exit_code == 0
    newest = _records()[0]
    assert newest["warnings"] == [], "warnings are what this run read, and it read nothing"


def test_a_step_that_raises_leaves_the_error_and_the_step_it_stopped_in(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)

    def broken(*args, **kwargs):
        raise RuntimeError("the facts step broke")

    monkeypatch.setattr("prudence.facts.registry.build", broken)
    result = CliRunner().invoke(main, ["ingest"])
    assert result.exit_code == 1
    record = _records()[0]
    assert record["exit"] == 1 and record["ended_at"] is not None
    assert record["error"]["type"] == "RuntimeError"
    assert record["error"]["message"] == "the facts step broke"
    assert any("prudence/store/pipeline.py" in frame for frame in record["error"]["traceback"])
    assert not any(frame.startswith("/") for frame in record["error"]["traceback"])
    finished = [step["name"] for step in record["steps"] if not step.get("failed")]
    assert finished[-1] == "outcomes", "the step before `facts`"
    assert record["steps"][-1] == {"name": "facts", "seconds": None, "counts": {}, "failed": True}
    assert runlog.state(record) == runlog.FAILED


def test_an_ingest_killed_halfway_is_shown_as_interrupted(lab: Workspace) -> None:
    record_one_session(lab)
    script = (
        "import os, signal\n"
        "from prudence.facts import registry\n"
        "registry.build = lambda *a, **k: os.kill(os.getpid(), signal.SIGKILL)\n"
        "from prudence.cli import main\n"
        "main(['ingest', '--workers', '1'])\n"
    )
    killed = subprocess.run(
        [sys.executable, "-c", script], env=dict(os.environ), capture_output=True, timeout=120
    )
    assert killed.returncode == -signal.SIGKILL

    record = _records()[0]
    assert record["command"] == ["ingest", "--workers", "1"]
    assert record["ended_at"] is None and record["exit"] is None
    assert runlog.state(record) == runlog.INTERRUPTED

    shown = CliRunner().invoke(main, ["logs", "--interrupted"])
    assert shown.exit_code == 0, shown.output
    (line,) = shown.output.strip().splitlines()
    assert "ingest --workers 1" in line and "interrupted" in line
    everything = CliRunner().invoke(main, ["logs"]).output.strip().splitlines()
    assert len(everything) == 3, "the interrupted run, the finished ingest and the init"


def test_a_run_whose_process_is_alive_is_running_not_interrupted(lab: Workspace) -> None:
    run = runlog.start(["ingest"])
    record = next(record for record in _records() if record["run_id"] == run.run_id)
    assert runlog.state(record) == runlog.RUNNING
    runlog.finish(run, 0)
    record = next(record for record in _records() if record["run_id"] == run.run_id)
    assert runlog.state(record) == runlog.FINISHED


def test_every_check_holds_on_a_store_the_pipeline_built(lab: Workspace) -> None:
    _scenario(lab)
    _enable()
    assert CliRunner().invoke(main, ["ingest"]).exit_code == 0
    connection = db.connect()
    try:
        results = checks.run(connection)
    finally:
        connection.close()
    assert [check.name for check in results if not check.passed] == []
    tokens = next(check for check in results if check.name == "token_totals_agree")
    assert tokens.numbers["usage"] == tokens.numbers["response"] > 0


def test_token_check_uses_explicit_input_total_when_cache_is_a_subset(lab: Workspace) -> None:
    _scenario(lab)
    _enable()
    assert CliRunner().invoke(main, ["ingest"]).exit_code == 0
    connection = db.connect()
    try:
        connection.execute(
            "UPDATE usage SET input_tokens = 100, cache_read_tokens = 60,"
            " cache_creation_tokens = NULL, total_input_tokens = 100, output_tokens = 20"
        )
        connection.execute(
            "UPDATE response SET input_tokens = 100, cache_read_tokens = 60,"
            " cache_creation_tokens = NULL, total_input_tokens = 100, output_tokens = 20"
            " WHERE input_tokens IS NOT NULL"
        )
        result = checks.token_totals_agree(connection)
    finally:
        connection.close()
    assert result.passed
    assert result.numbers["usage"] == result.numbers["response"]


@pytest.mark.parametrize(
    ("statement", "failing"),
    [
        ("UPDATE usage SET input_tokens = input_tokens + 1", {"token_totals_agree"}),
        ("DELETE FROM turn", {"every_response_has_turn", "subagent_tokens_attached"}),
        (
            "UPDATE response SET turn_id = 'nowhere' WHERE agent_id IS NOT NULL",
            {"every_response_has_turn", "subagent_tokens_attached"},
        ),
        ("DROP VIEW app_status", {"app_views_answer"}),
        (
            "UPDATE meta SET value = '3' WHERE key = 'app_contract_version'",
            {"contract_version_matches"},
        ),
        ("UPDATE session SET repo_key = NULL", {"sessions_have_repository"}),
        ("UPDATE record SET parser_version = 5", {"row_versions_current"}),
    ],
)
def test_each_check_fails_when_its_invariant_is_broken(
    lab: Workspace, statement: str, failing: set[str]
) -> None:
    _scenario(lab)
    _enable()
    assert CliRunner().invoke(main, ["ingest"]).exit_code == 0
    connection = db.connect()
    try:
        connection.execute(statement)
        failed = {check.name for check in checks.run(connection) if not check.passed}
    finally:
        connection.close()
    assert failed == failing


def _failing(connection: sqlite3.Connection) -> checks.Check:
    return checks.Check("always_fails", False, {"left": 1, "right": 2})


def test_a_failed_check_is_a_warning_and_the_last_line_and_exit_3_under_strict(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    monkeypatch.setattr(checks, "CHECKS", (*checks.CHECKS, _failing))
    runner = CliRunner()

    lenient = runner.invoke(main, ["ingest"])
    assert lenient.exit_code == 0, lenient.output
    assert lenient.output.strip().splitlines()[-1] == (
        "Self-checks: 1 of 8 failed: always_fails {'left': 1, 'right': 2}."
    )
    record = _records()[0]
    assert record["exit"] == 0
    assert record["warnings"] == [
        {
            "kind": "check_failed",
            "count": 1,
            "sample": [{"check": "always_fails", "numbers": {"left": 1, "right": 2}}],
        }
    ]

    strict = runner.invoke(main, ["ingest", "--strict"])
    assert strict.exit_code == 3, strict.output
    assert strict.output.strip().splitlines()[-1].startswith("Self-checks: 1 of 8 failed")
    record = _records()[0]
    assert record["exit"] == 3 and record["error"] is None
    assert "--strict" in record["command"]

    rebuilt = runner.invoke(main, ["rebuild", "--strict"])
    assert rebuilt.exit_code == 3, rebuilt.output
    assert rebuilt.output.strip().splitlines()[-1].startswith("Self-checks: 1 of 8 failed")


def test_strict_passes_when_every_check_holds(lab: Workspace) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["ingest", "--strict"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().splitlines()[-1] == "Self-checks: all 7 passed."


def test_the_log_rotates_at_its_limit_and_keeps_two_files(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runlog, "ROTATE_BYTES", 1)
    first = runlog.start(["review"])
    runlog.finish(first, 0)
    second = runlog.start(["review"])
    third = runlog.start(["export"])
    runlog.finish(second, 0)
    runlog.finish(third, 0)
    directory = runs_log_file().parent
    assert sorted(path.name for path in directory.iterdir()) == ["runs.1.jsonl", "runs.jsonl"]
    records = _records()
    ids = {record["run_id"] for record in records}
    assert first.run_id not in ids, "the oldest file was replaced"
    folded = {record["run_id"]: record for record in records}
    assert folded[second.run_id]["ended_at"] is not None, "start and end lines in two files"
    assert folded[third.run_id]["ended_at"] is not None


def test_logs_prints_one_line_per_run_newest_first(lab: Workspace) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert runner.invoke(main, ["ingest"]).exit_code == 0
    shown = runner.invoke(main, ["logs"])
    assert shown.exit_code == 0, shown.output
    lines = shown.output.strip().splitlines()
    assert len(lines) == 3
    assert "ingest --workers" in lines[0] and "init --enable alpha" in lines[-1]
    assert re.search(
        r"  \d+\.\d s  files 0 parsed, 1 skipped  warnings 0  checks failed 0$", lines[0]
    )
    assert "files 1 parsed, 0 skipped" in lines[1]

    last = runner.invoke(main, ["logs", "--last", "1", "--json"])
    (record,) = json.loads(last.output)
    assert record["command"][0] == "ingest" and record["exit"] == 0
    assert runner.invoke(main, ["logs", "--interrupted"]).output.strip() == "No interrupted runs."


def test_diagnose_writes_a_bundle_with_the_user_name_stripped(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(lab.root))
    record_one_session(lab)
    app_log = runs_log_file().parent / "app.log"
    app_log.write_text("".join(f"line {number}\n" for number in range(600)))

    result = CliRunner().invoke(main, ["diagnose"])
    assert result.exit_code == 0, result.output
    (bundle,) = (Path(os.environ["PRUDENCE_DATA_DIR"]) / "diagnose").iterdir()
    assert result.output.strip() == str(bundle).replace(str(lab.root), "~")
    assert sorted(path.name for path in bundle.iterdir()) == [
        "README",
        "app.log",
        "config.toml",
        "machine.txt",
        "runs.jsonl",
        "status.json",
    ]
    for path in bundle.iterdir():
        assert str(lab.root) not in path.read_text(), path.name
    assert "~/alpha" in (bundle / "config.toml").read_text()
    runs = [json.loads(line) for line in (bundle / "runs.jsonl").read_text().splitlines()]
    assert [run["command"][0] for run in runs] == ["init", "ingest"], "oldest first"
    assert json.loads((bundle / "status.json").read_text())["engine_version"]
    tail = (bundle / "app.log").read_text().splitlines()
    assert len(tail) == 500 and tail[-1] == "line 599"
    assert "No transcript text is present" in (bundle / "README").read_text()
    assert "cores:" in (bundle / "machine.txt").read_text()


def test_diagnose_refuses_to_copy_the_store(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prudence.paths import database_file

    # `prudence.cli` exports the command under the module's name, so ask for the module.
    diagnose_module = importlib.import_module("prudence.cli.diagnose")

    record_one_session(lab)
    monkeypatch.setattr(diagnose_module, "app_log_file", database_file)
    result = CliRunner().invoke(main, ["diagnose"])
    assert result.exit_code == 1
    assert "is part of the record" in result.output
    transcript = next(lab.project.glob("*.jsonl"))
    with pytest.raises(diagnose_module.Refused):
        diagnose_module.refuse_archive(transcript)


def test_hooks_install_and_uninstall_are_recorded(
    lab: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_one_session(lab)
    directory = lab.root / "claude-settings"
    directory.mkdir()
    (directory / "settings.json").write_text("{}\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(directory))
    runner = CliRunner()
    assert runner.invoke(main, ["hooks", "install", "--yes"]).exit_code == 0
    assert runner.invoke(main, ["hooks", "uninstall", "--yes"]).exit_code == 0
    uninstalled, installed = _records()[:2]
    assert installed["command"] == ["hooks", "install", "--yes", "--source", "claude"]
    assert installed["steps"][0]["name"] == "install"
    assert installed["steps"][0]["counts"]["added"] == 6
    assert uninstalled["command"] == ["hooks", "uninstall", "--yes", "--source", "claude"]
    assert uninstalled["steps"][0]["counts"]["removed"] > 0


def test_init_records_a_change_and_not_a_scan(lab: Workspace) -> None:
    write_transcript(lab.project, MAIN, [prompt(MAIN, str(lab.repo), "hello")])
    runner = CliRunner()
    assert runner.invoke(main, ["init", "--scan"]).exit_code == 0
    assert _records() == []
    _enable()
    (record,) = _records()
    assert record["command"] == ["init", "--enable", "alpha", "--level", "full"]
    assert record["steps"][0]["counts"] == {"enabled": 1, "disabled": 0}
    refused = runner.invoke(main, ["init", "--disable", "beta"])
    assert refused.exit_code == 2
    assert _records()[0]["error"]["type"] == "UsageError" and _records()[0]["exit"] == 2


def test_review_export_and_import_are_recorded(lab: Workspace, monkeypatch) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert runner.invoke(main, ["review", "--force", "--no-explain"]).exit_code == 0
    bundle = lab.root / "bundle.tar.gz"
    assert runner.invoke(main, ["export", "--out", str(bundle)]).exit_code == 0
    exported, reviewed = _records()[:2]
    assert reviewed["command"] == ["review", "--force", "--no-explain"]
    assert reviewed["steps"][0]["counts"] == {"written": 1}
    assert exported["steps"][0]["name"] == "export"
    assert exported["steps"][0]["counts"]["rows"] > 0
    assert exported["steps"][0]["counts"]["tables"]["session"] == 1

    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(lab.root / "elsewhere"))
    assert runner.invoke(main, ["import", str(bundle)]).exit_code == 0
    (imported,) = _records()
    assert imported["command"] == ["import", str(bundle)]
    assert imported["steps"][0]["counts"]["rows"] == exported["steps"][0]["counts"]["rows"]


def test_the_command_line_is_read_back_from_the_parsed_options() -> None:
    import click

    seen: list[list[str]] = []

    @click.command()
    @click.argument("source")
    @click.option("--flag", is_flag=True)
    @click.option("--explain/--no-explain", default=None)
    @click.option("--tag", multiple=True)
    @click.option("--count", type=int, default=None)
    def probe(source, flag, explain, tag, count):
        seen.append(recording.command_line(click.get_current_context()))

    assert (
        CliRunner().invoke(probe, ["x", "--no-explain", "--tag", "a", "--tag", "b"]).exit_code == 0
    )
    assert CliRunner().invoke(probe, ["y", "--flag", "--count", "3"]).exit_code == 0
    assert seen == [
        ["x", "--no-explain", "--tag", "a", "--tag", "b"],
        ["y", "--flag", "--count", "3"],
    ]
