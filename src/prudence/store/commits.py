"""Commits, as the right-hand side of attribution: what each one really added.

Harvested from the repository itself, never from the agent, and only with read-only
commands. Every reachable commit on every branch is read once with `-p -U0`, because a
commit that is not in the store cannot be attributed and a branch that was never merged
is still work the developer did.

Three decisions come from the attribution spikes. Generated and vendored paths are
excluded, because a lock file adds thousands of lines nobody wrote and would drown
every coverage figure. The committer date is stored in UTC, because an edit made in one
timezone has to be comparable with a commit made in another. And the patch id and tree
are stored beside the hash, because round two measured that a third of the hashes the
agent printed no longer name a reachable object: rebases and squashes rewrite them, and
the patch id is what lets a rewritten commit be recognised as the same work.

Nothing of the diff is stored. A line becomes a keyed hash through `store.lines`, the
same function the edits went through, or the two sides would never meet.

Fact version 2 added `is_bot`. A robot's commits are not somebody else's work in the
sense the multi-author guard cares about: `dependabot` bumping a dependency says nothing
about who writes this repository's code, and on the founder's own repository it was
enough to suppress every outcome fact. The decision is made here, during the harvest,
on the raw author name and email, because those are the only place the words
`dependabot` or `[bot]` exist; only the hash of the email is stored, as before.

A commit is immutable: its hash names its tree, its parents, its author and its dates,
so what it added is the same on every run. `prudence ingest` therefore reads only the
commits it has not stored yet, and deletes the stored ones no longer reachable from any
ref (a rebase, a deleted branch); `git rev-list --all` says which are which. It reads a
repository whole again when its capture level, the line-hash key or this module's fact
version changed, because each of those changes what a stored row would say. `prudence
rebuild` reads every repository whole, as it always did. Each repository's rows are
replaced in one transaction.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from prudence.store import lines as line_module
from prudence.store import meta as meta_module
from prudence.store import progress as progress_module
from prudence.store.repos import Repository

FACT_VERSION = 2

# Where the harvest remembers, per repository, what its stored rows were read under.
POLICY_KEY = "harvest_policy"

RECORD = "\x01"
FIELD = "\x1f"
LOG_FORMAT = f"{RECORD}%H{FIELD}%cI{FIELD}%aI{FIELD}%T{FIELD}%ae{FIELD}%an{FIELD}%P"

# An author name or email carrying one of these is a robot, not a colleague. Matched
# against the raw fields at harvest time, lowercased; the store keeps only the hash.
BOT_MARKERS = ("dependabot", "[bot]", "github-actions", "renovate")

# Paths whose content is produced rather than written. Approximate in both directions,
# as the spike said, but leaving them in makes every coverage number meaningless.
GENERATED = re.compile(
    r"(^|/)(node_modules|vendor|dist|build|out|coverage|__pycache__|\.next|\.nuxt|target)/"
    r"|(^|/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb"
    r"|poetry\.lock|uv\.lock|Pipfile\.lock|Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock"
    r"|Podfile\.lock|flake\.lock|pubspec\.lock)$"
    r"|\.min\.[^/]+$|\.map$|\.lock$"
    r"|\.(png|jpe?g|gif|webp|ico|pdf|zip|gz|tgz|bz2|xz|7z|jar|war|wasm|so|dylib|dll|exe"
    r"|o|a|class|pyc|woff2?|ttf|eot|otf|mp[34]|mov|avi|db|sqlite3?|bin|dat)$",
    re.IGNORECASE,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS "commit"(
    commit_hash TEXT PRIMARY KEY,
    repo_key TEXT,
    committer_at TEXT,
    author_at TEXT,
    patch_id TEXT,
    tree TEXT,
    added_lines INTEGER NOT NULL DEFAULT 0,
    files_changed INTEGER NOT NULL DEFAULT 0,
    is_merge INTEGER NOT NULL DEFAULT 0,
    author_email_hash TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    fact_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS commit_repo ON "commit"(repo_key, committer_at);
CREATE TABLE IF NOT EXISTS commit_line(
    commit_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    line_hash TEXT NOT NULL,
    PRIMARY KEY (commit_hash, path, line_hash)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS commit_line_hash ON commit_line(line_hash);
"""


@dataclass
class HarvestStats:
    repositories: int = 0
    commits: int = 0
    merges: int = 0
    added_lines: int = 0
    excluded_paths: int = 0
    unreadable: int = 0
    # Commits already stored and still reachable, not read again; and stored ones
    # no longer reachable, deleted.
    kept: int = 0
    dropped: int = 0
    elapsed: float = 0.0


@dataclass
class _Commit:
    commit_hash: str
    repo_key: str
    committer_at: str | None
    author_at: str | None
    tree: str | None
    author_email_hash: str | None
    is_bot: int = 0
    is_merge: int = 0
    paths: set[str] | None = None


def harvest(
    connection: sqlite3.Connection,
    repositories: list[Repository],
    key: bytes,
    levels: dict[str, str] | None = None,
    progress: progress_module.Step | None = None,
    keep: bool = False,
) -> HarvestStats:
    """Read every reachable commit of every enabled repository into the store.

    At `metadata-only` the commits are counted and dated but their lines are not
    hashed into the store. A keyed hash is not readable, but a hash of every line an
    employer's repository ever gained is more than the shape that level promises, and
    without the left-hand side there would be nothing to match it against anyway.

    `keep` (what `ingest` asks for) keeps the commits already stored, as the module
    docstring says; without it every repository is read whole.
    """
    started = time.monotonic()
    stats = HarvestStats()
    levels = levels or {}
    progress = progress or progress_module.silent()
    _ensure_schema(connection)
    policies = json.loads(meta_module.get_meta(connection, POLICY_KEY) or "{}")
    digest = hashlib.sha256(key).hexdigest()[:12]
    progress.start(len(repositories), "repositories")
    for repository in repositories:
        progress.advance(label=f"Harvesting {repository.name}")
        directory = repository.toplevel
        if not directory:
            stats.unreadable += 1
            continue
        stats.repositories += 1
        keep_lines = levels.get(repository.repo_key, "full") == "full"
        policy = f"lines {keep_lines}; key {digest}; fact version {FACT_VERSION}"
        reachable = _reachable(directory)
        connection.execute("BEGIN IMMEDIATE")
        try:
            if keep and policies.get(repository.repo_key) == policy:
                stored = _stored(connection, repository.repo_key)
            else:
                _forget(connection, repository.repo_key)
                stored = set()
            gone = sorted(stored - set(reachable))
            _drop(connection, gone)
            stats.dropped += len(gone)
            stats.kept += len(stored) - len(gone)
            fresh = [commit for commit, merge in reachable.items() if not merge]
            merges = [commit for commit, merge in reachable.items() if merge]
            if stored:
                fresh = [commit for commit in fresh if commit not in stored]
                merges = [commit for commit in merges if commit not in stored]
            if fresh:
                patch_ids = _patch_ids(directory, fresh if stored else None)
                _read_commits(
                    connection,
                    repository,
                    directory,
                    key,
                    patch_ids,
                    stats,
                    keep_lines,
                    fresh if stored else None,
                )
            if merges:
                _read_merges(connection, repository, directory, stats, merges if stored else None)
            policies[repository.repo_key] = policy
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    meta_module.set_meta(connection, POLICY_KEY, json.dumps(policies, sort_keys=True))
    stats.elapsed = time.monotonic() - started
    return stats


def _reachable(directory: str) -> dict[str, bool]:
    """Every commit reachable from any ref or HEAD, and whether it is a merge."""
    try:
        result = subprocess.run(
            ["git", "-C", directory, "rev-list", "--all", "--parents"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {}
    if result.returncode != 0:
        return {}
    found: dict[str, bool] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts:
            found[parts[0]] = len(parts) > 2
    return found


def _stored(connection: sqlite3.Connection, repo_key: str) -> set[str]:
    """The commits stored for one repository. A fact version change never reaches here: it
    changes the repository's policy, and a changed policy reads the repository whole."""
    return {
        row[0]
        for row in connection.execute(
            'SELECT commit_hash FROM "commit" WHERE repo_key = ?', (repo_key,)
        )
    }


def _drop(connection: sqlite3.Connection, hashes: list[str]) -> None:
    """Commits no longer reachable, and the lines they added, out of the store."""
    for start in range(0, len(hashes), 400):
        batch = hashes[start : start + 400]
        marks = ", ".join("?" * len(batch))
        connection.execute(f"DELETE FROM commit_line WHERE commit_hash IN ({marks})", batch)
        connection.execute(f'DELETE FROM "commit" WHERE commit_hash IN ({marks})', batch)


def counts(connection: sqlite3.Connection) -> tuple[int, int]:
    """Commits and commit lines stored, or zeroes before the first harvest."""
    try:
        commits = connection.execute('SELECT COUNT(*) FROM "commit"').fetchone()[0]
        commit_lines = connection.execute("SELECT COUNT(*) FROM commit_line").fetchone()[0]
    except sqlite3.OperationalError:
        return 0, 0
    return commits, commit_lines


def utc(stamp: str | None) -> str | None:
    """Any ISO timestamp as UTC to the second, the one form everything is compared in."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _ensure_schema(connection: sqlite3.Connection) -> None:
    """Create the tables, dropping first when an older fact version wrote them.

    Architecture rule 1: a harvested table is rebuilt, never migrated. Every row here
    comes from `git log`, so a column this version writes and the stored table lacks is
    answered by harvesting again, which this run is about to do anyway.
    """
    wanted = {
        "commit_hash",
        "repo_key",
        "committer_at",
        "author_at",
        "patch_id",
        "tree",
        "added_lines",
        "files_changed",
        "is_merge",
        "author_email_hash",
        "is_bot",
        "fact_version",
    }
    found = {row[1] for row in connection.execute('PRAGMA table_info("commit")')}
    if found and found != wanted:
        connection.execute("DROP TABLE IF EXISTS commit_line")
        connection.execute('DROP TABLE IF EXISTS "commit"')
    connection.executescript(SCHEMA)


def _forget(connection: sqlite3.Connection, repo_key: str) -> None:
    connection.execute(
        "DELETE FROM commit_line WHERE commit_hash IN"
        ' (SELECT commit_hash FROM "commit" WHERE repo_key = ?)',
        (repo_key,),
    )
    connection.execute('DELETE FROM "commit" WHERE repo_key = ?', (repo_key,))


def _read_commits(
    connection: sqlite3.Connection,
    repository: Repository,
    directory: str,
    key: bytes,
    patch_ids: dict[str, str],
    stats: HarvestStats,
    keep_lines: bool,
    revisions: list[str] | None = None,
) -> None:
    """One streaming pass over the diffs, hashing added lines as they go past.

    `revisions` None reads every reachable commit; otherwise exactly those commits.
    """
    process = _log(
        directory, "--no-merges", "-p", "-U0", f"--format={LOG_FORMAT}", revisions=revisions
    )
    if process is None:
        stats.unreadable += 1
        return
    current: _Commit | None = None
    seen: set[tuple[str, str]] = set()
    path: str | None = None
    in_hunk = False
    pending: list[tuple[str, str, str]] = []
    assert process.stdout is not None
    for raw in process.stdout:
        line = raw.rstrip("\n")
        if line.startswith(RECORD):
            _flush(connection, current, seen, pending, patch_ids, stats)
            current = _parse_header(line, repository.repo_key)
            seen, path, in_hunk = set(), None, False
            continue
        if current is None:
            continue
        if line.startswith("diff --git "):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            path = _path(line[4:], stats)
        elif line.startswith("@@"):
            in_hunk = path is not None
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            path, in_hunk = None, False
        elif in_hunk and path is not None and line.startswith("+"):
            digest = line_module.hash_line(key, line[1:])
            if digest is not None and (path, digest) not in seen:
                seen.add((path, digest))
                if keep_lines:
                    pending.append((current.commit_hash, path, digest))
    _flush(connection, current, seen, pending, patch_ids, stats)
    process.stdout.close()
    process.wait()


def _read_merges(
    connection: sqlite3.Connection,
    repository: Repository,
    directory: str,
    stats: HarvestStats,
    revisions: list[str] | None = None,
) -> None:
    """Merges carry no lines of their own, but a commit missing from the store is a hole."""
    process = _log(directory, "--merges", f"--format={LOG_FORMAT}", revisions=revisions)
    if process is None:
        return
    assert process.stdout is not None
    rows = []
    for raw in process.stdout:
        line = raw.rstrip("\n")
        if not line.startswith(RECORD):
            continue
        commit = _parse_header(line, repository.repo_key)
        if commit is None:
            continue
        commit.is_merge = 1
        rows.append(_row(commit, None, 0, 0))
    process.stdout.close()
    process.wait()
    connection.executemany(
        'INSERT OR REPLACE INTO "commit" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows
    )
    stats.merges += len(rows)


def _flush(
    connection: sqlite3.Connection,
    commit: _Commit | None,
    seen: set[tuple[str, str]],
    pending: list[tuple[str, str, str]],
    patch_ids: dict[str, str],
    stats: HarvestStats,
) -> None:
    if commit is None:
        return
    paths = {path for path, _ in seen}
    connection.execute(
        'INSERT OR REPLACE INTO "commit" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        _row(commit, patch_ids.get(commit.commit_hash), len(seen), len(paths)),
    )
    if pending:
        connection.executemany("INSERT OR REPLACE INTO commit_line VALUES (?, ?, ?)", pending)
    stats.commits += 1
    stats.added_lines += len(seen)
    pending.clear()


def _row(commit: _Commit, patch_id: str | None, added: int, files: int) -> tuple:
    return (
        commit.commit_hash,
        commit.repo_key,
        commit.committer_at,
        commit.author_at,
        patch_id,
        commit.tree,
        added,
        files,
        commit.is_merge,
        commit.author_email_hash,
        commit.is_bot,
        FACT_VERSION,
    )


def is_bot(name: str | None, email: str | None) -> bool:
    """Whether the raw author fields name a robot rather than a person."""
    text = f"{name or ''} {email or ''}".lower()
    return any(marker in text for marker in BOT_MARKERS)


def _parse_header(line: str, repo_key: str) -> _Commit | None:
    fields = line[len(RECORD) :].split(FIELD)
    if len(fields) < 6 or len(fields[0]) < 7:
        return None
    email = fields[4].strip().lower()
    return _Commit(
        commit_hash=fields[0],
        repo_key=repo_key,
        committer_at=utc(fields[1]),
        author_at=utc(fields[2]),
        tree=fields[3] or None,
        author_email_hash=hashlib.sha256(email.encode()).hexdigest() if email else None,
        is_bot=int(is_bot(fields[5], email)),
    )


def _path(raw: str, stats: HarvestStats) -> str | None:
    """The post-image path of a diff, or None when it is deleted or generated."""
    text = raw.strip()
    if text in ("/dev/null", ""):
        return None
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].encode().decode("unicode_escape", "replace")
    if text.startswith("b/"):
        text = text[2:]
    text = text.split("\t")[0]
    if GENERATED.search(text):
        stats.excluded_paths += 1
        return None
    return text


def _patch_ids(directory: str, revisions: list[str] | None = None) -> dict[str, str]:
    """`git log -p | git patch-id` in one go: a stable id per commit, rewrites and all."""
    try:
        log = subprocess.Popen(
            ["git", "-C", directory, "log", *_which(revisions), "--no-merges", "-p", "-U0"],
            stdin=subprocess.PIPE if revisions is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        _feed(log, revisions, binary=True)
        ids = subprocess.Popen(
            ["git", "-C", directory, "patch-id", "--stable"],
            stdin=log.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return {}
    if log.stdout is not None:
        log.stdout.close()
    result: dict[str, str] = {}
    assert ids.stdout is not None
    for line in ids.stdout:
        parts = line.split()
        if len(parts) == 2:
            result[parts[1]] = parts[0]
    ids.stdout.close()
    ids.wait()
    log.wait()
    return result


def _log(directory: str, *args: str, revisions: list[str] | None = None) -> subprocess.Popen | None:
    try:
        process = subprocess.Popen(
            ["git", "-C", directory, "log", *_which(revisions), *args],
            stdin=subprocess.PIPE if revisions is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    _feed(process, revisions, binary=False)
    return process


def _which(revisions: list[str] | None) -> list[str]:
    """Every reachable commit, or exactly the commits named on standard input."""
    return ["--all"] if revisions is None else ["--no-walk=unsorted", "--stdin"]


def _feed(process: subprocess.Popen, revisions: list[str] | None, binary: bool) -> None:
    """Name the commits on standard input. git reads all of them before it writes."""
    if revisions is None or process.stdin is None:
        return
    text = "".join(f"{commit}\n" for commit in revisions)
    process.stdin.write(text.encode() if binary else text)
    process.stdin.close()
