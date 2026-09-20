"""The join: which splits become an observation, which are withheld, and how they read.

The rule under test lives in `store/observations.py`. These scenarios are built by
writing the derived rows directly rather than by ingesting transcripts, because what is
under test is the arithmetic of the join and the two floors, and a split needs more
sessions on each side than a readable fixture could produce through a real repository.
`store/outcomes.py` and `facts/` have their own tests against real git and real
transcripts; this file assumes those tables and asks only what the join does with them.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from click.testing import CliRunner

from prudence.cli import main
from prudence.facts import registry as facts_registry
from prudence.store import db, observations, transfer, views

ALPHA = "repo-alpha"
BETA = "repo-beta"


def _store() -> sqlite3.Connection:
    """An empty store with every table an export can carry, and two repositories."""
    connection = db.connect()
    transfer.ensure_tables(connection)
    for repo_key, name in ((ALPHA, "alpha"), (BETA, "beta")):
        connection.execute(
            "INSERT INTO repository (repo_key, name, toplevel, outcomes_suppressed,"
            " fact_version) VALUES (?, ?, ?, 0, 1)",
            (repo_key, name, f"/tmp/{name}"),
        )
    return connection


def _session(
    connection: sqlite3.Connection,
    session_id: str,
    repo_key: str,
    *,
    lines: int = 10,
    reworked: int = 0,
    alive: int = 10,
    facts: dict[str, float] | None = None,
    purpose: str | None = None,
) -> None:
    """One session credited with one commit of `lines` followed lines, and its facts."""
    started = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
    connection.execute(
        "INSERT INTO session (session_id, repo_key, first_at, last_at, capture_level,"
        " parser_version) VALUES (?, ?, ?, ?, 'full', 1)",
        (session_id, repo_key, started, started),
    )
    commit_hash = f"c{session_id}"
    connection.execute(
        "INSERT INTO attribution (commit_hash, session_id, method, rank, lines_matched,"
        " coverage, confidence, fact_version) VALUES (?, ?, 'in_session', 1, ?, 0.9, 'fact', 1)",
        (commit_hash, session_id, lines),
    )
    connection.executemany(
        "INSERT INTO line_fate VALUES (?, 'src/app.py', ?, 1, 1, 1, ?, ?, ?, ?, 1)",
        [
            (
                commit_hash,
                f"{commit_hash}-{index}",
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


def _split(
    connection: sqlite3.Connection,
    repo_key: str,
    *,
    fact: str = "formatter_runs",
    with_n: int,
    without_n: int,
    with_rework: int,
    without_rework: int,
    lines: int = 10,
    tag: str = "a",
) -> None:
    """`with_n` sessions that ran the fact and `without_n` that did not, with their rework."""
    for index in range(with_n):
        _session(
            connection,
            f"{tag}-with-{index}",
            repo_key,
            lines=lines,
            alive=lines,
            reworked=with_rework,
            facts={fact: 1.0},
        )
    for index in range(without_n):
        _session(
            connection,
            f"{tag}-without-{index}",
            repo_key,
            lines=lines,
            alive=lines,
            reworked=without_rework,
            facts={fact: 0.0},
        )


def _rows(connection: sqlite3.Connection) -> list[dict]:
    return views.observations(connection)


def test_every_behaviour_fact_has_a_documented_threshold() -> None:
    """A fact with no entry in SPLITS would silently never be joined against anything."""
    assert [split.fact for split in observations.SPLITS] == [
        fact.name for fact in facts_registry.FACTS
    ]


def test_a_clear_gap_becomes_an_observation_with_both_counts() -> None:
    """Six sessions that ran a formatter reworked nothing; six that did not reworked half."""
    connection = _store()
    try:
        _split(
            connection,
            ALPHA,
            with_n=6,
            without_n=6,
            with_rework=0,
            without_rework=5,
        )
        stats = observations.build(connection)
        rows = _rows(connection)
    finally:
        connection.close()

    assert stats.sessions == 12
    assert [(row["repo_key"], row["fact"], row["outcome"]) for row in rows] == [
        (ALPHA, "formatter_runs", "rework")
    ]
    row = rows[0]
    assert (row["with_n"], row["without_n"]) == (6, 6)
    assert (row["with_value"], row["without_value"]) == (0.0, 0.5)
    assert row["direction"] == "lower"
    assert row["threshold_text"] == "formatter_runs > 0"
    assert row["fact_version"] == observations.FACT_VERSION


def test_a_gap_below_ten_points_is_withheld() -> None:
    """Five points apart is not a finding, and a finding that small was never one."""
    connection = _store()
    try:
        _split(
            connection,
            ALPHA,
            with_n=6,
            without_n=6,
            with_rework=0,
            without_rework=1,
            lines=20,
        )
        observations.build(connection)
        assert _rows(connection) == []
    finally:
        connection.close()


def test_a_side_below_the_sample_floor_is_withheld() -> None:
    """Four sessions on one side, an enormous gap, and still nothing is reported."""
    connection = _store()
    try:
        _split(
            connection,
            ALPHA,
            with_n=4,
            without_n=8,
            with_rework=0,
            without_rework=9,
        )
        observations.build(connection)
        assert _rows(connection) == []
    finally:
        connection.close()


def test_the_pooled_row_appears_only_where_no_project_could_answer() -> None:
    """Formatter clears the floor inside alpha; subagents only when both projects pool."""
    connection = _store()
    try:
        _split(connection, ALPHA, with_n=6, without_n=6, with_rework=0, without_rework=5)
        for repo_key, tag in ((ALPHA, "s"), (BETA, "t")):
            _split(
                connection,
                repo_key,
                fact="subagent_used",
                with_n=3,
                without_n=3,
                with_rework=0,
                without_rework=8,
                tag=tag,
            )
        stats = observations.build(connection)
        rows = _rows(connection)
    finally:
        connection.close()

    found = {(row["repo_key"], row["fact"], row["outcome"]) for row in rows}
    assert (ALPHA, "formatter_runs", "rework") in found, "one project answered it alone"
    assert (observations.POOLED, "formatter_runs", "rework") not in found, (
        "a project answered it, so the pooled row is not computed"
    )
    assert (observations.POOLED, "subagent_used", "rework") in found, (
        "neither project had five sessions a side; pooled, they do"
    )
    assert not any(
        row["fact"] == "subagent_used" and row["repo_key"] != observations.POOLED for row in rows
    )
    assert stats.pooled == 1


def test_a_purpose_label_is_compared_against_every_other_label() -> None:
    """A label is not a number: one label against the rest, never a threshold on it."""
    connection = _store()
    try:
        for index in range(6):
            _session(connection, f"d{index}", ALPHA, reworked=0, purpose="development")
        for index in range(6):
            _session(connection, f"r{index}", ALPHA, reworked=6, purpose="research")
        observations.build(connection)
        rows = _rows(connection)
    finally:
        connection.close()

    facts = {row["fact"] for row in rows}
    assert facts == {"purpose:development", "purpose:research"}
    development = next(row for row in rows if row["fact"] == "purpose:development")
    assert development["threshold_text"] == "purpose = development"
    assert (development["with_value"], development["without_value"]) == (0.0, 0.6)


def test_the_wording_carries_the_numbers_and_the_caveat() -> None:
    """The sentence a surface prints, in plain words, with no adjective and no score."""
    connection = _store()
    try:
        _split(connection, ALPHA, with_n=6, without_n=6, with_rework=0, without_rework=5)
        observations.build(connection)
    finally:
        connection.close()

    listed = CliRunner().invoke(main, ["observations"])
    assert listed.exit_code == 0, listed.output
    assert (
        "In alpha, your 6 sessions that ran a formatter reworked 0% of their lines (median); "
        "the 6 that did not, 50%." in listed.output
    )
    assert "(coverage: 90%, method: 12 fact, 0 inferred)" in listed.output
    assert "descriptions, not advice" in listed.output.replace("\n", " ")

    joined = CliRunner().invoke(main, ["outcomes", "--project", "alpha", "--last", "90d"])
    assert joined.exit_code == 0, joined.output
    assert "observations" in joined.output
    assert "that ran a formatter reworked 0% of their lines" in joined.output


def test_nothing_qualifying_says_which_floor_was_not_cleared() -> None:
    connection = _store()
    try:
        _split(connection, ALPHA, with_n=6, without_n=6, with_rework=2, without_rework=2)
        observations.build(connection)
    finally:
        connection.close()

    listed = CliRunner().invoke(main, ["observations"])
    assert listed.exit_code == 0, listed.output
    assert (
        "No observation clears the sample floor (5 sessions each side) and the gap floor "
        "(10 points) yet." in listed.output
    )


def test_a_rebuild_of_the_table_reproduces_it_exactly() -> None:
    """The same store at the same version produces the same rows, every time."""
    connection = _store()
    try:
        _split(connection, ALPHA, with_n=6, without_n=6, with_rework=0, without_rework=5)
        for repo_key, tag in ((ALPHA, "s"), (BETA, "t")):
            _split(
                connection,
                repo_key,
                fact="subagent_used",
                with_n=3,
                without_n=3,
                with_rework=0,
                without_rework=8,
                tag=tag,
            )
        observations.build(connection)
        before = _rows(connection)
        observations.build(connection)
        assert _rows(connection) == before
        assert before, "there is something to reproduce"
    finally:
        connection.close()
