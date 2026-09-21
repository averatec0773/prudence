"""`prudence ask`: reading the question, finding the evidence, answering over it.

The three halves are tested separately on purpose (see `ask/__init__.py`): a parsing bug
and a retrieval bug produce the same empty answer, and only separate tests tell them
apart. Every model call is a replay; the fixture is keyed by the real request.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner
from conftest import SAMPLE_SESSION, record_one_session

from prudence.ask import answer as answer_module
from prudence.ask import schema as ask_schema
from prudence.ask.parse import parse
from prudence.ask.retrieve import retrieve, tables
from prudence.cli import main
from prudence.model import guard
from prudence.model.recorded import input_hash
from prudence.store import db, transfer, views

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)  # a Sunday
PROJECTS = {"repo-alpha": "alpha", "repo-beatos": "beatos"}

ANSWER = (
    "The one session in the range is credited with a commit whose lines are still "
    "there. There is not enough here to say more than that."
)
INVENTED = "About 40% of your lines came back, which is more than you would want."


# --- reading the question -------------------------------------------------------------


def test_last_week_is_the_previous_monday_to_monday() -> None:
    question = parse("what did I do last week", now=NOW, projects=PROJECTS)
    assert question.since == "2026-09-07T00:00:00"
    assert question.until == "2026-09-14T00:00:00"
    assert question.range_label == "last week"
    assert "last week" in question.matched


def test_counted_ranges_in_words_and_digits() -> None:
    assert parse("the last 30 days", now=NOW).since == "2026-08-21T12:00:00"
    assert parse("in the last two weeks", now=NOW).since == "2026-09-06T12:00:00"
    assert parse("over the past 3 months", now=NOW).range_label == "the last 90 days"


def test_in_august_is_the_most_recent_august() -> None:
    question = parse("what did I ship in August", now=NOW)
    assert question.since == "2026-08-01T00:00:00"
    assert question.until == "2026-09-01T00:00:00"
    assert question.range_label == "August 2026"


def test_since_monday_reaches_back_to_the_most_recent_one() -> None:
    question = parse("since Monday", now=NOW)
    assert question.since == "2026-09-14T00:00:00"
    assert parse("since 2026-09-01", now=NOW).since == "2026-09-01T00:00:00"


def test_a_project_a_path_and_quoted_text_come_out_of_the_question() -> None:
    question = parse(
        'why do my refactors on beatos keep breaking src/store/views.py with "no such table"',
        now=NOW,
        projects=PROJECTS,
    )
    assert question.project == "repo-beatos"
    assert question.path == "src/store/views.py"
    assert question.quoted == ["no such table"]
    assert "refactors" in question.terms
    # The words the rules ate, and the filler, are not search terms.
    assert "beatos" not in question.terms
    assert "why" not in question.terms
    assert question.search == "src/store/views.py"


def test_an_extension_is_a_search_term_when_no_path_is_named() -> None:
    question = parse("how much of my work was in .swift files", now=NOW)
    assert question.extension == ".swift"
    assert question.search == ".swift"


def test_a_question_with_nothing_in_it_parses_to_nothing() -> None:
    question = parse("how am I doing", now=NOW, projects=PROJECTS)
    assert question.since is None
    assert question.project is None
    assert question.search == ""


# --- the evidence -----------------------------------------------------------------------


def test_retrieval_finds_the_sessions_and_their_computed_rows(lab) -> None:
    record_one_session(lab)
    session_id = SAMPLE_SESSION
    connection = db.connect()
    question = parse("what did I do in the last 90 days", now=None, projects={})
    evidence = retrieve(connection, question)

    assert session_id in evidence.session_ids
    row = evidence.sessions[0]
    assert set(row) >= {"session_id", "purpose", "tokens", "commits_attributed", "coverage"}
    assert evidence.usage is not None
    assert evidence.excerpts == []  # never without --with-content

    text = tables(evidence, views.repository_names(connection))
    assert session_id[:8] in text
    assert "Question:" in text
    connection.close()


def test_a_term_that_matches_nothing_falls_back_to_the_range_and_says_so(lab) -> None:
    record_one_session(lab)
    connection = db.connect()
    question = parse("what happened with zzzznotathing", now=None, projects={})
    evidence = retrieve(connection, question)
    assert evidence.sessions, "a question should not silently answer nothing"
    assert any("Nothing matched" in note for note in evidence.notes)
    connection.close()


# --- the command ------------------------------------------------------------------------


def _write(directory: Path, request, text: str) -> str:
    key = input_hash(request)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.json").write_text(
        json.dumps({"text": text, "model": "recorded-haiku", "output_tokens": 90})
    )
    return key


def _record(directory: Path, evidence, text: str) -> str:
    return _write(directory, answer_module.build_request(evidence), text)


def _record_with_retry(directory: Path, evidence, first: str, second: str) -> None:
    """The first draft and the corrected one, which is a different prompt and hash."""
    request = answer_module.build_request(evidence)
    _write(directory, request, first)
    verdict = guard.judge(first, answer_module.allowed_numbers(evidence))
    _write(directory, guard.corrected(request, verdict), second)


def _evidence(question_text: str):
    connection = db.connect()
    try:
        return retrieve(connection, parse(question_text, projects={}))
    finally:
        connection.close()


def test_ask_no_model_prints_the_evidence_and_calls_nothing(lab) -> None:
    record_one_session(lab)
    session_id = SAMPLE_SESSION
    result = CliRunner().invoke(main, ["ask", "what did I do lately", "--no-model"])
    assert result.exit_code == 0, result.output
    assert "Sending to" not in result.output
    assert session_id[:8] in result.output
    assert "No model was called" in result.output

    connection = db.connect()
    row = ask_schema.by_id(connection, 1)
    assert row is not None
    assert row["answer"] is None
    assert row["model"] is None
    connection.close()

    shown = CliRunner().invoke(main, ["show", "--question", "1"])
    assert shown.exit_code == 0, shown.output
    assert "what did I do lately" in shown.output


def test_ask_with_a_recorded_completion_answers_and_stores(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    question = "what did I do lately"
    _record(tmp_path / "fixtures", _evidence(question), ANSWER)
    monkeypatch.setenv("PRUDENCE_MODEL", "recorded")
    monkeypatch.setenv("PRUDENCE_MODEL_FIXTURES", str(tmp_path / "fixtures"))

    result = CliRunner().invoke(main, ["ask", question])
    assert result.exit_code == 0, result.output
    assert "Sending to recorded:" in result.output
    assert "no transcript content" in result.output
    assert "## Answer" in result.output
    assert ANSWER.split(".")[0] in result.output
    assert "every number checked against it" in result.output

    connection = db.connect()
    row = ask_schema.by_id(connection, 1)
    assert row["model"] == "recorded-haiku"
    assert row["answer"].startswith("The one session")
    assert len(row["evidence_hash"]) == 16
    connection.close()


def test_a_refused_answer_is_never_printed_and_never_stored(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    question = "what did I do lately"
    _record_with_retry(tmp_path / "fixtures", _evidence(question), INVENTED, INVENTED)
    monkeypatch.setenv("PRUDENCE_MODEL", "recorded")
    monkeypatch.setenv("PRUDENCE_MODEL_FIXTURES", str(tmp_path / "fixtures"))

    result = CliRunner().invoke(main, ["ask", question])
    assert result.exit_code != 0
    assert "40%" in result.output, "the offending number is named"
    assert "discarded unread" in result.output
    assert "--no-model" in result.output
    # Not one word of the draft reaches the reader.
    assert "came back" not in result.output
    assert "## Answer" not in result.output
    assert result.output.count("Sending to recorded:") == 2
    # The evidence still is printed: it is the part that was computed.
    assert "Question: what did I do lately" in result.output
    assert SAMPLE_SESSION[:8] in result.output

    connection = db.connect()
    row = ask_schema.by_id(connection, 1)
    assert row is not None, "asking is part of the record even when the answer is not kept"
    assert row["answer"] is None
    assert "40%" in row["refused_numbers"]
    connection.close()

    shown = CliRunner().invoke(main, ["show", "--question", "1"])
    assert shown.exit_code == 0, shown.output
    assert "refused" in shown.output
    assert "came back" not in shown.output


def test_a_graded_answer_is_refused_too(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    question = "what did I do lately"
    graded = "One session in the range. The coverage there is solid."
    _record_with_retry(tmp_path / "fixtures", _evidence(question), graded, graded)
    monkeypatch.setenv("PRUDENCE_MODEL", "recorded")
    monkeypatch.setenv("PRUDENCE_MODEL_FIXTURES", str(tmp_path / "fixtures"))

    result = CliRunner().invoke(main, ["ask", question])
    assert result.exit_code != 0
    assert "graded the work" in result.output
    assert "solid" in result.output
    assert "The coverage there is solid" not in result.output


def test_ask_json_is_json(lab) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["ask", "what did I do lately", "--no-model", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["id"] == 1
    assert payload["answer"] is None
    assert payload["evidence"]["sessions"]


def test_an_unknown_project_is_an_error_not_an_empty_answer(lab) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(
        main, ["ask", "anything", "--no-model", "--project", "not-a-repository"]
    )
    assert result.exit_code != 0
    assert "not-a-repository" in result.output


# --- the two promises about the table ----------------------------------------------------


def test_questions_survive_rebuild_and_travel_in_an_export(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert runner.invoke(main, ["ask", "what did I do lately", "--no-model"]).exit_code == 0

    assert runner.invoke(main, ["rebuild"]).exit_code == 0
    connection = db.connect()
    assert ask_schema.by_id(connection, 1) is not None

    bundle = tmp_path / "store.tar.gz"
    stats = transfer.export(connection, bundle)
    connection.close()
    assert stats.tables["question"] == 1

    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(tmp_path / "restored"))
    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(tmp_path / "restored-config"))
    restored = db.connect()
    transfer.import_bundle(restored, bundle)
    back = ask_schema.by_id(restored, 1)
    assert back is not None
    assert back["question"] == "what did I do lately"
    restored.close()


def test_the_ask_engine_imports_without_the_command_line() -> None:
    """The MCP server in batch 3 imports `ask.answer` alone; it must not need `cli`."""
    import subprocess
    import sys

    for module in ("parse", "retrieve", "answer", "schema"):
        done = subprocess.run(
            [sys.executable, "-c", f"import prudence.ask.{module}"],
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, f"prudence.ask.{module}: {done.stderr}"
