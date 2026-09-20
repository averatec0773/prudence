---
name: sessions
description: Show recent Prudence-recorded sessions (this developer's own Claude Code history) as a table, with their edits, commands and attributed commits. Use when the user invokes /prudence:sessions, or asks things like "what have I worked on recently", "show my sessions", "what did I do last week/month", or names a project and a time range for their own session history.
---

# /prudence:sessions

Show the user's own recorded session history by running the `prudence sessions` CLI
command and printing its table.

## Steps

1. Read the user's words for a time range and a project name.
   - A time range maps to `--last <N><unit>`, where unit is `d` (days), `w` (weeks) or
     `h` (hours): "last week" or "past 7 days" -> `--last 7d`; "last month" or "past 30
     days" -> `--last 30d`; "last quarter" or "past 90 days" -> `--last 90d`. When the
     user gives no time range at all, do not pass `--last` and let the command default
     to 7 days.
   - A project or repository name maps to `--project <name>`: "on offeros" or "in the
     offeros repo" -> `--project offeros`. Omit `--project` when the user names none.
2. Run the command, for example:
   ```
   prudence sessions --last 30d --project offeros
   ```
   or, with no arguments given, simply `prudence sessions`.
3. Show the table exactly as printed. Do not reformat it, summarize it away, or add
   numbers of your own; the command's own output is the whole answer. Two columns read
   oddly out of context and should be explained if the user asks: `tokens` is input,
   output and cache tokens together in thousands, with a dash where the Claude Code
   version recorded none; `commits` is `N (+M) (?K)`, that is N known for certain, M
   inferred from line matching, and K uncertain attributions that enter no count.
4. Offer to look at any one session in more depth: "Run `prudence show --session
   <id>` for the full record of any of these." Use the `session` column (an 8-character
   id prefix) from the table for `<id>`.

## What not to do

- Do not invent session ids, counts, or dates that are not in the command's output.
- Do not run `prudence ingest` or any other command unless the user asks; this skill
  only reads what has already been recorded.
- If the command reports nothing ingested yet, tell the user to run `prudence init`
  and `prudence ingest` themselves; do not run those for them.
