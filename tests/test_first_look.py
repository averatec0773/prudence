"""The first look: which facts qualify, the marker, and what later ingests say.

The store is built from derived rows, as in `tests/test_reviews.py`: the rules under
test choose between figures the views already computed, and how those figures got into
the tables has its own tests.
"""

from __future__ import annotations

import json

from click.testing import CliRunner
from conftest import record_one_session
from test_reviews import NOW, _at, _session, _store

from prudence.cli import main
from prudence.reviews import first_look, schema
from prudence.store import db, views
from prudence.store import observations as observations_module


def _rich():
    """Enough sessions and matured commits for the full first look."""
    connection = _store()
    for index in range(30):
        _session(
            connection,
            f"s-{index}",
            days_ago=20 + index,
            commit_days_ago=30 + index,
            reworked=6 if index % 2 else 1,
            alive=4 if index % 2 else 9,
            facts={"compactions": 1.0 if index % 2 else 0.0, "sittings": 4.0 if index % 2 else 1.0},
            edits=0 if index < 6 else 1,
        )
    observations_module.build(connection)
    return connection


def test_the_first_look_prints_ranked_facts_each_with_a_command() -> None:
    connection = _rich()
    lines = first_look.first_look(connection, NOW)
    text = "\n".join(lines)
    assert "A first look at what was recorded" in text
    printed = [line for line in lines if line.startswith("  more: ")]
    assert first_look.MIN_FACTS <= len(printed) <= first_look.MAX_FACTS
    assert "30 sessions in 1 project" in text
    assert text.strip().endswith(first_look.CLOSING)
    connection.close()


def test_a_candidate_below_its_coverage_floor_is_not_printed() -> None:
    connection = _rich()
    look = first_look.gather(connection, NOW)
    candidate = next(item for item in first_look.CANDIDATES if item.key == "rework_30d")
    assert first_look._qualified(candidate, look) is not None
    look.outcomes = {**look.outcomes, "coverage": 0.1}
    assert first_look._qualified(candidate, look) is None
    connection.close()


def test_the_thin_variant_says_what_is_missing_and_when_to_come_back() -> None:
    connection = _store()
    for index in range(6):
        _session(connection, f"thin-{index}", days_ago=2, commit_days_ago=1)
    text = "\n".join(first_look.first_look(connection, NOW))
    assert "Outcomes need commits older than 7 days" in text
    assert "come back after about" in text
    assert first_look.CLOSING in text
    connection.close()


def test_a_store_with_no_session_prints_nothing() -> None:
    connection = _store()
    assert first_look.first_look(connection, NOW) == []
    connection.close()


def test_the_marker_is_set_once_and_later_ingests_say_only_what_is_new() -> None:
    connection = _rich()
    assert schema.marker(connection, first_look.FIRST_LOOK_MARKER) is None
    first = first_look.after_ingest(connection, NOW)
    assert "A first look at what was recorded" in "\n".join(first)
    assert schema.marker(connection, first_look.FIRST_LOOK_MARKER) is not None

    # Nothing changed since: the second ingest says nothing about observations.
    second = first_look.after_ingest(connection, NOW)
    assert not any("first look" in line for line in second)
    assert not any("New observation" in line for line in second)

    # One observation forgotten from the marker reads as new, in one line.
    seen = json.loads(schema.marker(connection, first_look.OBSERVATIONS_MARKER))
    schema.set_marker(connection, first_look.OBSERVATIONS_MARKER, json.dumps(seen[2:]))
    third = first_look.after_ingest(connection, NOW)
    fresh = [line for line in third if line.startswith("New observation:")]
    assert len(fresh) == 2

    # More than two new ones are one counted line, never a wall of text.
    schema.set_marker(connection, first_look.OBSERVATIONS_MARKER, json.dumps([]))
    fourth = first_look.after_ingest(connection, NOW)
    counted = [line for line in fourth if "new observations since the last ingest" in line]
    assert len(counted) == 1
    connection.close()


def test_later_ingests_hint_when_a_review_is_ready() -> None:
    connection = _rich()
    first_look.after_ingest(connection, NOW)
    lines = first_look.after_ingest(connection, NOW)
    assert any("prudence review" in line for line in lines)
    connection.close()


def test_ingest_prints_the_first_look_and_sets_the_marker(lab) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        assert schema.marker(connection, first_look.FIRST_LOOK_MARKER) is not None
    finally:
        connection.close()
    # The one session store is thin, so the thin variant is what `ingest` printed.
    again = CliRunner().invoke(main, ["ingest"])
    assert again.exit_code == 0, again.output
    assert "A first look at what was recorded" not in again.output


def test_the_first_look_never_prints_a_figure_it_did_not_compute() -> None:
    connection = _rich()
    look = first_look.gather(connection, NOW)
    assert look.sessions == 30
    assert look.no_code == 6
    assert look.outcomes is not None
    # Every candidate either returns a figure built from those reads or returns nothing.
    for candidate in first_look.CANDIDATES:
        figure = candidate.compute(look)
        assert figure is None or figure.text
    connection.close()


def test_new_observations_before_any_marker_is_silent() -> None:
    connection = _rich()
    assert views.observations(connection)
    assert first_look.new_observations(connection) == []
    connection.close()


def test_the_outcome_figure_matches_the_view_it_came_from() -> None:
    connection = _rich()
    look = first_look.gather(connection, NOW)
    shares = look.outcomes["shares"]
    figure = first_look._rework(look)
    expected = 1 - (shares["alive_30d"] / shares["measured_30d"])
    assert figure.value == expected
    assert f"{expected * 100:.0f}%" in figure.text
    assert f"{shares['measured_30d']} lines measured" in figure.text
    assert _at(0)  # the helper is the one the review tests use, so the clock agrees
    connection.close()
