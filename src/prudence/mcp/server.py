"""The MCP server: eight read-only tools over the store, for Claude Code and other agents.

Same promise as every other surface, stated once here because an agent reading this
code is exactly the audience: no message text ever leaves the store, at any capture
level. A tool returns ids, dates, counts, repository names, full file paths (never at
`metadata-only`) and commit hashes, and nothing else. Rule 7 in ARCHITECTURE.md applies
here as much as anywhere: a tool reports numbers already computed; it does not compute
new ones and it never writes prose about them.

That last rule decides one thing about `ask`. In a terminal, `prudence ask` retrieves the
evidence and then makes one model call over it. Here the caller *is* a model, so the tool
stops after the evidence, as `--no-model` does, and says so. Two models writing prose
about one set of rows is a worse answer than one, and the second one would be the one
without the guards. The tool also writes nothing: the CLI stores a `question` row, and a
read-only surface leaves the store alone.

The rest of Prudence never imports the `mcp` package. This module is the one place that
does, and it fails at import time with an actionable message rather than a bare
`ModuleNotFoundError` if the optional dependency is missing.
"""

from __future__ import annotations

import sqlite3
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as error:  # pragma: no cover - exercised only when `mcp` is absent
    raise ImportError(
        "The mcp package is not installed. Install with: uv tool install 'prudence-dev[mcp]'"
    ) from error

from prudence.paths import database_file
from prudence.store import db, views

NOT_INGESTED = "Nothing ingested yet. Run `prudence ingest`."

mcp = FastMCP("prudence")


def _connect() -> sqlite3.Connection | None:
    """Open the store, or None when `prudence ingest` has never run.

    `db.connect()` creates the file the moment it is called, so the existence check has
    to come first or every tool would quietly manufacture an empty database.
    """
    if not database_file().exists():
        return None
    return db.connect()


def _resolve_session(connection: sqlite3.Connection, token: str) -> str | None:
    """A session id from an id or an unambiguous prefix; None otherwise, never a guess."""
    rows = [
        row["session_id"]
        for row in connection.execute(
            "SELECT session_id FROM session WHERE session_id LIKE ? ORDER BY session_id",
            (f"{token}%",),
        )
    ]
    return rows[0] if len(rows) == 1 else None


@mcp.tool()
def search_sessions(
    query: str = "",
    repo: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search recorded sessions, newest first.

    `query` matches full-capture edited file paths (repository-relative) and Bash
    command classes (`git_commit`, `test`, and so on); it never matches message text,
    because none is stored at any capture level. `repo` filters by repository name or
    key. `since`/`until` accept an ISO date (`2026-09-01`) or `7d`/`30d`/`90d` shorthand.
    `limit` defaults to 20 and is capped at 100 no matter what is asked for.

    Returns `{"results": [...], "total": N, "truncated": bool}`, or `{"message": "..."}`
    when nothing has been ingested yet. Each result carries only: session_id,
    repository, started_at, sittings, prompts, edits, tokens (input, output and cache
    tokens together, null when the Claude Code version recorded none), commits_fact,
    commits_inferred, commits_uncertain, commits_attributed (fact plus inferred, never
    uncertain), coverage and capture_notes. No message text is ever included.
    """
    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        repo_key = None
        if repo:
            repo_key = views.repo_key_for(connection, repo)
            if repo_key is None:
                return {"results": [], "total": 0, "truncated": False}
        return views.search_sessions(
            connection, query=query, repo_key=repo_key, since=since, until=until, limit=limit
        )
    finally:
        connection.close()


@mcp.tool()
def show_session(session_id: str) -> dict[str, Any]:
    """Everything `prudence show --session` prints, as structured JSON.

    `session_id` may be a full id or an unambiguous prefix. Returns identity (repository,
    capture level, timestamps, sittings), counts (records, turns, tool calls, edits,
    commands), token usage per model (null when the Claude Code version recorded none),
    edited files at full capture only (withheld at `metadata-only`), attributed commits
    with their method, confidence, rank and coverage, and the commits_fact,
    commits_inferred and commits_uncertain counts. Returns `{"message": "..."}` when
    nothing has been ingested yet or when the id does not match exactly one session.
    No message text at any capture level, because none is stored.
    """
    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        resolved = _resolve_session(connection, session_id)
        if resolved is None:
            return {"message": f"No single recorded session matches {session_id!r}."}
        summary = views.session_summary(connection, resolved)
        assert summary is not None  # resolved id came straight from the session table
        return summary
    finally:
        connection.close()


@mcp.tool()
def status() -> dict[str, Any]:
    """What `prudence status` prints, as JSON.

    Per-repository counts (files, archived bytes, sessions, edits, commits) and
    store-wide totals (archive size, derived table counts, token usage, commits by
    attribution method and by confidence, what became of every commit hash a session
    printed, hook events, unassigned sessions, unknown record types). No message text.
    """
    connection = _connect()
    try:
        return views.status_summary(connection)
    finally:
        if connection is not None:
            connection.close()


@mcp.tool()
def session_outcomes(session_id: str) -> dict[str, Any]:
    """One session's outcomes: survival, rework, coverage, purpose and behaviour facts.

    `session_id` may be a full id or an unambiguous prefix. Returns `outcomes` (survival
    share at 7, 30 and 90 days and at head, each next to the count of lines that mark
    was measured over; `reworked_share`; None when nothing about this session's counted
    lines was measured yet), `outcomes_suppressed` and `outcomes_suppressed_reason`
    (true, with why, when this repository's other authors dominate and outcome facts
    are withheld rather than shown wrong), `commits_fact`, `commits_inferred`,
    `commits_uncertain` and `coverage` (the method mix behind the counted commits),
    `purpose` (a label from tool mix, never from the conversation) and
    `behaviour_facts` (each with its `value`, `trust` and `fact_version`). Returns
    `{"message": "..."}` when nothing has been ingested yet or when the id does not
    match exactly one session. No message text at any capture level, because none is
    stored.
    """
    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        resolved = _resolve_session(connection, session_id)
        if resolved is None:
            return {"message": f"No single recorded session matches {session_id!r}."}
        summary = views.session_outcomes(connection, resolved)
        assert summary is not None  # resolved id came straight from the session table
        return summary
    finally:
        connection.close()


@mcp.tool()
def usage_summary(since: str = "30d", repo: str | None = None) -> dict[str, Any]:
    """Tokens by kind and active hours, summed by purpose and by project.

    The same sessions and the same sums `prudence usage` prints: input, output, cache
    read and cache creation tokens, and active hours (the sum of a session's own
    sittings, not the wall clock between its first and last record), grouped by purpose
    (`development`, `debugging`, `research`, `conversation`, `mixed`, `unknown`) and by
    project. `since` accepts an ISO date (`2026-09-01`) or `7d`/`30d`/`90d` shorthand
    and defaults to 30 days. `repo` filters by repository name or key. A purpose or
    project cell's token counts are 0 with `measured` at 0 when no session in it
    recorded any usage, which is not the same as recording zero tokens. Returns
    `{"message": "..."}` when nothing has been ingested yet. No message text.
    """
    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        repo_key = None
        if repo:
            repo_key = views.repo_key_for(connection, repo)
            if repo_key is None:
                return {
                    "sessions": 0,
                    "by_purpose": {},
                    "by_project": {},
                    "purpose_rule_version": None,
                }
        return views.usage_summary(connection, views.resolve_date(since), repo_key=repo_key)
    finally:
        connection.close()


@mcp.tool()
def observations(repo: str | None = None) -> dict[str, Any]:
    """The observations: how the user's own outcomes differ with and without a habit.

    Each row carries `sentence` (the finding in plain words, exactly as `prudence
    observations` prints it) and `caveat` (its coverage and method mix) alongside the
    numbers behind them: `repo_key`, `fact`, `threshold_text`, `outcome`, `with_n`,
    `without_n`, `with_value`, `without_value`, `direction`, `coverage`,
    `fact_commits`, `inferred_commits` and `fact_version`. `repo` restricts the answer
    to one project's own rows; left out, every row comes back, a project's own rows
    before the pooled ones (`repo_key` `"*"`, "across your projects", computed only for
    a behaviour no single project had enough sessions to answer). Returns
    `{"observations": []}` when the store holds none yet, or `{"message": "..."}` when
    nothing has been ingested at all. No message text: a sentence is built entirely
    from counts, never from reading a conversation.
    """
    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        from prudence.store import observations as observations_module

        repo_key = None
        if repo:
            repo_key = views.repo_key_for(connection, repo)
            if repo_key is None:
                return {"observations": []}
        names = views.repository_names(connection)
        rows = views.observations(connection, repo_key)
        return {
            "observations": [
                {
                    **row,
                    "sentence": observations_module.sentence(row, names.get(row["repo_key"])),
                    "caveat": observations_module.caveat(row),
                }
                for row in rows
            ]
        }
    finally:
        connection.close()


@mcp.tool()
def latest_review(project: str | None = None) -> dict[str, Any]:
    """The most recent stored `prudence review`, as JSON and as its Markdown page.

    `project` filters by repository name or key and returns the newest review written
    for that project alone; left out, the newest review of any scope comes back, which
    is the one `prudence review` last wrote. Returns `headline`, `project`, `repo_key`,
    `range` and `outcome_range` (the commits whose seven-day mark fell inside the
    range), `coverage`, `sections` (each with its title, headers, rows and notes),
    `numbers` (the inventory of every figure the sections contain, each with its key,
    text and coverage), `segment` (the optional model-written "what this means", with
    the model id and the numbers it was allowed to use, or null), the fact and parser
    versions the review was computed at, and `markdown`, the whole page exactly as the
    command printed it.

    Every figure here was computed by the engine before any model saw it: relay them,
    do not recompute them, and do not add one of your own. Returns
    `{"message": "..."}` when nothing has been ingested or no review has been written.
    """
    from prudence.reviews import render as render_module
    from prudence.reviews import schema as review_schema

    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        repo_key = None
        if project:
            repo_key = views.repo_key_for(connection, project)
            if repo_key is None:
                return {"message": f"No recorded repository is called {project!r}."}
            row = review_schema.last_review(connection, repo_key)
        else:
            rows = review_schema.reviews(connection, limit=1)
            row = rows[0] if rows else None
        if row is None:
            where = f" for {project}" if project else ""
            return {"message": f"No review has been written{where} yet. Run `prudence review`."}

        payload = review_schema.sections_of(row)
        names = views.repository_names(connection)
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "headline": render_module.headline(row),
            "repo_key": row["project"],
            "project": names.get(row["project"], row["project"]) or "every project",
            "range": {"start": row["range_start"], "end": row["range_end"]},
            "outcome_range": {
                "start": row["outcome_range_start"],
                "end": row["outcome_range_end"],
            },
            "coverage": row["coverage"],
            "sections": payload.get("sections", []),
            "numbers": payload.get("numbers", []),
            "segment": review_schema.segment_of(row),
            "fact_version": row["fact_version"],
            "parser_version": row["parser_version"],
            "markdown": render_module.render(row),
        }
    finally:
        connection.close()


@mcp.tool()
def ask(question: str, project: str | None = None) -> dict[str, Any]:
    """The evidence one question about the user's own work is answered from. No model.

    The same retrieval `prudence ask` runs: the question's time range, project, file
    path and quoted text are read by rules, the sessions of that range are found, and
    the computed rows behind them are the answer's evidence. `project` restricts it to
    one repository by name or key, over and above any the question itself names.

    Returns `question` (what the rules read out of it), `sessions` (each with its
    purpose, tokens, commits by confidence, coverage and what became of its lines),
    `usage` and `totals` (tokens and active hours by purpose, already summed),
    `observations` (each with the sentence `prudence observations` prints), `notes`
    (what was left out and why), and `text`, the whole thing rendered as the table
    `prudence ask --no-model` prints.

    This tool never calls a model, because the caller is one. Every number in it is
    rounded exactly as the CLI prints it, so quote them as they stand: do no arithmetic
    of your own, add no figure that is not here, cite the eight-character session ids so
    the user can run `prudence show --session <id>`, and describe rather than grade. The
    user can run `prudence ask "<question>"` themselves for a written answer over these
    same rows, with the number and tone guards applied to it.
    """
    from prudence.ask import answer as answer_module

    connection = _connect()
    if connection is None:
        return {"message": NOT_INGESTED}
    try:
        try:
            result = answer_module.ask(connection, question, model=None, project=project)
        except LookupError as error:
            return {"message": str(error)}
        return {
            **result.evidence.as_dict(),
            "text": answer_module.render(result, views.repository_names(connection)),
            "model": None,
            "note": (
                "Evidence only: this tool calls no model. For a written answer over the "
                'same rows, run `prudence ask "<question>"` in a terminal.'
            ),
        }
    finally:
        connection.close()


def run() -> None:
    """Start the server on stdio. The entry point `prudence mcp` calls."""
    mcp.run()
