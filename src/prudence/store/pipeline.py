"""The order the store is built in, in one place, so `ingest` and `rebuild` agree.

Nine steps, and the order between them is the only thing this module knows. The
repositories come first because every later step needs to know which directories
belong to what, including directories that no longer exist. The archive comes next
because raw bytes are the truth, and Prudence's own hook spool is archived in the same
pass for the same reason. The parser reads the archive alone, and so does the spool
fold. Turn trees and hand edits come right after the spool fold, because they read
`hook_event` alone and nothing later needs them. Commits are harvested from the
repositories, not from the agent. Attribution joins the last two. Outcomes come next,
because they ask what became of the lines of the commits attribution has just decided
to count. Behaviour facts (`facts/registry.py`) come next to last, because several of
them read across `command`, `attribution`, `hook_event`/`hand_edit` and `session`
together and none of the earlier steps need anything a fact produces. Observations are
last of all, because they are the join of the two steps before them: a behaviour fact on
one side and what became of the lines on the other.

`ingest` runs all nine; `rebuild` runs all but the archive, which is what makes a
parser change a rebuild rather than a migration. After the last step, and counting as
none of them, `store/app_views.install_app_views` recreates the `app_*` read contract
over whatever the nine have just written.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

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
    observations,
    outcomes,
    repos,
    spool,
)


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


def run(connection: sqlite3.Connection, config: config_module.Config, with_archive: bool) -> Result:
    """Build everything the store holds, from the sources each step is allowed to read."""
    result = Result()
    # The `app_*` read contract comes down before the first step and goes back up after
    # the last one: `derived.build` renames tables into place, and SQLite refuses a
    # rename while a view in the schema points at a table the swap has dropped.
    app_views.drop_app_views(connection)
    resolver = repos.resolver(connection, config)
    repositories = list(resolver.repositories.values())
    result.repositories = len(repositories)

    if with_archive:
        targets = archive.collect_targets(resolver.keys, resolver=resolver)
        targets += archive.spool_targets()
        result.archived = archive.archive(connection, targets)
        repos.save_discoveries(connection, resolver)

    result.parsed = derived.build(connection, config.levels, resolver)
    result.hooks = spool.build(connection, resolver)
    result.turn_trees = hand_edits.build(connection)
    key = lines.load_key()
    result.harvested = commits.harvest(connection, repositories, key, config.levels)
    result.attributed = attribution.build(connection, repositories)
    result.outcomes = outcomes.build(connection, repositories, key)
    result.facts = facts_registry.build(connection)
    result.observations = observations.build(connection)
    # Last of all, and not a step: the `app_*` views are a read contract over the tables
    # the nine steps have just finished writing. They are recreated here rather than
    # migrated because `derived.build` swaps its tables by renaming, which leaves a view
    # over the old name pointing at nothing.
    app_views.install_app_views(connection)
    return result
