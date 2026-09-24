"""The `app_*` views: the one contract every surface that is not the CLI reads.

The Mac app owns no numbers (M3 rule 8). It reads these five views and the stored rows
behind them, and nothing else; a screen that needs a figure the engine does not compute
gets a new view here rather than a join in Swift. `meta.app_contract_version` is the
version of the column lists below and changes only when one of them changes.

Real SQL views rather than tables, for two reasons. A view is always in step with the
tables under it, so no step can forget to refresh it; and a view costs nothing to store
beside a 700 MB archive. They are dropped and recreated at the end of every `ingest` and
`rebuild` (`pipeline.run` calls `replace_app_views` once, after the last step that
derives anything), because `derived.build` swaps its tables by renaming, and a view over
a renamed table would be left pointing at nothing. The drop and the recreation are one
transaction, so an ingest that fails leaves the contract it found rather than none.

Every view is written from the same tables and the same rules as the matching function
in `store/views/`, so the app and the CLI cannot disagree:

- `app_usage_by_bucket_day` (contract 4) sums the `response` table: each reply's four
  token counts, on the day the reply began, under the bucket `store/buckets.py` gave it
  and the project of its session, exactly as `views.bucket_usage` sums them for
  `cli/usage.py`. `heuristic_tokens` is the part of a row whose bucket rests on the name
  heuristic, and `sessions` counts the sessions with at least one reply in the row. A
  reply with no bucket (a record the adapter could not read) is in no row; its tokens
  are `app_status.coverage_gap_tokens`. The one deliberate difference from the CLI: the
  day is the local day (`date(..., 'localtime')`), because a person reading a chart of
  their own week means their own midnight, while `cli/usage.py` takes the stored UTC
  timestamp. Only the day a reply falls on can differ, never a total. It replaced
  `app_usage_by_purpose_day`, which put a whole session's tokens under one word chosen
  by thresholds (`RETIRED_VIEWS`).
- `app_outcomes_by_week` counts a commit once, at its best confidence label, over the
  commits `views.counted_pairs` would count (`fact` and `inferred` only), and sums
  `line_fate` the way `views.outcomes_by_repository` sums it. The week begins on the
  local Monday, the same deliberate difference from the CLI the day views make and for
  the same reason: a person reading a chart of their own weeks means their own midnight.
  A commit made late on a Sunday evening in UTC therefore lands in the week its author
  was living in, not the week before. Only the bucket can differ, never a total.
  A repository whose
  outcomes are suppressed by the multi-author guard has no rows here at all, because
  `outcomes.build` writes it no `line_fate` rows in the first place; the reason stays on
  `repository.outcomes_suppressed_note`.
- `app_session_list` counts commits per session the way `views.credited_map` does: one
  commit once, at its best label, `uncertain` reported and never folded into the other
  two. A session whose records carried no usage fields has `total_tokens` NULL, not 0
  (architecture rule 10). Contract 4 added the four bucket shares, each the share of the
  session's bucketed tokens, NULL when the session has no reply with tokens. `purpose`
  stays for this release beside them, for comparison, and goes in the next.
- `app_commits_by_day` counts a commit once, on the local day it was committed, at its
  best confidence label, over exactly the commits `views.credited_by_commit` returns
  (`fact` and `inferred`; a commit whose only attribution is `uncertain` is not counted
  at all). Merges are excluded, because a merge adds no lines of its own and would
  double a day's count. A test asserts a day's totals against `credited_by_commit`.
- `app_observation` is the `observation` table with its project name, a `pooled` flag and
  the very sentence `prudence observations` prints. The sentence is prose built by
  `store/observations.sentence`, which is Python, so it cannot be a SQL expression: it is
  materialised into `app_observation_text` by `install_app_views` and joined here. The
  `observation` table is `WITHOUT ROWID` and has no row id of its own, so
  `observation_id` is the row's position in `views.observations`'s own fixed order, given
  once by `ROW_NUMBER()` in the view and by `enumerate` in the fill, over the same
  ORDER BY. A test checks every row's sentence against the CLI's. Contract 3 added
  `threshold_value` and `threshold_op`, the same split as a number and one of `>=`, `>`
  or `==`, taken from `observations.SPLITS` in the same fill and for the same reason.
- `app_review` is one row per stored review, newest first, with the headline a dropdown
  shows and the two JSON blocks (`sections` and `numbers`) a review screen renders. The
  review tables are not derived from the archive and a store may not have them yet, so
  `prepare_sources` calls `reviews.schema.ensure` before the view is defined; that is the
  simpler of the two options in the task and it also brings the segment columns along.

Nothing here returns message text, because none is stored.

Measured after a full `prudence ingest` on a copy of the founder's store (740 MB, 148
sessions, 227,399 records, 2,054 attributions, 82,680 line fates), best of three warm,
`COUNT(*)` then a full `SELECT *`:

    app_status                    0 ms /  1 ms
    app_usage_by_purpose_day     10 ms / 10 ms   (retired at contract 4)
    app_outcomes_by_week         24 ms / 24 ms
    app_observation               0 ms /  0 ms
    app_session_list             12 ms / 13 ms

and, at contract 2 on the same store after another day's work (720 MB, 148 sessions,
229,325 records, 90,785 followed lines), measured through the `sqlite3` binary so each
figure carries about 5 ms of process start with it:

    app_commits_by_day           10 ms / 11 ms
    app_observation                    /  7 ms
    app_review                         /  7 ms
    app_session_list                   / 23 ms   (12 ms at contract 1, plus `edits`)

`install_app_views` itself takes about 290 ms on that store, almost all of it the one
pass over `record` that fills `app_session_time`. Written as plain views, the two that
need the sitting rule cost 230 ms each per query instead, which is why that one
aggregate is materialised and the index below exists.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from prudence import __version__
from prudence.facts import purpose as purpose_module
from prudence.store import attribution as attribution_module
from prudence.store import buckets as buckets_module
from prudence.store import commits as commits_module
from prudence.store import derived as derived_module
from prudence.store import meta as meta_module
from prudence.store import observations as observations_module
from prudence.store import outcomes as outcomes_module
from prudence.store import progress as progress_module
from prudence.store import spool as spool_module
from prudence.store import tokens
from prudence.store.views.usage import TOKEN_COLUMNS

# The contract. These lists are what the app compiles against and what the tests assert;
# a view's SELECT may be rewritten freely as long as it still answers with these columns,
# and changing one of them is what bumps `meta.APP_CONTRACT_VERSION`.
APP_VIEWS: dict[str, tuple[str, ...]] = {
    "app_status": (
        "engine_version",
        "last_ingest_at",
        "sessions",
        "projects",
        "app_contract_version",
        "parser_version",
        "purpose_rule_version",
        "commit_fact_version",
        "attribution_fact_version",
        "outcome_fact_version",
        "observation_fact_version",
        "hook_fact_version",
        # Contract 4: which rule gave the replies their buckets, and how many tokens sit
        # in replies no bucket could be given.
        "bucket_rule_version",
        "coverage_gap_tokens",
    ),
    "app_usage_by_bucket_day": (
        "day",
        "repo_key",
        "project",
        "bucket",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "total_tokens",
        "responses",
        "heuristic_tokens",
        "sessions",
    ),
    # Active time is a property of a session, not of a response, so it keeps a view of
    # its own: the hours figure and the heat strip read this, the token charts the one above.
    "app_activity_by_day": (
        "day",
        "repo_key",
        "project",
        "active_minutes",
        "sessions",
        "measured_sessions",
    ),
    "app_outcomes_by_week": (
        "repo_key",
        "project",
        "week_start",
        "commits",
        "commits_fact",
        "commits_inferred",
        "lines",
        "measured_7d",
        "alive_7d",
        "measured_30d",
        "alive_30d",
        "measured_90d",
        "alive_90d",
        "alive_head",
        "alive_head_anywhere",
        "blame_head",
        "reworked",
        "coverage",
    ),
    "app_commits_by_day": (
        "day",
        "repo_key",
        "project",
        "commits",
        "commits_fact",
        "commits_inferred",
    ),
    "app_observation": (
        "repo_key",
        "project",
        "pooled",
        "fact",
        "threshold_text",
        "outcome",
        "direction",
        "with_n",
        "without_n",
        "with_value",
        "without_value",
        "coverage",
        "fact_commits",
        "inferred_commits",
        "fact_version",
        # Contract 2. Appended rather than inserted, so that a surface reading the
        # earlier columns by position is not moved out from under by the bump.
        "observation_id",
        "sentence",
        # Contract 3: the same split as a number and an operator, for a chart that draws
        # the line. `threshold_text` is unchanged and stays the thing a person reads.
        "threshold_value",
        "threshold_op",
    ),
    "app_session_sources": ("session_id", "source_id", "kind", "label", "home"),
    "app_session_list": (
        "session_id",
        "repo_key",
        "project",
        "started_at",
        "ended_at",
        "purpose",
        "total_tokens",
        "commits_fact",
        "commits_inferred",
        "commits_uncertain",
        "coverage",
        "sittings",
        "capture_level",
        "content_archived",
        # Contract 2, appended for the same reason.
        "edits",
        # Contract 4: the share of the session's tokens in each bucket, 0 to 1.
        "change_share",
        "run_share",
        "read_share",
        "talk_share",
        "source",
        "source_ids",
        "source_labels",
        "models",
    ),
    "app_review": (
        "id",
        "created_at",
        "range_start",
        "range_end",
        "outcome_range_start",
        "outcome_range_end",
        "repo_key",
        "project",
        "headline",
        "sections",
        "numbers",
        "coverage",
        "segment_text",
        "segment_model",
        "segment_created_at",
        # Contract 3, appended for the same reason: the language the segment was asked
        # for. NULL on a row written before there was a choice, which reads as English.
        "segment_language",
    ),
}

# Views an earlier contract had and this one does not. Dropped with the rest, so a store
# upgraded in place does not keep answering a question no engine maintains any more.
RETIRED_VIEWS: tuple[str, ...] = ("app_usage_by_purpose_day",)

# Indexes these views need beyond the ones `derived.INDEXES` already creates. Recreated
# after every rebuild, because a rebuild swaps the table this one sits on. The sitting
# rule reads every record of a session in time order, and `derived`'s `record_session`
# stops at the session: without the timestamp in the index SQLite sorts 226,558 rows for
# each of the two views that use it, which is the whole of their cost.
INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS record_session_time ON record(session_id, timestamp)",
)

# The sitting rule, in SQL. `views.SITTING_GAP` is 60 minutes: a gap longer than that is
# a break, so it is neither active time nor part of the sitting before it.
SITTING_GAP_SECONDS = 3600

# The one thing here that is a table rather than a view, and the reason is measurement:
# the sitting rule reads every record in time order, which costs about 230 ms over the
# founder's 226,558 records and is paid again by each of the two views that need it. One
# row per session (148 of them) is filled once at the end of `ingest` instead, and both
# views join it. It is not part of the contract; `APP_VIEWS` is.
SESSION_TIME_TABLE = "app_session_time"

_SESSION_TIME_SCHEMA = f"""
    CREATE TABLE {SESSION_TIME_TABLE}(
        session_id TEXT PRIMARY KEY,
        active_seconds REAL NOT NULL,
        sittings INTEGER NOT NULL
    )
"""

# The gap between each record and the one before it, per session. Both the active-time
# sum and the sitting count are one aggregate over this.
_GAPS = """
        SELECT session_id,
               (julianday(timestamp) - julianday(
                    LAG(timestamp) OVER (PARTITION BY session_id ORDER BY timestamp)
               )) * 86400.0 AS gap
        FROM record
        WHERE timestamp IS NOT NULL
"""

# The second materialised table, and for the opposite reason: not because the SQL is slow
# but because there is no SQL. An observation's sentence is built by
# `store/observations.sentence`, in Python, from the same row the view already carries;
# retyping it as a string expression would be a second implementation of one sentence and
# two chances to word it differently. It is refilled with the views, from at most a few
# hundred rows, and costs about a millisecond. Not part of the contract; `APP_VIEWS` is.
#
# Contract 3 put the structured threshold here too, for the same reason: it is read off
# `observations.SPLITS`, which is Python, and an `above_median` row's number is parsed
# back out of the very text that module wrote.
OBSERVATION_TEXT_TABLE = "app_observation_text"

_OBSERVATION_TEXT_SCHEMA = f"""
    CREATE TABLE {OBSERVATION_TEXT_TABLE}(
        observation_id INTEGER PRIMARY KEY,
        sentence TEXT NOT NULL,
        threshold_value REAL,
        threshold_op TEXT
    )
"""

# The order `views.observations` returns its rows in, written once and used twice: by the
# fill, which numbers the rows, and by the view, whose ROW_NUMBER() has to agree with it.
_OBSERVATION_ORDER = (
    f"CASE WHEN o.repo_key = '{observations_module.POOLED}' THEN 1 ELSE 0 END,"
    " o.repo_key, o.fact, o.outcome"
)

_SESSION_TIME_FILL = f"""
    INSERT INTO {SESSION_TIME_TABLE}(session_id, active_seconds, sittings)
    SELECT session_id,
           SUM(CASE WHEN gap <= {SITTING_GAP_SECONDS} THEN gap ELSE 0 END),
           1 + SUM(CASE WHEN gap > {SITTING_GAP_SECONDS} THEN 1 ELSE 0 END)
    FROM ({_GAPS.strip()}) GROUP BY session_id
"""

# One commit's best confidence label and the coverage on that row, per session. The same
# rule as `views.credited_map`: a session that both ran `git commit` and wrote the lines
# is credited with one commit, at the better of the two labels.
_BEST_PER_SESSION = f"""
        SELECT session_id, commit_hash, confidence, coverage FROM (
            SELECT session_id, commit_hash, confidence, coverage,
                   ROW_NUMBER() OVER (
                       PARTITION BY session_id, commit_hash
                       ORDER BY CASE confidence
                           WHEN '{attribution_module.FACT}' THEN 0
                           WHEN '{attribution_module.INFERRED}' THEN 1
                           ELSE 2 END
                   ) AS rn
            FROM attribution
        ) WHERE rn = 1
"""

# The same, ignoring which session is credited: what `views.credited_by_commit` returns.
_BEST_PER_COMMIT = f"""
        SELECT commit_hash, confidence, coverage FROM (
            SELECT commit_hash, confidence, coverage,
                   ROW_NUMBER() OVER (
                       PARTITION BY commit_hash
                       ORDER BY CASE confidence
                           WHEN '{attribution_module.FACT}' THEN 0
                           WHEN '{attribution_module.INFERRED}' THEN 1
                           ELSE 2 END
                   ) AS rn
            FROM attribution
        ) WHERE rn = 1 AND confidence IN
            ('{attribution_module.FACT}', '{attribution_module.INFERRED}')
"""

# What became of one commit's added lines. `measured_*` are the denominators: a mark
# still in the future is NULL in `line_fate` and belongs in neither numerator.
_FATE_PER_COMMIT = """
        SELECT commit_hash, COUNT(*) AS lines,
               SUM(CASE WHEN alive_7d IS NOT NULL THEN 1 ELSE 0 END) AS measured_7d,
               SUM(COALESCE(alive_7d, 0)) AS alive_7d,
               SUM(CASE WHEN alive_30d IS NOT NULL THEN 1 ELSE 0 END) AS measured_30d,
               SUM(COALESCE(alive_30d, 0)) AS alive_30d,
               SUM(CASE WHEN alive_90d IS NOT NULL THEN 1 ELSE 0 END) AS measured_90d,
               SUM(COALESCE(alive_90d, 0)) AS alive_90d,
               SUM(COALESCE(alive_head, 0)) AS alive_head,
               SUM(COALESCE(alive_head_anywhere, 0)) AS alive_head_anywhere,
               SUM(COALESCE(blame_head, 0)) AS blame_head,
               SUM(CASE WHEN reworked_by IS NOT NULL THEN 1 ELSE 0 END) AS reworked
        FROM line_fate GROUP BY commit_hash
"""


SESSION_SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_source(
    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    home TEXT,
    PRIMARY KEY(session_id, source_id)
)
"""


def fill_session_sources(connection: sqlite3.Connection) -> None:
    connection.execute(
        "DELETE FROM session_source WHERE session_id NOT IN (SELECT session_id FROM session)"
    )
    connection.execute("""
        INSERT OR REPLACE INTO session_source
        SELECT DISTINCT s.session_id, o.source_id, s.source,
               COALESCE(c.label, o.source_id), c.home
        FROM session s
        JOIN archive_file a ON a.session_id = s.session_id AND a.agent_kind = s.source
        JOIN archive_origin o ON o.path = a.path
        LEFT JOIN collection_source c ON c.id = o.source_id
    """)


def replace_app_views(
    connection: sqlite3.Connection, progress: progress_module.Step | None = None
) -> None:
    """Swap the whole contract in one transaction: the new one, or the one already there.

    `pipeline.run` calls this once, after every step that writes a table. Taking the old
    views down and putting the new ones up is a single transaction because a store with
    half a contract is a store no surface can render, and an ingest can be interrupted
    at any moment.
    """
    prepare_sources(connection)
    connection.execute("BEGIN IMMEDIATE")
    try:
        drop_app_views(connection)
        _install(connection, progress)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def drop_app_views(connection: sqlite3.Connection) -> None:
    """Take the contract down, for the moment before it goes back up."""
    for name in (*APP_VIEWS, *RETIRED_VIEWS):
        _quietly(connection, f"DROP VIEW IF EXISTS {name}")


def install_app_views(
    connection: sqlite3.Connection, progress: progress_module.Step | None = None
) -> None:
    """Recreate every `app_*` view, for a caller that is not the pipeline."""
    prepare_sources(connection)
    _install(connection, progress)


def prepare_sources(connection: sqlite3.Connection) -> None:
    """Create the one table a view names that no pipeline step writes.

    `app_review` names the `review` table, and a store that has never had a review
    written has no such table. Creating it here rather than leaving the view broken is
    the simpler of the two options: `ensure` is idempotent, it also adds the segment
    columns an older store is missing, and it is the same call `prudence review` makes.

    It happens outside the transaction that replaces the views, because `ensure` runs a
    script and `sqlite3` commits whatever transaction it finds open before a script. The
    table is not part of the contract, so ensuring it early costs nothing.
    """
    from prudence.reviews import schema as review_schema

    _quietly_call(lambda: review_schema.ensure(connection))
    connection.execute(SESSION_SOURCE_SCHEMA)


def _install(connection: sqlite3.Connection, progress: progress_module.Step | None = None) -> None:
    """Every view and both materialised tables, over the sources as they now stand.

    Never fatal: a store missing a table a view names is not an error, because SQLite
    accepts the definition and the view raises only if something selects from it, which
    is the surface's problem and not the ingest's.

    The two materialised tables are counted beside the views because they cost more than
    all of them together, so a progress bar that left them out would stall on the step.
    """
    progress = progress or progress_module.silent()
    progress.start(len(APP_VIEWS) + 3, "tables")
    progress.advance(label="Recording session origins")
    _quietly_call(lambda: fill_session_sources(connection))
    meta_module.set_meta(
        connection, meta_module.APP_CONTRACT_VERSION_KEY, meta_module.APP_CONTRACT_VERSION
    )
    for statement in INDEXES:
        _quietly(connection, statement)
    progress.advance(label="Measuring session time")
    _quietly(connection, f"DROP TABLE IF EXISTS {SESSION_TIME_TABLE}")
    _quietly(connection, _SESSION_TIME_SCHEMA)
    _quietly(connection, _SESSION_TIME_FILL)
    progress.advance(label="Writing observation sentences")
    _quietly(connection, f"DROP TABLE IF EXISTS {OBSERVATION_TEXT_TABLE}")
    _quietly(connection, _OBSERVATION_TEXT_SCHEMA)
    _quietly_call(lambda: fill_observation_text(connection))
    for name in RETIRED_VIEWS:
        _quietly(connection, f"DROP VIEW IF EXISTS {name}")
    for name, select in definitions().items():
        progress.advance(label=f"Building {name}")
        _quietly(connection, f"DROP VIEW IF EXISTS {name}")
        _quietly(connection, f"CREATE VIEW IF NOT EXISTS {name} AS{select}")


def fill_observation_text(connection: sqlite3.Connection) -> int:
    """One sentence and one structured threshold per row, numbered as the view numbers them.

    `views.observations` and the view's `ROW_NUMBER()` sort by the same expression, so
    the nth row here is the nth row there. Returns how many rows were written.
    """
    from prudence.store import views

    rows = views.observations(connection)
    names = views.repository_names(connection)
    connection.executemany(
        f"INSERT INTO {OBSERVATION_TEXT_TABLE}(observation_id, sentence, threshold_value,"
        " threshold_op) VALUES (?, ?, ?, ?)",
        [
            (
                index,
                observations_module.sentence(row, names.get(row["repo_key"])),
                *observations_module.threshold_of(row),
            )
            for index, row in enumerate(rows, start=1)
        ],
    )
    return len(rows)


def definitions() -> dict[str, str]:
    """Each view's SELECT, with the versions this build of the engine carries baked in.

    The versions are literals rather than a join because they belong to the code, not to
    the store: they are the answer to "which rules produced what you are looking at",
    and the view is rewritten on every ingest anyway.
    """
    totals = tokens.total_sql("u")
    per_kind = ", ".join(f"SUM(p.{column}) AS {column}" for column in TOKEN_COLUMNS)
    reply = tokens.total_sql("p")
    shares = ",\n".join(
        f"           SUM(CASE WHEN p.bucket = '{bucket}' THEN {reply} ELSE 0 END) * 1.0"
        f" / NULLIF(SUM({reply}), 0) AS {bucket}_share"
        for bucket in buckets_module.BUCKETS
    )
    return {
        "app_status": f"""
    SELECT '{__version__}' AS engine_version,
           (SELECT MAX(last_seen) FROM archive_file) AS last_ingest_at,
           (SELECT COUNT(*) FROM session) AS sessions,
           (SELECT COUNT(*) FROM repository) AS projects,
           '{meta_module.APP_CONTRACT_VERSION}' AS app_contract_version,
           {derived_module.PARSER_VERSION} AS parser_version,
           (SELECT MAX(rule_version) FROM session_label
             WHERE name = '{purpose_module.LABEL.name}') AS purpose_rule_version,
           {commits_module.FACT_VERSION} AS commit_fact_version,
           {attribution_module.FACT_VERSION} AS attribution_fact_version,
           {outcomes_module.FACT_VERSION} AS outcome_fact_version,
           {observations_module.FACT_VERSION} AS observation_fact_version,
           {spool_module.FACT_VERSION} AS hook_fact_version,
           (SELECT MAX(bucket_rule_version) FROM response) AS bucket_rule_version,
           (SELECT COALESCE(SUM({reply}), 0) FROM response p WHERE p.bucket IS NULL)
               AS coverage_gap_tokens
""",
        "app_usage_by_bucket_day": f"""
    SELECT date(p.started_at, 'localtime') AS day,
           s.repo_key AS repo_key,
           COALESCE(r.name, s.repo_key, 'unassigned') AS project,
           p.bucket AS bucket,
           {per_kind},
           SUM({reply}) AS total_tokens,
           COUNT(*) AS responses,
           SUM(CASE WHEN p.heuristic = 1 THEN {reply} ELSE 0 END) AS heuristic_tokens,
           COUNT(DISTINCT p.session_id) AS sessions
    FROM response p
    JOIN session s ON s.session_id = p.session_id
    LEFT JOIN repository r ON r.repo_key = s.repo_key
    WHERE p.bucket IS NOT NULL AND p.started_at IS NOT NULL
    GROUP BY day, s.repo_key, project, p.bucket
    ORDER BY day, project, p.bucket
""",
        "app_activity_by_day": f"""
    SELECT date(s.first_at, 'localtime') AS day,
           s.repo_key AS repo_key,
           COALESCE(r.name, s.repo_key, 'unassigned') AS project,
           SUM(COALESCE(a.active_seconds, 0)) / 60.0 AS active_minutes,
           COUNT(*) AS sessions,
           SUM(CASE WHEN a.session_id IS NULL THEN 0 ELSE 1 END) AS measured_sessions
    FROM session s
    LEFT JOIN repository r ON r.repo_key = s.repo_key
    LEFT JOIN {SESSION_TIME_TABLE} a ON a.session_id = s.session_id
    WHERE s.first_at IS NOT NULL
    GROUP BY day, s.repo_key, project
    ORDER BY day, project
""",
        "app_outcomes_by_week": f"""
    WITH counted AS (
        SELECT DISTINCT commit_hash FROM attribution
        WHERE confidence IN ('{attribution_module.FACT}', '{attribution_module.INFERRED}')
    ), best AS ({_BEST_PER_COMMIT.strip()}
    ), fate AS ({_FATE_PER_COMMIT.strip()}
    )
    SELECT c.repo_key AS repo_key,
           COALESCE(r.name, c.repo_key, 'unassigned') AS project,
           date(c.committer_at, 'localtime',
                '-' || ((strftime('%w', c.committer_at, 'localtime') + 6) % 7)
                    || ' days') AS week_start,
           COUNT(*) AS commits,
           SUM(CASE WHEN b.confidence = '{attribution_module.FACT}' THEN 1 ELSE 0 END)
               AS commits_fact,
           SUM(CASE WHEN b.confidence = '{attribution_module.INFERRED}' THEN 1 ELSE 0 END)
               AS commits_inferred,
           SUM(f.lines) AS lines,
           SUM(f.measured_7d) AS measured_7d, SUM(f.alive_7d) AS alive_7d,
           SUM(f.measured_30d) AS measured_30d, SUM(f.alive_30d) AS alive_30d,
           SUM(f.measured_90d) AS measured_90d, SUM(f.alive_90d) AS alive_90d,
           SUM(f.alive_head) AS alive_head,
           SUM(f.alive_head_anywhere) AS alive_head_anywhere,
           SUM(f.blame_head) AS blame_head,
           SUM(f.reworked) AS reworked,
           AVG(b.coverage) AS coverage
    FROM fate f
    JOIN counted n ON n.commit_hash = f.commit_hash
    JOIN "commit" c ON c.commit_hash = f.commit_hash
    LEFT JOIN best b ON b.commit_hash = f.commit_hash
    LEFT JOIN repository r ON r.repo_key = c.repo_key
    WHERE c.committer_at IS NOT NULL
    GROUP BY c.repo_key, project, week_start
    ORDER BY week_start, project
""",
        "app_commits_by_day": f"""
    WITH best AS ({_BEST_PER_COMMIT.strip()}
    )
    SELECT date(c.committer_at, 'localtime') AS day,
           c.repo_key AS repo_key,
           COALESCE(r.name, c.repo_key, 'unassigned') AS project,
           COUNT(*) AS commits,
           SUM(CASE WHEN b.confidence = '{attribution_module.FACT}' THEN 1 ELSE 0 END)
               AS commits_fact,
           SUM(CASE WHEN b.confidence = '{attribution_module.INFERRED}' THEN 1 ELSE 0 END)
               AS commits_inferred
    FROM best b
    JOIN "commit" c ON c.commit_hash = b.commit_hash
    LEFT JOIN repository r ON r.repo_key = c.repo_key
    WHERE c.committer_at IS NOT NULL AND c.is_merge = 0
    GROUP BY day, c.repo_key, project
    ORDER BY day DESC, project
""",
        "app_observation": f"""
    WITH numbered AS (
        SELECT o.*,
               CASE WHEN o.repo_key = '{observations_module.POOLED}' THEN 1 ELSE 0 END AS pooled,
               ROW_NUMBER() OVER (ORDER BY {_OBSERVATION_ORDER}) AS observation_id
        FROM observation o
    )
    SELECT n.repo_key AS repo_key,
           COALESCE(r.name, n.repo_key) AS project,
           n.pooled AS pooled,
           n.fact AS fact, n.threshold_text AS threshold_text, n.outcome AS outcome,
           n.direction AS direction,
           n.with_n AS with_n, n.without_n AS without_n,
           n.with_value AS with_value, n.without_value AS without_value,
           n.coverage AS coverage,
           n.fact_commits AS fact_commits, n.inferred_commits AS inferred_commits,
           n.fact_version AS fact_version,
           n.observation_id AS observation_id,
           t.sentence AS sentence,
           t.threshold_value AS threshold_value,
           t.threshold_op AS threshold_op
    FROM numbered n
    LEFT JOIN repository r ON r.repo_key = n.repo_key
    LEFT JOIN {OBSERVATION_TEXT_TABLE} t ON t.observation_id = n.observation_id
    ORDER BY n.pooled, n.repo_key, n.fact, n.outcome
""",
        "app_review": """
    SELECT v.id AS id,
           v.created_at AS created_at,
           v.range_start AS range_start,
           v.range_end AS range_end,
           v.outcome_range_start AS outcome_range_start,
           v.outcome_range_end AS outcome_range_end,
           v.project AS repo_key,
           COALESCE(r.name, v.project, 'all projects') AS project,
           'Review ' || v.id || ': ' || COALESCE(r.name, v.project, 'all projects')
               || ', ' || substr(v.range_start, 1, 10)
               || ' to ' || substr(v.range_end, 1, 10) AS headline,
           CASE WHEN json_valid(v.sections)
                THEN json_extract(v.sections, '$.sections') END AS sections,
           CASE WHEN json_valid(v.sections)
                THEN json_extract(v.sections, '$.numbers') END AS numbers,
           v.coverage AS coverage,
           v.segment_text AS segment_text,
           v.segment_model AS segment_model,
           v.segment_created_at AS segment_created_at,
           v.segment_language AS segment_language
    FROM review v
    LEFT JOIN repository r ON r.repo_key = v.project
    ORDER BY v.id DESC
""",
        "app_session_sources": """
    SELECT o.session_id, o.source_id, o.kind, o.label, o.home
    FROM session_source o JOIN session s ON s.session_id = o.session_id
""",
        "app_session_list": f"""
    WITH tokens AS (
        SELECT session_id, SUM({totals}) AS total_tokens FROM usage u GROUP BY session_id
    ), edited AS (
        SELECT session_id, COUNT(*) AS edits FROM edit GROUP BY session_id
    ), mix AS (
        SELECT p.session_id,
{shares}
        FROM response p WHERE p.bucket IS NOT NULL GROUP BY p.session_id
    ), best AS ({_BEST_PER_SESSION.strip()}
    ), credited AS (
        SELECT session_id,
               SUM(CASE WHEN confidence = '{attribution_module.FACT}' THEN 1 ELSE 0 END)
                   AS commits_fact,
               SUM(CASE WHEN confidence = '{attribution_module.INFERRED}' THEN 1 ELSE 0 END)
                   AS commits_inferred,
               SUM(CASE WHEN confidence = '{attribution_module.UNCERTAIN}' THEN 1 ELSE 0 END)
                   AS commits_uncertain,
               AVG(CASE WHEN confidence IN
                   ('{attribution_module.FACT}', '{attribution_module.INFERRED}')
                   THEN coverage END) AS coverage
        FROM best GROUP BY session_id
    )
    SELECT s.session_id AS session_id,
           s.repo_key AS repo_key,
           COALESCE(r.name, s.repo_key, 'unassigned') AS project,
           s.first_at AS started_at,
           s.last_at AS ended_at,
           l.label AS purpose,
           t.total_tokens AS total_tokens,
           COALESCE(c.commits_fact, 0) AS commits_fact,
           COALESCE(c.commits_inferred, 0) AS commits_inferred,
           COALESCE(c.commits_uncertain, 0) AS commits_uncertain,
           c.coverage AS coverage,
           COALESCE(sat.sittings, 1) AS sittings,
           s.capture_level AS capture_level,
           CASE WHEN s.capture_level = 'metadata-only' THEN 0 ELSE 1 END AS content_archived,
           COALESCE(e.edits, 0) AS edits,
           m.change_share AS change_share,
           m.run_share AS run_share,
           m.read_share AS read_share,
           m.talk_share AS talk_share,
           s.source AS source,
           (SELECT json_group_array(source_id) FROM
               (SELECT source_id FROM app_session_sources ss
                WHERE ss.session_id = s.session_id ORDER BY source_id)) AS source_ids,
           (SELECT json_group_array(label) FROM
               (SELECT label FROM app_session_sources ss
                WHERE ss.session_id = s.session_id ORDER BY source_id)) AS source_labels,
           (SELECT json_group_array(model) FROM
               (SELECT DISTINCT model FROM usage u WHERE u.session_id = s.session_id
                AND model IS NOT NULL ORDER BY model)) AS models
    FROM session s
    LEFT JOIN repository r ON r.repo_key = s.repo_key
    LEFT JOIN session_label l
           ON l.session_id = s.session_id AND l.name = '{purpose_module.LABEL.name}'
    LEFT JOIN tokens t ON t.session_id = s.session_id
    LEFT JOIN edited e ON e.session_id = s.session_id
    LEFT JOIN mix m ON m.session_id = s.session_id
    LEFT JOIN credited c ON c.session_id = s.session_id
    LEFT JOIN {SESSION_TIME_TABLE} sat ON sat.session_id = s.session_id
    ORDER BY s.first_at DESC
""",
    }


def columns(connection: sqlite3.Connection, name: str) -> tuple[str, ...]:
    """The columns a view actually answers with, for a surface checking the contract."""
    return tuple(row["name"] for row in connection.execute(f"PRAGMA table_info({name})"))


def _quietly(connection: sqlite3.Connection, statement: str) -> None:
    """Run one statement; a store that cannot take it keeps the rest of the contract."""
    try:
        connection.execute(statement)
    except sqlite3.OperationalError:
        return


def _quietly_call(step: Callable[[], object]) -> None:
    """The same promise for a step that is Python rather than one statement."""
    try:
        step()
    except sqlite3.OperationalError:
        return
