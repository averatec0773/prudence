"""`prudence ingest`: copy new bytes into the archive, then rebuild what they mean.

Archiving and parsing are one command because they are one promise: after `ingest`,
what the agent wrote is in the archive and the tables agree with it. They are separate
functions because only the first is irreversible.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping

import click

from prudence import config as config_module
from prudence import hooks as hooks_module
from prudence.cli.render import size
from prudence.facts import registry as facts_registry
from prudence.paths import enabled_list_file
from prudence.reviews import first_look
from prudence.store import db, parse_pool, pipeline
from prudence.store import progress as progress_module

WORKERS_HELP = (
    "Processes that read archived files while parsing. Defaults to the number of cores"
    f" minus one, at most {parse_pool.MAX_DEFAULT_WORKERS}; 1 reads in this process."
)


def workers_option(function):
    """`--workers`, shared by `ingest` and `rebuild`."""
    return click.option(
        "--workers",
        type=click.IntRange(min=1),
        default=parse_pool.default_workers,
        show_default="cores minus one",
        help=WORKERS_HELP,
    )(function)


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Print what each step did as JSON.")
@click.option(
    "--progress",
    "show_progress",
    is_flag=True,
    help="Write one JSON progress line per step to stderr while the ingest runs.",
)
@workers_option
def ingest(as_json: bool, show_progress: bool, workers: int) -> None:
    """Record everything new from the enabled repositories."""
    config = config_module.load()
    if not config.repositories:
        raise click.UsageError(
            "No repository is enabled. Run `prudence init` to choose what is recorded."
        )
    try:
        with db.ingest_lock():
            _run(config, as_json, show_progress, workers)
    except db.Locked as error:
        raise click.ClickException(str(error)) from error


def progress_sink(enabled: bool) -> progress_module.Sink | None:
    """One JSON object per line on stderr, and nothing else there, or nobody listening.

    stderr rather than stdout because `--progress` has to work beside `--json`, and the
    summary on stdout is what a script parses. Shared with `prudence rebuild`, which
    reports the same steps without the archive.
    """
    if not enabled:
        return None

    def write(event: progress_module.Event) -> None:
        click.echo(json.dumps(event.as_dict()), err=True)

    return write


def _run(
    config: config_module.Config,
    as_json: bool = False,
    show_progress: bool = False,
    workers: int = 1,
) -> None:
    connection = db.connect()
    try:
        result = pipeline.run(
            connection,
            config,
            with_archive=True,
            progress=progress_sink(show_progress),
            workers=workers,
        )
        _refresh_enabled(connection)
        if as_json:
            click.echo(json.dumps(summary(result), indent=2, default=str))
            return
        for line in report(result) + first_look.after_ingest(connection):
            click.echo(line)
    finally:
        connection.close()


def summary(result: pipeline.Result) -> dict:
    """Every step's own statistics, as the dataclasses carry them.

    `report` below writes the same numbers as sentences. Nothing is reshaped on the way
    out: a step's dataclass is its answer, so a new counter reaches the JSON the moment
    it reaches the text. `dataclasses.asdict` is not used, because it rebuilds a
    `Counter` from its own items and turns `{'fact': 3}` into `{('fact', 3): 1}`.
    """
    return _plain(result)


def _plain(value):
    """A dataclass tree as plain JSON types, with every mapping key a string."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_plain(item) for item in value]
    return value


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
    if parsed.mode == "incremental":
        lines.append(
            f"Read {parsed.files_parsed} of {parsed.files_total} archived files "
            f"({parsed.sessions_parsed} sessions) with {parsed.workers} workers; every other "
            "session's rows were kept from the last parse."
        )
    else:
        lines.append(
            f"Read all {parsed.files_total} archived files with {parsed.workers} workers "
            f"(a full parse: {parsed.full_reason})."
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
    turn_trees = result.turn_trees
    if turn_trees.sessions:
        lines.append(
            f"Turn trees: {turn_trees.turns} turns over {turn_trees.sessions} sessions with "
            f"hook data; {turn_trees.hand_edits} hand edits between turns found, "
            f"{turn_trees.elapsed:.1f} s."
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
        f"{harvested.excluded_paths} generated paths skipped; {harvested.kept} already stored"
        f" and kept, {harvested.dropped} no longer reachable and dropped),"
        f" {harvested.elapsed:.1f} s."
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
    if attributed.silent_matched:
        lines.append(
            f"{attributed.silent_matched} commits were matched to a `git commit` that printed "
            "no hash at all (the same timing and overlap rule)."
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
    fates = result.outcomes
    lines.append(
        f"Outcomes: {fates.lines} attributed lines of {fates.commits} commits followed to "
        f"7, 30 and 90 days and to HEAD ({fates.blamed_paths} files blamed, "
        f"{fates.reworked} lines reworked; {fates.marks_measured} marks read from git, "
        f"{fates.marks_kept} kept from an earlier run), {fates.elapsed:.1f} s."
    )
    if fates.sampled_repositories:
        lines.append(
            f"{fates.sampled_commits} commits were left out of the outcome sample in "
            f"{fates.sampled_repositories} repositories (deterministic by commit hash, so a "
            "rebuild draws the same sample)."
        )
    if fates.bot_commits:
        lines.append(
            f"{fates.bot_commits} commits are by a robot (dependabot and the like) and were "
            f"left out of the multi-author guard; {fates.identities} author identities are "
            "yours (they committed inside a session, or are a repository's majority author)."
        )
    for repo_key, guard in sorted(fates.suppressed.items()):
        lines.append(f"Outcomes suppressed for {repo_key}: {guard.note()}.")
    facts = result.facts
    lines.append(
        f"Behaviour facts: {facts.rows} rows over {facts.sessions} sessions "
        f"({len(facts_registry.FACTS)} facts), {facts.labels} purpose labels "
        f"({len(facts_registry.LABELS)} label rules), {facts.elapsed:.1f} s."
    )
    joined = result.observations
    lines.append(
        f"Observations: {joined.rows} in {joined.repositories} projects and {joined.pooled} "
        f"pooled over all of them, from {joined.sessions} sessions with lines that could be "
        f"followed, {joined.elapsed:.1f} s."
    )
    return lines
