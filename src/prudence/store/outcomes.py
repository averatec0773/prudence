"""What became of the lines: presence at four moments, blame at one, and rework.

This is the table the product's central promise rests on. A session is credited with a
commit by `store/attribution.py`; this module asks what happened to that commit's lines
afterwards, and records the answer per line so that every aggregate above it can be
rebuilt, checked and shown with its denominator.

Five measurements per line, and they are deliberately not one number:

- `alive_7d`, `alive_30d`, `alive_90d`: the line was still in the same file in the tree
  the repository had at the commit's own moment plus seven, thirty and ninety days. The
  tree is found with `git rev-list -1 --before=<mark> <branch>` and read with
  `git cat-file`; nothing diffs anything. A mark that has not happened yet is NULL, not
  a death: round two of the spike could not compute one-day survival at all because the
  newest commit in every repository was older than the cut-off, and a zero there would
  have been a lie about young work.
- `alive_head`: the same test at HEAD now. `alive_head_anywhere` repeats it over every
  file at HEAD, which is how a line that moved to another path stays visible as moved
  rather than dead.
- `blame_head`: `git blame -w -M --line-porcelain` at HEAD still credits that line to
  the commit (or to a commit the alias table says is the same work). The spike measured
  presence and blame within two points of each other on average and five in the worst
  repository, always in the same direction, because presence counts an identical line
  somewhere in the file as alive even when the original was deleted and rewritten. Both
  are stored, presence is the figure shown, blame is the check, exactly as round two
  recommended.

Rework is the sixth column and a different kind of fact: `reworked_by` holds the first
later commit, inside the ninety-day window and carrying the same `author_email_hash` as
the original, whose diff removed that line from that path. Removals are read in one
streaming `git log -p -U0` pass, filtered to the lines this table already holds, so the
memory is bounded by the table and not by the repository.

Two guards. A repository where other people commit gets no outcome facts at all: if
more than a fifth of its commits in the window carry an author email hash other than
the majority's, `repository.outcomes_suppressed` is set and every surface says why,
because "your lines died" is a false statement when somebody else wrote them. And a
repository with more attributed commits than `MAX_COMMITS` is sampled deterministically
by commit hash, so a rebuild produces exactly the same sample and the surfaces can say
which share of the work they speak for.

Read-only git only: `ls-tree`, `cat-file`, `rev-list`, `blame`, `log`.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from prudence.store import lines as line_module
from prudence.store.commits import GENERATED, utc
from prudence.store.repos import Repository

FACT_VERSION = 1

# The marks, in days after the commit. A mark in the future is NULL, never zero.
MARKS = (7, 30, 90)

# How far after a commit a later commit still counts as rework of it.
WINDOW = timedelta(days=90)

# The multi-author guard: the share of a repository's commits in the window that may
# carry an author email hash other than the majority's before outcomes are suppressed.
OTHER_AUTHOR_SHARE = 0.20

# Attributed commits per repository before the set is sampled. Deterministic by hash,
# so a rebuild draws the same sample; the surfaces print the share when it fires.
MAX_COMMITS = 2000

# Blobs larger than this are not read. A file nobody can read a line out of has no
# line to find, and one huge generated file should not decide the run's cost.
MAX_BLOB_BYTES = 2_000_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS line_fate(
    commit_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    line_hash TEXT NOT NULL,
    alive_7d INTEGER,
    alive_30d INTEGER,
    alive_90d INTEGER,
    alive_head INTEGER,
    alive_head_anywhere INTEGER,
    blame_head INTEGER,
    reworked_by TEXT,
    fact_version INTEGER NOT NULL,
    PRIMARY KEY (commit_hash, path, line_hash)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS line_fate_path ON line_fate(path);
"""


@dataclass
class OutcomeStats:
    repositories: int = 0
    commits: int = 0
    sampled_repositories: int = 0
    sampled_commits: int = 0
    lines: int = 0
    reworked: int = 0
    # Repository name to the share of the window's commits by another author identity.
    suppressed: dict[str, float] = field(default_factory=dict)
    blamed_paths: int = 0
    elapsed: float = 0.0


@dataclass
class _Commit:
    commit_hash: str
    committer_at: str | None
    author_email_hash: str | None


def build(
    connection: sqlite3.Connection,
    repositories: list[Repository],
    key: bytes,
    now: datetime | None = None,
) -> OutcomeStats:
    """Recompute every line's fate. Dropped and rebuilt, never migrated (rule 1)."""
    started = time.monotonic()
    stats = OutcomeStats()
    # Naive UTC throughout, the one form `store/commits.utc` puts every timestamp in.
    moment = now or datetime.now(UTC).replace(tzinfo=None)
    connection.execute("DROP TABLE IF EXISTS line_fate")
    connection.executescript(SCHEMA)
    connection.execute("UPDATE repository SET outcomes_suppressed = 0")

    for repository in repositories:
        if not repository.toplevel:
            continue
        share = _other_author_share(connection, repository.repo_key, moment)
        if share > OTHER_AUTHOR_SHARE:
            connection.execute(
                "UPDATE repository SET outcomes_suppressed = 1 WHERE repo_key = ?",
                (repository.repo_key,),
            )
            stats.suppressed[repository.name or repository.repo_key] = share
            continue
        _one_repository(connection, repository, key, moment, stats)

    stats.elapsed = time.monotonic() - started
    return stats


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Rows, commits covered and rework found, or zeroes before the first run."""
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS lines, COUNT(DISTINCT commit_hash) AS commits,"
            " SUM(CASE WHEN reworked_by IS NOT NULL THEN 1 ELSE 0 END) AS reworked"
            " FROM line_fate"
        ).fetchone()
    except sqlite3.OperationalError:
        return {"lines": 0, "commits": 0, "reworked": 0}
    return {
        "lines": row["lines"] or 0,
        "commits": row["commits"] or 0,
        "reworked": row["reworked"] or 0,
    }


def suppressed_repositories(connection: sqlite3.Connection) -> list[str]:
    """Repositories whose outcome facts were withheld because other authors dominate."""
    try:
        return [
            row["repo_key"]
            for row in connection.execute(
                "SELECT repo_key FROM repository WHERE outcomes_suppressed = 1 ORDER BY repo_key"
            )
        ]
    except sqlite3.OperationalError:
        return []


# --- one repository --------------------------------------------------------------------


def _one_repository(
    connection: sqlite3.Connection,
    repository: Repository,
    key: bytes,
    now: datetime,
    stats: OutcomeStats,
) -> None:
    directory = repository.toplevel
    assert directory is not None
    commits = _counted_commits(connection, repository.repo_key)
    if not commits:
        return
    total = len(commits)
    commits = _sample(commits)
    if len(commits) < total:
        stats.sampled_repositories += 1
    stats.sampled_commits += total - len(commits)

    fates = _fate_keys(connection, [commit.commit_hash for commit in commits])
    if not fates:
        return
    stats.repositories += 1
    stats.commits += len(commits)
    paths = {path for entries in fates.values() for path, _ in entries}

    blobs = _Blobs(directory, key)
    try:
        by_path, everywhere = _head_index(directory, key, blobs)
        marks = _marks(directory, commits, now)
        at_mark = _mark_lines(blobs, fates, commits, marks)
        blamed = _blame(directory, key, paths & set(by_path), stats)
        reworked = _rework(directory, key, fates, commits)
        aliases = _alias_groups(connection)

        rows = []
        for commit in commits:
            for entry in fates.get(commit.commit_hash, ()):
                path, line_hash = entry
                rows.append(
                    (
                        commit.commit_hash,
                        path,
                        line_hash,
                        *(
                            _present(at_mark.get((commit.commit_hash, days)), path, line_hash)
                            for days in MARKS
                        ),
                        int(line_hash in by_path.get(path, ())),
                        int(line_hash in everywhere),
                        _blamed(blamed, path, line_hash, commit.commit_hash, aliases),
                        reworked.get((commit.commit_hash, path, line_hash)),
                        FACT_VERSION,
                    )
                )
        connection.executemany(
            "INSERT OR REPLACE INTO line_fate VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
        stats.lines += len(rows)
        stats.reworked += sum(1 for row in rows if row[9] is not None)
    finally:
        blobs.close()


def _counted_commits(connection: sqlite3.Connection, repo_key: str) -> list[_Commit]:
    """Commits a session is credited with at `fact` or `inferred`. Never `uncertain`."""
    return [
        _Commit(row["commit_hash"], row["committer_at"], row["author_email_hash"])
        for row in connection.execute(
            'SELECT c.commit_hash, c.committer_at, c.author_email_hash FROM "commit" c'
            " WHERE c.repo_key = ? AND c.is_merge = 0 AND c.commit_hash IN"
            " (SELECT commit_hash FROM attribution WHERE confidence IN (?, ?))"
            " ORDER BY c.commit_hash",
            (repo_key, "fact", "inferred"),
        )
    ]


def _sample(commits: list[_Commit]) -> list[_Commit]:
    """Every commit, or a deterministic slice of them when there are too many.

    The hash decides, so the same commits are drawn on every rebuild and the sample is
    not a function of the order the store happens to return rows in.
    """
    if len(commits) <= MAX_COMMITS:
        return commits
    stride = (len(commits) // MAX_COMMITS) + 1
    return [
        commit for commit in commits if int(commit.commit_hash[:8], 16) % stride == 0
    ] or commits[:MAX_COMMITS]


def _fate_keys(
    connection: sqlite3.Connection, hashes: list[str]
) -> dict[str, list[tuple[str, str]]]:
    """The (path, line hash) pairs of each commit, straight out of `commit_line`."""
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for start in range(0, len(hashes), 400):
        batch = hashes[start : start + 400]
        marks = ", ".join("?" * len(batch))
        for row in connection.execute(
            f"SELECT commit_hash, path, line_hash FROM commit_line WHERE commit_hash IN ({marks})",
            batch,
        ):
            found[row["commit_hash"]].append((row["path"], row["line_hash"]))
    return dict(found)


def _other_author_share(connection: sqlite3.Connection, repo_key: str, now: datetime) -> float:
    """The share of the window's commits not made by the majority author identity."""
    since = (now - WINDOW).strftime("%Y-%m-%dT%H:%M:%S")
    rows = connection.execute(
        'SELECT author_email_hash AS who, COUNT(*) AS n FROM "commit"'
        " WHERE repo_key = ? AND is_merge = 0 AND committer_at >= ? GROUP BY who",
        (repo_key, since),
    ).fetchall()
    total = sum(row["n"] for row in rows)
    if not total:
        return 0.0
    majority = max(row["n"] for row in rows)
    return (total - majority) / total


# --- reading trees ----------------------------------------------------------------------


class _Blobs:
    """One `git cat-file --batch` per repository, answering `<rev>:<path>` in line hashes."""

    def __init__(self, directory: str, key: bytes) -> None:
        self.key = key
        self.cache: dict[str, frozenset[str] | None] = {}
        try:
            self.process: subprocess.Popen | None = subprocess.Popen(
                ["git", "-C", directory, "cat-file", "--batch"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.process = None

    def lines(self, spec: str) -> frozenset[str] | None:
        """The keyed hashes of one blob's lines, or None when it does not exist there."""
        if spec in self.cache:
            return self.cache[spec]
        result = self._read(spec)
        self.cache[spec] = result
        return result

    def _read(self, spec: str) -> frozenset[str] | None:
        process = self.process
        if process is None or "\n" in spec:
            return None
        assert process.stdin is not None and process.stdout is not None
        try:
            process.stdin.write(spec.encode() + b"\n")
            process.stdin.flush()
            header = process.stdout.readline()
        except (OSError, ValueError):
            self.close()
            return None
        parts = header.split()
        if len(parts) != 3 or parts[1] != b"blob":
            return None
        size = int(parts[2])
        body = process.stdout.read(size + 1)[:size]
        if size > MAX_BLOB_BYTES or b"\0" in body[:8000]:
            return frozenset()
        text = body.decode("utf-8", "replace")
        return frozenset(line_module.hash_lines(self.key, text.splitlines()))

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
        except OSError:
            pass
        process.wait()


def _head_index(
    directory: str, key: bytes, blobs: _Blobs
) -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    """Every readable file at HEAD, by path and as one set for the "anywhere" question."""
    listing = _git(directory, "ls-tree", "-r", "-z", "--format=%(objectname) %(path)", "HEAD")
    by_path: dict[str, frozenset[str]] = {}
    everywhere: set[str] = set()
    for entry in (listing or "").split("\0"):
        blob, _, path = entry.partition(" ")
        if not path or len(blob) != 40 or GENERATED.search(path):
            continue
        hashes = blobs.lines(blob)
        if not hashes:
            continue
        by_path[path] = hashes
        everywhere.update(hashes)
    return by_path, frozenset(everywhere)


def _marks(directory: str, commits: list[_Commit], now: datetime) -> dict[tuple[str, int], str]:
    """The commit the branch stood at, for every mark that has already happened."""
    resolved: dict[str, str | None] = {}
    marks: dict[tuple[str, int], str] = {}
    for commit in commits:
        made = utc(commit.committer_at)
        if made is None:
            continue
        base = datetime.fromisoformat(made)
        for days in MARKS:
            when = base + timedelta(days=days)
            if when > now:
                continue
            stamp = when.strftime("%Y-%m-%dT%H:%M:%S")
            if stamp not in resolved:
                resolved[stamp] = _git(directory, "rev-list", "-1", f"--before={stamp}", "HEAD")
            found = resolved[stamp]
            if found:
                marks[(commit.commit_hash, days)] = found
    return marks


def _mark_lines(
    blobs: _Blobs,
    fates: dict[str, list[tuple[str, str]]],
    commits: list[_Commit],
    marks: dict[tuple[str, int], str],
) -> dict[tuple[str, int], dict[str, frozenset[str]]]:
    """The lines of each commit's paths in the tree at each of its marks."""
    result: dict[tuple[str, int], dict[str, frozenset[str]]] = {}
    for commit in commits:
        paths = {path for path, _ in fates.get(commit.commit_hash, ())}
        for days in MARKS:
            mark = marks.get((commit.commit_hash, days))
            if mark is None:
                continue
            result[(commit.commit_hash, days)] = {
                path: blobs.lines(f"{mark}:{path}") or frozenset() for path in paths
            }
    return result


def _present(at_mark: dict[str, frozenset[str]] | None, path: str, line_hash: str) -> int | None:
    """1, 0, or None when that mark has not happened yet (which is not a death)."""
    if at_mark is None:
        return None
    return int(line_hash in at_mark.get(path, frozenset()))


# --- blame -------------------------------------------------------------------------------


def _blame(
    directory: str, key: bytes, paths: set[str], stats: OutcomeStats
) -> dict[str, dict[str, set[str]]]:
    """Which commit blame credits each line of each file to, at HEAD, cached per path."""
    result: dict[str, dict[str, set[str]]] = {}
    for path in sorted(paths):
        output = _git(directory, "blame", "-w", "-M", "--line-porcelain", "HEAD", "--", path)
        if output is None:
            continue
        stats.blamed_paths += 1
        per_line: dict[str, set[str]] = defaultdict(set)
        current: str | None = None
        for line in output.splitlines():
            if line.startswith("\t"):
                if current is not None:
                    digest = line_module.hash_line(key, line[1:])
                    if digest is not None:
                        per_line[digest].add(current)
                current = None
            else:
                head = line.split(" ", 1)[0]
                if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
                    current = head
        result[path] = dict(per_line)
    return result


def _alias_groups(connection: sqlite3.Connection) -> dict[str, set[str]]:
    """Commit hashes the alias table says are the same work, keyed by each of them."""
    by_printed: dict[str, set[str]] = defaultdict(set)
    try:
        rows = connection.execute("SELECT printed_hash, commit_hash FROM commit_alias").fetchall()
    except sqlite3.OperationalError:
        return {}
    for row in rows:
        by_printed[row["printed_hash"]].add(row["commit_hash"])
    groups: dict[str, set[str]] = defaultdict(set)
    for members in by_printed.values():
        for member in members:
            groups[member].update(members)
    return dict(groups)


def _blamed(
    blamed: dict[str, dict[str, set[str]]],
    path: str,
    line_hash: str,
    commit_hash: str,
    aliases: dict[str, set[str]],
) -> int:
    """1 when blame still credits that line to this commit or to one of its aliases.

    A path blame was not run on is a path that no longer exists at HEAD, where no line
    is credited to anybody, so the honest answer there is 0 rather than unmeasured.
    """
    per_line = blamed.get(path)
    if per_line is None:
        return 0
    credited = per_line.get(line_hash)
    if not credited:
        return 0
    return int(bool(credited & ({commit_hash} | aliases.get(commit_hash, set()))))


# --- rework -------------------------------------------------------------------------------


def _rework(
    directory: str,
    key: bytes,
    fates: dict[str, list[tuple[str, str]]],
    commits: list[_Commit],
) -> dict[tuple[str, str, str], str]:
    """The first later commit of the same author that removed each line from its path.

    One streaming `git log -p -U0` pass, filtered to the lines this table already holds,
    so nothing is remembered about a line nobody asked about.
    """
    wanted = {(path, line_hash) for entries in fates.values() for path, line_hash in entries}
    if not wanted:
        return {}
    removals = _removed_lines(directory, key, wanted)
    result: dict[tuple[str, str, str], str] = {}
    for commit in commits:
        made = utc(commit.committer_at)
        if made is None or commit.author_email_hash is None:
            continue
        deadline = (datetime.fromisoformat(made) + WINDOW).strftime("%Y-%m-%dT%H:%M:%S")
        for path, line_hash in fates.get(commit.commit_hash, ()):
            for when, later, author in removals.get((path, line_hash), ()):
                if when <= made or when > deadline or later == commit.commit_hash:
                    continue
                if author == commit.author_email_hash:
                    result[(commit.commit_hash, path, line_hash)] = later
                    break
    return result


def _removed_lines(
    directory: str, key: bytes, wanted: set[tuple[str, str]]
) -> dict[tuple[str, str], list[tuple[str, str, str]]]:
    """Every removal of a line we care about, oldest first: when, by which commit, by whom."""
    record, field_sep = "\x01", "\x1f"
    process = _log(directory, f"--format={record}%H{field_sep}%cI{field_sep}%ae")
    if process is None:
        return {}
    removals: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    commit_hash = when = author = ""
    path: str | None = None
    in_hunk = False
    assert process.stdout is not None
    for raw in process.stdout:
        line = raw.rstrip("\n")
        if line.startswith(record):
            parts = line[1:].split(field_sep)
            if len(parts) < 3:
                commit_hash, path, in_hunk = "", None, False
                continue
            commit_hash = parts[0]
            when = utc(parts[1]) or ""
            email = parts[2].strip().lower()
            author = hashlib.sha256(email.encode()).hexdigest() if email else ""
            path, in_hunk = None, False
        elif line.startswith("diff --git "):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("--- "):
            path = _post_path(line[4:])
        elif line.startswith("@@"):
            in_hunk = path is not None
        elif in_hunk and path is not None and line.startswith("-"):
            digest = line_module.hash_line(key, line[1:])
            if digest is not None and (path, digest) in wanted and commit_hash:
                removals[(path, digest)].append((when, commit_hash, author))
    process.stdout.close()
    process.wait()
    for entries in removals.values():
        entries.sort()
    return dict(removals)


def _post_path(raw: str) -> str | None:
    """The pre-image path of a diff, which is the path a removed line was removed from."""
    text = raw.strip().split("\t")[0]
    if text in ("/dev/null", ""):
        return None
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].encode().decode("unicode_escape", "replace")
    if text.startswith("a/"):
        text = text[2:]
    return None if GENERATED.search(text) else text


# --- git ------------------------------------------------------------------------------------


def _git(directory: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", directory, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip("\n") or None


def _log(directory: str, *args: str) -> subprocess.Popen | None:
    try:
        return subprocess.Popen(
            ["git", "-C", directory, "log", "--all", "--no-merges", "-p", "-U0", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
