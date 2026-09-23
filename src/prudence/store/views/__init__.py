"""Read-only queries over the derived tables, shared by `prudence show` and the MCP server.

Both surfaces need the same facts about a session: `cli/show.py` renders them as text,
`prudence/mcp/server.py` returns them as JSON. This package is the one place the SQL is
written, so the two never drift. Nothing here formats anything; that stays with the
caller. No function returns message text, because none is stored anywhere it could be
read from (architecture rule: no code leaves the archive).

Every name below is re-exported here, so `views.anything(...)` reads the same as it did
when this was one module. What each module holds:

- `common` - the sitting rule and the batched `session_id IN (...)` query both others need.
- `sessions` - one session at a time: its row, its counts, its files, `session_summary`.
- `usage` - tokens per session and per model, the purpose label, the active time.
- `outcomes` - commits credited to a session and what became of the lines they added.
- `observations` - the observation rows, per project or pooled.
- `search` - resolving a repository or a date, and searching across sessions.
- `status` - `prudence status`, as JSON.
"""

from __future__ import annotations

from prudence.store.views.common import SITTING_GAP, _batched
from prudence.store.views.observations import observations
from prudence.store.views.outcomes import (
    FATE_KEYS,
    _outcome_fact_version,
    counted_pairs,
    credited,
    credited_by_commit,
    credited_map,
    empty_fate,
    fate_by_commit,
    outcome_shares,
    outcomes_by_repository,
    outcomes_map,
    outcomes_of,
    session_outcomes,
    share,
    suppressed_repositories,
    suppression_notes,
)
from prudence.store.views.search import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    _counted_map,
    _sittings_map,
    repo_key_for,
    resolve_date,
    search_sessions,
)
from prudence.store.views.sessions import (
    _hook_turns,
    _scalar,
    archived_files,
    attributed_commits,
    commands_by_class,
    edit_totals,
    edited_files,
    hand_edits,
    hook_timeline,
    record_turn_toolcall_counts,
    repository_names,
    session_facts,
    session_row,
    session_summary,
    sittings,
    tool_calls_by_name,
    turn_ordinals,
)
from prudence.store.views.status import mapped_by_fallback, status_summary
from prudence.store.views.usage import (
    TOKEN_COLUMNS,
    _accumulate_usage,
    _empty_usage_cell,
    active_seconds_map,
    bucket_sessions,
    bucket_shares_map,
    bucket_totals,
    bucket_usage,
    purpose_counts,
    purpose_map,
    purpose_of,
    purpose_rule_version,
    session_usage,
    usage_by_kind_map,
    usage_map,
    usage_of_session,
    usage_summary,
    usage_totals,
)

__all__ = [
    "DEFAULT_LIMIT",
    "FATE_KEYS",
    "MAX_LIMIT",
    "SITTING_GAP",
    "TOKEN_COLUMNS",
    "_accumulate_usage",
    "_batched",
    "_counted_map",
    "_empty_usage_cell",
    "_hook_turns",
    "_outcome_fact_version",
    "_scalar",
    "_sittings_map",
    "active_seconds_map",
    "bucket_sessions",
    "bucket_shares_map",
    "bucket_totals",
    "bucket_usage",
    "archived_files",
    "attributed_commits",
    "commands_by_class",
    "counted_pairs",
    "credited",
    "credited_by_commit",
    "credited_map",
    "edit_totals",
    "edited_files",
    "empty_fate",
    "fate_by_commit",
    "hand_edits",
    "hook_timeline",
    "mapped_by_fallback",
    "observations",
    "outcome_shares",
    "outcomes_by_repository",
    "outcomes_map",
    "outcomes_of",
    "purpose_counts",
    "purpose_map",
    "purpose_of",
    "purpose_rule_version",
    "record_turn_toolcall_counts",
    "repo_key_for",
    "repository_names",
    "resolve_date",
    "search_sessions",
    "session_facts",
    "session_outcomes",
    "session_row",
    "session_summary",
    "session_usage",
    "share",
    "sittings",
    "status_summary",
    "suppressed_repositories",
    "suppression_notes",
    "tool_calls_by_name",
    "turn_ordinals",
    "usage_by_kind_map",
    "usage_map",
    "usage_of_session",
    "usage_summary",
    "usage_totals",
]
