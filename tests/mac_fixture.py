"""Builds the fixture store the desktop app's tests read. Not collected by the normal run.

The app's tests (Rust and JavaScript) decode real `app_*` rows rather than SQL retyped in
another language, which means they need a store the engine itself wrote. This file makes
one out of the same synthetic machine `conftest.py` gives every other test, adds a few
rows the small scenario cannot produce on its own (observations need five sessions a
side, a review needs a range), and vacuums the result into `apps/desktop/fixtures/` at
well under a megabyte.

The name has no `test_` prefix on purpose, so `pytest` does not collect it with the suite.
It is skipped unless `MAC_FIXTURE_TARGET` names where the store should land.

**Regenerating the fixture.** Run this from the repository root whenever
`store/app_views.APP_VIEWS` or `meta.APP_CONTRACT_VERSION` changes, and commit the `.db`
it writes with the app change that reads the new columns:

    MAC_FIXTURE_TARGET=apps/desktop/fixtures/store.db \\
        uv run pytest tests/mac_fixture.py -q

**What is in it, and why.** The app's tests are written against these shapes, and each of
them is deliberate here rather than incidental:

- **two projects** (`alpha` and `beta`, each with sessions, usage, a commit and an
  observation), so that choosing one in the picker can drop the other's rows;
- **three ISO weeks of usage**, one of them holding two days of the same bucket, so a
  chart of weekly bars has more than one bar and a week is one slice per bucket rather
  than one per day (contract 4: each session is one reply in `response`, in the bucket
  its old purpose maps to, plus a `talk` reply, so a session's mix has two shares);
- **three ISO weeks of outcomes for `alpha` where the middle one has `measured_30d = 0`**,
  so a survival line has a hole to leave open. The hole is drawn on purpose: real 30-day
  marks arrive in commit order, and no ordinary history has a measured week, then an
  unmeasured one, then another measured one. It is here because the chart has to be able
  to draw one;
- **a second review with no model segment**, so a review page can be read without one;
- **a newest review whose five sections all carry rows** (three purposes, the four
  survival marks with their rework row, two observations with their group sizes, a
  comparison whose previous survival cell is a dash, and one open suggestion), so a shot
  of the review screen shows every card filled and the charts have something to draw.

It also carries one commit credited to two sessions, which is the case where counting
commits per session and counting commits per day must disagree (`app_commits_by_day`
counts it once, `app_session_list` reports it against both sessions), and review numbers
carrying the `label` that `reviews/build.py` writes on every figure.

Nothing here is a real transcript, and every timestamp is fixed, so two runs of this file
produce the same rows.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest
from conftest import Workspace, record_one_session

from prudence.paths import database_file
from prudence.reviews import REVIEW_VERSION, schema
from prudence.reviews.build import Number, Section
from prudence.store import app_views, db, meta
from prudence.store import observations as observations_module

TARGET = os.environ.get("MAC_FIXTURE_TARGET")

BETA = "repo-beta"

# The three ISO weeks of usage. The two September 1 and 3 sessions share a purpose, a
# bucket and a week, so that week is one slice made of two days. The purpose label is still
# written, because `app_session_list.purpose` stays for one release beside the shares.
USAGE: tuple[tuple[str, str, str, str], ...] = (
    ("synthetic-w1a", "alpha", "2026-09-01T09:00:00", "development"),
    ("synthetic-w1b", "alpha", "2026-09-03T09:00:00", "development"),
    ("synthetic-w2a", "alpha", "2026-09-08T09:00:00", "research"),
    ("synthetic-b1", "beta", "2026-09-09T09:00:00", "development"),
    ("synthetic-b2", "beta", "2026-09-10T09:00:00", "debugging"),
    ("synthetic-a", "alpha", "2026-09-15T09:00:00", "development"),
    ("synthetic-b", "alpha", "2026-09-15T10:00:00", "research"),
    ("synthetic-c", "alpha", "2026-09-14T09:00:00", "debugging"),
)

# The bucket of each session's main reply, by the purpose the session was labelled with.
BUCKET_OF_PURPOSE = {"development": "change", "research": "read", "debugging": "run"}

# One commit per ISO week. `measured_30d` is the third field: 0 means the 30-day mark has
# not arrived for any of its lines, which is the hole the survival chart has to leave.
# (hash, project, committed at, lines, lines whose 30-day mark arrived, alive, reworked)
COMMITS: tuple[tuple[str, str, str, int, int, int, int], ...] = (
    ("aaaa111", "alpha", "2026-07-06T10:00:00", 120, 120, 96, 12),
    ("aaaa222", "alpha", "2026-07-13T10:00:00", 80, 0, 0, 7),
    ("aaaa333", "alpha", "2026-07-20T10:00:00", 140, 140, 98, 21),
    ("bbbb111", "beta", "2026-07-06T10:00:00", 60, 60, 51, 4),
)

# The one commit two sessions are credited with, which is what makes counting commits per
# day and summing them per session two different numbers.
SHARED_COMMIT = "aaaa333"
SHARED_SESSIONS = ("synthetic-a", "synthetic-b")

# The thresholds are written the way `observations._threshold` writes them, so the
# structured pair the view derives from `SPLITS` (contract 3) is the pair a real row
# would carry: `test_runs > 0`, `sittings >= 3`.
OBSERVATION_FIELDS = (
    "repo_key",
    "fact",
    "threshold_text",
    "outcome",
    "with_n",
    "without_n",
    "with_value",
    "without_value",
    "direction",
    "coverage",
    "fact_commits",
    "inferred_commits",
)

OBSERVATIONS: tuple[tuple, ...] = (
    ("alpha", "test_runs", "test_runs > 0", "rework", 7, 9, 0.12, 0.31, "lower", 0.86, 5, 2),
    ("alpha", "sittings", "sittings >= 3", "alive_head", 6, 11, 0.71, 0.54, "higher", 0.9, 4, 3),
    ("beta", "compactions", "compactions > 0", "rework", 5, 8, 0.19, 0.36, "lower", 0.81, 3, 2),
    ("*", "subagent_used", "subagent_used > 0", "rework", 8, 14, 0.22, 0.4, "lower", 0.77, 6, 5),
)

# The names the two observations in the stored review's own section are written under.
PROJECT_NAMES = {"alpha": "alpha", "beta": "beta"}

# The suggestion the older review left open, keyed to the first observation above, so the
# store holds an open row and the newest review's last section has something to show.
SUGGESTION_TEXT = "In alpha, your sessions that ran tests reworked less of their lines."


@pytest.mark.skipif(not TARGET, reason="set MAC_FIXTURE_TARGET to regenerate the fixture")
def test_make_fixture(lab: Workspace) -> None:
    record_one_session(lab)
    connection = db.connect()
    try:
        keys = {"alpha": lab.repo_key(), "beta": BETA}
        _repository(connection, BETA, "beta")
        for session_id, project, first_at, purpose in USAGE:
            _usage_session(connection, session_id, keys[project], first_at, purpose)
        for commit_hash, project, at, lines, measured, alive, reworked in COMMITS:
            _commit(connection, commit_hash, keys[project], at, lines, measured, alive, reworked)
        # Every commit is credited to the session that shares its project; one of them is
        # credited to two, which is the disagreement `app_commits_by_day` has to survive.
        _attribute(connection, "aaaa111", "synthetic-w1a", 0.91)
        _attribute(connection, "aaaa222", "synthetic-w2a", 0.88)
        for session_id in SHARED_SESSIONS:
            _attribute(connection, SHARED_COMMIT, session_id, 0.93)
        _attribute(connection, "bbbb111", "synthetic-b1", 0.79)
        for row in OBSERVATIONS:
            connection.execute(
                "INSERT OR REPLACE INTO observation (repo_key, fact, threshold_text, outcome,"
                " with_n, without_n, with_value, without_value, direction, coverage,"
                " fact_commits, inferred_commits, fact_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (keys.get(row[0], row[0]), *row[1:]),
            )

        # The older review is the one with no segment, and it is written first so that it
        # is not the newest: `latestReview()` is what the review screen opens on, and a
        # test there reads the segment of whatever that returns.
        without_segment = schema.insert_review(
            connection,
            created_at="2026-09-08T18:00:00",
            range_start="2026-09-01T00:00:00",
            range_end="2026-09-08T00:00:00",
            project=keys["alpha"],
            outcome_range_start="2026-08-25T00:00:00",
            outcome_range_end="2026-09-01T00:00:00",
            sections=_sections(),
            coverage=0.91,
            fact_version=1,
            parser_version=2,
        )
        latest = schema.insert_review(
            connection,
            created_at="2026-09-15T18:00:00",
            range_start="2026-09-08T00:00:00",
            range_end="2026-09-15T00:00:00",
            project=None,
            outcome_range_start="2026-09-01T00:00:00",
            outcome_range_end="2026-09-08T00:00:00",
            sections=_sections(),
            coverage=0.82,
            fact_version=1,
            parser_version=2,
        )
        schema.store_segment(
            connection,
            latest,
            text=(
                "Two development sessions in the range, and 5k tokens across them. "
                "Nothing here has reached its seven-day mark yet, so what became of the "
                "lines is not in the record."
            ),
            prompt_version=1,
            model="recorded-haiku",
            input_hash="0" * 16,
            numbers=[{"key": "did.sessions.development", "text": "2"}],
            created_at="2026-09-15T18:01:00",
            language="en",
        )
        schema.insert_suggestion(
            connection,
            review_id=without_segment,
            observation_key=f"{keys['alpha']}|test_runs|rework",
            text=SUGGESTION_TEXT,
            created_at="2026-09-08T18:00:01",
        )
        app_views.install_app_views(connection)
        connection.commit()

        # The fixture is only worth having if it is what the app will read. Contract and
        # column lists first, then the shapes the app's tests need.
        assert meta.get_meta(connection, meta.APP_CONTRACT_VERSION_KEY) == "5"
        for name, columns in app_views.APP_VIEWS.items():
            assert app_views.columns(connection, name) == columns, name

        review = connection.execute("SELECT * FROM app_review WHERE id = ?", (latest,)).fetchone()
        assert review["headline"].startswith("Review "), review["headline"]
        assert review["segment_model"] == "recorded-haiku"
        assert review["segment_language"] == "en", "contract 3: the segment says its language"
        # The newest review has a segment (the screen opens on it) and exactly one older
        # one has none.
        assert _count(connection, "SELECT MAX(id) FROM review") == latest
        assert _count(connection, "SELECT COUNT(*) FROM review WHERE segment_text IS NULL") == 1
        assert schema.review_by_id(connection, without_segment)["segment_text"] is None
        labels = [
            row["label"]
            for row in connection.execute(
                "SELECT json_extract(value, '$.label') AS label FROM app_review,"
                " json_each(app_review.numbers) WHERE app_review.id = ?",
                (latest,),
            )
        ]
        assert labels and all(labels), labels

        # Five sections with rows in all of them, and the keys the charts read off them.
        sections = json.loads(review["sections"])
        assert [section["key"] for section in sections] == [
            "did",
            "became",
            "observations",
            "compared",
            "suggestions",
        ]
        assert all(section["rows"] for section in sections), "every card has something in it"
        numbers = {number["key"]: number for number in json.loads(review["numbers"])}
        paired = [number for key, number in numbers.items() if key.startswith("observation.")]
        assert len(paired) == 4 and all(
            number["with_n"] and number["without_n"] for number in paired
        )
        assert numbers["compared.sessions.now"]["previous_value"] == 5
        dashed = numbers["compared.alive_at_7_days.previous"]
        assert dashed["text"] == "-" and dashed["value"] is None, "a dash carries no number"

        observations = list(connection.execute("SELECT * FROM app_observation"))
        assert len(observations) == len(OBSERVATIONS)
        assert all(row["sentence"] for row in observations)
        # Contract 3: every fixture observation is a numeric split, so all four carry both.
        assert all(row["threshold_op"] in (">", ">=") for row in observations), observations
        assert all(row["threshold_value"] is not None for row in observations)
        assert _count(connection, "SELECT COUNT(DISTINCT project) FROM app_session_list") >= 2
        assert _count(connection, WEEKS_OF_USAGE) >= 3
        assert _count(connection, WEEK_WITH_TWO_DAYS) >= 1
        assert _count(connection, GAP_IN_THE_SERIES) >= 1
        assert _count(connection, "SELECT COUNT(*) FROM app_commits_by_day") >= 1
        assert _count(connection, "SELECT SUM(edits) FROM app_session_list") >= 1
        # Contract 4: all four buckets have tokens somewhere, and a session's shares add up.
        assert _count(connection, "SELECT COUNT(DISTINCT bucket) FROM app_usage_by_bucket_day") == 4
        assert _count(connection, "SELECT COUNT(*) FROM app_session_list WHERE change_share > 0")
        assert _count(connection, UNBALANCED_SHARES) == 0
        # One commit, two sessions: the per-day count and the per-session sum disagree,
        # and a test in the app can only see that if they do.
        per_day = _count(connection, "SELECT SUM(commits) FROM app_commits_by_day")
        per_session = _count(
            connection, "SELECT SUM(commits_fact + commits_inferred) FROM app_session_list"
        )
        assert per_session == per_day + 1, (per_session, per_day)
    finally:
        connection.close()

    target = Path(TARGET)
    target.parent.mkdir(parents=True, exist_ok=True)
    # `VACUUM INTO` refuses to write a file that is already there, and regenerating means
    # writing over the one that is. Removing it first is the whole of the fix; without it
    # the second run of this file fails on the store it is meant to replace.
    target.unlink(missing_ok=True)
    source = sqlite3.connect(database_file())
    try:
        source.execute("VACUUM INTO ?", (str(target),))
    finally:
        source.close()
    shutil.rmtree(target.parent / "__pycache__", ignore_errors=True)
    size = target.stat().st_size
    assert size < 1_000_000, size
    print(f"\n{target} is {size / 1024:.0f} KB")


# The three questions the app's tests ask of the fixture before they agree to run, asked
# here too, so a regeneration that lost one of them fails at the source rather than
# silently switching a test off again.
WEEKS_OF_USAGE = """
    SELECT COUNT(*) FROM (
        SELECT DISTINCT date(day, '-' || ((strftime('%w', day) + 6) % 7) || ' days') AS week
          FROM app_usage_by_bucket_day WHERE COALESCE(total_tokens, 0) > 0
    )
"""

WEEK_WITH_TWO_DAYS = """
    SELECT COUNT(*) FROM (
        SELECT date(day, '-' || ((strftime('%w', day) + 6) % 7) || ' days') AS week, bucket
          FROM app_usage_by_bucket_day WHERE COALESCE(total_tokens, 0) > 0
         GROUP BY week, bucket HAVING COUNT(DISTINCT day) >= 2
    )
"""

UNBALANCED_SHARES = """
    SELECT COUNT(*) FROM app_session_list
     WHERE change_share IS NOT NULL
       AND abs(change_share + run_share + read_share + talk_share - 1) > 1e-9
"""

GAP_IN_THE_SERIES = """
    SELECT COUNT(*) FROM app_outcomes_by_week a
     WHERE COALESCE(a.measured_30d, 0) > 0
       AND EXISTS (SELECT 1 FROM app_outcomes_by_week b
                    WHERE b.project = a.project AND b.week_start > a.week_start
                      AND COALESCE(b.measured_30d, 0) = 0)
       AND EXISTS (SELECT 1 FROM app_outcomes_by_week c
                    WHERE c.project = a.project AND c.week_start > a.week_start
                      AND COALESCE(c.measured_30d, 0) > 0)
"""


def _count(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0] or 0)


def _sections() -> dict:
    """A stored review payload whose sections are the shape `reviews/build.py` writes.

    Built out of `build.Section` and `build.Number` rather than typed as literals, so a
    field added to either record appears here too instead of being missed by a fixture
    nobody re-read. All five sections carry rows, because the review screen lays one card
    out per section and a shot of it is only worth judging when every card has something
    in it.
    """
    sections = [_did(), _became(), _observed(), _compared(), _suggested()]
    numbers = [number for section in sections for number in section.numbers]
    return {
        "review_version": REVIEW_VERSION,
        "project_name": None,
        "sections": [asdict(section) for section in sections],
        "numbers": [asdict(number) for number in numbers],
    }


def _did() -> Section:
    """Three purposes and their total, the way `usage` sums a range."""
    section = Section(key="did", title="What you did")
    section.headers = ["purpose", "sessions", "tokens", "active h"]
    cells = (("development", 4, "18k", 18320.0, "3.2"), ("research", 2, "5k", 5080.0, "1.4"))
    for label, count, tokens, raw, hours in (*cells, ("debugging", 1, "2k", 2040.0, "0.6")):
        section.rows.append([label, str(count), tokens, hours])
        section.numbers += [
            Number(f"did.sessions.{label}", f"sessions labelled {label}", str(count), float(count)),
            Number(f"did.tokens.{label}", f"tokens in {label} sessions", tokens, raw),
            Number(f"did.hours.{label}", f"active hours in {label} sessions", hours, float(hours)),
        ]
    section.rows.append(["all purposes", "7", "25k", "5.2"])
    section.numbers += [
        Number("did.sessions", "sessions in the range", "7", 7.0),
        Number("did.tokens", "tokens in the range", "25k", 25440.0),
        Number("did.hours", "active hours in the range", "5.2", 5.2),
        Number("did.commits", "commits credited to those sessions", "6", 6.0),
        Number("did.coverage", "mean coverage of those commits", "91%", 0.91, 0.91),
    ]
    section.notes = [
        "7 sessions, 6 commits credited to them at fact or inferred confidence, mean coverage 91%.",
        "The purpose label comes from rules over the tool mix; no message text is read.",
    ]
    return section


def _became() -> Section:
    """The survival figures, each with the coverage it is over, as `outcomes` prints them."""
    section = Section(key="became", title="What became of earlier work")
    section.headers = ["figure", "value", "coverage", "method"]
    coverage, method = "88%", "5 fact, 2 inferred"
    figures = (
        ("lines followed", "400", 400.0),
        ("alive at 7 days", "82% (400)", 0.82),
        ("alive at 30 days", "74% (260)", 0.74),
        ("alive at 90 days", "68% (120)", 0.68),
        ("alive at head", "61% (400)", 0.61),
        ("reworked by you later", "11% (400)", 0.11),
    )
    for label, text, value in figures:
        section.rows.append([label, text, coverage, method])
        section.numbers.append(
            Number(f"became.{label.replace(' ', '_')}", label, text, value, 0.88)
        )
    section.numbers.append(Number("became.commits", "commits in the outcome window", "7", 7.0))
    section.numbers.append(
        Number("became.coverage", "mean coverage of those commits", coverage, 0.88, 0.88)
    )
    section.notes = [
        "7 commits, 5 fact, 2 inferred. Coverage is the mean share of a counted commit's "
        "added lines the session itself wrote.",
        "A mark still in the future is a dash, not a death.",
    ]
    return section


def _observed() -> Section:
    """Two observations, in the engine's own words, with the two group sizes on each."""
    section = Section(key="observations", title="Observations")
    section.headers = ["what your own sessions did", "coverage and method"]
    for entry in OBSERVATIONS[:2]:
        row = dict(zip(OBSERVATION_FIELDS, entry, strict=True))
        section.rows.append(
            [
                observations_module.sentence(row, PROJECT_NAMES[row["repo_key"]]),
                observations_module.caveat(row),
            ]
        )
        key = f"{row['repo_key']}|{row['fact']}|{row['outcome']}"
        for side in ("with", "without"):
            section.numbers.append(
                Number(
                    f"observation.{key}.{side}",
                    f"{row['fact']} {row['outcome']} on the side that did"
                    + ("" if side == "with" else " not"),
                    f"{row[f'{side}_value'] * 100:.0f}%",
                    row[f"{side}_value"],
                    row["coverage"],
                    with_n=row["with_n"],
                    without_n=row["without_n"],
                )
            )
    section.notes = [
        "2 observations, 0 of them pooled over every project.",
        "These are descriptions, not advice.",
    ]
    return section


def _compared() -> Section:
    """This period against the one before it, with one cell the record cannot fill.

    The previous period has no commit whose lines could be followed, so its survival cell
    and the change beside it are dashes with no number under them: the one place in the
    fixture where a chart has to draw an absence rather than a zero (rule 10).
    """
    section = Section(key="compared", title="Compared with the previous period")
    section.headers = ["figure", "this period", "previous period", "change"]
    rows = (
        ("sessions", "7", "5", "+2", 7, 5, 2),
        ("active hours", "5.2", "4.4", "+0.8", 5.2, 4.4, 0.8),
        ("tokens", "25k", "19k", "+6k", 25440.0, 19120.0, 6.0),
        ("rework share", "11%", "18%", "-7 points", 0.11, 0.18, -7),
        ("alive at 7 days", "82%", "-", "-", 0.82, None, None),
    )
    for label, now, previous, change, now_value, previous_value, change_value in rows:
        section.rows.append([label, now, previous, change])
        key = label.replace(" ", "_")
        section.numbers += [
            Number(
                f"compared.{key}.now",
                f"{label}, this period",
                now,
                now_value,
                previous_value=previous_value,
            ),
            Number(
                f"compared.{key}.previous", f"{label}, previous period", previous, previous_value
            ),
            Number(f"compared.{key}.change", f"{label}, change", change, change_value),
        ]
    section.notes = [
        "The previous period of the same length: 2026-09-01 to 2026-09-08 (7 days).",
        "One of the two periods has no commit with followed lines, so its outcome cells "
        "are dashes rather than zeroes.",
    ]
    return section


def _suggested() -> Section:
    """The one suggestion an earlier review left open, and what has become of it."""
    section = Section(key="suggestions", title="Last time's suggestions")
    section.headers = ["suggestion", "then", "since", "sessions"]
    section.rows.append([f"#1 {SUGGESTION_TEXT}", "31%", "12%", "9 then, 7 since"])
    section.numbers += [
        Number("suggestion.1.before", "suggestion 1: the outcome before", "31%", 0.31),
        Number("suggestion.1.since", "suggestion 1: the outcome since", "12%", 0.12),
    ]
    section.notes = [
        "Then is the sessions that started before this review's range, since is the ones "
        "inside it.",
        "Dismiss one with `prudence suggestions dismiss <id>`; it is not raised again.",
    ]
    return section


def _repository(connection: sqlite3.Connection, repo_key: str, name: str) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO repository (repo_key, name, toplevel, outcomes_suppressed,"
        " fact_version) VALUES (?, ?, ?, 0, 1)",
        (repo_key, name, f"/tmp/{name}"),
    )


def _usage_session(
    connection: sqlite3.Connection, session_id: str, repo_key: str, first_at: str, purpose: str
) -> None:
    connection.execute(
        "INSERT INTO session (session_id, repo_key, source, entrypoint, cwd, first_at,"
        " last_at, record_count, capture_level, parser_version, notes)"
        " VALUES (?, ?, 'claude_code', 'cli', NULL, ?, ?, 1, 'full', 2, NULL)",
        (session_id, repo_key, first_at, first_at),
    )
    tokens = {"development": (4000, 900, 120, 60), "research": (700, 150, 20, 5)}.get(
        purpose, (200, 40, 0, 0)
    )
    replies = (
        (f"{session_id}-r1", first_at, BUCKET_OF_PURPOSE[purpose], tokens),
        (f"{session_id}-r2", first_at[:-2] + "30", "talk", (50, 20, 0, 0)),
    )
    for reply_id, at, bucket, counts in replies:
        connection.execute(
            "INSERT INTO usage (record_id, session_id, turn_id, request_id, model,"
            " input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,"
            " parser_version) VALUES (?, ?, NULL, ?, 'claude-x', ?, ?, ?, ?, 6)",
            (f"{reply_id}-record", session_id, f"{reply_id}-req", *counts),
        )
        connection.execute(
            "INSERT INTO response (response_id, session_id, turn_id, agent_id, started_at,"
            " bucket, bucket_rule_version, heuristic, input_tokens, output_tokens,"
            " cache_read_tokens, cache_creation_tokens, parser_version)"
            " VALUES (?, ?, NULL, NULL, ?, ?, 1, 0, ?, ?, ?, ?, 6)",
            (reply_id, session_id, at, bucket, *counts),
        )
    connection.execute(
        "INSERT INTO session_label (session_id, name, label, rule_version)"
        " VALUES (?, 'purpose', ?, 1)",
        (session_id, purpose),
    )


def _commit(
    connection: sqlite3.Connection,
    commit_hash: str,
    repo_key: str,
    at: str,
    lines: int,
    measured_30d: int,
    alive_30d: int,
    reworked: int,
) -> None:
    """One commit and the fate of every line it added, written the way `outcomes` writes it.

    `alive_30d` is NULL on the lines whose 30-day mark has not arrived, never 0: an
    unmeasured mark is not a dead line (architecture rule 10), and the difference is the
    whole of what the survival chart's hole is about.
    """
    connection.execute(
        'INSERT OR REPLACE INTO "commit" (commit_hash, repo_key, committer_at, author_at,'
        " added_lines, files_changed, is_merge, is_bot, fact_version)"
        " VALUES (?, ?, ?, ?, ?, 1, 0, 0, 2)",
        (commit_hash, repo_key, at, at, lines),
    )
    connection.executemany(
        "INSERT OR REPLACE INTO line_fate (commit_hash, path, line_hash, alive_7d, alive_30d,"
        " alive_90d, alive_head, alive_head_anywhere, blame_head, reworked_by, fact_version)"
        " VALUES (?, 'src/app.py', ?, ?, ?, NULL, ?, ?, ?, ?, 2)",
        [
            (
                commit_hash,
                f"{commit_hash}-{index}",
                1 if index < alive_30d else 0,
                (1 if index < alive_30d else 0) if index < measured_30d else None,
                1 if index < alive_30d else 0,
                1 if index < alive_30d else 0,
                1 if index < alive_30d else 0,
                "later" if index < reworked else None,
            )
            for index in range(lines)
        ],
    )


def _attribute(
    connection: sqlite3.Connection, commit_hash: str, session_id: str, coverage: float
) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO attribution (commit_hash, session_id, method, rank,"
        " lines_matched, coverage, confidence, fact_version)"
        " VALUES (?, ?, 'in_session', 1, 10, ?, 'fact', 3)",
        (commit_hash, session_id, coverage),
    )
