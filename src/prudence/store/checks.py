"""Self-checks: what must hold over the store after every ingest and rebuild.

Each check is a named predicate over tables the pipeline has just written, and it returns
the numbers it compared as well as the verdict, so a failure in the run log says what
disagreed with what without anyone opening the store. A check that fails is a bug in the
pipeline, not in the data: every one of them holds by construction when the steps are
right, whatever the agent wrote. `pipeline.run` runs them all after the last step, turns
each failure into a `check_failed` warning (`store/run_warnings.py`), and `--strict` on
`ingest` and `rebuild` turns any failure into exit code 3.

The checks read only; none of them repairs anything. A table a check needs that is not
there makes that check fail with the SQLite error's type and message, which name a
table or a column, never a value.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from prudence.store import app_views, buckets, derived, edits, meta
from prudence.store.views.usage import TOKEN_COLUMNS

_TOTAL = " + ".join(f"COALESCE({column}, 0)" for column in TOKEN_COLUMNS)


@dataclass(frozen=True)
class Check:
    """One predicate's verdict and the numbers behind it."""

    name: str
    passed: bool
    numbers: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "numbers": self.numbers}


def token_totals_agree(connection: sqlite3.Connection) -> Check:
    """`usage`, `response` and `app_usage_by_bucket_day` count the same tokens.

    A reply's tokens are on one `usage` row and one `response` row, so the two sums are
    equal. The view leaves out the replies with no bucket (the coverage gap) and those with
    no time (an unreadable record has none), so it plus those two is the same sum again.
    """
    usage = _one(connection, f"SELECT COALESCE(SUM({_TOTAL}), 0) FROM usage")
    response = _one(connection, f"SELECT COALESCE(SUM({_TOTAL}), 0) FROM response")
    view = _one(connection, "SELECT COALESCE(SUM(total_tokens), 0) FROM app_usage_by_bucket_day")
    gap = _one(connection, f"SELECT COALESCE(SUM({_TOTAL}), 0) FROM response WHERE bucket IS NULL")
    undated = _one(
        connection,
        f"SELECT COALESCE(SUM({_TOTAL}), 0) FROM response"
        " WHERE bucket IS NOT NULL AND started_at IS NULL",
    )
    return Check(
        "token_totals_agree",
        usage == response == view + gap + undated,
        {"usage": usage, "response": response, "view": view, "gap": gap, "undated": undated},
    )


def every_response_has_turn(connection: sqlite3.Connection) -> Check:
    """Every reply of the model names a turn, and the turn exists."""
    responses = _one(connection, "SELECT COUNT(*) FROM response")
    without = _one(connection, "SELECT COUNT(*) FROM response WHERE turn_id IS NULL")
    dangling = _one(
        connection,
        "SELECT COUNT(*) FROM response WHERE turn_id IS NOT NULL"
        " AND turn_id NOT IN (SELECT turn_id FROM turn)",
    )
    return Check(
        "every_response_has_turn",
        without == 0 and dangling == 0,
        {"responses": responses, "without_turn": without, "turn_missing": dangling},
    )


def subagent_tokens_attached(connection: sqlite3.Connection) -> Check:
    """Every subagent token sits on a turn that exists (`store/agent_turns.py`)."""
    subagent = _one(
        connection,
        f"SELECT COALESCE(SUM({_TOTAL}), 0) FROM response WHERE agent_id IS NOT NULL",
    )
    attached = _one(
        connection,
        f"SELECT COALESCE(SUM({_TOTAL}), 0) FROM response WHERE agent_id IS NOT NULL"
        " AND turn_id IN (SELECT turn_id FROM turn)",
    )
    return Check(
        "subagent_tokens_attached",
        subagent == attached,
        {"subagent_tokens": subagent, "attached_tokens": attached},
    )


def app_views_answer(connection: sqlite3.Connection) -> Check:
    """Every `app_*` view answers a query, with exactly its contract's columns."""
    wrong: list[str] = []
    for name, expected in app_views.APP_VIEWS.items():
        try:
            cursor = connection.execute(f"SELECT * FROM {name} LIMIT 0")
        except sqlite3.OperationalError:
            wrong.append(name)
            continue
        if tuple(column[0] for column in cursor.description) != expected:
            wrong.append(name)
    return Check(
        "app_views_answer",
        not wrong,
        {
            "views": len(app_views.APP_VIEWS),
            "answering": len(app_views.APP_VIEWS) - len(wrong),
            "wrong": wrong,
        },
    )


def contract_version_matches(connection: sqlite3.Connection) -> Check:
    """The store says the contract version this code installs."""
    stored = meta.get_meta(connection, meta.APP_CONTRACT_VERSION_KEY)
    return Check(
        "contract_version_matches",
        stored == meta.APP_CONTRACT_VERSION,
        {"stored": stored, "code": meta.APP_CONTRACT_VERSION},
    )


def sessions_have_repository(connection: sqlite3.Connection) -> Check:
    """A session has no repository only when the parse found none for it.

    The parse's own record of how it placed each session (`parse_session.mapping_method`)
    is `unassigned` exactly when no rule found a repository, the store's side of the
    scan's `no repository` group. A session with no repository and any other method lost
    its repository somewhere after it was found.
    """
    without = _one(connection, "SELECT COUNT(*) FROM session WHERE repo_key IS NULL")
    unexplained = _one(
        connection,
        "SELECT COUNT(*) FROM session s LEFT JOIN parse_session p USING(session_id)"
        " WHERE s.repo_key IS NULL AND COALESCE(p.mapping_method, '') <> 'unassigned'",
    )
    return Check(
        "sessions_have_repository",
        unexplained == 0,
        {"without_repository": without, "unexplained": unexplained},
    )


# The version every row of each session table carries, and the column it is in. `edit`
# and `command` hold the fact versions of their own rules in `parser_version`.
_ROW_VERSIONS: tuple[tuple[str, str, int], ...] = (
    *(
        (table, "parser_version", derived.PARSER_VERSION)
        for table in ("session", "record", "turn", "tool_call", "usage", "response")
    ),
    ("edit", "parser_version", edits.EDIT_FACT_VERSION),
    ("command", "parser_version", edits.COMMAND_FACT_VERSION),
    ("response", "bucket_rule_version", buckets.BUCKET_RULE_VERSION),
)


def row_versions_current(connection: sqlite3.Connection) -> Check:
    """Every derived row was written by this code's parser, fact and bucket versions."""
    stale = {
        f"{table}.{column}": _one(
            connection, f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT ?", (version,)
        )
        for table, column, version in _ROW_VERSIONS
    }
    return Check(
        "row_versions_current",
        not any(stale.values()),
        {"parser_version": derived.PARSER_VERSION, "stale_rows": stale},
    )


CHECKS: tuple[Callable[[sqlite3.Connection], Check], ...] = (
    token_totals_agree,
    every_response_has_turn,
    subagent_tokens_attached,
    app_views_answer,
    contract_version_matches,
    sessions_have_repository,
    row_versions_current,
)


def run(connection: sqlite3.Connection) -> list[Check]:
    """Every check, in `CHECKS` order."""
    results = []
    for check in CHECKS:
        try:
            results.append(check(connection))
        except sqlite3.OperationalError as error:
            results.append(
                Check(
                    check.__name__,
                    False,
                    {"error": type(error).__name__, "message": str(error)},
                )
            )
    return results


def summary_line(results: list[Check]) -> str:
    """The last line of a human summary: all passed, or which failed and on what numbers."""
    failed = [check for check in results if not check.passed]
    if not failed:
        return f"Self-checks: all {len(results)} passed."
    detail = "; ".join(f"{check.name} {check.numbers}" for check in failed)
    return f"Self-checks: {len(failed)} of {len(results)} failed: {detail}."


def _one(connection: sqlite3.Connection, query: str, parameters: tuple = ()) -> int:
    return connection.execute(query, parameters).fetchone()[0]
