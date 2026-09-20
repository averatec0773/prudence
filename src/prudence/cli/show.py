"""`prudence show --session`: everything recorded about one session, and nothing else.

Decision P5 says the user can always see what was recorded. This command is where that
promise is kept in full: not a summary of a session but the whole row set, grouped by
what kind of fact it is, with the version of the code that produced each group and the
trust level the schema document assigns it printed beside the group's heading. A reader
who wants to know whether a number can be relied on should not have to open the schema.

No message text appears here at any capture level, because none is stored. At
`metadata-only` the file paths and the command text are not stored either, and the
command says so in place of the missing column rather than printing an empty table.
"""

from __future__ import annotations

import sqlite3
from collections import Counter

import click

from prudence.cli.render import size
from prudence.paths import database_file
from prudence.store import attribution, commits, db, derived, edits, spool, views

WITHHELD = "file paths withheld at metadata-only"


@click.command()
@click.option("--session", "token", required=True, metavar="ID", help="Session id, or a prefix.")
@click.option(
    "--files", "list_files", is_flag=True, help="List every archived file, not a summary."
)
def show(token: str, list_files: bool) -> None:
    """Show everything recorded about one session, fact group by fact group."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        session_id = resolve(connection, token)
        click.echo(render(connection, session_id, list_files=list_files))
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def resolve(connection: sqlite3.Connection, token: str) -> str:
    """One session id from an id or a unique prefix; anything else is an error, not a guess."""
    rows = [
        row["session_id"]
        for row in connection.execute(
            "SELECT session_id FROM session WHERE session_id LIKE ? ORDER BY session_id",
            (f"{token}%",),
        )
    ]
    if not rows:
        raise click.UsageError(f"No recorded session starts with {token!r}.")
    if len(rows) > 1:
        listed = ", ".join(rows[:5]) + (" ..." if len(rows) > 5 else "")
        raise click.UsageError(f"{token!r} matches {len(rows)} sessions: {listed}")
    return rows[0]


def render(connection: sqlite3.Connection, session_id: str, list_files: bool = False) -> str:
    """The whole record of one session as text, grouped by kind of fact."""
    row = views.session_row(connection, session_id)
    full = row["capture_level"] == "full"
    lines = [f"session {session_id}"]
    lines += _identity(connection, row)
    lines += _counts(connection, session_id)
    lines += _usage(connection, session_id)
    lines += _files(connection, session_id, full)
    lines += _commits(connection, session_id)
    lines += _hooks(connection, session_id)
    lines += _archive(connection, session_id, list_files)
    lines.append("")
    lines.append("No message text is recorded, at any capture level.")
    return "\n".join(lines)


def _heading(title: str, tables: str, version: str, trust: str) -> list[str]:
    return ["", f"{title}", f"  from {tables}; {version}; trust {trust}"]


def _identity(connection: sqlite3.Connection, row: sqlite3.Row) -> list[str]:
    names = views.repository_names(connection)
    lines = _heading(
        "identity",
        "session",
        f"parser version {row['parser_version']}",
        "high for times and counts, medium for the repository and the entrypoint",
    )
    pairs = [
        ("repository", names.get(row["repo_key"], row["repo_key"] or "unassigned")),
        ("capture level", row["capture_level"] or "?"),
        ("source", row["source"] or "?"),
        ("entrypoint", row["entrypoint"] or "?"),
        ("working directory", row["cwd"] or WITHHELD),
        ("first record", row["first_at"] or "?"),
        ("last record", row["last_at"] or "?"),
        ("sittings", str(views.sittings(connection, row["session_id"]))),
        ("mapping notes", row["notes"] or "none (read straight off the working directory)"),
    ]
    lines += [f"  {label:<20} {value}" for label, value in pairs]
    return lines


def _counts(connection: sqlite3.Connection, session_id: str) -> list[str]:
    counted = views.record_turn_toolcall_counts(connection, session_id)
    lines = _heading(
        "counts",
        "record, turn, tool_call",
        f"parser version {derived.PARSER_VERSION}",
        "high, except the turn key which is medium",
    )
    lines.append(
        f"  records {counted['records']}, turns {counted['turns']}, "
        f"tool calls {counted['tool_calls']}"
    )
    by_tool = views.tool_calls_by_name(connection, session_id)
    lines.append(
        "  tool calls by name: " + (", ".join(f"{r['name']} {r['n']}" for r in by_tool) or "none")
    )

    edit = views.edit_totals(connection, session_id)
    lines.append("")
    lines.append(f"  edits (edit, fact version {edits.EDIT_FACT_VERSION}, trust medium)")
    lines.append(
        f"    {edit['n']} edits, {edit['added']} lines added, {edit['removed']} lines removed"
    )
    by_class = views.commands_by_class(connection, session_id)
    lines.append(f"  commands (command, fact version {edits.COMMAND_FACT_VERSION}, trust medium)")
    lines.append(
        "    by class: " + (", ".join(f"{r['command_class']} {r['n']}" for r in by_class) or "none")
    )
    return lines


def _usage(connection: sqlite3.Connection, session_id: str) -> list[str]:
    """What the session spent, per model, counted once per API response."""
    lines = _heading(
        "token usage",
        "usage",
        f"parser version {derived.PARSER_VERSION}",
        "high: these are the numbers the API itself reported",
    )
    summary = views.usage_of_session(connection, session_id)
    if summary is None:
        lines.append("  none recorded (this Claude Code version wrote no usage fields)")
        return lines
    lines.append(
        f"  {'model':<30} {'requests':>9} {'input':>10} {'output':>10} {'cache read':>11} "
        f"{'cache write':>12} {'total':>11}"
    )
    for model, counted in summary["by_model"].items():
        lines.append(
            f"  {model[:30]:<30} {counted['requests']:>9} {counted['input_tokens']:>10} "
            f"{counted['output_tokens']:>10} {counted['cache_read_tokens']:>11} "
            f"{counted['cache_creation_tokens']:>12} {counted['total_tokens']:>11}"
        )
    lines.append(
        f"  {'all models':<30} {summary['requests']:>9} {summary['input_tokens']:>10} "
        f"{summary['output_tokens']:>10} {summary['cache_read_tokens']:>11} "
        f"{summary['cache_creation_tokens']:>12} {summary['total_tokens']:>11}"
    )
    lines.append(
        "  one row per API response, not per record: Claude Code repeats the same usage "
        "on every record of one response."
    )
    return lines


def _files(connection: sqlite3.Connection, session_id: str, full: bool) -> list[str]:
    lines = _heading(
        "files edited",
        "edit",
        f"fact version {edits.EDIT_FACT_VERSION}",
        "medium: the path is the agent's, made relative by the longest known worktree root",
    )
    if not full:
        lines.append(f"  {WITHHELD}")
        return lines
    rows = views.edited_files(connection, session_id)
    if not rows:
        lines.append("  none")
        return lines
    lines.append(f"  {'path':<52} {'edits':>6} {'+':>7} {'-':>7}")
    for row in rows:
        lines.append(
            f"  {_tail(row['path']):<52} {row['n']:>6} {row['added'] or 0:>7} "
            f"{row['removed'] or 0:>7}"
        )
    return lines


def _tail(path: str, width: int = 52) -> str:
    """Long paths are cut at the front: the file name is the part worth reading."""
    return path if len(path) <= width else "..." + path[-(width - 3) :]


def _commits(connection: sqlite3.Connection, session_id: str) -> list[str]:
    lines = _heading(
        "commits attributed",
        "attribution, commit",
        f"fact version {attribution.FACT_VERSION} over commit fact version {commits.FACT_VERSION}",
        "high for in_session and git_ai_note, medium for line_match and for a rewritten "
        "commit found again by time and lines",
    )
    rows = views.attributed_commits(connection, session_id)
    if not rows:
        lines.append("  none")
        return lines
    lines.append(
        f"  {'commit':<10} {'committed':<17} {'method':<13} {'confidence':<10} {'rank':>4} "
        f"{'matched':>8} {'of':>6} {'coverage':>9}"
    )
    for row in rows:
        coverage = "-" if row["coverage"] is None else f"{row['coverage'] * 100:.0f}%"
        method = row["method"] + (f" ({row['method_note']})" if row["method_note"] else "")
        lines.append(
            f"  {row['commit_hash'][:10]:<10} {(row['committer_at'] or '')[:17]:<17} "
            f"{method[:13]:<13} {row['confidence']:<10} {row['rank']:>4} "
            f"{row['lines_matched']:>8} "
            f"{row['added_lines'] if row['added_lines'] is not None else '?':>6} {coverage:>9}"
        )
    counted = views.credited(connection, session_id)
    lines.append(
        f"  counted: {counted['fact']} fact, {counted['inferred']} inferred; "
        f"{counted['uncertain']} uncertain, which enter no statistic "
        f"(floor {attribution.COVERAGE_FLOOR:.2f} of a commit's added lines, "
        f"margin {attribution.MARGIN}x over rank 2)."
    )
    lines.append("  coverage is NULL, printed as -, when there is no line evidence at all.")
    return lines


def _hooks(connection: sqlite3.Connection, session_id: str) -> list[str]:
    """The hook timeline, per turn: the tree before the turn and after it."""
    rows = views.hook_timeline(connection, session_id)
    if not rows:
        return []
    lines = _heading(
        "hook timeline",
        "hook_event",
        f"fact version {spool.FACT_VERSION}",
        "high: git answered these at the moment of the event",
    )
    turns: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        turns.setdefault(row["prompt_id"] or "(no turn)", []).append(row)
    lines.append(
        f"  {'turn':<26} {'events':>6} {'first':<21} {'head before':<12} {'head after':<12} "
        f"{'dirty':>6}"
    )
    for turn_id, events in turns.items():
        first, last = events[0], events[-1]
        lines.append(
            f"  {turn_id[:26]:<26} {len(events):>6} {(first['ts'] or '')[:21]:<21} "
            f"{(first['head'] or '-')[:10]:<12} {(last['head'] or '-')[:10]:<12} "
            f"{last['dirty_count'] if last['dirty_count'] is not None else '?':>6}"
        )
    return lines


def _archive(connection: sqlite3.Connection, session_id: str, list_files: bool) -> list[str]:
    lines = _heading(
        "archive files",
        "archive_file",
        f"archive schema version {db.ARCHIVE_SCHEMA_VERSION}",
        "high: these are the bytes every derived row above was built from",
    )
    rows = views.archived_files(connection, session_id)
    if not rows:
        lines.append("  none")
        return lines
    total = 0
    counted: Counter[str] = Counter()
    for row in rows:
        total += row["size"]
        counted[row["source"]] += 1
        if list_files:
            lines.append(f"  {row['source']:<13} {size(row['size']):>10}  {row['path']}")
    detail = ", ".join(f"{count} {source}" for source, count in sorted(counted.items()))
    lines.append(f"  {len(rows)} files ({detail}), {size(total)} of agent bytes.")
    if not list_files:
        lines.append("  (add --files to list them)")
    return lines
