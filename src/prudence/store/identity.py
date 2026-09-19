"""Repository identity: which project a directory belongs to.

A path is not an identity: it changes when a directory is moved, and a second clone
has a different one. So a repository is identified by its root commit (stable across
moves, renames, clones and worktrees), with the first remote URL and the absolute git
common directory kept as fallbacks and for display. All three are stored so the
primary key can be changed later without re-scanning.

Known limit: two repositories whose root commits are byte-identical (same empty tree,
author, message and second) share an identity. It happens in tests that create repos in
a loop, and almost never in real life; a manual override is the remedy if it ever does.

Only read-only git commands are used.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class RepoIdentity:
    root_commits: tuple[str, ...]  # usually one; more after unrelated histories were merged
    remote_url: str | None
    common_dir: str  # absolute path of the shared .git directory
    toplevel: str  # absolute path of the main working tree (for display)

    @property
    def key(self) -> str:
        """The identity Prudence groups by. Root commit first, then remote, then path."""
        if self.root_commits:
            return "root:" + self.root_commits[0]
        if self.remote_url:
            return "remote:" + self.remote_url
        return "dir:" + self.common_dir

    @property
    def display_name(self) -> str:
        return Path(self.toplevel).name


@lru_cache(maxsize=4096)
def identify(directory: str) -> RepoIdentity | None:
    """Identity of the repository containing `directory`, or None if there is none.

    None also covers directories that no longer exist (for example a deleted worktree);
    the caller decides what to do with those.
    """
    if not Path(directory).is_dir():
        return None
    common_dir = _git(directory, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common_dir is None:
        return None
    # Ask questions of the main working tree so linked worktrees resolve to the same answer.
    main_tree = str(Path(common_dir).parent) if Path(common_dir).name == ".git" else common_dir
    root_out = _git(main_tree, "rev-list", "--max-parents=0", "HEAD") or ""
    root_commits = tuple(sorted(line.strip() for line in root_out.splitlines() if line.strip()))
    remote = _git(main_tree, "remote", "get-url", "origin")
    toplevel = _git(main_tree, "rev-parse", "--show-toplevel") or main_tree
    return RepoIdentity(
        root_commits=root_commits,
        remote_url=normalise_remote(remote) if remote else None,
        common_dir=common_dir,
        toplevel=toplevel,
    )


def normalise_remote(url: str) -> str:
    """Make ssh and https forms of the same remote compare equal."""
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@") and ":" in url:
        host, _, path = url[4:].partition(":")
        url = f"https://{host}/{path}"
    if url.startswith("ssh://git@"):
        url = "https://" + url[len("ssh://git@") :]
    return url.rstrip("/").lower()


def _git(directory: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", directory, *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
