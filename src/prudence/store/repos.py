"""Which repository a directory belongs to, including directories that are gone.

A path is the weakest thing in the record. Claude Desktop runs each of its sessions in
a throwaway worktree under `<repository>/.claude/worktrees/<adjective-surname-hash>`
and removes it afterwards, so by the time Prudence reads the transcript the working
directory no longer exists and `git` cannot be asked anything about it. On the
founder's machine that is 33 of the 35 sessions that resolve to nothing, all of them
under exactly that pattern, which is why the pattern is worth knowing by name.

So resolution is a ladder, tried in order, and the rung that answered is recorded in
`session.notes` so no later number can quietly rest on a guess:

1. the directory still exists and git names a repository we enabled;
2. the directory is under a worktree we know, including one recorded before it vanished;
3. the directory matches the Desktop worktree pattern of an enabled repository;
4. the transcript names a branch and the parent directory carries the repository's name;
5. nothing: the session stays unassigned and is counted in `prudence status`.

Worktree roots learned this way are written back to the `repository` row, so the next
run recognises the same path without re-deriving it, and so an edit made inside a
vanished worktree can still be made relative to the repository it belonged to.

Only read-only git commands are used.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from prudence import config as config_module
from prudence.store import progress as progress_module
from prudence.store.identity import identify

FACT_VERSION = 3

DESKTOP_WORKTREE_PARENTS = (".claude/worktrees", "worktrees")

# `outcomes_suppressed` and its note are written by `store/outcomes.py`, not here: a
# repository where other people commit gets no survival facts, and the flag lives beside
# the repository it is about so that every surface reads one row rather than joining a
# second table. The note carries the counts behind the decision, so a surface can say
# how many commits of how many were by somebody else instead of only that some were.
SCHEMA = """
CREATE TABLE IF NOT EXISTS repository(
    repo_key TEXT PRIMARY KEY,
    name TEXT,
    root_commits TEXT,
    remote_url TEXT,
    common_dir TEXT,
    toplevel TEXT,
    worktrees TEXT,
    outcomes_suppressed INTEGER NOT NULL DEFAULT 0,
    outcomes_suppressed_note TEXT,
    fact_version INTEGER NOT NULL
)
"""


@dataclass
class Repository:
    """One enabled repository and every directory its work has been seen in."""

    repo_key: str
    name: str
    root_commits: tuple[str, ...] = ()
    remote_url: str | None = None
    common_dir: str | None = None
    toplevel: str | None = None
    worktrees: set[str] = field(default_factory=set)

    @property
    def roots(self) -> list[str]:
        """Every directory a file of this repository can sit under, longest first."""
        roots = set(self.worktrees)
        if self.toplevel:
            roots.add(self.toplevel)
        return sorted(roots, key=len, reverse=True)


@dataclass(frozen=True)
class Match:
    """The repository a working directory belongs to, and how we know."""

    repo_key: str | None
    method: str


def build(
    connection: sqlite3.Connection,
    config: config_module.Config,
    progress: progress_module.Step | None = None,
) -> list[Repository]:
    """Refresh the `repository` table from the config plus git's own worktree list."""
    progress = progress or progress_module.silent()
    connection.execute(SCHEMA)
    known = {row.repo_key: row for row in read(connection)}
    repositories: list[Repository] = []
    progress.start(len(config.repositories), "repositories")
    for entry in config.repositories.values():
        progress.advance(label=f"Reading {entry.name}")
        previous = known.get(entry.key)
        common_dir = entry.common_dir or (previous.common_dir if previous else None)
        toplevel = _toplevel(common_dir)
        worktrees = set(previous.worktrees) if previous else set()
        worktrees.update(worktree_roots(common_dir))
        if toplevel:
            worktrees.add(toplevel)
        repositories.append(
            Repository(
                repo_key=entry.key,
                name=entry.name,
                root_commits=entry.root_commits,
                remote_url=entry.remote,
                common_dir=common_dir,
                toplevel=toplevel or (previous.toplevel if previous else None),
                worktrees=worktrees,
            )
        )
    # Dropped rather than altered: every column here is derived from the config, from
    # git and from the worktree roots just read back into memory, so a schema change is
    # a rebuild and never a migration (architecture rule 1). One transaction, so a crash
    # between the two statements cannot lose the learned worktree roots.
    connection.execute("BEGIN")
    try:
        connection.execute("DROP TABLE IF EXISTS repository")
        write(connection, repositories)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return repositories


def read(connection: sqlite3.Connection) -> list[Repository]:
    """The repositories as last recorded, or an empty list before the first build."""
    try:
        rows = list(connection.execute("SELECT * FROM repository"))
    except sqlite3.OperationalError:
        return []
    return [
        Repository(
            repo_key=row["repo_key"],
            name=row["name"],
            root_commits=tuple(_json_list(row["root_commits"])),
            remote_url=row["remote_url"],
            common_dir=row["common_dir"],
            toplevel=row["toplevel"],
            worktrees=set(_json_list(row["worktrees"])),
        )
        for row in rows
    ]


def write(connection: sqlite3.Connection, repositories: list[Repository]) -> None:
    """Store the repositories, keeping every worktree path either side already knew.

    Every column is named rather than passed positionally, so that rewriting a
    repository row never silently clears the suppression flag or its note, both of
    which `store/outcomes.py` writes.
    """
    connection.execute(SCHEMA)
    connection.executemany(
        "INSERT OR REPLACE INTO repository"
        " (repo_key, name, root_commits, remote_url, common_dir, toplevel, worktrees,"
        " fact_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                repository.repo_key,
                repository.name,
                json.dumps(sorted(repository.root_commits)),
                repository.remote_url,
                repository.common_dir,
                repository.toplevel,
                json.dumps(sorted(repository.worktrees)),
                FACT_VERSION,
            )
            for repository in repositories
        ],
    )


def worktree_roots(common_dir: str | None) -> list[str]:
    """Every working tree git currently knows about for this repository."""
    if not common_dir:
        return []
    directory = str(Path(common_dir).parent) if Path(common_dir).name == ".git" else common_dir
    output = _git(directory, "worktree", "list", "--porcelain")
    if output is None:
        return []
    return [
        line[len("worktree ") :].strip()
        for line in output.splitlines()
        if line.startswith("worktree ")
    ]


class Resolver:
    """Turns a working directory into a repository, and an absolute path into a relative one."""

    def __init__(self, repositories: list[Repository]) -> None:
        self.repositories = {repository.repo_key: repository for repository in repositories}
        self.discovered: set[str] = set()

    @property
    def keys(self) -> set[str]:
        return set(self.repositories)

    def resolve(self, cwd: str | None, git_branch: str | None = None) -> Match:
        """Which repository a session worked in, and by which of the rules.

        The Desktop pattern is tried before the list of known worktrees, although both
        are the same rung: once a pattern root has been learned it is also a known
        worktree, and the more specific answer is the more useful one to record.
        """
        if not cwd:
            return Match(None, "unassigned")
        identity = identify(cwd)
        if identity is not None and identity.key in self.repositories:
            return Match(identity.key, "cwd")
        pattern = self._by_pattern(cwd)
        if pattern is not None:
            return pattern
        for repository in self.repositories.values():
            if any(_under(root, cwd) for root in repository.roots):
                return Match(repository.repo_key, "worktree")
        if git_branch:
            parent = Path(cwd).parent.name
            for repository in self.repositories.values():
                if repository.toplevel and Path(repository.toplevel).name == parent:
                    return Match(repository.repo_key, "branch-and-name")
        return Match(None, "unassigned")

    def repo_of_path(self, path: str | None) -> tuple[str | None, str | None]:
        """The repository an edited file belongs to, by longest known root, and its path in it."""
        if not path:
            return None, None
        best: tuple[str | None, str | None, int] = (None, None, -1)
        for repository in self.repositories.values():
            for root in repository.roots:
                if _under(root, path) and len(path) > len(root) > best[2]:
                    best = (repository.repo_key, path[len(root) :].lstrip("/"), len(root))
        return best[0], best[1]

    def relative_path(self, repo_key: str | None, path: str | None) -> str | None:
        """A file path as the repository sees it, whichever worktree it was edited in."""
        if not repo_key or not path:
            return None
        repository = self.repositories.get(repo_key)
        if repository is None:
            return None
        for root in repository.roots:
            if _under(root, path) and len(path) > len(root):
                return path[len(root) :].lstrip("/")
        return None

    def _by_pattern(self, cwd: str) -> Match | None:
        """Claude Desktop's own worktrees, whose names are random and whose paths are gone."""
        for repository in self.repositories.values():
            for base in self._pattern_bases(repository):
                if not _under(base, cwd) or len(cwd) <= len(base):
                    continue
                name = cwd[len(base) :].lstrip("/").split("/")[0]
                if not name:
                    continue
                root = f"{base}/{name}"
                repository.worktrees.add(root)
                self.discovered.add(repository.repo_key)
                return Match(repository.repo_key, "worktree-pattern")
        return None

    @staticmethod
    def _pattern_bases(repository: Repository) -> list[str]:
        bases = []
        if repository.toplevel:
            bases.append(f"{repository.toplevel}/{DESKTOP_WORKTREE_PARENTS[0]}")
        if repository.common_dir:
            bases.append(f"{repository.common_dir}/{DESKTOP_WORKTREE_PARENTS[1]}")
        return bases


def resolver(
    connection: sqlite3.Connection,
    config: config_module.Config | None = None,
    progress: progress_module.Step | None = None,
) -> Resolver:
    """A resolver over the recorded repositories, refreshed from the config when given."""
    repositories = build(connection, config, progress) if config is not None else read(connection)
    return Resolver(repositories)


def save_discoveries(connection: sqlite3.Connection, instance: Resolver) -> int:
    """Persist worktree roots learned during a run, so the next run knows them at once."""
    if not instance.discovered:
        return 0
    changed = [instance.repositories[key] for key in sorted(instance.discovered)]
    write(connection, changed)
    count = len(changed)
    instance.discovered.clear()
    return count


def _toplevel(common_dir: str | None) -> str | None:
    if not common_dir:
        return None
    path = Path(common_dir)
    directory = str(path.parent) if path.name == ".git" else common_dir
    identity = identify(directory)
    if identity is not None:
        return identity.toplevel
    return str(path.parent) if path.name == ".git" else None


def _under(root: str, path: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _json_list(value: object) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
    except ValueError:
        return []
    return [item for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _git(directory: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", directory, *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None
