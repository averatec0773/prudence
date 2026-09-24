"""What one response did, as one of four words: `change`, `run`, `read` or `talk`.

A response is one reply of the model: the records that share one message id. Its bucket
is decided by the tool calls in it and nothing else. No message text is read, no
threshold exists and no model is asked, so the same archive always gives the same
answer and a new release of the rule is a new `BUCKET_RULE_VERSION`, never a drift.

The session-level `purpose` label (`facts/purpose.py`) asked what a session was for and
answered with one word from thresholds over aggregate counts; every threshold that moved
reshuffled the founder's tokens. This rule asks only what each reply did, and every level
above the response (turn, session, project, week) is a sum of replies.

The rule, applied to each tool call and then to the response:

- `change` wrote or changed a file: the edit tools, and MCP tools whose name says so.
- `run` executed something that can change the world or produce a result: a shell
  command that is not read-only, skills and workflows, and the browser and simulator
  actions MCP servers offer.
- `read` only looked: the read and search tools, and a read-only shell command.
- `talk` touched neither files nor the shell: no tool at all, or only questions, task
  lists, dispatching a subagent and MCP tools that report state.

When one response does several kinds, the highest wins: change > run > read > talk.

A tool name none of the lists knows is classified by the words in its name and marked as
a guess (`heuristic`), so every surface can say how many tokens rest on one. A shell
command is read-only only when every part of it is: split on `&&`, `||`, `;`, `|`, `&`
and newlines outside quotes, with heredoc bodies set aside, each part's program has to
be on the read list (`sed` and `awk` without in-place editing, `find` without `-exec`
or `-delete`, `git` with a reading subcommand, `sqlite3` with SQL that only reads), and
no part may redirect into a file. Anything else runs.

The lists are the ones the 2026-09-22 demo proved on the founder's store (zero model
calls, every response classified). They are data, here and nowhere else; changing one
is a new rule version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BUCKET_RULE_VERSION = 2

CHANGE = "change"
RUN = "run"
READ = "read"
TALK = "talk"
# In precedence order, highest first; also the order every surface prints them in.
BUCKETS = (CHANGE, RUN, READ, TALK)
_RANK = {CHANGE: 3, RUN: 2, READ: 1, TALK: 0}

# --- tools, by name ----------------------------------------------------------------

CHANGE_TOOLS = frozenset(
    {
        "Edit",
        "MultiEdit",
        "Write",
        "NotebookEdit",
        "FileChange",
        "apply_patch",
        "functions.apply_patch",
    }
)
RUN_TOOLS = frozenset(
    {"Skill", "Workflow", "Monitor", "KillShell", "EnterWorktree", "ExitWorktree"}
)
READ_TOOLS = frozenset(
    {
        "Read",
        "NotebookRead",
        "Grep",
        "Glob",
        "WebFetch",
        "WebSearch",
        "LSP",
        "ToolSearch",
        "TaskOutput",
        "BashOutput",
    }
)
READ_PREFIXES = ("ReadMcpResource", "ListMcpResources")
TALK_TOOLS = frozenset(
    {
        "AskUserQuestion",
        "TodoWrite",
        "TaskCreate",
        "TaskUpdate",
        "TaskList",
        "TaskGet",
        "TaskStop",
        "Agent",
        "Task",
        "SendMessage",
        "ScheduleWakeup",
        "ListAgents",
        "StructuredOutput",
        "EnterPlanMode",
        "ExitPlanMode",
        "ReportFindings",
        "PushNotification",
        "SendUserFile",
    }
)
SHELL_TOOLS = frozenset({"Bash", "bash", "CommandExecution"})

# MCP tools, keyed by the part of the name after the last `__`, classified by hand from
# the names that occur on the founder's store. A name not listed falls to the write
# words, then to the name heuristic.
MCP_PREFIX = "mcp__"
MCP_CHANGE = frozenset({"merge_metadata"})
MCP_RUN = frozenset(
    {
        "navigate",
        "computer",
        "browser_batch",
        "javascript_tool",
        "form_input",
        "file_upload",
        "tabs_create_mcp",
        "tabs_close_mcp",
        "tabs_create",
        "tabs_close",
        "tabs_select",
        "resize_window",
        "preview_start",
        "preview_stop",
        "preview_eval",
        "preview_click",
        "preview_resize",
        "preview_fill",
        "browser_navigate",
        "browser_navigate_back",
        "browser_click",
        "browser_evaluate",
        "browser_type",
        "browser_press_key",
        "browser_hover",
        "browser_drag",
        "browser_drop",
        "browser_select_option",
        "browser_fill_form",
        "browser_file_upload",
        "browser_handle_dialog",
        "browser_run_code_unsafe",
        "browser_resize",
        "browser_close",
        "browser_wait_for",
        "browser_tabs",
        "left_click",
        "double_click",
        "right_click",
        "triple_click",
        "scroll",
        "left_click_drag",
        "mouse_move",
        "open_application",
        "computer_batch",
        "control",
        "build",
        "launch",
    }
)
MCP_TALK = frozenset(
    {
        "get_page_text",
        "read_page",
        "find",
        "browser_snapshot",
        "browser_take_screenshot",
        "browser_console_messages",
        "browser_network_requests",
        "browser_network_request",
        "browser_find",
        "tabs_context_mcp",
        "tabs_context",
        "read_console_messages",
        "read_network_requests",
        "list_connected_browsers",
        "select_browser",
        "screenshot",
        "zoom",
        "request_access",
        "preview_screenshot",
        "preview_console_logs",
        "preview_list",
        "preview_inspect",
        "preview_logs",
        "read_terminal",
        "getDiagnostics",
        "mark_chapter",
        "spawn_task",
        "dismiss_task",
        "read_widget_context",
        "get_usage",
        "read_me",
        "show_widget",
        "notion-fetch",
        "notion-search",
        "notion-list-private-pages",
        "search_threads",
        "get_draft",
        "get_thread",
        "list_drafts",
        "get_message",
        "list_issues",
        "list_projects",
        "beatos_status",
        "list_tracks",
    }
)
# An MCP tool whose name says it writes is a change by the rule, not by a guess.
MCP_WRITE_WORDS = ("write", "create", "update", "edit")
# The guess for a name no list knows, tried in this order; nothing matched is talk.
HEURISTIC_WORDS = (
    (CHANGE, ("write", "create", "update", "edit", "delete")),
    (RUN, ("run", "exec", "navigate", "click", "type")),
    (READ, ("read", "get", "list", "search", "fetch")),
)

# --- shell commands ----------------------------------------------------------------

READ_PROGRAMS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "find",
        "fd",
        "wc",
        "stat",
        "file",
        "tree",
        "pwd",
        "echo",
        "printf",
        "which",
        "type",
        "env",
        "printenv",
        "du",
        "df",
        "jq",
        "sort",
        "uniq",
        "cut",
        "tr",
        "column",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "date",
        "whoami",
        "uname",
        "diff",
        "cmp",
        "nl",
        "shasum",
        "md5",
        "xxd",
        "od",
        "strings",
        "test",
        "[",
    }
)
# Words that neither read nor run on their own: they neither make a command read-only
# nor stop it from being so.
NEUTRAL_WORDS = frozenset(
    {
        "cd",
        "pushd",
        "popd",
        "export",
        "unset",
        "set",
        "true",
        "false",
        ":",
        "sleep",
        "wait",
        "for",
        "done",
        "fi",
        "esac",
        "if",
        "while",
        "until",
        "case",
        "}",
        ")",
        "local",
        "shopt",
    }
)
# Words in front of the program that do not change what it does.
PREFIX_WORDS = frozenset(
    {
        "sudo",
        "time",
        "command",
        "builtin",
        "do",
        "then",
        "else",
        "elif",
        "{",
        "(",
        "!",
        "nohup",
        "exec",
    }
)
GIT_READ = frozenset(
    {
        "log",
        "show",
        "diff",
        "status",
        "rev-parse",
        "ls-files",
        "blame",
        "describe",
        "shortlog",
        "cat-file",
        "ls-tree",
        "rev-list",
        "merge-base",
        "show-ref",
        "for-each-ref",
        "grep",
        "reflog",
    }
)
GIT_BRANCH_READ = frozenset(
    {
        "--list",
        "-l",
        "-a",
        "-r",
        "-v",
        "-vv",
        "--show-current",
        "--all",
        "--remotes",
        "--contains",
        "--merged",
        "--no-merged",
    }
)
FIND_WRITES = frozenset({"-exec", "-execdir", "-delete", "-ok", "-okdir", "-fprint"})
SQL_WRITES = re.compile(
    r"\b(insert|update|delete|create|drop|alter|replace|vacuum|attach|reindex)\b|\.import"
    r"|\.restore|\.save|\.output|\.once",
    re.I,
)
SQL_READS = re.compile(r"\b(select|pragma|with|explain)\b|\.schema|\.tables|\.indexes", re.I)
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_WRITE_REDIRECT = re.compile(
    r"(?<![0-9&<>])>>?(?![>&])(?!\s*/dev/null)|[0-9]>>?(?![>&])(?!\s*/dev/null)"
)
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_TEE = re.compile(r"\btee\b")


def call_kind(tool_name: str | None, command: str | None = None) -> tuple[str, bool]:
    """The bucket one tool call belongs to, and whether that rests on the name heuristic.

    `command` is the shell command for a shell tool and is ignored for every other one.
    """
    name = tool_name or ""
    if name in CHANGE_TOOLS:
        return CHANGE, False
    if name in SHELL_TOOLS:
        return (READ if shell_read_only(command or "") else RUN), False
    if name in RUN_TOOLS:
        return RUN, False
    if name in READ_TOOLS or name.startswith(READ_PREFIXES):
        return READ, False
    if name in TALK_TOOLS:
        return TALK, False
    if name.startswith(MCP_PREFIX):
        tail = name.rsplit("__", 1)[-1]
        if tail in MCP_CHANGE:
            return CHANGE, False
        if tail in MCP_RUN:
            return RUN, False
        if tail in MCP_TALK:
            return TALK, False
        if any(word in tail.lower() for word in MCP_WRITE_WORDS):
            return CHANGE, False
        return _guess(tail), True
    return _guess(name), True


def bucket_of(kinds: list[tuple[str, bool]]) -> tuple[str, bool]:
    """A response's bucket from its calls' kinds, and whether the winner is only a guess.

    No call at all is `talk`. The winning kind is a guess only when every call that
    produced it was one: a response that ran `pytest` and also called an unknown tool
    that looks like it runs something rests on the `pytest`.
    """
    if not kinds:
        return TALK, False
    best = max((kind for kind, _ in kinds), key=_RANK.__getitem__)
    return best, all(guessed for kind, guessed in kinds if kind == best)


def shell_read_only(command: str) -> bool:
    """True when every part of a shell command only reads."""
    if not command.strip():
        return False
    body = _without_heredocs(command)
    parts = _split(body)
    if any(_part_read_only(part, command) is False for part in parts):
        return False
    return not any(_TEE.search(part) for part in parts)


def _guess(name: str) -> str:
    low = name.lower()
    for kind, words in HEURISTIC_WORDS:
        if any(word in low for word in words):
            return kind
    return TALK


def _without_heredocs(command: str) -> str:
    """The command with each heredoc's body removed, so its text is not read as commands."""
    lines = command.split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        match = _HEREDOC.search(line)
        if match:
            end = match.group(1)
            while index < len(lines) and lines[index].strip() != end:
                index += 1
            index += 1
    return "\n".join(kept)


def _split(command: str) -> list[str]:
    """The parts of a compound command: split on && || ; | & and newlines, outside quotes."""
    parts: list[str] = []
    buffer: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            buffer.append(char)
            if char == "\\" and quote == '"' and index + 1 < len(command):
                buffer.append(command[index + 1])
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"":
            quote = char
            buffer.append(char)
            index += 1
            continue
        if char == "\\" and index + 1 < len(command):
            buffer.append(command[index : index + 2])
            index += 2
            continue
        if char in ";\n|&":
            # `2>&1` and `&>` are redirections, not a separator.
            redirect = char == "&" and (
                (index > 0 and command[index - 1] in "<>")
                or (index + 1 < len(command) and command[index + 1] == ">")
            )
            if redirect:
                buffer.append(char)
                index += 1
                continue
            parts.append("".join(buffer))
            buffer = []
            index += 2 if command[index : index + 2] in ("&&", "||") else 1
            continue
        buffer.append(char)
        index += 1
    parts.append("".join(buffer))
    return [part.strip() for part in parts if part.strip()]


def _part_read_only(part: str, whole: str) -> bool | None:
    """True reads, False runs or writes, None neither (`cd`, `sleep`, loop keywords).

    `whole` is the entire command with its heredoc bodies, because `sqlite3` is often fed
    its SQL from one.
    """
    if part.lstrip().startswith("#"):
        return None
    bare = _QUOTED.sub("''", part)
    if _WRITE_REDIRECT.search(bare):
        return False
    words = bare.split()
    while words and (words[0] in PREFIX_WORDS or _ASSIGNMENT.match(words[0])):
        words = words[1:]
    words = [word.strip("()") for word in words]
    words = [word for word in words if word]
    if not words:
        return None
    program = words[0].split("/")[-1]
    arguments = words[1:]
    if program in NEUTRAL_WORDS:
        return None
    if program == "env":
        rest = [w for w in arguments if not _ASSIGNMENT.match(w) and not w.startswith("-")]
        return _part_read_only(" ".join(rest), whole) if rest else True
    if program in {"sed", "gsed"}:
        return not any(w.startswith("-i") or w.startswith("--in-place") for w in arguments)
    if program in {"awk", "gawk"}:
        return "-i" not in arguments and "inplace" not in bare
    if program == "find":
        return not any(w in FIND_WRITES for w in arguments)
    if program == "sqlite3":
        sql = part + "\n" + whole
        return bool(SQL_READS.search(sql)) and not SQL_WRITES.search(sql)
    if program == "git":
        return _git_reads(arguments)
    return program in READ_PROGRAMS


def _git_reads(arguments: list[str]) -> bool:
    rest = list(arguments)
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag in {"-C", "-c"} and rest:
            rest.pop(0)
    if not rest:
        return False
    sub, tail = rest[0], rest[1:]
    if sub in GIT_READ:
        return True
    if sub == "branch":
        return all(word in GIT_BRANCH_READ for word in tail)
    if sub == "remote":
        return not tail or tail == ["-v"] or tail[0] in {"-v", "show", "get-url"}
    if sub == "stash":
        return bool(tail) and tail[0] in {"list", "show"}
    if sub == "config":
        return any(word in {"--get", "--list", "-l", "--get-all"} for word in tail)
    if sub == "worktree":
        return bool(tail) and tail[0] == "list"
    return False


# --- the rule's own test table -----------------------------------------------------


@dataclass(frozen=True)
class Case:
    """One response: its calls as (tool name, shell command), and the answer expected."""

    name: str
    calls: tuple[tuple[str, str | None], ...]
    bucket: str
    heuristic: bool = False


def _shell(command: str) -> tuple[str, str]:
    return ("Bash", command)


CASES = (
    Case("no tools at all", (), TALK),
    Case("read tools only", (("Read", None), ("Grep", None), ("Glob", None)), READ),
    Case("a test run", (_shell("uv run pytest -q"),), RUN),
    Case("an edit", (("Edit", None),), CHANGE),
    Case("a completed file change", (("FileChange", None),), CHANGE),
    Case("a completed read command", (("CommandExecution", "git status"),), READ),
    Case("a completed running command", (("CommandExecution", "pytest -q"),), RUN),
    Case(
        "compound read-only shell, quoted SQL with semicolons, git read, stderr to null",
        (
            _shell(
                "cd src && ls -la | grep x && git log --oneline -5 2>/dev/null; "
                'sqlite3 db "select 1; pragma table_info(t);"'
            ),
        ),
        READ,
    ),
    Case(
        "compound shell whose heredoc writes a file: every part must be read-only",
        (_shell("cd src && ls | grep x && cat > notes.txt <<'EOF'\nhello; rm -rf /\nEOF"),),
        RUN,
    ),
    Case(
        "mixed: edit beats run beats read beats talk",
        (("Read", None), _shell("pytest"), ("Edit", None), ("TodoWrite", None)),
        CHANGE,
    ),
    Case(
        "mixed: run beats read; an MCP browser navigate is run",
        (("Grep", None), ("mcp__claude-in-chrome__navigate", None), ("AskUserQuestion", None)),
        RUN,
    ),
    Case(
        "unknown tools fall to the name heuristic and are marked as a guess",
        (("mcp__acme__delete_item", None), ("FrobnicateThing", None), ("Read", None)),
        CHANGE,
        heuristic=True,
    ),
    Case(
        "dispatch and questions only; MCP tools that report state are talk",
        (("Agent", None), ("AskUserQuestion", None), ("mcp__claude-in-chrome__read_page", None)),
        TALK,
    ),
    Case(
        "a compound shell command with one writing part",
        (_shell("git status && ls src && rm -rf build"),),
        RUN,
    ),
    Case("sed without -i reads", (_shell("sed -n '1,40p' src/app.py"),), READ),
    Case("sed -i edits in place, which runs", (_shell("sed -i '' 's/a/b/' src/app.py"),), RUN),
    Case("git push runs", (_shell("git push origin main"),), RUN),
    Case("sqlite3 with SELECT reads", (_shell('sqlite3 store.db "SELECT COUNT(*) FROM t"'),), READ),
    Case(
        "sqlite3 with INSERT runs",
        (_shell('sqlite3 store.db "INSERT INTO t VALUES (1)"'),),
        RUN,
    ),
    Case(
        "an MCP tool no list knows, matched by the heuristic",
        (("mcp__acme__run_report", None),),
        RUN,
        heuristic=True,
    ),
    Case(
        "a guessed kind does not taint a winner the rule knows",
        (_shell("make build"), ("mcp__acme__run_report", None)),
        RUN,
    ),
    Case(
        "a subagent's response is classified like any other: reading its brief is read",
        (("Read", None), ("Glob", None), _shell("rg -n TODO src")),
        READ,
    ),
)
