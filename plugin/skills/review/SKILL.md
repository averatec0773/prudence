---
name: review
description: Show the user's latest Prudence review, the stored page of what they did, what became of earlier work, the observations, and the comparison with the previous period. Use when the user invokes /prudence:review, or asks things like "show my review", "what did my last review say", "read me my review", "how did the last two weeks go", or asks to write a new review of their own recorded work.
---

# /prudence:review

Show the user's latest stored review, or write a new one, by running the `prudence
review` CLI command and printing its output.

## Steps

1. Decide whether the user wants to **read** the review they already have or **write**
   a new one. "Show my review", "what did my last review say" and "read me my review"
   mean read; "review my last two weeks", "write me a review" and "review beatos" mean
   write. When the words are ambiguous, read first: reading costs nothing and a new
   review changes the default range of the next one.
2. To read, call the `latest_review` MCP tool (`project` when the user names one) and
   print its `markdown` field verbatim. That is the stored page; it is already
   complete.
3. To write, map the user's words to the command's options, the same mapping
   `/prudence:sessions` uses:
   - A time range maps to `--last <N><unit>` (`7d`, `14d`, `2w`), or to
     `--month YYYY-MM` when the user names a month, or to `--since`/`--until` when they
     give dates. With no range given, pass none and let the command pick: everything
     since the last review of that scope, or the last seven days when there is none.
   - A project or repository name maps to `--project <name>`.
   Then run it, for example:
   ```
   prudence review --project offeros --last 14d
   ```
4. Print the page exactly as the command produced it. Do not reformat the tables,
   summarize them away, or recompute any figure in them.
5. If the command says the review is **not ready** ("2 new sessions since ... (needs
   5)"), relay that sentence and stop. Do not pass `--force` on your own; tell the user
   that `prudence review --force` writes it anyway and let them decide.
6. Offer the two follow-ups the page supports: `prudence show --review <id>` for the
   stored row, and `prudence suggestions` for what the review left open.

## What this skill will not do

- Do not invent, re-derive, round differently or "sanity check" any number on the page.
  Every figure in a review was computed by the engine and stored with an inventory of
  itself; a number you work out is a number nobody can re-derive.
- Do not turn the review into advice, a grade or a score. It describes what happened and
  what became of it. No adjective of judgement: not solid, strong, poor or concerning.
- Do not pass `--explain` unless the user asks for the model segment by name. It makes a
  billed model call.
- Do not run `prudence ingest`, `--force`, or anything else the user did not ask for.
- If the command reports nothing ingested yet, tell the user to run `prudence init` and
  `prudence ingest` themselves.
