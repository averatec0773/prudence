---
name: recall
description: Recall whether and when the user has worked on something before, using the Prudence MCP tools over their own recorded session history. Use when the user asks things like "have I worked on X before", "did I already build this", "when did I last touch this file/repo", or when starting a task where knowing prior related work would help.
---

# /prudence:recall

Search the user's own recorded session history for prior work related to the current
task, using the `prudence` MCP server's tools rather than the CLI.

## Steps

1. Build a short search query from the current task or the user's question: the main
   file paths, module or feature names, or repository involved. Keep it to a few words,
   the way you would search a codebase.
2. Call the `search_sessions` MCP tool with that query, and a `repo` filter when the
   current repository is known. Widen `since` (for example to `90d`) if the first search
   returns nothing.
3. For the most relevant matches (by recency and by how well the edited files or command
   classes match the task), call `show_session` to get each one's full detail: files
   edited, commits attributed, and coverage.
4. Present findings with their dates and repositories, for example: "You worked on
   `src/store/attribution.py` in the `prudence` repo on 2026-09-15 (session
   `9bc04769`), with a commit attributed at 92% coverage." Cite the session id so the
   user can look further with `prudence show --session <id>`.

## What not to do

- Never invent content: these tools return only ids, dates, counts, repository names,
  full file paths, and commit hashes. No message text is ever returned, so do not guess
  at what was discussed or written; describe only what the structured result shows.
- If `search_sessions` and `show_session` return no results, say so plainly. Do not
  fall back to guessing from general knowledge of the codebase and present it as
  session history.
- If a tool call returns a message about nothing being ingested yet, tell the user to
  run `prudence init` and `prudence ingest` themselves.
