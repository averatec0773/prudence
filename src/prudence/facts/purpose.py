"""What a session was for, decided by its tool mix. A label, never a number.

M0's fifth finding was that a large share of recent sessions produce no code at all and
that the table could not say why; the founder could, session by session (one repository
is job applications and notes, another moved from building a demo to preparing a talk),
and that is the column this module adds. Principle 3 allows it explicitly: "usage broken
down by purpose (what the tokens and time went to)" is factual feedback on the data.

The rules read counts only: tool calls, reads, searches, edits, test runs, repeated
errors and whether the session committed. No message text is read, here or anywhere, so
a session about job applications is not recognised as such; it is recognised as a
session that talked and did not edit. That is the honest limit of a tier-1 rule
(proposal v2 section 4.11) and the footer of every surface that prints the label says
so. The tier-3 alternative, a model reading redacted text, is designed in
`cli/classify.py` and deliberately not implemented.

The rules, in order, first match wins:

1. `conversation`: no tool calls at all, or fewer tool calls than
   `CONVERSATION_TOOL_SHARE` of the prompts with no edit at all. Thinking out loud.
2. `research`: reads and searches together are at least `RESEARCH_RATIO` times the
   edits, and there are fewer than `RESEARCH_MAX_EDITS` edits. Reading the code or the
   web, with at most an incidental change.
3. `debugging`: at least `DEBUG_MIN_TEST_RUNS` test runs over at most
   `DEBUG_MAX_FILES` distinct files, or a repeated identical error with fewer than
   `DEBUG_MAX_EDITS` edits. Going round the same loop.
4. `development`: at least `DEVELOPMENT_MIN_EDITS` edits, or any commit the session
   itself made. Building something.
5. `mixed`: tool use that fits none of the shapes above.
6. `unknown`: the session has no records at all. A `metadata-only` session still has
   counts and gets a real label; only an empty one is unknown.

The order matters more than any single threshold. Research sits before debugging because
a session that reads far more than it edits is reading, whatever else it ran; debugging
sits before development because a loop of tests and small edits is not the same work as
writing five files, even though both edit. Every threshold is a constant here, because a
number buried in an `if` is a number nobody revises.
"""

from __future__ import annotations

import sqlite3

from prudence.facts import repeated_errors
from prudence.facts.base import Case, Label

RULE_VERSION = 1

CONVERSATION = "conversation"
RESEARCH = "research"
DEBUGGING = "debugging"
DEVELOPMENT = "development"
MIXED = "mixed"
UNKNOWN = "unknown"
PURPOSES = (CONVERSATION, RESEARCH, DEBUGGING, DEVELOPMENT, MIXED, UNKNOWN)

# Below this share of the prompt count, the tool calls are incidental to a conversation.
CONVERSATION_TOOL_SHARE = 0.05
# Reading outweighs editing by this much, with this few edits, before it is research.
RESEARCH_RATIO = 3
RESEARCH_MAX_EDITS = 5
# A test loop: this many test runs over at most this many files, or a repeated error
# in a session that is not also a large build.
DEBUG_MIN_TEST_RUNS = 3
DEBUG_MAX_FILES = 5
DEBUG_MAX_EDITS = 20
# Enough edits to be building something, whatever else happened.
DEVELOPMENT_MIN_EDITS = 5

# The tools that count as looking rather than changing.
READ_TOOLS = ("Read", "NotebookRead")
SEARCH_TOOLS = ("Grep", "Glob", "WebSearch", "WebFetch")


def compute(connection: sqlite3.Connection, session_id: str) -> str:
    """The label for one session. Always a word from `PURPOSES`, never None."""
    if not _count(connection, "SELECT COUNT(*) FROM record WHERE session_id = ?", session_id):
        return UNKNOWN

    prompts = _count(connection, "SELECT COUNT(*) FROM turn WHERE session_id = ?", session_id)
    tool_calls = _count(
        connection, "SELECT COUNT(*) FROM tool_call WHERE session_id = ?", session_id
    )
    edits = _count(connection, "SELECT COUNT(*) FROM edit WHERE session_id = ?", session_id)

    if tool_calls == 0 or (tool_calls < CONVERSATION_TOOL_SHARE * prompts and edits == 0):
        return CONVERSATION

    looked = _looked(connection, session_id)
    if looked >= RESEARCH_RATIO * edits and edits < RESEARCH_MAX_EDITS:
        return RESEARCH

    tests = _count(
        connection,
        "SELECT COUNT(*) FROM command WHERE session_id = ? AND command_class = 'test'",
        session_id,
    )
    files = _count(
        connection,
        "SELECT COUNT(DISTINCT COALESCE(rel_path, file_path, tool_use_id)) FROM edit"
        " WHERE session_id = ?",
        session_id,
    )
    repeated = repeated_errors.compute(connection, session_id) or 0
    if (tests >= DEBUG_MIN_TEST_RUNS and files <= DEBUG_MAX_FILES) or (
        repeated > 0 and edits < DEBUG_MAX_EDITS
    ):
        return DEBUGGING

    if edits >= DEVELOPMENT_MIN_EDITS or _committed(connection, session_id):
        return DEVELOPMENT
    return MIXED


def _looked(connection: sqlite3.Connection, session_id: str) -> int:
    """Read and search tool calls together, the left-hand side of the research rule."""
    names = READ_TOOLS + SEARCH_TOOLS
    placeholders = ", ".join("?" * len(names))
    return _count(
        connection,
        f"SELECT COUNT(*) FROM tool_call WHERE session_id = ? AND tool_name IN ({placeholders})",
        session_id,
        names,
    )


def _committed(connection: sqlite3.Connection, session_id: str) -> bool:
    """Whether the session itself ran a `git commit` that produced a commit we found."""
    try:
        return bool(
            _count(
                connection,
                "SELECT COUNT(*) FROM attribution WHERE session_id = ? AND method = 'in_session'",
                session_id,
            )
        )
    except sqlite3.OperationalError:
        return False


def _count(
    connection: sqlite3.Connection, query: str, session_id: str, extra: tuple[str, ...] = ()
) -> int:
    return connection.execute(query, (session_id, *extra)).fetchone()[0]


def _turns(session_id: str, count: int) -> list[dict]:
    return [
        {"turn_id": f"{session_id}-t{index}", "session_id": session_id} for index in range(count)
    ]


def _records(session_id: str, count: int = 1) -> list[dict]:
    return [
        {
            "record_id": f"{session_id}-r{index}",
            "session_id": session_id,
            "timestamp": "2026-09-15T09:00:00Z",
        }
        for index in range(count)
    ]


def _calls(session_id: str, tool_name: str, count: int) -> list[dict]:
    return [
        {
            "tool_use_id": f"{session_id}-{tool_name}-{index}",
            "session_id": session_id,
            "tool_name": tool_name,
        }
        for index in range(count)
    ]


def _edits(session_id: str, count: int, path: str = "src/app.py") -> list[dict]:
    return [
        {
            "tool_use_id": f"{session_id}-{path}-{index}",
            "session_id": session_id,
            "tool_name": "Edit",
            "rel_path": path,
        }
        for index in range(count)
    ]


def _commands(session_id: str, command_class: str, count: int) -> list[dict]:
    return [
        {
            "tool_use_id": f"{session_id}-c{index}",
            "session_id": session_id,
            "command_class": command_class,
        }
        for index in range(count)
    ]


CASES = (
    Case(
        name="no records at all: unknown",
        session_id="s0",
        expected=UNKNOWN,
        rows={"session": [{"session_id": "s0", "capture_level": "full"}]},
    ),
    Case(
        name="twenty prompts and no tool call at all: conversation",
        session_id="s1",
        expected=CONVERSATION,
        rows={
            "session": [{"session_id": "s1", "capture_level": "full"}],
            "record": _records("s1", 3),
            "turn": _turns("s1", 20),
        },
    ),
    Case(
        name="forty prompts, one tool call, no edit: still conversation",
        session_id="s2",
        expected=CONVERSATION,
        rows={
            "session": [{"session_id": "s2", "capture_level": "full"}],
            "record": _records("s2", 3),
            "turn": _turns("s2", 40),
            "tool_call": _calls("s2", "Read", 1),
        },
    ),
    Case(
        name="twelve reads and searches against one edit: research",
        session_id="s3",
        expected=RESEARCH,
        rows={
            "session": [{"session_id": "s3", "capture_level": "full"}],
            "record": _records("s3", 3),
            "turn": _turns("s3", 6),
            "tool_call": _calls("s3", "Read", 8) + _calls("s3", "Grep", 4),
            "edit": _edits("s3", 1),
        },
    ),
    Case(
        name="four test runs over two files: debugging",
        session_id="s4",
        expected=DEBUGGING,
        rows={
            "session": [{"session_id": "s4", "capture_level": "full"}],
            "record": _records("s4", 3),
            "turn": _turns("s4", 10),
            "tool_call": _calls("s4", "Read", 2) + _calls("s4", "Bash", 4),
            "edit": _edits("s4", 6, "src/one.py") + _edits("s4", 2, "src/two.py"),
            "command": _commands("s4", "test", 4),
        },
    ),
    Case(
        name="a repeated identical error and a handful of edits: debugging",
        session_id="s5",
        expected=DEBUGGING,
        rows={
            "session": [{"session_id": "s5", "capture_level": "full"}],
            "record": _records("s5", 3),
            "turn": _turns("s5", 8),
            "tool_call": [
                *_calls("s5", "Read", 2),
                *[
                    {
                        "tool_use_id": f"s5-err{index}",
                        "session_id": "s5",
                        "tool_name": "Bash",
                        "is_error": 1,
                        "error_hash": "h1",
                    }
                    for index in range(3)
                ],
            ],
            "edit": _edits("s5", 6),
        },
    ),
    Case(
        name="eight edits, little reading, no test loop: development",
        session_id="s6",
        expected=DEVELOPMENT,
        rows={
            "session": [{"session_id": "s6", "capture_level": "full"}],
            "record": _records("s6", 3),
            "turn": _turns("s6", 9),
            "tool_call": _calls("s6", "Read", 3) + _calls("s6", "Edit", 8),
            "edit": _edits("s6", 8),
        },
    ),
    Case(
        name="two edits and a commit of its own: development, not mixed",
        session_id="s7",
        expected=DEVELOPMENT,
        rows={
            "session": [{"session_id": "s7", "capture_level": "full"}],
            "record": _records("s7", 3),
            "turn": _turns("s7", 5),
            "tool_call": _calls("s7", "Edit", 2) + _calls("s7", "Bash", 3),
            "edit": _edits("s7", 2),
            "attribution": [
                {
                    "commit_hash": "a" * 40,
                    "session_id": "s7",
                    "method": "in_session",
                    "rank": 1,
                    "confidence": "fact",
                }
            ],
        },
    ),
    Case(
        name="three edits, two reads, no commit and no test loop: mixed",
        session_id="s8",
        expected=MIXED,
        rows={
            "session": [{"session_id": "s8", "capture_level": "full"}],
            "record": _records("s8", 3),
            "turn": _turns("s8", 7),
            "tool_call": _calls("s8", "Read", 2) + _calls("s8", "Bash", 4),
            "edit": _edits("s8", 3),
        },
    ),
    Case(
        name="metadata-only still has counts, so it still gets a label",
        session_id="s9",
        expected=RESEARCH,
        rows={
            "session": [{"session_id": "s9", "capture_level": "metadata-only"}],
            "record": _records("s9", 3),
            "turn": _turns("s9", 6),
            "tool_call": _calls("s9", "Read", 9),
        },
    ),
)

LABEL = Label(name="purpose", version=RULE_VERSION, values=PURPOSES, compute=compute, cases=CASES)
