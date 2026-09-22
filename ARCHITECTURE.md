# Architecture

How the code is organised and the rules that keep it easy to change. Read this before
adding a feature.

## One engine, several surfaces

Prudence is a Python library with a command-line interface. Every surface (the CLI, the
Claude Code plugin and MCP server, the menu-bar app, later a dashboard) reads the same
local store. Surfaces never contain analysis logic.

```
src/prudence/
  paths.py        every path Prudence reads or writes, in one place
  config.py       the user's choices, as TOML: which repositories, at which level
  scan.py         read-only inventory of agent history on this machine
  sources/        where we see the developer's work: one module per agent
    claude_code.py
  hooks/          the one thing we write into the user's world, and how to undo it
    __init__.py       install, uninstall and inspect the settings entries
    prudence-hook.sh  the POSIX shell hook itself, shipped as package data
  store/          Prudence's own record
    identity.py   which repository a directory belongs to
    repos.py      which repository a directory belongs to when it no longer exists
    db.py         the one SQLite file: connection, file mode, archive migrations
    archive.py    the agent's bytes, compressed, unmodified, appended incrementally
    derived.py    the versioned tables built from the archive and nothing else
    edits.py      what one tool call did: lines changed, what a command was for
    lines.py      one normalisation and one keyed hash, used by both sides of a match
    commits.py    what each commit added, harvested from the repository itself
    attribution.py  which session produced which commit, and how sure we are
    rewritten.py  commits a rebase renamed, or a quiet `git commit` never named, found
                   again by timing and overlapping lines
    outcomes.py   what became of each attributed line: presence at 7, 30, 90 days and at
                   HEAD, blame as the check, and rework by the author's own later commit
    observations.py  the join: for one behaviour and one threshold, the median outcome of
                   the sessions above it against the sessions below, inside one project
    spool.py      what the hooks saw, folded from the archived spool into hook_event
    erase.py      taking a session or a repository back out, archive included
    transfer.py   the whole store as one .tar.gz, and back into an empty one
    sampling.py   the precision sample: the hard quarter, drawn, and every method's score
    labels.py     the founder's own verdict on a sampled commit; user-authored, never rebuilt
    pipeline.py   the order the seven steps run in, so ingest and rebuild agree
    meta.py       the one key/value table a rebuild does not touch; holds the contract
                   version the app checks before it renders anything
    app_views.py  the `app_*` SQL views, the only thing a surface other than the CLI
                   reads: the column lists are the contract, recreated after every
                   ingest and rebuild
    views/        the read queries every surface shares; no formatting: sessions.py,
                   usage.py, outcomes.py, observations.py, search.py, status.py
  reviews/        the review: stored rows, not a report generator. Beside `store/`
                  rather than inside it, because a review is the user's own history of
                  what they were told and is never rebuilt from the archive.
    schema.py     the `review` and `suggestion` tables, and the shared `meta` markers
    ranges.py     which range a review covers, and which commits its outcomes are about
    readiness.py  whether enough has happened since the last review to write another
    build.py      the sections, from `store/views` and nothing else, with every figure
                   listed beside them as the `numbers` inventory
    render.py     one stored review as Markdown; layout only
    suggestions.py  the rows a review leaves open, their lifecycle and the follow-up
    first_look.py   the ranked candidate facts printed after the first `ingest`
  facts/          one behaviour fact per module, each versioned, trusted and self-tested:
                  base.py (the `Fact`/`Label`/`Case` dataclasses), registry.py (the
                  explicit lists and the `session_fact` plus `session_label` build step,
                  last in the pipeline), one module per fact reading only the derived
                  tables and carrying its own `CASES`; purpose.py is the one label,
                  a word per session from its tool mix, never a number
  cli/            one file per command; thin, calls the engine
  mcp/            the MCP server: server.py (FastMCP, stdio), the only place `mcp` is
                   imported; started by `cli/mcp.py`
apps/desktop/     the desktop app (Rust shell, HTML frontend): the menu-bar panel and
                  the window, for macOS and Windows from one codebase, reading the
                  `app_*` views and owning no numbers (apps/desktop/README.md).
apps/mac/         the previous macOS app (Swift), frozen at v0.4.0 as the comparison and
                  the way back. Not built, not changed (apps/mac/README.md).
                  It replaced the Python `rumps` prototype in M3; `prudence menubar`
                  now prints one line saying where the menu bar went.
plugin/           the Claude Code plugin: `.claude-plugin/plugin.json`, `.mcp.json`
                  wiring the `prudence mcp` command, `hooks/` (a copy of the hook set,
                  see plugin/README.md), and six skills: `skills/sessions`,
                  `skills/recall`, `skills/outcomes`, `skills/usage`, `skills/review`,
                  `skills/ask`
tests/            pytest; fixtures are synthetic, one file per observed format version
docs/reference/store-schema.md   every table and column, with its trust level
```

## Rules

1. **Raw bytes are the truth.** Agent data is archived unmodified. Every derived table can
   be dropped and rebuilt from the archive, so changing a parser is a rebuild, never a
   migration.
2. **Every derived fact carries the version of the code that produced it.** Bumping the
   version rebuilds that fact only. New facts are new functions; existing ones are not
   edited to add a column.
3. **Unknown input is kept, counted and skipped.** Record types the parser does not know
   are archived and reported by `prudence status`, never dropped and never fatal. The
   agents' transcript formats are internal and change between releases.
4. **Small named modules, no plug-in machinery yet.** A shared interface is extracted when
   the second source or the tenth fact arrives (rule of three), not before.
5. **The store schema is the contract.** `store/` documents every table, column, version
   and trust level. Surfaces read tables, not internals.
6. **Read-only toward the developer's world.** Prudence never writes to a repository or to
   an agent's files, except the hook entries it installs with consent and can uninstall.
7. **Numbers come from computation; a model only writes prose about numbers already
   computed.** Findings cite their evidence and state their coverage.
8. **No code leaves the archive.** Every other table holds counts, classes and keyed
   line hashes. The key is 32 random bytes made once per install and kept beside the
   config, so a hash cannot be tested against a guess and two machines' stores cannot
   be joined line by line. At `metadata-only` even the hashes are withheld, on both
   sides: that level promises shape, and a fingerprint of an employer's every line is
   not shape.
9. **A derived fact says how it was derived.** A session records which rule found its
   repository; an attribution records which of the three methods named it, its rank
   among the candidates, its coverage and, since M2, its confidence. A surface may
   present a guess, never as a fact.
10. **A number and its doubt travel together.** Every attribution carries `fact`,
   `inferred` or `uncertain` by one rule in one place (`store/attribution.confidence`,
   whose constants cite the labelled data behind them). A surface counts `fact` and
   `inferred`, shows `uncertain` beside them, and never folds one into the other. An
   absent measurement is NULL and printed as a dash: a session whose Claude Code version
   wrote no token usage has no usage rows, which is not zero tokens. The same holds for
   an outcome whose moment has not arrived: `line_fate.alive_90d` is NULL, never 0, for
   a commit made three weeks ago.
11. **A fact that would be about someone else is not computed at all.** Outcome facts are
   suppressed for a repository where more than `outcomes.OTHER_AUTHOR_SHARE` of the
   window's commits are by an identity that is not the user's; the flag and the counts
   behind it live on the `repository` row and every surface prints the reason in place
   of the number. Suppression is preferred to a caveat, because a survival percentage
   that silently includes a colleague's work is wrong rather than imprecise. Who counts
   as the user is decided once, in `outcomes.user_identities`: every author email hash
   that committed inside one of the user's sessions, anywhere in the store, plus the
   majority identity of each repository. A person commits under more than one address,
   and a robot is not a person at all: `commit.is_bot` is decided during the harvest on
   the raw author fields (`commits.BOT_MARKERS`) and leaves the denominator entirely.
12. **A label is not a number.** A classification (so far only a session's purpose) goes
   to `session_label` with the version of the rule that chose it, never to
   `session_fact`, whose `value` is REAL and is summed and averaged. Labels are grouped
   by and printed; they are never ranked, scored or averaged, and every surface that
   prints one says that it comes from counts rather than from reading the conversation.
13. **An observation is a join, and it is descriptive.** One row of `observation`
   (`store/observations.py`) compares one behaviour fact, at a threshold stored on the
   row as text, against one outcome of the user's own sessions: the sessions credited
   with lines that could be followed are split in two and each side's median is taken.
   It qualifies only with at least `observations.MIN_SESSIONS` sessions on each side and
   at least `observations.MIN_GAP` between the two medians, and it carries the fact
   version, the coverage and the method mix of the sessions behind it, like every
   outcome row. A row belongs to the project its sessions came from (principle 2); the
   pooled row, `repo_key = '*'`, exists only for a behaviour no single project had the
   sessions to answer, says "across your projects" in its own words, and is never shown
   inside a project's view. An observation states what the two sides did and stops there:
   no advice, no ranking, no score, and no adjective (principle 3). `direction` says
   which side is higher, not which is better.
14. **The Mac app reads only `app_*` views.** A screen that needs a number the engine
   does not compute gets a new view in `store/app_views.py`, never a join in Swift;
   `meta.app_contract_version` changes only when a view's columns change.
15. **A review is a row, and the page is a rendering of it.** `prudence review` stores
   the sections as JSON with an inventory of every figure that appears in them
   (`reviews/build.numbers`), and `reviews/render.py` prints those texts and nothing
   else numeric. No surface computes a review's arithmetic: the terminal, the Markdown
   file under `reports/` and the app's review screen all read the same row. A review is
   complete without a model; a model segment, when one exists, is stored beside the
   numbers list and may use no figure that is not in it.
16. **The model writes prose over numbers it was given, and two guards prove it.** The
   whole vendor dependency is `model/anthropic_backend.py`; every other backend
   (`recorded`, `none`) satisfies the same one-method protocol, and `select_model` is
   the only chooser. A model never computes and never grades: `numbers.check_numbers`
   flags a figure that was not in the input (principle 2) and `tone.check_tone` flags a
   word that judges the work (principle 3). A draft that fails either is sent back once
   with its offending tokens named (`model/guard.py`); if it fails again it is
   **discarded unprinted and unstored**, and the user is told which numbers or words
   were wrong, never what the draft said. Showing a rejected draft under a disclaimer
   would still leave its invented figures with the reader. A figure the prose wants and
   the rows lack is the engine's job to compute, not the model's, which is why `ask`
   sends a `totals` block. Every call prints the whole request shape before it is sent,
   and transcript content is sent only for a `full` project with `--with-content`.

## Adding things

- A new agent: one module in `sources/` that finds the agent's files and yields records.
- A new model backend: one file in `model/` with a `complete(request) -> Completion`, a
  name in `model.BACKENDS`, and its prices in `model/prices.py`. No other module imports
  a vendor SDK, and no command branches on which backend is in use.
- A new derived table or column: `store/derived.py`, then bump `PARSER_VERSION` and
  document the change in `docs/reference/store-schema.md`. Never write a migration.
- A new table harvested from git rather than from the archive: its own module under
  `store/`, a `FACT_VERSION`, a step in `store/pipeline.py`, and a section in the
  schema document. Read-only git commands only: `log`, `show`, `rev-parse`,
  `rev-list`, `notes`, `cat-file`, `blame`, `ls-tree`, `worktree list`, `patch-id`.
  A step that runs a command per commit caches by its argument and reads trees rather
  than diffs; if a repository is still too large, it samples deterministically by commit
  hash (`store/outcomes.MAX_COMMITS`) so that a rebuild reproduces the same sample, and
  every surface says how much was left out.
- A new derived fact computed from those tables: one function in `facts/` with a version
  and its test cases as data. `derived.py` builds the tables; `facts/` reads them.
  `rev-list`, `notes`, `cat-file`, `blame`, `worktree list`, `patch-id`.
- A new derived fact computed from those tables: one module in `facts/`, a `Fact` naming
  its version and trust level (high, medium or low, as in the coaching reference), a
  `compute(connection, session_id)` reading only `record`, `turn`, `tool_call`,
  `command`, `edit`, `attribution` and `session`, and its own `CASES`: synthetic session
  shapes with the value expected back, run by the one parametrised test in
  `tests/test_facts.py`. A missing field belongs in `derived.py` behind a
  `PARSER_VERSION` bump, never read from the archive inside a fact. Add the module's
  `FACT` to the list in `facts/registry.py`, which builds `session_fact` last in the
  pipeline; a fact returning `None` for a session leaves no row, not a fabricated zero.
  `derived.py` builds the tables; `facts/` reads them.
- A new label (a word per session rather than a number): the same module shape with a
  `Label` instead of a `Fact`, a closed tuple of the words it may answer with, a rule
  version, and its `CASES`; added to `LABELS` in `facts/registry.py`, which writes it to
  `session_label`. `facts/purpose.py` is the pattern.
- A new archive column: `store/db.py`, with `ARCHIVE_SCHEMA_VERSION` bumped and a step in
  `migrate`. Archive tables are the only ones that are migrated rather than rebuilt.
- A new setting the user chooses: `config.py`, and show it in `prudence status`.
- A new language: one entry in `model/language.LANGUAGES` and, if it needs one, a word
  list in `model/tone.WORDS_BY_LANGUAGE`. Only prose a model writes is translated: the
  prompts write in the configured language, every sentence the engine stores stays
  English, and a surface composes a localised sentence from the row's columns rather
  than asking the engine for a translated one.
- A new command: one file in `cli/`, registered in `cli/__init__.py`.
- A new surface: reads the store; puts nothing in `src/prudence/` except a thin adapter.
  `store/app_views.py` is the pattern: one view per screen, so a surface's own numbers
  are tested against the CLI's without its GUI toolkit anywhere near the test.
- A user-authored table (typed by a person, not derived from anything Prudence read):
  its own module beside the derived ones, e.g. `store/labels.py`. It lives next to the
  derived tables but is never rebuilt: `derived.build`'s table swap and any table a
  rebuild step drops must not name it, because a rebuild is only safe to run at all
  when nothing it touches was written by a person.
- A new hook event: the tuple in `hooks/__init__.py` and a branch in `prudence-hook.sh`.
  The script must stay POSIX shell, must exit 0 on every path, and must write nothing
  when `PRUDENCE_INTERNAL` is set or the working directory is not in `enabled.txt`.
- A new column anything can hold: it must survive `export` and `import` untouched,
  which is automatic as long as `store/transfer.py` knows how to create the table.

## The hooks, and the one thing they are allowed to write

`prudence hooks install` copies `prudence-hook.sh` to `<data dir>/hooks/` and adds six
synchronous entries to Claude Code's settings file, each running that copy with the
event name as its argument. The copy exists because Claude Code stores an absolute
command and a path inside a virtual environment stops existing on the next upgrade.

The script reads the hook JSON from stdin, pulls five known keys with one `awk` pass,
and stops at once unless the working directory sits under a path in
`<data dir>/hooks/enabled.txt`, which `hooks install` and every `ingest` write from the
`repository` table. When it does record, it appends one line to `<data dir>/spool.jsonl`
with the event, an ISO timestamp, the ids, the working directory, git's HEAD and branch,
a fingerprint and a count of `git status --porcelain`, and its own elapsed time. It
never fails and never prints. `ingest` archives that file like a transcript and folds it
into `hook_event`; the spool is never truncated.

## Privacy rules for contributors

- Never commit real transcripts. Fixtures are synthetic or anonymised, and the anonymiser
  lives in the repository.
- Tests never read `~/.claude`; they build their own files under a temporary directory and
  point Prudence at it with `CLAUDE_CONFIG_DIR`.
