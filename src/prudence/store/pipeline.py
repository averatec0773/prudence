"""The order the store is built in, in one place, so `ingest` and `rebuild` agree.

Ten steps that write the store and one that rebuilds the read contract over it, and the
order between them is the only thing this module knows. The repositories come first
because every later step needs to know which directories belong to what, including
directories that no longer exist. The archive comes next because raw bytes are the
truth, and Prudence's own hook spool is archived in the same pass for the same reason.
The parser reads the archive alone, and so does the spool fold. Turn trees and hand
edits come right after the spool fold, because they read `hook_event` alone and nothing
later needs them. Commits are harvested from the repositories, not from the agent.
Attribution joins the last two. Outcomes come next, because they ask what became of the
lines of the commits attribution has just decided to count. Behaviour facts
(`facts/registry.py`) come next to last, because several of them read across `command`,
`attribution`, `hook_event`/`hand_edit` and `session` together and none of the earlier
steps need anything a fact produces. Observations are last of the steps that derive
anything, because they are the join of the two before them: a behaviour fact on one side
and what became of the lines on the other.

`ingest` runs all eleven; `rebuild` runs all but the archive, which is what makes a
parser change a rebuild rather than a migration. They differ in one more way: an ingest
parses only the sessions whose inputs moved, harvests only the commits it has not
stored and keeps the outcome marks already measured, where a rebuild parses, harvests
and measures everything; `tests/test_incremental.py` holds the two to the same tables
(ARCHITECTURE.md, "What an ingest reads again"). The last step derives nothing: it is
`store/app_views.replace_app_views`, which puts the `app_*` read contract back over
whatever the earlier steps have just written. It is a step here because a client
watching `--progress` waits for it like any other.

The contract stays up while the store is rewritten. It used to come down before the
first step, because `derived.build` and three other steps swap their tables by renaming
and, since SQLite 3.25, a rename walks every view in the schema and fails on one whose
table the swap has just dropped. An ingest that died in between then left a store with
no views at all and every surface refusing to render. So the rename is put back into its
older behaviour for the length of the run (`PRAGMA legacy_alter_table`), which leaves a
view's text alone; each swap drops `x` and renames `x__new` to `x`, so the name a view
holds exists again by the time anything reads it. The views themselves are replaced once
at the end, inside one transaction, so a store always has either the previous contract
or the new one.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from prudence import config as config_module
from prudence.facts import registry as facts_registry
from prudence.store import (
    app_views,
    archive,
    attribution,
    commits,
    derived,
    hand_edits,
    lines,
    meta,
    observations,
    outcomes,
    repos,
    spool,
)
from prudence.store import progress as progress_module

# Every step, in the order it runs. `rebuild` runs the same list without `archive`.
ARCHIVE = "archive"
STEPS: tuple[str, ...] = (
    "repositories",
    ARCHIVE,
    "parse",
    "hooks",
    "turn_trees",
    "commits",
    "attribution",
    "outcomes",
    "facts",
    "observations",
    "views",
)

# What a step is called in a progress event before it knows anything more specific. A
# step that works repository by repository replaces it with the project's own name.
LABELS: dict[str, str] = {
    "repositories": "Reading repositories",
    ARCHIVE: "Archiving",
    "parse": "Parsing transcripts",
    "hooks": "Folding hook events",
    "turn_trees": "Building turn trees",
    "commits": "Harvesting commits",
    "attribution": "Attributing commits",
    "outcomes": "Following lines",
    "facts": "Computing behaviour facts",
    "observations": "Joining behaviour to outcomes",
    "views": "Rebuilding the app views",
}


# SQLite's page cache for the run's connection, in KiB. The default is 2 MiB, and the
# commit harvest and the parse write into primary keys and indexes of tens to hundreds of
# megabytes in no particular order, so with the default nearly every row inserted read
# its pages back from disk. The cache is taken as pages are used and freed at the end.
CACHE_KIB = 256 * 1024

# Where the last run of each command says what it did, in `meta`, which no step rebuilds.
LAST_RUN_KEYS = {True: "last_ingest", False: "last_rebuild"}


@dataclass
class Result:
    archived: archive.IngestStats | None = None
    parsed: derived.BuildStats = field(default_factory=derived.BuildStats)
    hooks: spool.SpoolStats = field(default_factory=spool.SpoolStats)
    turn_trees: hand_edits.BuildStats = field(default_factory=hand_edits.BuildStats)
    harvested: commits.HarvestStats = field(default_factory=commits.HarvestStats)
    attributed: attribution.AttributionStats = field(default_factory=attribution.AttributionStats)
    outcomes: outcomes.OutcomeStats = field(default_factory=outcomes.OutcomeStats)
    facts: facts_registry.BuildStats = field(default_factory=facts_registry.BuildStats)
    observations: observations.ObservationStats = field(
        default_factory=observations.ObservationStats
    )
    repositories: int = 0
    # Wall-clock seconds per step, in the order they ran.
    steps: dict[str, float] = field(default_factory=dict)


def run(
    connection: sqlite3.Connection,
    config: config_module.Config,
    with_archive: bool,
    progress: progress_module.Sink | None = None,
    workers: int = 1,
) -> Result:
    """Build everything the store holds, from the sources each step is allowed to read.

    `ingest` (with the archive) parses incrementally; `rebuild` reads everything.
    `workers` is how many processes read archived files during the parse.
    """
    result = Result()
    steps = STEPS if with_archive else tuple(name for name in STEPS if name != ARCHIVE)
    reporter = progress_module.Run(progress, steps, LABELS)
    # The swaps below rename tables the `app_*` views name; see the module docstring for
    # why that is allowed to happen under them rather than after they are taken down.
    connection.execute("PRAGMA legacy_alter_table=ON")
    connection.execute(f"PRAGMA cache_size=-{CACHE_KIB}")
    try:
        with reporter.step("repositories") as step:
            resolver = repos.resolver(connection, config, progress=step)
        repositories = list(resolver.repositories.values())
        result.repositories = len(repositories)
        names = {repository.repo_key: repository.name for repository in repositories}

        if with_archive:
            with reporter.step(ARCHIVE) as step:
                targets = archive.collect_targets(resolver.keys, resolver=resolver)
                targets += archive.spool_targets()
                result.archived = archive.archive(connection, targets, names, progress=step)
            repos.save_discoveries(connection, resolver)

        with reporter.step("parse") as step:
            result.parsed = derived.build(
                connection,
                config.levels,
                resolver,
                progress=step,
                incremental=with_archive,
                workers=workers,
            )
        with reporter.step("hooks") as step:
            result.hooks = spool.build(connection, resolver, progress=step)
        with reporter.step("turn_trees") as step:
            result.turn_trees = hand_edits.build(connection, progress=step)
        key = lines.load_key()
        with reporter.step("commits") as step:
            result.harvested = commits.harvest(
                connection, repositories, key, config.levels, progress=step, keep=with_archive
            )
        with reporter.step("attribution") as step:
            result.attributed = attribution.build(connection, repositories, progress=step)
        with reporter.step("outcomes") as step:
            result.outcomes = outcomes.build(
                connection,
                repositories,
                key,
                progress=step,
                keep_marks=with_archive,
                workers=workers,
            )
        with reporter.step("facts") as step:
            result.facts = facts_registry.build(connection, progress=step)
        with reporter.step("observations") as step:
            result.observations = observations.build(connection, progress=step)
    finally:
        connection.execute("PRAGMA legacy_alter_table=OFF")
    # Last of all, and deriving nothing: the `app_*` views are a read contract over the
    # tables the steps above have just finished writing, and they are replaced in one
    # transaction so that a store never holds half a contract.
    with reporter.step("views") as step:
        app_views.replace_app_views(connection, progress=step)
    result.steps = dict(reporter.elapsed)
    meta.set_meta(connection, LAST_RUN_KEYS[with_archive], json.dumps(_run_record(result)))
    return result


def _run_record(result: Result) -> dict:
    """What `prudence status` says about the last ingest or rebuild: what was read, how long."""
    parsed, fates = result.parsed, result.outcomes
    return {
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seconds": round(sum(result.steps.values()), 3),
        "steps": result.steps,
        "workers": parsed.workers,
        "parse_mode": parsed.mode,
        "full_reason": parsed.full_reason,
        "files_parsed": parsed.files_parsed,
        "files_skipped": parsed.files_skipped,
        "sessions_parsed": parsed.sessions_parsed,
        "marks_measured": fates.marks_measured,
        "marks_kept": fates.marks_kept,
    }


def last_runs(connection: sqlite3.Connection) -> dict[str, dict | None]:
    """The records `run` left for the last ingest and the last rebuild, or None each."""
    found: dict[str, dict | None] = {}
    for key in LAST_RUN_KEYS.values():
        value = meta.get_meta(connection, key)
        found[key] = json.loads(value) if value else None
    return found
