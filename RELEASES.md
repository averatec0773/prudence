# Releases

This file lists what shipped in each Prudence release. It replaces a conventional
`CHANGELOG.md` here (the name is reserved for a private, harness-internal file that
must never appear in this public repository; see the leak-guard check in
`.github/workflows/ci.yml`). `RELEASES.md` is where public release notes live instead,
and `CONTRIBUTING.md` says so under "Releasing."

## One-time PyPI setup

Before the first tag can publish, the project owner does this once, on pypi.org:

1. Sign in, go to your account, and create the project's trusted publisher before the
   project exists on PyPI: **Publishing** -> **Add a pending publisher**.
2. Fill in:
   - PyPI project name: `prudence-dev`
   - Owner: `averatec0773`
   - Repository name: `prudence`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. Save it. The first push of tag `v0.1.0` that runs `.github/workflows/release.yml`
   will then be allowed to publish without any stored password or API token: GitHub
   Actions gets a short-lived OpenID Connect token, scoped to this repository and this
   workflow, and PyPI exchanges it for a publish permission.

Nothing else needs a secret. There is no `PYPI_API_TOKEN` to create or rotate.

## 0.2.0 - 2026-09-20

M2: what became of the code, and where the tokens went. On top of 0.1.0's recorder,
Prudence now follows an attributed commit's lines forward (still present at 7, 30 and 90
days, still at head, reworked by your own later commit) and follows a session's tokens
and active time back to a purpose (development, research, debugging, conversation,
mixed), so a session that produced no code stops looking like a gap in the record. A new
join, observations, compares your own sessions with a behaviour against your own
sessions without it, inside one project, and says so only when the sample and the gap
both clear a floor. Attribution itself got more careful: a rewritten or quietly
committed hash can now be re-identified, and every commit carries a confidence label
instead of being trusted or not as a block.

What's included:

- `prudence outcomes --project <repo> --last <window>`: survival at 7/30/90 days and at
  head, rework, coverage and method mix per session; a repository where other people
  commit prints why its numbers are withheld instead of a wrong number.
- `prudence usage --last <window> --project <repo>`: tokens (input, output, cache read,
  cache creation) and active hours, broken down by purpose and by project, with each
  purpose's share.
- `prudence facts --last <window>`: one row per session, one column per behaviour fact.
- `prudence observations --project <repo>`: the join, in plain words with its numbers.
- `prudence sample`: draws the hard quarter of commits for labelling, so line matching
  keeps being checked against real, unlabelled-by-construction work.
- `prudence classify --model`: designed and documented, refuses to run; the rule-based
  purpose label ships, the optional model label does not.
- **Attribution confidence**: every commit attribution is now `fact` (an in-session
  commit or a git-ai note), `inferred` (a rank-1 line match at or above a third of the
  commit's added lines and beating the runner-up by 2x), or `uncertain` (everything
  else, shown but never counted).
- **Rewritten and silent commits re-identified**: a commit a rebase or squash renamed,
  or one a quiet `git commit` never printed a hash for at all, is matched back to its
  session by committer timing plus overlapping lines, one alias per printed hash.
- **Line survival and rework**: presence at 7/30/90 days and at head (same path, then
  any path), `git blame -w -M` as a second check, and rework when the user's own later
  commit removed the line; suppressed with a stated reason in a repository where other
  authors dominate.
- **Twelve behaviour facts**, each versioned and trust-labelled: sittings, files edited
  before read, formatter runs, test runs, tests before commit, commit attempts per
  commit, repeated identical errors, subagent use, compactions, context resets, prompts
  per active hour, hand edits between turns.
- **Session purpose labels** from tool mix alone (development, research, debugging,
  conversation, mixed, unknown), with the rule version stored beside every label.
- **Observations**: a behaviour and an outcome compared across a project's own sessions,
  shown only with at least 5 sessions on each side and at least a 10-point gap between
  the two medians.
- **Hand edits between turns**: for sessions recorded since the hooks were installed,
  a working-tree change between two turns with no Bash call in between is counted as a
  hand edit, per turn and per session.
- Three new MCP tools (`session_outcomes`, `usage_summary`, `observations`) alongside
  the two from 0.1.0, and two new skills, `/prudence:outcomes` and `/prudence:usage`.
- The menu bar now shows this week's tokens by purpose and the latest observation.

Known limits:

- Purpose is a label read from tool-call counts, not from what the session was about;
  it can misclassify, and no finding rests on a label alone.
- Observations are descriptive correlations within one project, never advice, a
  ranking or a score, and never compared across projects unless no single project had
  enough sessions to answer.
- Hand-edit detection only covers sessions recorded since the hooks were installed;
  older sessions report "not captured", not zero.
- Windows is untested.

Rebuild note: the parser and fact versions changed in this release, so 0.2.0 rebuilds
every derived and harvested table automatically on the first `ingest` or `rebuild` you
run after upgrading. The archive itself, your raw recorded bytes, is untouched.

## 0.1.0 - 2026-09-19

M1: the first demo skeleton, released publicly as a recorder. Prudence records your
Claude Code sessions (opt-in, per repository, at `full` or `metadata-only` capture),
archives the raw session data unmodified, and links it to the commits it produced,
reachable from the terminal, from inside a Claude Code session (a skill and an MCP
tool), and from a macOS menu-bar prototype. No model calls, no outcomes, no review yet.

What's included:

- `prudence init --scan` / `prudence init --enable <repo> --level full|metadata-only`
- `prudence ingest`
- `prudence sessions --last 30d`
- `prudence show --session <id>`
- `prudence hooks install` / `prudence hooks uninstall`
- `prudence forget --session <id>` / `prudence forget --project <name>`
- `prudence export` / `prudence import`
- `prudence menubar` (macOS, optional `[menubar]` extra)
- `prudence mcp` and the Claude Code plugin in `plugin/` (optional `[mcp]` extra)

Known limits:

- Attribution precision (line_match 97% when it answers, window methods 98%) was
  measured on one machine and one developer's history. It has not been checked on a
  second machine or a different working style.
- Windows is untested.
- No outcomes or reviews yet; this release is a recorder only.
