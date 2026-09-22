"""`prudence status`: everything recorded, and where it is.

Decision P5 says the user can always see what was recorded, so this command shows the
paths as well as the counts, and it lists the record types the parser did not
recognise: a format change is visible here before it matters anywhere else.
"""

from __future__ import annotations

import json
import sqlite3

import click

from prudence import __version__
from prudence import config as config_module
from prudence.cli.render import size, thousands
from prudence.paths import database_file
from prudence.reviews import readiness
from prudence.store import (
    archive,
    attribution,
    commits,
    db,
    derived,
    observations,
    outcomes,
    rewritten,
    spool,
    views,
)


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Print the same numbers as JSON.")
def status(as_json: bool) -> None:
    """Show what Prudence has recorded so far."""
    config = config_module.load()
    if as_json:
        click.echo(json.dumps(summary(), indent=2))
        return
    lines = [f"prudence {__version__}", f"config: {config.path}", f"data:   {database_file()}", ""]
    if not config.repositories:
        lines.append("No repository is enabled. Run `prudence init` to choose what is recorded.")
        click.echo("\n".join(lines))
        return

    database_exists = database_file().exists()
    connection = db.connect() if database_exists else None
    try:
        lines.append(
            f"{'repository':<28} {'level':<14} {'files':>7} {'archived':>10} "
            f"{'sessions':>8} {'edits':>7} {'commits':>8}"
        )
        for repo in sorted(config.repositories.values(), key=lambda r: r.name):
            files, archived = _per_repo(connection, repo.key)
            counted = _per_repo_derived(connection, repo.key)
            lines.append(
                f"{repo.name[:28]:<28} {repo.level:<14} {files:>7} {size(archived):>10} "
                f"{counted['sessions']:>8} {counted['edits']:>7} {counted['commits']:>8}"
            )
        lines.append("")
        if connection is None:
            lines.append("Nothing ingested yet. Run `prudence ingest`.")
        else:
            lines.extend(_store_lines(connection))
    finally:
        if connection is not None:
            connection.close()
    click.echo("\n".join(lines))


def summary() -> dict:
    """The same counts the text is built from, as `views.status_summary` returns them.

    `views.status_summary` is where the MCP server already reads them, so `--json` is
    that dictionary plus the three things only a command line shows: which engine wrote
    it, where the files are, and whether a review is worth writing now.
    """
    config = config_module.load()
    connection = db.connect() if database_file().exists() else None
    try:
        return {
            "engine_version": __version__,
            "config_path": str(config.path),
            "database_path": str(database_file()),
            **views.status_summary(connection),
            "readiness": readiness_summary(connection, config),
        }
    finally:
        if connection is not None:
            connection.close()


def readiness_summary(connection: sqlite3.Connection | None, config: config_module.Config) -> dict:
    """Whether a review is ready, over everything and then per enabled project.

    The rule stays in `reviews/readiness.py` and is asked, never restated: a surface
    that counted sessions itself would be a second copy of the rule, and the two would
    disagree the day one of the thresholds moved. A store that does not exist yet is an
    empty one, which the rule answers with zeroes of its own accord.
    """
    empty = sqlite3.connect(":memory:") if connection is None else None
    if empty is not None:
        empty.row_factory = sqlite3.Row
    asked = connection if connection is not None else empty
    try:
        return {
            **_readiness_entry(readiness.readiness(asked)),
            "projects": [
                _readiness_entry(readiness.readiness(asked, repo.key, name=repo.name))
                for repo in sorted(config.repositories.values(), key=lambda r: r.name)
            ],
        }
    finally:
        if empty is not None:
            empty.close()


def _readiness_entry(verdict: readiness.Readiness) -> dict:
    """One verdict as JSON, with both thresholds beside the counts they are compared to."""
    return {
        "ready": verdict.ready,
        "new_sessions": verdict.new_sessions,
        "required_sessions": readiness.MIN_NEW_SESSIONS,
        "matured_commits": verdict.matured_commits,
        "required_commits": readiness.MIN_MATURED_COMMITS,
        "since": verdict.since,
        "project": verdict.project,
    }


def _per_repo(connection: sqlite3.Connection | None, repo_key: str) -> tuple[int, int]:
    if connection is None:
        return 0, 0
    row = connection.execute(
        "SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS size FROM archive_file"
        " WHERE repo_key = ?",
        (repo_key,),
    ).fetchone()
    return row["files"], row["size"]


def _per_repo_derived(connection: sqlite3.Connection | None, repo_key: str) -> dict[str, int]:
    """Sessions, edits and commits recorded for one repository, zero before the first build."""
    counted = {"sessions": 0, "edits": 0, "commits": 0}
    if connection is None:
        return counted
    for name, statement in (
        ("sessions", "SELECT COUNT(*) FROM session WHERE repo_key = ?"),
        ("edits", "SELECT COUNT(*) FROM edit WHERE repo_key = ?"),
        ("commits", 'SELECT COUNT(*) FROM "commit" WHERE repo_key = ?'),
    ):
        try:
            counted[name] = connection.execute(statement, (repo_key,)).fetchone()[0]
        except sqlite3.OperationalError:
            counted[name] = 0
    return counted


def _store_lines(connection: sqlite3.Connection) -> list[str]:
    files, original, stored = archive.archive_totals(connection)
    counts = derived.counts(connection)
    lines = [
        f"archive: {files} files, {size(original)} of agent data, {size(stored)} stored compressed",
    ]
    if counts["session"] < 0:
        lines.append("derived tables: not built yet. Run `prudence ingest` or `prudence rebuild`.")
        return lines
    lines.append(
        f"derived: {counts['session']} sessions, {counts['record']} records, "
        f"{counts['turn']} turns, {counts['tool_call']} tool calls, {counts['edit']} edits, "
        f"{counts['command']} commands (parser version {derived.PARSER_VERSION})"
    )
    lines.extend(_usage_lines(connection))
    lines.extend(_command_lines(connection))
    lines.extend(_hook_lines(connection))
    lines.extend(_commit_lines(connection))
    lines.extend(_outcome_lines(connection))
    lines.extend(_purpose_lines(connection))
    lines.extend(_observation_lines(connection))
    lines.extend(_readiness_lines(connection))
    lines.extend(_mapping_lines(connection))
    resumed = connection.execute(
        "SELECT COUNT(*) FROM session WHERE notes LIKE '%resumed%'"
    ).fetchone()[0]
    if resumed:
        lines.append(f"resumed sessions noted: {resumed}")
    return lines + _unknown_lines(connection)


def _usage_lines(connection: sqlite3.Connection) -> list[str]:
    """Tokens, counted once per API response. Nothing at all before parser version 3."""
    totals = views.usage_totals(connection)
    if not totals["requests"]:
        return ["tokens: none recorded (no Claude Code version here wrote usage fields)"]
    models = ", ".join(f"{count} {model}" for model, count in totals["by_model"].items())
    return [
        f"tokens: {thousands(totals['total_tokens'])} over {totals['requests']} API responses "
        f"in {totals['sessions']} sessions "
        f"({thousands(totals['input_tokens'])} input, {thousands(totals['output_tokens'])} output, "
        f"{thousands(totals['cache_read_tokens'])} cache read, "
        f"{thousands(totals['cache_creation_tokens'])} cache creation)",
        f"responses by model: {models}",
    ]


def _command_lines(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT command_class, COUNT(*) AS n FROM command GROUP BY command_class ORDER BY n DESC"
    ).fetchall()
    if not rows:
        return []
    detail = ", ".join(f"{row['n']} {row['command_class']}" for row in rows)
    return [f"commands by class: {detail}"]


def _hook_lines(connection: sqlite3.Connection) -> list[str]:
    """What the hooks recorded, which is nothing at all until the user installs them."""
    events, sessions = spool.counts(connection)
    if not events:
        return ["hook events: none (run `prudence hooks install` to record git state)"]
    return [f"hook events: {events} over {sessions} sessions (fact version {spool.FACT_VERSION})"]


def _commit_lines(connection: sqlite3.Connection) -> list[str]:
    """What the harvest found and what attribution made of it, with its methods named."""
    harvested, commit_lines = commits.counts(connection)
    if not harvested:
        return ["commits: none harvested yet"]
    methods = attribution.counts(connection)
    attributed = connection.execute(
        "SELECT COUNT(DISTINCT commit_hash) FROM attribution WHERE rank = 1"
    ).fetchone()[0]
    detail = ", ".join(f"{count} {method}" for method, count in sorted(methods.items())) or "none"
    labels = attribution.confidence_counts(connection)
    printed = rewritten.resolution(connection)
    return [
        f"commits: {harvested} harvested, {commit_lines} added lines hashed "
        f"(fact version {commits.FACT_VERSION})",
        f"attributed: {attributed} commits, by method {detail} "
        f"(fact version {attribution.FACT_VERSION})",
        f"confidence: {labels.get('fact', 0)} fact, {labels.get('inferred', 0)} inferred, "
        f"{labels.get('uncertain', 0)} uncertain (floor {attribution.COVERAGE_FLOOR:.2f}, "
        f"margin {attribution.MARGIN}x)",
        f"commit hashes printed in a session: {printed['printed']}, of which "
        f"{printed['resolved']} still resolve, {printed['reidentified']} were re-identified "
        f"after a rewrite, {printed['unresolved']} are gone "
        f"(commit_alias fact version {rewritten.FACT_VERSION})",
        f"silent commits matched: {rewritten.silent_matches(connection)} "
        "(a `git commit` that printed no hash, matched by timing plus overlapping lines)",
    ]


def _outcome_lines(connection: sqlite3.Connection) -> list[str]:
    """What became of the attributed lines, and which repositories were withheld."""
    counted = outcomes.counts(connection)
    if counted["lines"]:
        lines = [
            f"outcomes: {counted['lines']} attributed lines over {counted['commits']} commits, "
            f"{counted['reworked']} reworked by a later commit of your own "
            f"(line_fate fact version {outcomes.FACT_VERSION})"
        ]
    else:
        lines = ["outcomes: none computed yet (no attributed line has a fate row)"]
    bots = connection.execute('SELECT COUNT(*) FROM "commit" WHERE is_bot = 1').fetchone()[0]
    lines.append(
        f"bot commits excluded from the multi-author guard: {bots} "
        f"(author name or email carrying {', '.join(commits.BOT_MARKERS)})"
    )
    names = views.repository_names(connection)
    for key, note in sorted(outcomes.suppression_notes(connection).items()):
        lines.append(f"outcomes suppressed for {names.get(key, key)}: {note}")
    return lines


def _purpose_lines(connection: sqlite3.Connection) -> list[str]:
    """What the sessions were for, as the tool-mix rules read them. Labels, not numbers."""
    counted = views.purpose_counts(connection)
    if not counted:
        return ["purpose: no labels yet (run `prudence rebuild`)"]
    detail = ", ".join(f"{count} {label}" for label, count in counted.items())
    version = views.purpose_rule_version(connection)
    return [
        f"purpose: {detail} (rule version {version}; a label from the tool mix, not from "
        "reading the conversation)"
    ]


def _observation_lines(connection: sqlite3.Connection) -> list[str]:
    """How many joins of a behaviour against an outcome cleared both floors."""
    counted = observations.counts(connection)
    return [
        f"observations: {counted['projects']} in a project, {counted['pooled']} pooled across "
        f"your projects (at least {observations.MIN_SESSIONS} sessions each side, at least "
        f"{observations.MIN_GAP * 100:.0f} points apart; `prudence observations`)"
    ]


def _readiness_lines(connection: sqlite3.Connection) -> list[str]:
    """Whether a review is worth writing now, in the readiness rule's own words."""
    return [f"review: {readiness.readiness(connection).reason}"]


def _mapping_lines(connection: sqlite3.Connection) -> list[str]:
    """How many sessions needed a fallback to find their repository, and how many failed."""
    unassigned = connection.execute(
        "SELECT COUNT(*) FROM session WHERE repo_key IS NULL"
    ).fetchone()[0]
    recovered = views.mapped_by_fallback(connection)
    lines = []
    if recovered:
        detail = ", ".join(f"{count} by {method}" for method, count in sorted(recovered.items()))
        lines.append(f"sessions mapped by a fallback: {detail}")
    lines.append(f"sessions with no repository: {unassigned}")
    return lines


def _unknown_lines(connection: sqlite3.Connection) -> list[str]:
    lines: list[str] = []
    unknown = connection.execute(
        "SELECT type, claude_version, count FROM unknown_record_type ORDER BY count DESC, type"
    ).fetchall()
    if not unknown:
        lines.append("unknown record types: none")
        return lines
    lines.append(f"unknown record types ({len(unknown)} type and version pairs):")
    for row in unknown:
        lines.append(f"  {row['type']:<28} {row['claude_version'] or '?':<12} {row['count']}")
    return lines
