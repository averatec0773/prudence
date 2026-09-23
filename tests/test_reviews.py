"""Reviews: which range, whether it is ready, what the row holds, and how it reads.

The scenarios are written as derived rows rather than ingested from transcripts, the
same way `tests/test_observations.py` does and for the same reason: what is under test
is which sessions and commits a range picks up and what the sections make of them, and
a split needs more sessions than a readable fixture could produce through a real
repository. The parsers and the harvest have their own tests.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta

from click.testing import CliRunner
from conftest import record_one_session

from prudence.cli import main
from prudence.facts import registry as facts_registry
from prudence.reviews import build, first_look, ranges, readiness, render, schema
from prudence.reviews import suggestions as suggestions_module
from prudence.store import app_views, db, transfer, views
from prudence.store import observations as observations_module

ALPHA = "repo-alpha"
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
STAMP = "%Y-%m-%dT%H:%M:%S"


def _at(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime(STAMP)


def _local(day: str) -> str:
    """The UTC stamp of local midnight on `day`, which is what a written date now means."""
    return ranges.local_midnight(datetime.fromisoformat(f"{day}T00:00:00")).strftime(STAMP)


def _store() -> sqlite3.Connection:
    connection = db.connect()
    transfer.ensure_tables(connection)
    connection.execute(
        "INSERT INTO repository (repo_key, name, toplevel, outcomes_suppressed, fact_version)"
        " VALUES (?, 'alpha', '/tmp/alpha', 0, 1)",
        (ALPHA,),
    )
    return connection


def _session(
    connection: sqlite3.Connection,
    session_id: str,
    *,
    days_ago: float,
    commit_days_ago: float | None = None,
    lines: int = 10,
    reworked: int = 0,
    alive: int = 10,
    facts: dict[str, float] | None = None,
    purpose: str | None = "development",
    edits: int = 1,
    repo_key: str = ALPHA,
) -> None:
    """One session, one commit it is credited with, and the fate of that commit's lines."""
    started = _at(days_ago)
    connection.execute(
        "INSERT INTO session (session_id, repo_key, first_at, last_at, capture_level,"
        " parser_version) VALUES (?, ?, ?, ?, 'full', 4)",
        (session_id, repo_key, started, started),
    )
    for index in range(edits):
        connection.execute(
            "INSERT INTO edit (session_id, repo_key, tool_use_id, rel_path, lines_added,"
            " lines_removed, parser_version) VALUES (?, ?, ?, 'src/app.py', 3, 0, 4)",
            (session_id, repo_key, f"{session_id}-e{index}"),
        )
    if commit_days_ago is None:
        return
    commit_hash = f"c{session_id}"
    connection.execute(
        'INSERT INTO "commit" (commit_hash, repo_key, author_at, committer_at, added_lines,'
        " is_merge, is_bot, fact_version) VALUES (?, ?, ?, ?, ?, 0, 0, 1)",
        (commit_hash, repo_key, _at(commit_days_ago), _at(commit_days_ago), lines),
    )
    connection.execute(
        "INSERT INTO attribution (commit_hash, session_id, method, rank, lines_matched,"
        " coverage, confidence, fact_version) VALUES (?, ?, 'in_session', 1, ?, 0.9, 'fact', 1)",
        (commit_hash, session_id, lines),
    )
    connection.executemany(
        "INSERT INTO line_fate VALUES (?, 'src/app.py', ?, 1, ?, NULL, ?, ?, ?, ?, 2)",
        [
            (
                commit_hash,
                f"{commit_hash}-{index}",
                1 if index < alive else 0,
                1 if index < alive else 0,
                1 if index < alive else 0,
                1 if index < alive else 0,
                "later" if index < reworked else None,
            )
            for index in range(lines)
        ],
    )
    for name, value in (facts or {}).items():
        connection.execute(
            f"INSERT INTO {facts_registry.TABLE} VALUES (?, ?, ?, 'high', 1)",
            (session_id, name, value),
        )
    if purpose is not None:
        connection.execute(
            f"INSERT INTO {facts_registry.LABEL_TABLE} VALUES (?, 'purpose', ?, 1)",
            (session_id, purpose),
        )


def _populated() -> sqlite3.Connection:
    """A store with two weeks of sessions, matured commits, and one clear observation."""
    connection = _store()
    # Ten sessions inside the last seven days, their commits ten days old so that their
    # seven-day mark falls inside the window.
    for index in range(10):
        _session(
            connection,
            f"recent-{index}",
            days_ago=3,
            commit_days_ago=10,
            reworked=3 if index < 5 else 0,
            facts={"compactions": 1.0 if index < 5 else 0.0},
        )
    # Ten more a fortnight back, for the previous-period comparison.
    for index in range(10):
        _session(
            connection,
            f"older-{index}",
            days_ago=11,
            commit_days_ago=18,
            reworked=8 if index < 5 else 1,
            facts={"compactions": 1.0 if index < 5 else 0.0},
        )
    observations_module.build(connection)
    return connection


# --- ranges ---------------------------------------------------------------------------


def test_last_window_and_its_outcome_range() -> None:
    window = ranges.resolve(None, last="14d", now=NOW)
    assert window.start == _at(14)
    assert window.end == _at(0)
    # The outcome window is the same span shifted back by the maturity mark, which is
    # every commit whose seven-day mark fell inside the activity window.
    assert window.outcome_start == _at(21)
    assert window.outcome_end == _at(7)
    assert round(window.days) == 14


def test_month_window_covers_the_whole_month() -> None:
    """A month is the user's own July, stored as the UTC stamps of its two local edges."""
    window = ranges.resolve(None, month="2026-07", now=NOW)
    assert window.start == _local("2026-07-01")
    assert window.end == _local("2026-08-01")


def test_a_written_date_is_local_midnight_and_the_stamp_is_utc() -> None:
    """The one date convention: `--since` is the user's calendar, the row keeps UTC."""
    window = ranges.resolve(None, since="2026-09-08", until="2026-09-15", now=NOW)
    assert window.start == _local("2026-09-08")
    assert ranges.parse(window.start).tzinfo == UTC
    # The same instant `app_usage_by_bucket_day` calls the start of that local day.
    assert (
        datetime.fromisoformat(window.start)
        .replace(tzinfo=UTC)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
        == "2026-09-08 00:00"
    )


def test_since_until_and_the_previous_period() -> None:
    window = ranges.resolve(None, since="2026-09-08", until="2026-09-15", now=NOW)
    previous = window.previous()
    assert previous.start == _local("2026-09-01")
    assert previous.end == _local("2026-09-08")


def test_default_range_starts_at_the_last_review_of_the_same_scope() -> None:
    connection = _populated()
    first = ranges.resolve(connection, since="2026-09-01", until="2026-09-10", project=ALPHA)
    _store_review(connection, first)
    again = ranges.resolve(connection, project=ALPHA, now=NOW)
    assert again.start == first.end == _local("2026-09-10")
    assert "since review" in again.source
    # Another project's scope has no review of its own, so it falls back to seven days.
    other = ranges.resolve(connection, project="repo-beta", now=NOW)
    assert other.start == _at(ranges.DEFAULT_DAYS)
    connection.close()


def test_two_range_options_are_refused() -> None:
    try:
        ranges.resolve(None, last="7d", month="2026-07", now=NOW)
    except ranges.Unreadable as error:
        assert "one" in str(error)
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("two ranges were accepted")


# --- readiness ------------------------------------------------------------------------


def test_ready_when_sessions_and_a_matured_commit_are_there() -> None:
    connection = _populated()
    verdict = readiness.readiness(connection, ALPHA, NOW)
    assert verdict.ready
    assert verdict.new_sessions == 20
    assert verdict.matured_commits == 20
    assert "prudence review" in verdict.hint
    connection.close()


def test_not_ready_right_after_a_review_and_says_the_count() -> None:
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    _store_review(connection, window)
    verdict = readiness.readiness(connection, ALPHA, NOW)
    assert not verdict.ready
    assert verdict.reason.startswith("not ready:")
    assert f"needs {readiness.MIN_NEW_SESSIONS}" in verdict.reason
    connection.close()


def test_not_ready_when_no_commit_has_matured() -> None:
    connection = _store()
    for index in range(6):
        _session(connection, f"young-{index}", days_ago=1, commit_days_ago=1)
    verdict = readiness.readiness(connection, ALPHA, NOW)
    assert not verdict.ready
    assert "no commit crossed" in verdict.reason
    connection.close()


# --- the stored row -------------------------------------------------------------------


def _store_review(connection: sqlite3.Connection, window: ranges.Window) -> int:
    payload = build.build(connection, window, now=NOW)
    return schema.insert_review(
        connection,
        created_at=schema.now_text(NOW),
        range_start=window.start,
        range_end=window.end,
        project=window.project,
        outcome_range_start=window.outcome_start,
        outcome_range_end=window.outcome_end,
        sections=payload,
        coverage=build.coverage_of(payload),
        fact_version=2,
        parser_version=4,
    )


def test_the_row_holds_every_section_and_a_numbers_list() -> None:
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    review_id = _store_review(connection, window)
    row = schema.review_by_id(connection, review_id)
    payload = schema.sections_of(row)

    assert payload["review_version"] == build.REVIEW_VERSION
    assert [section["key"] for section in payload["sections"]] == [
        spec.key for spec in build.SECTIONS
    ]
    assert payload["numbers"], "a review of a populated store has figures"
    assert row["coverage"] == 0.9
    # The sections are built only from figures the views computed: the ten sessions of
    # the window and the ten commits whose mark fell inside it.
    did = _section(payload, "did")
    assert ["all purposes", "10", "-", "0.0"] in did["rows"]
    became = _section(payload, "became")
    assert ["lines followed", "100", "90%", "10 fact, 0 inferred"] in became["rows"]
    connection.close()


def test_the_row_keeps_a_coverage_even_when_nothing_has_matured() -> None:
    """The column was NULL for exactly the reviews a user writes most: recent work.

    A review of the last few days has no commit whose seven-day mark has passed, so the
    outcome section is empty and `became.coverage` does not exist. The activity section's
    mean over the commits credited to the range's own sessions does, and that is what the
    row now carries, so `app_review.coverage` has something to show.
    """
    connection = _store()
    for index in range(3):
        _session(connection, f"fresh-{index}", days_ago=1, commit_days_ago=1)
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    payload = build.build(connection, window, now=NOW)

    assert _section(payload, "became")["empty"], "nothing has reached its mark"
    keys = {number["key"]: number for number in payload["numbers"]}
    assert "became.coverage" not in keys
    assert keys["did.coverage"]["coverage"] == 0.9

    row = schema.review_by_id(connection, _store_review(connection, window))
    assert row["coverage"] == 0.9
    # And it reaches the app through the view that already selects the column.
    app_views.install_app_views(connection)
    app = connection.execute("SELECT coverage FROM app_review WHERE id = ?", (row["id"],))
    assert app.fetchone()["coverage"] == 0.9
    connection.close()


def test_the_numbers_carry_the_group_sizes_and_the_previous_values() -> None:
    """Review version 2: what a paired bar and a compare card need, as numbers.

    The texts are unchanged; these are the same figures the page prints, in a form a
    chart can measure with instead of parsing the string back.
    """
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    payload = build.build(connection, window, now=NOW)
    connection.close()

    assert payload["review_version"] == 2
    numbers = {number["key"]: number for number in payload["numbers"]}
    observed = [number for key, number in numbers.items() if key.startswith("observation.")]
    assert observed, "the populated store has an observation"
    # Ten sessions compacted and ten did not, over both weeks: an observation is about
    # every session in the store, not only the ones inside the review's range.
    for number in observed:
        assert number["with_n"] == 10 and number["without_n"] == 10, number["key"]

    sessions = numbers["compared.sessions.now"]
    assert (sessions["text"], sessions["value"], sessions["previous_value"]) == ("10", 10, 10)
    assert numbers["compared.sessions.change"]["value"] == 0
    # 15% of this period's lines against 45% of the previous period's, and the change in
    # points, each the number under the cell beside it.
    rework = numbers["compared.rework_share.now"]
    assert (rework["text"], rework["value"], rework["previous_value"]) == ("15%", 0.15, 0.45)
    assert numbers["compared.rework_share.previous"]["value"] == 0.45
    assert numbers["compared.rework_share.change"]["value"] == -30
    # A dash is never a zero: these sessions carry no usage rows at all, so every token
    # cell of the row is a dash and every number under it is null (rule 10).
    for suffix in ("now", "previous", "change"):
        cell = numbers[f"compared.tokens.{suffix}"]
        assert cell["text"] == "-" and cell["value"] is None, suffix
    assert numbers["compared.tokens.now"]["previous_value"] is None


def test_a_review_stored_before_the_new_keys_still_renders() -> None:
    """A version 1 row carries no `with_n` and no `previous_value`, and is still a page.

    The three keys were added, never required: a surface that finds them missing has an
    older review rather than a broken one.
    """
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    payload = _as_version_one(build.build(connection, window, now=NOW))
    review_id = schema.insert_review(
        connection,
        created_at=schema.now_text(NOW),
        range_start=window.start,
        range_end=window.end,
        project=window.project,
        outcome_range_start=window.outcome_start,
        outcome_range_end=window.outcome_end,
        sections=payload,
        coverage=build.coverage_of(payload),
        fact_version=2,
        parser_version=4,
    )
    row = schema.review_by_id(connection, review_id)
    stored = schema.sections_of(row)
    assert stored["review_version"] == 1
    assert all("with_n" not in number for number in stored["numbers"])

    text = render.render(row)
    missing = [number["text"] for number in stored["numbers"] if number["text"] not in text]
    assert not missing, f"figures stored but not printed: {missing}"
    assert "# Review" in text and "| purpose |" in text
    assert render.headline(row).startswith(f"Review {review_id}")

    # And the app reads the row as it always did: the JSON is what the view hands over.
    app_views.install_app_views(connection)
    view = connection.execute("SELECT * FROM app_review WHERE id = ?", (review_id,)).fetchone()
    assert json.loads(view["numbers"]) == stored["numbers"]
    connection.close()


def _as_version_one(payload: dict) -> dict:
    """The same payload as a review written before version 2, with the new keys gone."""
    older = json.loads(json.dumps(payload))
    older["review_version"] = 1
    lists = [older["numbers"], *(section["numbers"] for section in older["sections"])]
    for numbers in lists:
        for number in numbers:
            for key in ("with_n", "without_n", "previous_value"):
                number.pop(key, None)
    return older


def test_every_number_in_the_list_appears_in_the_markdown() -> None:
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    row = schema.review_by_id(connection, _store_review(connection, window))
    text = render.render(row)
    payload = schema.sections_of(row)
    missing = [number["text"] for number in payload["numbers"] if number["text"] not in text]
    assert not missing, f"figures stored but not printed: {missing}"
    assert "# Review" in text and "| purpose |" in text
    connection.close()


def test_the_outcome_section_carries_coverage_beside_every_figure() -> None:
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    payload = build.build(connection, window, now=NOW)
    became = _section(payload, "became")
    assert became["headers"][2] == "coverage"
    assert all(row[2] == "90%" for row in became["rows"])
    connection.close()


def test_a_range_with_nothing_in_it_says_so_rather_than_printing_zeroes() -> None:
    connection = _store()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    payload = build.build(connection, window, now=NOW)
    assert _section(payload, "did")["empty"]
    assert _section(payload, "became")["empty"]
    assert not payload["numbers"]
    connection.close()


def _section(payload: dict, key: str) -> dict:
    for section in payload["sections"]:
        if section["key"] == key:
            return section
    raise AssertionError(f"no section {key}")


# --- suggestions ----------------------------------------------------------------------


def test_suggestions_open_once_and_follow_the_lifecycle() -> None:
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    review_id = _store_review(connection, window)
    first = suggestions_module.refresh(connection, review_id, ALPHA, schema.now_text(NOW))
    assert first.opened == len(views.observations(connection, ALPHA))
    assert first.opened > 0

    # A second review of the same observations opens nothing new.
    again = suggestions_module.refresh(connection, review_id, ALPHA, schema.now_text(NOW))
    assert again.opened == 0
    assert again.kept == first.opened

    row = schema.open_suggestions(connection)[0]
    schema.set_status(connection, row["id"], schema.DISMISSED, schema.now_text(NOW))
    assert schema.suggestion_by_id(connection, row["id"])["status"] == schema.DISMISSED
    assert schema.suggestion_by_id(connection, row["id"])["resolved_at"] is not None
    # A dismissed key is not raised again (principle 4).
    third = suggestions_module.refresh(connection, review_id, ALPHA, schema.now_text(NOW))
    assert third.opened == 0
    connection.close()


def test_a_suggestion_expires_when_its_observation_stops_existing() -> None:
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    review_id = _store_review(connection, window)
    suggestions_module.refresh(connection, review_id, ALPHA, schema.now_text(NOW))
    connection.execute("DELETE FROM observation")
    stats = suggestions_module.refresh(connection, review_id, ALPHA, schema.now_text(NOW))
    assert stats.expired > 0
    assert not schema.open_suggestions(connection)
    connection.close()


def test_the_follow_up_compares_the_outcome_before_and_since() -> None:
    connection = _populated()
    key = build.observation_key(views.observations(connection, ALPHA)[0])
    moved = suggestions_module.follow_up(connection, key, _at(7))
    assert moved["before_n"] == 5 and moved["since_n"] == 5
    assert moved["before_text"].endswith("%") and moved["since_text"].endswith("%")
    # Below the observations' own session floor, a side is a dash rather than a number.
    thin = suggestions_module.follow_up(connection, key, _at(0.5))
    assert thin["since_text"] == "-"
    connection.close()


# --- the two promises about the tables --------------------------------------------------


def test_export_carries_reviews_and_import_brings_them_back(tmp_path, monkeypatch) -> None:
    connection = _populated()
    window = ranges.resolve(connection, last="7d", project=ALPHA, now=NOW)
    review_id = _store_review(connection, window)
    suggestions_module.refresh(connection, review_id, ALPHA, schema.now_text(NOW))
    bundle = tmp_path / "store.tar.gz"
    stats = transfer.export(connection, bundle)
    connection.close()
    assert stats.tables["review"] == 1
    assert stats.tables["suggestion"] > 0

    monkeypatch.setenv("PRUDENCE_DATA_DIR", str(tmp_path / "restored"))
    monkeypatch.setenv("PRUDENCE_CONFIG_DIR", str(tmp_path / "restored-config"))
    restored = db.connect()
    transfer.import_bundle(restored, bundle)
    back = schema.review_by_id(restored, review_id)
    assert back is not None
    assert back["range_start"] == window.start
    assert schema.open_suggestions(restored)
    restored.close()


def test_rebuild_keeps_the_review_rows(lab) -> None:
    record_one_session(lab)
    connection = db.connect()
    window = ranges.resolve(connection, last="30d", now=NOW)
    review_id = _store_review(connection, window)
    connection.close()

    result = CliRunner().invoke(main, ["rebuild"])
    assert result.exit_code == 0, result.output
    connection = db.connect()
    assert schema.review_by_id(connection, review_id) is not None
    connection.close()


# --- the commands -----------------------------------------------------------------------


def test_review_command_stores_prints_and_writes_a_file(lab) -> None:
    from prudence.paths import reports_dir

    record_one_session(lab)
    runner = CliRunner()
    result = runner.invoke(main, ["review", "--last", "90d", "--force"])
    assert result.exit_code == 0, result.output
    assert "# Review 1" in result.output
    assert (reports_dir() / "review-1.md").exists()

    # The second one is refused by the readiness rule, with the count in the reason.
    again = runner.invoke(main, ["review"])
    assert again.exit_code == 0, again.output
    assert "not ready:" in again.output

    shown = runner.invoke(main, ["show", "--review", "1"])
    assert shown.exit_code == 0, shown.output
    assert "# Review 1" in shown.output

    missing = runner.invoke(main, ["show", "--review", "9"])
    assert missing.exit_code != 0
    assert "no review 9" in missing.output


def test_review_json_is_json(lab) -> None:
    record_one_session(lab)
    result = CliRunner().invoke(main, ["review", "--last", "90d", "--force", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["id"] == 1
    assert payload["review_version"] == build.REVIEW_VERSION


def test_suggestions_command_lists_and_dismisses(lab) -> None:
    record_one_session(lab)
    connection = db.connect()
    window = ranges.resolve(connection, last="90d", now=NOW)
    review_id = _store_review(connection, window)
    schema.insert_suggestion(
        connection,
        review_id=review_id,
        observation_key=f"{ALPHA}|compactions|rework",
        text="In alpha, your sessions that compacted reworked more of their lines.",
        created_at=schema.now_text(NOW),
    )
    connection.close()

    runner = CliRunner()
    listed = runner.invoke(main, ["suggestions"])
    assert listed.exit_code == 0, listed.output
    assert "compacted" in listed.output

    dismissed = runner.invoke(main, ["suggestions", "dismiss", "1"])
    assert dismissed.exit_code == 0, dismissed.output
    assert runner.invoke(main, ["suggestions"]).output.startswith("No suggestion yet")
    assert "compacted" in runner.invoke(main, ["suggestions", "list", "--all"]).output


def test_the_engine_imports_without_the_command_line() -> None:
    """`reviews` must not need `cli` to load: the app and the MCP server import it alone.

    A subprocess per module, because in this process they are already imported and a
    cycle would never show. This caught `build` importing `cli.render` for one format
    string, which made `import prudence.reviews.build` fail on its own.
    """
    for module in ("build", "suggestions", "first_look", "render", "schema"):
        done = subprocess.run(
            [sys.executable, "-c", f"import prudence.reviews.{module}"],
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, f"prudence.reviews.{module}: {done.stderr}"


def test_first_look_marker_does_not_leak_into_the_review_tables() -> None:
    connection = _populated()
    schema.set_marker(connection, first_look.FIRST_LOOK_MARKER, schema.now_text(NOW))
    assert schema.marker(connection, first_look.FIRST_LOOK_MARKER) is not None
    assert schema.review_by_id(connection, 1) is None
    connection.close()
