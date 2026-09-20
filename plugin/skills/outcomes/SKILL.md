---
name: outcomes
description: Show what became of the code from the user's own Prudence-recorded sessions, survival at 7/30/90 days, rework, coverage, and the observations that connect a behaviour to an outcome. Use when the user invokes /prudence:outcomes, or asks things like "what survived", "how much of my code got reworked", "show my outcomes", or names a project for their own outcome history.
---

# /prudence:outcomes

Show the user's own outcomes by running the `prudence outcomes` CLI command and
printing its output.

## Steps

1. Read the user's words for a time range and a project name, the same mapping
   `/prudence:sessions` uses:
   - A time range maps to `--last <N><unit>`, where unit is `d` (days), `w` (weeks) or
     `h` (hours): "last week" or "past 7 days" -> `--last 7d`; "last month" or "past 30
     days" -> `--last 30d`; "last quarter" or "past 90 days" -> `--last 90d`. When the
     user gives no time range at all, do not pass `--last` and let the command default
     to 90 days.
   - A project or repository name maps to `--project <name>`. Omit `--project` when
     the user names none.
2. Run the command, for example:
   ```
   prudence outcomes --project offeros --last 30d
   ```
   or, with no arguments given, simply `prudence outcomes`.
3. Show the table and the observations exactly as printed, verbatim. Do not reformat
   them, summarize them away, or recompute any survival percentage, rework share or
   observation sentence; the command's own output is the whole answer. A dash means a
   mark has not happened yet, never a zero, and a repository suppressed for
   other-author dominance prints why in its own words instead of a number.
4. Offer to look at any one session in more depth: "Run `prudence show --session
   <id>` for the full record of any of these." Use the `session` column (an
   8-character id prefix) from the table for `<id>`.

## What not to do

- Do not invent survival percentages, rework shares, coverage figures or observation
  sentences that are not in the command's own output.
- Never turn an observation into advice. An observation describes what two groups of
  the user's own sessions did; it carries no ranking, no score and no recommendation,
  and neither should you when relaying it.
- Do not run `prudence ingest` or any other command unless the user asks; this skill
  only reads what has already been recorded.
- If the command reports nothing ingested yet, tell the user to run `prudence init`
  and `prudence ingest` themselves.
