---
name: ask
description: Answer a question about the user's own Prudence-recorded work from their record, using the computed evidence rather than a guess. Use when the user invokes /prudence:ask, or asks about their own history in words like "which of my sessions reworked the most", "why do my refactors keep getting reverted", "what did I spend last week on", or any question about their own sessions, commits, tokens or outcomes.
---

# /prudence:ask

Answer a question about the user's own recorded work from the evidence Prudence has
already computed.

## Steps

1. Call the `ask` MCP tool with the user's question as they asked it. Pass `project`
   only when they name a repository that the question itself does not contain. Do not
   rewrite the question first: the rules that read it handle "last week", "in August",
   "since Monday", a file path and quoted error text, and rewriting loses them.
2. Show the tool's `text` field first, verbatim. That is the evidence table: the
   sessions, the tokens by purpose, and the observations that apply. The user sees what
   the answer stands on before they read it.
3. Then answer the question in a few short paragraphs, using only the rows you were
   given:
   - Quote the numbers exactly as they appear. They are already rounded the way
     `prudence` prints them: shares are whole percents, tokens carry a `k` form beside
     the exact count, hours have one decimal.
   - Do no arithmetic. Do not add token counts together, and do not work out a total, an
     average, a difference, a ratio or a share of your own. The `totals` block holds the
     sums and shares that were computed; quote those. A figure that is in neither the
     rows nor `totals` is not in the record, and saying so is the correct answer.
   - Cite session ids as the first eight characters, so the user can run
     `prudence show --session <id>`.
   - Say what the evidence cannot tell. When the rows do not answer the question, name
     which part is unanswerable and what would answer it.
   - Every outcome figure travels with its coverage. When you quote one, say what it
     covers.
4. Mention once, at the end, that `prudence ask "<question>"` in a terminal writes the
   same answer with the engine's number and tone guards applied to it.

## What this skill will not do

- Do not invent a figure, extrapolate one, or round one differently. Every number in the
  answer must appear in the evidence you were handed.
- Do not grade the work. No scores, no rankings, and no word that judges: not solid,
  good, strong, healthy, impressive, poor, weak, concerning or dramatic. "92% coverage"
  is a fact; "92% coverage, which is solid" is a verdict, and it is not yours to give.
- Do not compare the user with anyone else or with an average. There is no data about
  any other person, here or anywhere in Prudence.
- Do not read transcript text. None is stored, and the tool cannot return any.
- Do not run `prudence ingest` or any other command unless the user asks.
- If the tool reports nothing ingested yet, tell the user to run `prudence init` and
  `prudence ingest` themselves.
