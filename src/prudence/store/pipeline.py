"""The order the store is built in, in one place, so `ingest` and `rebuild` agree.

Six steps, and the order between them is the only thing this module knows. The
repositories come first because every later step needs to know which directories
belong to what, including directories that no longer exist. The archive comes next
because raw bytes are the truth, and Prudence's own hook spool is archived in the same
pass for the same reason. The parser reads the archive alone, and so does the spool
fold. Commits are harvested from the repositories, not from the agent. Attribution
joins the last two and is therefore last.

`ingest` runs all six; `rebuild` runs all but the archive, which is what makes a
parser change a rebuild rather than a migration.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from prudence import config as config_module
from prudence.store import archive, attribution, commits, derived, lines, repos, spool


@dataclass
class Result:
    archived: archive.IngestStats | None = None
    parsed: derived.BuildStats = field(default_factory=derived.BuildStats)
    hooks: spool.SpoolStats = field(default_factory=spool.SpoolStats)
    harvested: commits.HarvestStats = field(default_factory=commits.HarvestStats)
    attributed: attribution.AttributionStats = field(default_factory=attribution.AttributionStats)
    repositories: int = 0


def run(connection: sqlite3.Connection, config: config_module.Config, with_archive: bool) -> Result:
    """Build everything the store holds, from the sources each step is allowed to read."""
    result = Result()
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
    key = lines.load_key()
    result.harvested = commits.harvest(connection, repositories, key, config.levels)
    result.attributed = attribution.build(connection, repositories)
    return result
