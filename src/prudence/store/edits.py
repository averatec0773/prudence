"""What a tool call actually did: lines changed, and what a shell command was for.

Two facts hide inside the same records. An edit tool call says which lines entered and
left a file, which is the left-hand side of every attribution. A Bash call says whether
the session committed, formatted or tested, which is how a commit gets a session for
free instead of by inference.

Neither fact is easy to read, because the transcript reports edits three different
ways. Round one of the attribution spike measured this: about half the edit results
carry a `structuredPatch`, a quarter carry only the tool input, and a quarter carry no
result object at all. So there are three paths here, taken in that order of trust, and
a missing one is never fatal.

No code and no command output is stored. An edit becomes counts plus keyed line hashes;
a command becomes a class, an exit code and a commit hash. The command text itself is
kept only at `full` capture, truncated, because it is the one string the founder asked
to be able to read back.
"""

from __future__ import annotations

import difflib
import re
import shlex
from dataclasses import dataclass, field

EDIT_FACT_VERSION = 1
COMMAND_FACT_VERSION = 1

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
COMMAND_TOOLS = frozenset({"Bash", "BashOutput"})
COMMAND_CLASSES = ("git_commit", "git_other", "formatter", "test", "other")
COMMAND_TEXT_LIMIT = 2000

# git's own options, before the subcommand. Those that take a separate value are listed
# so that `git -C /path commit` is a commit and `git log -- commit` is not.
_GIT_VALUE_OPTIONS = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
)

_FORMATTER = re.compile(
    r"(?:^|[\s/])(?:prettier|black|gofmt|rustfmt|clang-format|dart\s+format"
    r"|ruff\s+format|eslint\b[^|;&]*--fix"
    r"|(?:npm|yarn|pnpm|bun)\s+(?:run\s+)?(?:format|fmt|lint:fix))\b"
)
_TEST = re.compile(
    r"(?:^|[\s/])(?:pytest|jest|vitest|phpunit|rspec|tox|nose2"
    r"|(?:npm|yarn|pnpm|bun)\s+(?:run\s+)?test"
    r"|cargo\s+test|go\s+test|dotnet\s+test|mvn\s+test|gradle\s+test|swift\s+test)\b"
)
# git prints `[branch abc1234] subject`, or `[branch (root-commit) abc1234] subject`.
_COMMIT_BRACKET = re.compile(r"^\[[^\]\n]*?([0-9a-f]{7,40})\]", re.MULTILINE)
_SEGMENT = re.compile(r"&&|\|\||[;|\n]")


@dataclass
class EditFacts:
    """The lines one edit tool call added and removed, before hashing."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    is_new_file: bool = False
    file_path: str | None = None


@dataclass
class CommandFacts:
    """What one shell call was for, and what git said back."""

    command_class: str = "other"
    exit_code: int | None = None
    commit_hash: str | None = None
    command_text: str | None = None


def extract_edit(tool_name: str | None, payload: dict, result: object) -> EditFacts | None:
    """The lines an edit call changed, from the patch, the input or a diff, in that order.

    Returns None for a tool that does not edit and for a call with no readable change.
    """
    if tool_name not in EDIT_TOOLS:
        return None
    result_dict = result if isinstance(result, dict) else {}
    facts = EditFacts(file_path=_file_path(payload, result_dict))
    facts.is_new_file = _is_new_file(tool_name, payload, result_dict)

    patch = result_dict.get("structuredPatch")
    if isinstance(patch, list) and patch:
        _from_structured_patch(patch, facts)
        if facts.added or facts.removed:
            return facts

    _from_input(tool_name, payload, facts)
    return facts if (facts.added or facts.removed) else None


def classify_command(text: str | None) -> str:
    """Which of the five classes a shell command belongs to. Unknown is `other`."""
    if not text:
        return "other"
    classes = {_classify_segment(segment) for segment in _SEGMENT.split(text)}
    for name in COMMAND_CLASSES:
        if name in classes:
            return name
    return "other"


def extract_command(tool_name: str | None, payload: dict, full: bool) -> CommandFacts | None:
    """What a Bash call was for. The command text is kept at `full` capture only."""
    if tool_name not in COMMAND_TOOLS:
        return None
    text = payload.get("command")
    text = text if isinstance(text, str) else None
    facts = CommandFacts(command_class=classify_command(text))
    if full and text:
        facts.command_text = text[:COMMAND_TEXT_LIMIT]
    return facts


def read_result(result: object) -> tuple[int | None, str | None]:
    """The exit code and the commit hash a shell result reports, when it reports either.

    The hash is git's own reply, read from the structured field recent Claude Code
    versions provide and otherwise from the `[branch abc1234]` bracket. Round two of
    the spike measured that only 52.8% of commit calls print that bracket, which is
    why this is one of three attribution methods rather than the only one.
    """
    result_dict = result if isinstance(result, dict) else {}
    return _exit_code(result_dict), _commit_hash(result_dict)


def _classify_segment(segment: str) -> str:
    tokens = _tokens(segment)
    subcommand = _git_subcommand(tokens)
    if subcommand == "commit":
        return "git_commit"
    if _TEST.search(segment):
        return "test"
    if _FORMATTER.search(segment):
        return "formatter"
    if subcommand is not None:
        return "git_other"
    return "other"


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _git_subcommand(tokens: list[str]) -> str | None:
    """The subcommand of a `git` invocation, skipping git's own pre-subcommand options."""
    for index, token in enumerate(tokens):
        if token != "git" and not token.endswith("/git"):
            continue
        position = index + 1
        while position < len(tokens):
            token = tokens[position]
            if not token.startswith("-"):
                return token
            name = token.split("=", 1)[0]
            position += 2 if name in _GIT_VALUE_OPTIONS and "=" not in token else 1
        return None
    return None


def _from_structured_patch(patch: list, facts: EditFacts) -> None:
    for hunk in patch:
        if not isinstance(hunk, dict):
            continue
        lines = hunk.get("lines")
        if not isinstance(lines, list):
            continue
        for line in lines:
            if not isinstance(line, str) or not line:
                continue
            if line[0] == "+":
                facts.added.append(line[1:])
            elif line[0] == "-":
                facts.removed.append(line[1:])


def _from_input(tool_name: str, payload: dict, facts: EditFacts) -> None:
    """The fallback the spike found is needed half the time: read the input itself."""
    if tool_name == "Write":
        content = payload.get("content")
        if isinstance(content, str):
            facts.added.extend(content.splitlines())
        return
    if tool_name == "MultiEdit":
        for entry in payload.get("edits", []) if isinstance(payload.get("edits"), list) else []:
            if isinstance(entry, dict):
                _diff(entry.get("old_string"), entry.get("new_string"), facts)
        return
    if tool_name == "NotebookEdit":
        _diff(payload.get("old_source"), payload.get("new_source"), facts)
        return
    _diff(payload.get("old_string"), payload.get("new_string"), facts)


def _diff(old: object, new: object, facts: EditFacts) -> None:
    """Which lines a replacement really changed, rather than every line it rewrote."""
    old_lines = old.splitlines() if isinstance(old, str) else []
    new_lines = new.splitlines() if isinstance(new, str) else []
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            facts.removed.extend(old_lines[i1:i2])
        if tag in ("replace", "insert"):
            facts.added.extend(new_lines[j1:j2])


def _is_new_file(tool_name: str, payload: dict, result: dict) -> bool:
    if result.get("type") == "create":
        return True
    original = result.get("originalFile")
    if tool_name == "Write" and isinstance(original, str) and original:
        return False
    if tool_name == "Write" and "originalFile" in result:
        return True
    if tool_name == "Write" and not result:
        return not isinstance(payload.get("old_string"), str)
    return False


def _file_path(payload: dict, result: dict) -> str | None:
    sources = ((result, ("filePath",)), (payload, ("file_path", "notebook_path", "path")))
    for source, keys in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _exit_code(result: dict) -> int | None:
    """Claude Code rarely reports one; when it does not, the fact is absent, not zero."""
    for key in ("exitCode", "exit_code", "returnCode", "return_code"):
        value = result.get(key)
        if isinstance(value, int):
            return value
    return None


def _commit_hash(result: dict) -> str | None:
    """The new commit, from the structured field when present, else git's own bracket."""
    operation = result.get("gitOperation")
    if isinstance(operation, dict):
        commit = operation.get("commit")
        if isinstance(commit, dict) and isinstance(commit.get("sha"), str):
            return commit["sha"].strip() or None
    for key in ("stdout", "stderr"):
        text = result.get(key)
        if not isinstance(text, str):
            continue
        match = _COMMIT_BRACKET.search(text)
        if match:
            return match.group(1)
    return None
