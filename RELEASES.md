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

## 0.3.0 - 2026-09-21

M3: the app and the review. Two products now ship from this repository: the Python
engine and CLI (`prudence-dev`), and a native macOS menu-bar app (`apps/mac`, Swift,
built from the terminal, published as a DMG with each release) that reads the same
database through a versioned set of `app_*` SQL views and never computes a number of
its own. Underneath, `prudence review` turns the record into a stored review whose every
figure is computed, and `prudence ask` answers a question from retrieved evidence.

What's included:

- `prudence review [--last 14d | --since | --until | --month YYYY-MM] [--project]`:
  what you did (sessions, tokens and hours by purpose, commits, coverage), what became
  of earlier work (the commits whose 7-day mark fell inside the range), the observations
  that clear the floors, a comparison with the previous period of the same length, and
  the follow-up of last time's suggestions. Stored as a row (`review`, `suggestion`
  tables, never rebuilt, carried by export and import) and printed as Markdown into
  `reports/`. The default range is "since the last review"; a readiness rule refuses an
  empty review until at least five new sessions and one matured commit exist
  (`--force` overrides). Ranges follow your local calendar.
- `prudence review --explain` and `prudence explain <id>`: a model-written paragraph
  under "What this means", added only when a model is configured. The model receives
  the computed sections and a list of every number in them, and its text is refused
  if it uses a number not on that list or grades the work (a short list of praise and
  blame words is data, versioned); a refused draft is never printed or stored. Before
  the call Prudence prints what it sends: the sections, the number count, no transcript
  content, the size, the cap on the reply, whether the system prompt is cached, and the
  estimated cost.
- `prudence ask "<question>" [--project] [--no-model] [--with-content]`: rules read a
  range, a project, a file or an error from the question; the sessions in range (all of
  them unless a file or quoted text narrows) with their facts, outcomes and usage are
  the evidence, every number rounded as the terminal prints it; one model call answers
  from that evidence and cites session ids, under the same guards. `--no-model` prints
  the evidence alone; `--with-content` adds short archive excerpts for a `full` project
  and says so. Questions are stored (`question` table; `prudence show --question <id>`).
- `prudence config model`: backend (`anthropic` or `none`), model id (default
  `claude-sonnet-5`), key from `ANTHROPIC_API_KEY`; the SDK is the optional
  `prudence-dev[model]` extra. A recorded backend replays fixtures for tests.
- First look: the first completed `ingest` ends with three to five ranked facts about
  the history just read, each with the command that shows more; later ingests print at
  most two lines of new observations and a hint when a review is ready.
- The app contract: `store/app_views.py` creates `app_status`, `app_usage_by_purpose_day`,
  `app_outcomes_by_week`, `app_observation` (with the CLI's sentence), `app_session_list`,
  `app_commits_by_day` and `app_review` after every ingest and rebuild, all under 25 ms
  on a 740 MB store; `meta.app_contract_version` is `2`, and an app that does not know
  a version refuses to render. `--json` on `status`, `usage`, `outcomes`,
  `observations`, `sessions`, `ingest`, `review` and `ask`.
- The macOS app (`apps/mac`, version 0.1.0): a menu-bar icon whose dropdown shows
  today, this week's tokens by purpose, the latest observation, the last ingest and the
  last review's headline, with Open Prudence, Review now, Ingest now and Quit; a window
  with Overview (tokens by purpose per week as stacked bars, alive-at-30-days and rework
  shares per project as lines with their coverage, summary cards; project and range
  pickers), Review (the newest stored review rendered section by section, the model
  segment as a card, earlier reviews, Review now), Observations and Settings (engine
  path, database path, timed ingest every 30 minutes, open at login). XcodeGen project,
  a local Swift package with 76 tests, Swift Charts only, GRDB read-only, no sandbox;
  CI on `macos-26` builds unsigned and renders every screen to PNG in light and dark.
- The Claude Code plugin gains `/prudence:review` and `/prudence:ask`; the MCP server
  gains `latest_review` and `ask` (evidence only).
- The Python menu-bar prototype and the `menubar` extra are gone; `prudence menubar`
  says where the menu bar went.

Known limits: the app is published unsigned until the Developer ID certificate exists
(right-click, Open, on first launch); Sparkle updates and the Homebrew tap come with the
next app release; the suggestions follow-up has no screen yet (`prudence suggestions`).

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
