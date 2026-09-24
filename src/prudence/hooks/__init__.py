"""Putting the capture hook into Claude Code's settings, and taking it out again.

Architecture rule 6 says Prudence is read-only toward the developer's world, with one
exception: the hook entries it installs with consent and can remove. This module is
that exception, so it is the most careful code in the project.

The sequence never changes. Copy the script out of the package into the data directory,
because a path inside a virtual environment stops existing the moment the package is
upgraded. Write the enabled repository roots out as plain text, because a shell script
must not parse TOML. Back the settings file up under a timestamped name. Add only our
own entries, recognised by the command path, and add none that is already there. Write
to a temporary file and rename it into place, so an interrupted write cannot leave the
user with no settings at all. Parse the result again before saying it worked. Print the
diff and the backup path, so the user sees exactly what changed in their file.

`uninstall` removes exactly the entries whose command is ours. When the backup plus our
entries is the whole of the current file, it restores the backup byte for byte; when
something else changed in between, it removes our entries from the current file instead
and says so, because overwriting somebody's later edit would be worse than an imperfect
restore.
"""

from __future__ import annotations

import difflib
import json
import os
import shlex
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from prudence.hooks.policy import CLAUDE_EVENTS, events_for
from prudence.paths import (
    claude_settings_file,
    enabled_list_file,
    hook_script_file,
    spool_file,
)

EVENTS = CLAUDE_EVENTS

# Seconds. The script measured 52 to 82 ms on the founder's machine, so this is a
# guard against a pathological `git status`, not a working budget.
TIMEOUT_SECONDS = 10

SCRIPT_NAME = "prudence-hook.sh"
SCRIPT_MODE = 0o755

ENABLED_HEADER = (
    "# Repositories you enabled, one absolute working-tree path per line.\n"
    "# Written by `prudence hooks install`. The capture hook records nothing for a\n"
    "# directory that is not under one of these paths.\n"
)


class SettingsProblem(RuntimeError):
    """The settings file is not shaped the way hook entries need. Nothing was written."""


@dataclass
class InstallResult:
    settings_path: Path
    script_path: Path
    enabled_path: Path
    enabled_roots: int
    backup: Path | None = None
    added: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    diff: str = ""


@dataclass
class UninstallResult:
    settings_path: Path
    removed: list[str] = field(default_factory=list)
    restored_from: Path | None = None
    changed_since_backup: bool = False
    diff: str = ""


def script_source() -> Path:
    """The packaged script, as shipped. Never run from here; always run from the copy."""
    return Path(str(resources.files("prudence").joinpath(f"hooks/{SCRIPT_NAME}")))


def install_script(target: Path | None = None) -> Path:
    """Copy the hook into the data directory at mode 0755."""
    destination = target or hook_script_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(script_source().read_bytes())
    temporary.chmod(SCRIPT_MODE)
    os.replace(temporary, destination)
    return destination


def enabled_roots(connection: sqlite3.Connection, keys: set[str] | None = None) -> list[str]:
    """Every working-tree root of every enabled repository, longest path first.

    Read from the `repository` table rather than from the config, because the config
    holds one directory per repository and the table holds every worktree that
    repository's work has ever been seen in, which is what a working directory has to
    be compared against.
    """
    from prudence.store import repos as repos_module

    roots: set[str] = set()
    for repository in repos_module.read(connection):
        if keys is not None and repository.repo_key not in keys:
            continue
        roots.update(repository.roots)
    return sorted(roots)


def write_enabled(roots: list[str], target: Path | None = None) -> Path:
    """Write the enabled list atomically, so a hook never reads half a file."""
    destination = target or enabled_list_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    body = ENABLED_HEADER + "".join(f"{root}\n" for root in roots)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(body, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def install(
    connection: sqlite3.Connection,
    settings_path: Path | None = None,
    script_path: Path | None = None,
    now: datetime | None = None,
    kind: str = "claude_code",
    source_id: str = "claude",
) -> InstallResult:
    """Add our hook entries to the user's settings file. Idempotent."""
    settings_file = settings_path or claude_settings_file()
    script = install_script(script_path)
    roots = enabled_roots(connection)
    enabled_path = write_enabled(roots)

    before = _read_text(settings_file)
    settings = _parse(before, settings_file)
    added, already = _add_entries(settings, script, kind, source_id)
    result = InstallResult(
        settings_path=settings_file,
        script_path=script,
        enabled_path=enabled_path,
        enabled_roots=len(roots),
        added=added,
        already=already,
    )
    if not added:
        return result
    result.backup = _backup(settings_file, before, now)
    after = _dumps(settings)
    _write(settings_file, after)
    result.diff = _diff(before, after, settings_file)
    return result


def uninstall(
    settings_path: Path | None = None, script_path: Path | None = None
) -> UninstallResult:
    """Remove exactly our entries, restoring the backup byte for byte when it still fits."""
    settings_file = settings_path or claude_settings_file()
    script = script_path or hook_script_file()
    before = _read_text(settings_file)
    settings = _parse(before, settings_file)
    removed = _remove_entries(settings, script)
    result = UninstallResult(settings_path=settings_file, removed=removed)
    if not removed:
        return result

    stripped = _dumps(settings)
    backup = latest_backup(settings_file)
    if backup is not None:
        backup_text = backup.read_text(encoding="utf-8")
        try:
            original = json.loads(backup_text)
            comparable = dict(original) if isinstance(original, dict) else original
            if isinstance(comparable, dict) and comparable.get("hooks") == {}:
                comparable.pop("hooks")
            same = comparable == settings
        except ValueError:
            same = False
        if same:
            _write(settings_file, backup_text)
            result.restored_from = backup
            result.diff = _diff(before, backup_text, settings_file)
            return result
        result.changed_since_backup = True
    _write(settings_file, stripped)
    result.diff = _diff(before, stripped, settings_file)
    return result


def present(
    settings_path: Path | None = None,
    script_path: Path | None = None,
    kind: str = "claude_code",
    source_id: str = "claude",
) -> list[str]:
    """Which of our events are wired up in the settings file right now."""
    settings_file = settings_path or claude_settings_file()
    script = script_path or hook_script_file()
    try:
        settings = _parse(_read_text(settings_file), settings_file)
    except SettingsProblem:
        return []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    found = []
    for event, matcher in events_for(kind):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict) or not _matches(group, matcher):
                continue
            entries = group.get("hooks")
            if isinstance(entries, list) and any(
                _is_ours(entry, script, event, kind, source_id) for entry in entries
            ):
                found.append(event if matcher is None else f"{event}({matcher})")
                break
    return found


def latest_backup(settings_path: Path | None = None) -> Path | None:
    """The most recent backup we took of this settings file, by name."""
    settings_file = settings_path or claude_settings_file()
    directory = settings_file.parent
    if not directory.is_dir():
        return None
    backups = sorted(directory.glob(f"{settings_file.name}.prudence-backup-*"))
    return backups[-1] if backups else None


def spool_size(path: Path | None = None) -> int:
    target = path or spool_file()
    try:
        return target.stat().st_size
    except OSError:
        return 0


def _command(script: Path, event: str, kind: str = "claude_code", source_id: str = "claude") -> str:
    """The shell line Claude Code runs. Quoted, because the data directory on macOS is
    `~/Library/Application Support/...` and an unquoted space splits the path."""
    command = f"{shlex.quote(str(script))} {event}"
    if kind != "claude_code" or source_id != "claude":
        command += f" {shlex.quote(kind)} {shlex.quote(source_id)}"
    return command


def _is_ours(
    entry: object, script: Path, event: str, kind: str = "claude_code", source_id: str = "claude"
) -> bool:
    """Recognise our entry whether it was written quoted or, by an older version, bare."""
    if not isinstance(entry, dict):
        return False
    command = entry.get("command")
    expected = {_command(script, event, kind, source_id)}
    if kind == "claude_code" and source_id == "claude":
        expected.add(f"{script} {event}")
    return isinstance(command, str) and command in expected


def _entry(script: Path, event: str, kind: str = "claude_code", source_id: str = "claude") -> dict:
    return {
        "type": "command",
        "command": _command(script, event, kind, source_id),
        "timeout": TIMEOUT_SECONDS,
    }


def _matches(group: dict, matcher: str | None) -> bool:
    current = group.get("matcher")
    if matcher is None:
        return current in (None, "", "*")
    return current == matcher


def _add_entries(
    settings: dict, script: Path, kind: str = "claude_code", source_id: str = "claude"
) -> tuple[list[str], list[str]]:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SettingsProblem("`hooks` in the settings file is not an object; nothing was written.")
    added: list[str] = []
    already: list[str] = []
    for event, matcher in events_for(kind):
        label = event if matcher is None else f"{event}({matcher})"
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise SettingsProblem(f"`hooks.{event}` is not a list; nothing was written.")
        target = None
        for group in groups:
            if isinstance(group, dict) and _matches(group, matcher):
                target = group
                break
        if target is None:
            target = {"hooks": []} if matcher is None else {"matcher": matcher, "hooks": []}
            groups.append(target)
        entries = target.setdefault("hooks", [])
        if not isinstance(entries, list):
            raise SettingsProblem(f"`hooks.{event}[].hooks` is not a list; nothing was written.")
        if any(_is_ours(entry, script, event, kind, source_id) for entry in entries):
            already.append(label)
            continue
        entries.append(_entry(script, event, kind, source_id))
        added.append(label)
    return added, already


def _remove_entries(settings: dict, script: Path) -> list[str]:
    """Take out every entry whose command is ours, and nothing else.

    A group or an event key is dropped only when we are the reason it is empty. An
    empty group the user left behind stays empty, because removing it would be a change
    they did not ask for and would stop the backup from being restorable.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    prefixes = (str(script), shlex.quote(str(script)))
    removed: list[str] = []
    for event in list(hooks):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        surviving: list = []
        emptied = 0
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                surviving.append(group)
                continue
            keep = []
            dropped = 0
            for entry in group["hooks"]:
                command = entry.get("command") if isinstance(entry, dict) else None
                if isinstance(command, str) and command.startswith(prefixes):
                    matcher = group.get("matcher")
                    removed.append(event if not matcher else f"{event}({matcher})")
                    dropped += 1
                    continue
                keep.append(entry)
            group["hooks"] = keep
            if keep or not dropped or set(group) - {"hooks", "matcher"}:
                surviving.append(group)
            else:
                emptied += 1
        if surviving or not emptied:
            hooks[event] = surviving
        else:
            del hooks[event]
    if not hooks and removed:
        del settings["hooks"]
    return removed


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _parse(text: str, path: Path) -> dict:
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except ValueError as error:
        raise SettingsProblem(
            f"{path} is not valid JSON ({error}); nothing was written."
        ) from error
    if not isinstance(parsed, dict):
        raise SettingsProblem(f"{path} is not a JSON object; nothing was written.")
    return parsed


def _dumps(settings: dict) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"


def _write(path: Path, text: str) -> None:
    """Temporary file plus rename, then read the result back and parse it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".prudence-tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
    _parse(path.read_text(encoding="utf-8"), path)


def _backup(path: Path, text: str, now: datetime | None) -> Path | None:
    if not path.exists():
        return None
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.prudence-backup-{stamp}")
    suffix = 1
    while target.exists():
        target = path.with_name(f"{path.name}.prudence-backup-{stamp}-{suffix}")
        suffix += 1
    target.write_text(text, encoding="utf-8")
    return target


def _diff(before: str, after: str, path: Path) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
        )
    )


def write_enabled_sources(config) -> None:
    """Mirror collection consent for the cheap shell hook, without TOML parsing there."""
    refresh_installed_script()
    destination = enabled_list_file().with_name("sources-enabled.txt")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text("".join(f"{s.id}\n" for s in config.sources.values() if s.enabled))
    os.replace(temporary, destination)


def refresh_installed_script() -> None:
    """Upgrade only Prudence's installed copy; never install a hook or change settings."""
    installed = hook_script_file()
    if installed.is_file() and installed.read_bytes() != script_source().read_bytes():
        install_script(installed)
