"""The model segment on a review: what is sent, what is checked, what is stored.

Every model call here is a replay. The fixtures are written by the test itself from the
prompt the code builds, which is what keeps them honest: a fixture is keyed by the hash
of the real request, so a test cannot pass against a prompt that no longer exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from conftest import record_one_session

from prudence.cli import main
from prudence.model import guard
from prudence.model.recorded import input_hash
from prudence.reviews import explain as explain_module
from prudence.reviews import ranges, render, schema
from prudence.store import db

SEGMENT = (
    "Most of the range went to development work and the commits credited to it kept "
    "their lines. Nothing in the record contradicts that. You may want to keep an eye "
    "on the rework share the next time you read this page."
)
INVENTED = "You rework about 40% of your lines, which is worth watching."
GRADED = "Your 26 numbers describe the range. The 92% coverage is solid for this work."


def _write(directory: Path, request, text: str, model: str = "recorded-haiku") -> str:
    key = input_hash(request)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.json").write_text(
        json.dumps({"text": text, "model": model, "input_tokens": 900, "output_tokens": 120})
    )
    return key


def _record(directory: Path, payload: dict, text: str, model: str = "recorded-haiku") -> str:
    """Write the fixture for the prompt this payload really produces, and return its hash."""
    return _write(directory, explain_module.build_request(payload), text, model)


def _record_with_retry(directory: Path, payload: dict, first: str, second: str) -> None:
    """Both calls of a failed draft: the first attempt, and the corrected one after it.

    The correction is a different prompt, so it needs its own fixture; that is the point
    of keying on the input hash, and it is what stops a test passing against a retry
    instruction that no longer exists.
    """
    request = explain_module.build_request(payload)
    _write(directory, request, first)
    verdict = guard.judge(first, explain_module.allowed_numbers(payload))
    _write(directory, guard.corrected(request, verdict), second)


def _payload(connection) -> dict:
    from prudence.reviews import build

    window = ranges.resolve(connection, last="90d")
    return build.build(connection, window)


def _use_recorded(monkeypatch, directory: Path) -> None:
    monkeypatch.setenv("PRUDENCE_MODEL", "recorded")
    monkeypatch.setenv("PRUDENCE_MODEL_FIXTURES", str(directory))


# --- the prompt ---------------------------------------------------------------------------


def test_the_prompt_carries_the_numbers_and_no_transcript(lab) -> None:
    record_one_session(lab)
    connection = db.connect()
    payload = _payload(connection)
    connection.close()

    request = explain_module.build_request(payload)
    assert request.sent.content is False
    assert request.sent.numbers == len(payload["numbers"])
    assert "did" in request.sent.sections
    line = request.sent.line(
        "claude-haiku-4-5", 0.0012, max_tokens=request.max_tokens, caching=True
    )
    assert "no transcript content" in line
    assert line.startswith("Sending to claude-haiku-4-5:")
    assert f"{len(payload['numbers'])} numbers" in line
    # The whole request shape, not only its content: the cap and the caching.
    assert f"at most {request.max_tokens} tokens back" in line
    assert "the system prompt is cached" in line
    # Nothing in the body is prose from a session: the keys are the stored row's keys.
    body = json.loads(request.user)
    assert set(body) == {"scope", "window", "sections", "numbers"}


# --- the command --------------------------------------------------------------------------


def test_review_explain_stores_and_renders_the_segment(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    connection = db.connect()
    key = _record(tmp_path / "fixtures", _payload(connection), SEGMENT)
    connection.close()
    _use_recorded(monkeypatch, tmp_path / "fixtures")

    result = CliRunner().invoke(main, ["review", "--last", "90d", "--force", "--explain"])
    assert result.exit_code == 0, result.output
    assert "Sending to recorded:" in result.output
    assert "no transcript content" in result.output
    assert "## What this means" in result.output
    assert SEGMENT.split(".")[0] in result.output
    assert "every number checked against the review's" in result.output

    connection = db.connect()
    row = schema.review_by_id(connection, 1)
    segment = schema.segment_of(row)
    assert segment is not None
    assert segment["model"] == "recorded-haiku"
    assert segment["prompt_version"] == explain_module.EXPLAIN_PROMPT_VERSION
    assert segment["input_hash"] == key
    assert len(segment["numbers"]) == len(schema.sections_of(row)["numbers"])
    # The rendering reads the row, so `show --review` prints the same segment.
    assert "## What this means" in render.render(row)
    connection.close()


def test_an_invented_number_is_refused_and_never_printed(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    connection = db.connect()
    _record_with_retry(tmp_path / "fixtures", _payload(connection), INVENTED, INVENTED)
    connection.close()
    _use_recorded(monkeypatch, tmp_path / "fixtures")

    result = CliRunner().invoke(main, ["review", "--last", "90d", "--force", "--explain"])
    assert result.exit_code != 0
    assert "40%" in result.output, "the offending number is named"
    assert "discarded unread" in result.output
    # The draft itself never reaches the reader, disclaimer or no disclaimer.
    assert "worth watching" not in result.output
    assert "What this means" not in result.output
    # It was tried twice: once on its own, once told what was wrong.
    assert result.output.count("Sending to recorded:") == 2

    connection = db.connect()
    row = schema.review_by_id(connection, 1)
    assert row is not None, "the review itself is written even when the segment is refused"
    assert schema.segment_of(row) is None
    connection.close()


def test_a_graded_word_is_refused_the_same_way(lab, tmp_path, monkeypatch) -> None:
    """Principle 3: "92% coverage" is a fact, "which is solid" is a verdict."""
    record_one_session(lab)
    connection = db.connect()
    _record_with_retry(tmp_path / "fixtures", _payload(connection), GRADED, GRADED)
    connection.close()
    _use_recorded(monkeypatch, tmp_path / "fixtures")

    result = CliRunner().invoke(main, ["review", "--last", "90d", "--force", "--explain"])
    assert result.exit_code != 0
    assert "solid" in result.output, "the offending word is named"
    assert "graded the work" in result.output
    assert "coverage is solid for this work" not in result.output

    connection = db.connect()
    assert schema.segment_of(schema.review_by_id(connection, 1)) is None
    connection.close()


def test_a_corrected_second_draft_is_accepted(lab, tmp_path, monkeypatch) -> None:
    """The retry exists to rescue a draft that is one instruction away from usable."""
    record_one_session(lab)
    connection = db.connect()
    _record_with_retry(tmp_path / "fixtures", _payload(connection), GRADED, SEGMENT)
    connection.close()
    _use_recorded(monkeypatch, tmp_path / "fixtures")

    result = CliRunner().invoke(main, ["review", "--last", "90d", "--force", "--explain"])
    assert result.exit_code == 0, result.output
    assert result.output.count("Sending to recorded:") == 2
    assert "## What this means" in result.output
    assert "solid" not in result.output

    connection = db.connect()
    assert schema.segment_of(schema.review_by_id(connection, 1)) is not None
    connection.close()


def test_explain_adds_a_segment_to_a_review_written_without_one(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert runner.invoke(main, ["review", "--last", "90d", "--force"]).exit_code == 0

    connection = db.connect()
    row = schema.review_by_id(connection, 1)
    assert schema.segment_of(row) is None
    _record(tmp_path / "fixtures", schema.sections_of(row), SEGMENT)
    connection.close()
    _use_recorded(monkeypatch, tmp_path / "fixtures")

    added = runner.invoke(main, ["explain", "1"])
    assert added.exit_code == 0, added.output
    assert "## What this means" in added.output

    # A second one without --force is refused rather than silently overwriting.
    again = runner.invoke(main, ["explain", "1"])
    assert again.exit_code != 0
    assert "already has a segment" in again.output

    missing = runner.invoke(main, ["explain", "9"])
    assert missing.exit_code != 0
    assert "no review 9" in missing.output


def test_review_without_explain_is_a_whole_review(lab) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["review", "--last", "90d", "--force"])
    assert result.exit_code == 0, result.output
    assert "Sending to" not in result.output
    assert "## What this means" not in result.output
    assert "Nothing above this line was written by a model." in result.output


def test_config_model_shows_and_sets_without_printing_a_key(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")
    runner = CliRunner()
    shown = runner.invoke(main, ["config", "model"])
    assert shown.exit_code == 0, shown.output
    assert "ANTHROPIC_API_KEY (set)" in shown.output
    assert "secret" not in shown.output

    changed = runner.invoke(
        main, ["config", "model", "--backend", "none", "--model-id", "claude-haiku-4-5"]
    )
    assert changed.exit_code == 0, changed.output
    assert "backend      none" in changed.output

    from prudence import config as config_module

    assert config_module.load().model.model_id == "claude-haiku-4-5"


def test_review_explain_from_the_config_needs_no_flag(lab, tmp_path, monkeypatch) -> None:
    record_one_session(lab)
    runner = CliRunner()
    assert runner.invoke(main, ["config", "model", "--backend", "none"]).exit_code == 0

    from prudence import config as config_module

    settings = config_module.load()
    settings.review = config_module.ReviewSettings(explain=True)
    config_module.save(settings)

    connection = db.connect()
    _record(tmp_path / "fixtures", _payload(connection), SEGMENT)
    connection.close()
    _use_recorded(monkeypatch, tmp_path / "fixtures")

    result = runner.invoke(main, ["review", "--last", "90d", "--force"])
    assert result.exit_code == 0, result.output
    assert "## What this means" in result.output

    # And `--no-explain` turns the standing setting off for one run.
    plain = runner.invoke(main, ["review", "--last", "90d", "--force", "--no-explain"])
    assert plain.exit_code == 0, plain.output
    assert "## What this means" not in plain.output


def test_no_model_says_what_to_do_rather_than_failing_oddly(lab, monkeypatch) -> None:
    record_one_session(lab)
    monkeypatch.setenv("PRUDENCE_MODEL", "none")
    result = CliRunner().invoke(main, ["review", "--last", "90d", "--force", "--explain"])
    assert result.exit_code != 0
    assert "no model configured" in result.output
