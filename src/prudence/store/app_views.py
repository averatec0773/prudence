"""The `app_*` views: the one contract every surface that is not the CLI reads.

The Mac app owns no numbers (M3 rule 8). It reads these five views and the stored rows
behind them, and nothing else; a screen that needs a figure the engine does not compute
gets a new view here rather than a join in Swift. `meta.app_contract_version` is the
version of the column lists below and changes only when one of them changes.

Real SQL views rather than tables, for two reasons. A view is always in step with the
tables under it, so no step can forget to refresh it; and a view costs nothing to store
beside a 700 MB archive. They are dropped and recreated at the end of every `ingest` and
`rebuild` (`pipeline.run` calls `install_app_views` once, after the last step), because
`derived.build` swaps its tables by renaming, and a view over a renamed table would be
left pointing at nothing.

Every view is written from the same tables and the same rules as the matching function
in `store/views/`, so the app and the CLI cannot disagree:

- `app_usage_by_purpose_day` buckets a session's tokens, active time and count on the
  day its first record was written, exactly as `cli/usage.py` buckets them on the week
  of `session.first_at`. Active time is the sum of the gaps between consecutive records
  that are an hour or less, which is what `views.active_seconds_map` computes one
  session at a time (`julianday` rather than `datetime.fromisoformat`, so the totals
  agree to about a millisecond over a day of work, not to the microsecond).
  The one deliberate difference from the CLI: the day is the local
  day (`date(..., 'localtime')`), because a person reading a chart of their own week
  means their own midnight, while `cli/usage.py` takes the stored UTC timestamp. Only
  the bucket a session falls in can differ, never a total.
- `app_outcomes_by_week` counts a commit once, at its best confidence label, over the
  commits `views.counted_pairs` would count (`fact` and `inferred` only), and sums
  `line_fate` the way `views.outcomes_by_repository` sums it. A repository whose
  outcomes are suppressed by the multi-author guard has no rows here at all, because
  `outcomes.build` writes it no `line_fate` rows in the first place; the reason stays on
  `repository.outcomes_suppressed_note`.
- `app_session_list` counts commits per session the way `views.credited_map` does: one
  commit once, at its best label, `uncertain` reported and never folded into the other
  two. A session whose records carried no usage fields has `total_tokens` NULL, not 0
  (architecture rule 10).
- `app_observation` is the `observation` table with its project name and a `pooled` flag,
  in the order `views.observations` returns it. The sentence a surface prints is prose
  built by `store/observations.sentence`, so it is not here; the numbers behind it are.

Nothing here returns message text, because none is stored.

Measured after a full `prudence ingest` on a copy of the founder's store (740 MB, 148
sessions, 227,399 records, 2,054 attributions, 82,680 line fates), best of three warm,
`COUNT(*)` then a full `SELECT *`:

    app_status                    0 ms /  1 ms
    app_usage_by_purpose_day     10 ms / 10 ms
    app_outcomes_by_week         24 ms / 24 ms
    app_observation               0 ms /  0 ms
    app_session_list             12 ms / 13 ms

`install_app_views` itself takes about 290 ms on that store, almost all of it the one
pass over `record` that fills `app_session_time`. Written as plain views, the two that
need the sitting rule cost 230 ms each per query instead, which is why that one
aggregate is materialised and the index below exists.
"""

from __future__ import annotations

import sqlite3

from prudence import __version__
from prudence.facts import purpose as purpose_module
from prudence.store import attribution as attribution_module
from prudence.store import commits as commits_module
from prudence.store import derived as derived_module
from prudence.store import meta as meta_module
from prudence.store import observations as observations_module
from prudence.store import outcomes as outcomes_module
from prudence.store import spool as spool_module
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
    ),
    "app_usage_by_purpose_day": (
        "day",
        "repo_key",
        "project",
        "purpose",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "total_tokens",
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
    ),
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
    ),
}

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


def drop_app_views(connection: sqlite3.Connection) -> None:
    """Take the contract down before the pipeline runs, and mean it.

    `derived.build` swaps its tables with `ALTER TABLE ... RENAME`, and since SQLite
    3.25 a rename walks every view in the schema to fix up its references. A view over a
    table the swap has just dropped makes that rename fail and takes the whole rebuild
    with it, so the views are removed first and put back by `install_app_views` at the
    end. Nothing reads them in between; the app reads a store that is not being written.
    """
    for name in APP_VIEWS:
        _quietly(connection, f"DROP VIEW IF EXISTS {name}")


def install_app_views(connection: sqlite3.Connection) -> None:
    """Recreate every `app_*` view and record the contract version. Never fatal.

    Called once at the end of `pipeline.run`, so `ingest` and `rebuild` both leave the
    contract in place. A store missing a table a view names is not an error: SQLite
    accepts the definition and the view raises only if something selects from it, which
    is the surface's problem and not the ingest's.
    """
    meta_module.set_meta(
        connection, meta_module.APP_CONTRACT_VERSION_KEY, meta_module.APP_CONTRACT_VERSION
    )
    for statement in INDEXES:
        _quietly(connection, statement)
    _quietly(connection, f"DROP TABLE IF EXISTS {SESSION_TIME_TABLE}")
    _quietly(connection, _SESSION_TIME_SCHEMA)
    _quietly(connection, _SESSION_TIME_FILL)
    for name, select in definitions().items():
        _quietly(connection, f"DROP VIEW IF EXISTS {name}")
        _quietly(connection, f"CREATE VIEW IF NOT EXISTS {name} AS{select}")


def definitions() -> dict[str, str]:
    """Each view's SELECT, with the versions this build of the engine carries baked in.

    The versions are literals rather than a join because they belong to the code, not to
    the store: they are the answer to "which rules produced what you are looking at",
    and the view is rewritten on every ingest anyway.
    """
    totals = " + ".join(f"COALESCE(u.{column}, 0)" for column in TOKEN_COLUMNS)
    per_kind = ", ".join(f"SUM(COALESCE({column}, 0)) AS {column}" for column in TOKEN_COLUMNS)
    summed = ", ".join(f"SUM(COALESCE(t.{column}, 0)) AS {column}" for column in TOKEN_COLUMNS)
    grand = " + ".join(f"COALESCE(t.{column}, 0)" for column in TOKEN_COLUMNS)
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
           {spool_module.FACT_VERSION} AS hook_fact_version
""",
        "app_usage_by_purpose_day": f"""
    WITH tokens AS (
        SELECT session_id, {per_kind} FROM usage GROUP BY session_id
    )
    SELECT date(s.first_at, 'localtime') AS day,
           s.repo_key AS repo_key,
           COALESCE(r.name, s.repo_key, 'unassigned') AS project,
           COALESCE(l.label, '{purpose_module.UNKNOWN}') AS purpose,
           {summed},
           SUM({grand}) AS total_tokens,
           SUM(COALESCE(a.active_seconds, 0)) / 60.0 AS active_minutes,
           COUNT(*) AS sessions,
           SUM(CASE WHEN t.session_id IS NULL THEN 0 ELSE 1 END) AS measured_sessions
    FROM session s
    LEFT JOIN repository r ON r.repo_key = s.repo_key
    LEFT JOIN session_label l
           ON l.session_id = s.session_id AND l.name = '{purpose_module.LABEL.name}'
    LEFT JOIN tokens t ON t.session_id = s.session_id
    LEFT JOIN {SESSION_TIME_TABLE} a ON a.session_id = s.session_id
    WHERE s.first_at IS NOT NULL
    GROUP BY day, s.repo_key, project, purpose
    ORDER BY day, project, purpose
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
           date(c.committer_at,
                '-' || ((strftime('%w', c.committer_at) + 6) % 7) || ' days') AS week_start,
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
        "app_observation": f"""
    SELECT o.repo_key AS repo_key,
           COALESCE(r.name, o.repo_key) AS project,
           CASE WHEN o.repo_key = '{observations_module.POOLED}' THEN 1 ELSE 0 END AS pooled,
           o.fact AS fact, o.threshold_text AS threshold_text, o.outcome AS outcome,
           o.direction AS direction,
           o.with_n AS with_n, o.without_n AS without_n,
           o.with_value AS with_value, o.without_value AS without_value,
           o.coverage AS coverage,
           o.fact_commits AS fact_commits, o.inferred_commits AS inferred_commits,
           o.fact_version AS fact_version
    FROM observation o
    LEFT JOIN repository r ON r.repo_key = o.repo_key
    ORDER BY pooled, o.repo_key, o.fact, o.outcome
""",
        "app_session_list": f"""
    WITH tokens AS (
        SELECT session_id, SUM({totals}) AS total_tokens FROM usage u GROUP BY session_id
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
           CASE WHEN s.capture_level = 'metadata-only' THEN 0 ELSE 1 END AS content_archived
    FROM session s
    LEFT JOIN repository r ON r.repo_key = s.repo_key
    LEFT JOIN session_label l
           ON l.session_id = s.session_id AND l.name = '{purpose_module.LABEL.name}'
    LEFT JOIN tokens t ON t.session_id = s.session_id
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
