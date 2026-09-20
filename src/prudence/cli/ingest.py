"""`prudence ingest`: copy new bytes into the archive, then rebuild what they mean.

Archiving and parsing are one command because they are one promise: after `ingest`,
what the agent wrote is in the archive and the tables agree with it. They are separate
functions because only the first is irreversible.
"""

from __future__ import annotations

import click

from prudence import config as config_module
from prudence import hooks as hooks_module
from prudence.cli.render import size
from prudence.paths import enabled_list_file
from prudence.store import db, pipeline


@click.command()
def ingest() -> None:
    """Record everything new from the enabled repositories."""
    config = config_module.load()
    if not config.repositories:
        raise click.UsageError(
            "No repository is enabled. Run `prudence init` to choose what is recorded."
        )
    try:
        with db.ingest_lock():
            _run(config)
    except db.Locked as error:
        raise click.ClickException(str(error)) from error


def _run(config: config_module.Config) -> None:
    connection = db.connect()
    try:
        result = pipeline.run(connection, config, with_archive=True)
        _refresh_enabled(connection)
        for line in report(result):
            click.echo(line)
    finally:
        connection.close()


def _refresh_enabled(connection) -> None:
    """Keep the hook's enabled list in step with the config, once the hook is installed.

    A repository enabled after `hooks install` would otherwise be invisible to the hook
    until the user reinstalled it, and a repository disabled after it would keep being
    recorded, which is the one direction that must never happen silently.
    """
    if not enabled_list_file().exists():
        return
    hooks_module.write_enabled(hooks_module.enabled_roots(connection))


def report(result: pipeline.Result) -> list[str]:
    """What each step of the pipeline did, in the order it did it."""
    lines = []
    archived = result.archived
    if archived is not None:
        lines.append(
            f"Archived: {archived.files_seen} files seen, {archived.new_files} new, "
            f"{archived.rearchived_files} rewritten, {archived.unchanged_files} unchanged, "
            f"{size(archived.new_bytes)} new ({archived.new_bytes} bytes), "
            f"{archived.elapsed:.1f} s."
        )
        if archived.missing_files:
            lines.append(f"{archived.missing_files} files disappeared while reading; skipped.")
    parsed = result.parsed
    lines.append(
        f"Parsed: {parsed.sessions} sessions, {parsed.records} records, "
        f"{parsed.turns} turns, {parsed.tool_calls} tool calls, {parsed.edits} edits, "
        f"{parsed.commands} commands, {parsed.unknown_types} unknown record types, "
        f"{parsed.elapsed:.1f} s."
    )
    lines.append(
        f"Tokens: {parsed.usage_tokens} over {parsed.usage_rows} API responses "
        "(input, output and cache together; a response is counted once)."
    )
    hooks = result.hooks
    if hooks.files or hooks.events:
        lines.append(
            f"Hook events: {hooks.events} folded from {hooks.files} spool files "
            f"({hooks.duplicates} already recorded, {hooks.unreadable} unreadable), "
            f"{hooks.elapsed:.1f} s."
        )
    recovered = {
        method: count
        for method, count in parsed.mapping_methods.items()
        if method not in ("cwd", "unassigned")
    }
    if recovered or parsed.unassigned_sessions:
        detail = ", ".join(f"{count} by {method}" for method, count in sorted(recovered.items()))
        lines.append(
            f"Sessions mapped to a repository the hard way: {detail or 'none'}; "
            f"{parsed.unassigned_sessions} still unassigned."
        )
    harvested = result.harvested
    lines.append(
        f"Commits: {harvested.commits + harvested.merges} harvested from "
        f"{harvested.repositories} repositories ({harvested.merges} of them merges, which "
        f"carry no lines; {harvested.added_lines} added lines, "
        f"{harvested.excluded_paths} generated paths skipped), {harvested.elapsed:.1f} s."
    )
    attributed = result.attributed
    lines.append(
        f"Attributed: {attributed.commits_attributed} commits "
        f"({attributed.in_session} in session, {attributed.git_ai_note} by git-ai note, "
        f"{attributed.line_match_winners} by line match "
        f"from {attributed.line_match_candidates} candidates), {attributed.elapsed:.1f} s."
    )
    if attributed.reidentified:
        lines.append(
            f"{attributed.reidentified} rewritten commits were re-identified from the session "
            "that made them (timing plus overlapping lines; the printed hash is gone)."
        )
    if attributed.unresolved_hashes or attributed.unreadable_notes:
        lines.append(
            f"{attributed.unresolved_hashes} commit hashes named in a session no longer "
            f"resolve; {attributed.unreadable_notes} git-ai notes were not in the expected "
            "format and were skipped."
        )
    labels = attributed.by_confidence
    lines.append(
        f"Confidence: {labels.get('fact', 0)} fact, {labels.get('inferred', 0)} inferred, "
        f"{labels.get('uncertain', 0)} uncertain attribution rows."
    )
    return lines
