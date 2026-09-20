---
name: usage
description: Show where the user's own Prudence-recorded tokens and active time went, broken down by purpose and by project. Use when the user invokes /prudence:usage, or asks things like "where did my tokens go", "how much time did I spend", "show my usage", or asks for a breakdown of their own sessions by purpose or project.
---

# /prudence:usage

Show the user's own usage by running the `prudence usage` CLI command and printing
its output.

## Steps

1. Read the user's words for a time range and a project name, the same mapping
   `/prudence:sessions` uses: "last week" or "past 7 days" -> `--last 7d`; "last
   month" or "past 30 days" -> `--last 30d`; "last quarter" or "past 90 days" ->
   `--last 90d`; a project or repository name -> `--project <name>`. With no time
   range given, do not pass `--last` and let the command default to 30 days.
2. Run the command, for example:
   ```
   prudence usage --project offeros --last 30d
   ```
   or, with no arguments given, simply `prudence usage`.
3. Show the tables exactly as printed. Do not reformat them, summarize them away, or
   add a total or a judgement of your own; the command's own output is the whole
   answer. A dash means that Claude Code version wrote no usage fields, not zero
   tokens.
4. If the user asks what "purpose" means, explain in one line: purpose is a label
   from the session's tool mix (reads, searches, edits, test runs, repeated errors,
   whether it committed), never from reading the conversation, so it is a label
   rather than a measurement of intent.

## What not to do

- Do not invent token counts, hours or shares that are not in the command's output.
- Do not rank or score projects or purposes against each other, or suggest which
  purpose is a better use of tokens; the table is a breakdown, not a leaderboard.
- Do not run `prudence ingest` or any other command unless the user asks; this skill
  only reads what has already been recorded.
- If the command reports nothing ingested yet, tell the user to run `prudence init`
  and `prudence ingest` themselves.
