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
from datetime import datetime

import click

from prudence.cli.render import size
from prudence.cli.sessions import SITTING_GAP
from prudence.paths import database_file
from prudence.store import attribution, commits, db, derived, edits, spool

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
    row = connection.execute("SELECT * FROM session WHERE session_id = ?", (session_id,)).fetchone()
    full = row["capture_level"] == "full"
    lines = [f"session {session_id}"]
    lines += _identity(connection, row)
    lines += _counts(connection, session_id)
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
    names = {
        repo["repo_key"]: repo["name"] for repo in connection.execute("SELECT * FROM repository")
    }
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
        ("sittings", str(_sittings(connection, row["session_id"]))),
        ("mapping notes", row["notes"] or "none (read straight off the working directory)"),
    ]
    lines += [f"  {label:<20} {value}" for label, value in pairs]
    return lines


def _sittings(connection: sqlite3.Connection, session_id: str) -> int:
    """How many times the developer sat down: a gap over an hour starts a new one."""
    count = 0
    previous: datetime | None = None
    for row in connection.execute(
        "SELECT timestamp FROM record WHERE session_id = ? AND timestamp IS NOT NULL"
        " ORDER BY timestamp",
        (session_id,),
    ):
        try:
            moment = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if previous is None or moment - previous > SITTING_GAP:
            count += 1
        previous = moment
    return max(count, 1)


def _counts(connection: sqlite3.Connection, session_id: str) -> list[str]:
    records = _scalar(connection, "SELECT COUNT(*) FROM record WHERE session_id = ?", session_id)
    turns = _scalar(connection, "SELECT COUNT(*) FROM turn WHERE session_id = ?", session_id)
    calls = _scalar(connection, "SELECT COUNT(*) FROM tool_call WHERE session_id = ?", session_id)
    lines = _heading(
        "counts",
        "record, turn, tool_call",
        f"parser version {derived.PARSER_VERSION}",
        "high, except the turn key which is medium",
    )
    lines.append(f"  records {records}, turns {turns}, tool calls {calls}")
    by_tool = connection.execute(
        "SELECT COALESCE(tool_name, '?') AS name, COUNT(*) AS n FROM tool_call"
        " WHERE session_id = ? GROUP BY name ORDER BY n DESC, name",
        (session_id,),
    ).fetchall()
    lines.append(
        "  tool calls by name: " + (", ".join(f"{r['name']} {r['n']}" for r in by_tool) or "none")
    )

    edit = connection.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(lines_added), 0) AS added,"
        " COALESCE(SUM(lines_removed), 0) AS removed FROM edit WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    lines.append("")
    lines.append(f"  edits (edit, fact version {edits.EDIT_FACT_VERSION}, trust medium)")
    lines.append(
        f"    {edit['n']} edits, {edit['added']} lines added, {edit['removed']} lines removed"
    )
    by_class = connection.execute(
        "SELECT command_class, COUNT(*) AS n FROM command WHERE session_id = ?"
        " GROUP BY command_class ORDER BY n DESC, command_class",
        (session_id,),
    ).fetchall()
    lines.append(f"  commands (command, fact version {edits.COMMAND_FACT_VERSION}, trust medium)")
    lines.append(
        "    by class: " + (", ".join(f"{r['command_class']} {r['n']}" for r in by_class) or "none")
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
    rows = connection.execute(
        "SELECT COALESCE(rel_path, file_path, '?') AS path, COUNT(*) AS n,"
        " SUM(lines_added) AS added, SUM(lines_removed) AS removed FROM edit"
        " WHERE session_id = ? GROUP BY path ORDER BY added DESC, path",
        (session_id,),
    ).fetchall()
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
        "high for in_session and git_ai_note, medium for line_match",
    )
    rows = connection.execute(
        "SELECT a.commit_hash, a.method, a.rank, a.lines_matched, a.coverage, c.added_lines,"
        ' c.committer_at FROM attribution a LEFT JOIN "commit" c ON c.commit_hash = a.commit_hash'
        " WHERE a.session_id = ? ORDER BY c.committer_at, a.method, a.rank",
        (session_id,),
    ).fetchall()
    if not rows:
        lines.append("  none")
        return lines
    lines.append(
        f"  {'commit':<10} {'committed':<17} {'method':<13} {'rank':>4} {'matched':>8} "
        f"{'of':>6} {'coverage':>9}"
    )
    for row in rows:
        coverage = "-" if row["coverage"] is None else f"{row['coverage'] * 100:.0f}%"
        lines.append(
            f"  {row['commit_hash'][:10]:<10} {(row['committer_at'] or '')[:17]:<17} "
            f"{row['method']:<13} {row['rank']:>4} {row['lines_matched']:>8} "
            f"{row['added_lines'] if row['added_lines'] is not None else '?':>6} {coverage:>9}"
        )
    lines.append("  coverage is NULL, printed as -, when there is no line evidence at all.")
    return lines


def _hooks(connection: sqlite3.Connection, session_id: str) -> list[str]:
    """The hook timeline, per turn: the tree before the turn and after it."""
    try:
        rows = connection.execute(
            "SELECT event, ts, prompt_id, head, dirty_count FROM hook_event"
            " WHERE session_id = ? ORDER BY ts, event",
            (session_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
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
    rows = connection.execute(
        "SELECT path, source, size, generation FROM archive_file WHERE session_id = ?"
        " ORDER BY source, path",
        (session_id,),
    ).fetchall()
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


def _scalar(connection: sqlite3.Connection, query: str, session_id: str) -> int:
    return connection.execute(query, (session_id,)).fetchone()[0]
