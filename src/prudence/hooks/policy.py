"""Agent-specific hook selection and observation decoding, separate from historical facts.

Changing capture policy here does not change how archived transcripts are read.
Older Claude observations remain readable without retroactively inventing fields.
"""

from __future__ import annotations

# The set from the hooks spike: boundary events for identity and turn keys, and the
# Bash pair that is the only thing which sees a shell command change the tree. All
# synchronous, because `async: true` silently loses `Stop` and `SessionEnd`.
CLAUDE_EVENTS = (
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("Stop", None),
    ("SubagentStop", None),
    ("PreToolUse", "Bash"),
    ("PostToolUse", "Bash"),
)
CODEX_EVENTS = (
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("Stop", None),
    ("PreToolUse", "Bash|apply_patch"),
    ("PostToolUse", "Bash|apply_patch"),
)


def events_for(kind: str) -> tuple[tuple[str, str | None], ...]:
    return {"claude_code": CLAUDE_EVENTS, "codex": CODEX_EVENTS}[kind]


def normalize_observation(record: dict) -> dict:
    result = dict(record)
    result.setdefault("source", "claude_code")
    result.setdefault("source_id", "claude" if result["source"] == "claude_code" else "codex")
    if result["source"] == "codex":
        session = result.get("session_id")
        if isinstance(session, str) and not session.startswith("codex:"):
            result["session_id"] = f"codex:{session}"
        prompt = result.get("prompt_id") or result.get("turn_id")
        if isinstance(prompt, str) and not prompt.startswith("codex:"):
            prompt = f"{result['session_id']}:{prompt}"
        result["prompt_id"] = prompt
        call = result.get("tool_use_id")
        if isinstance(call, str) and call and not call.startswith("codex:"):
            result["tool_use_id"] = f"{result['session_id']}:{call}"
    return result
