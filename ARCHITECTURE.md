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
  sources/        where we see the developer's work: one package per agent, behind one
                   interface, so the store never learns an agent's file format
    base.py       the `Source` protocol and the event types; no agent knowledge
    __init__.py   the registry: kind -> adapter (`claude_code` and `codex`)
    codex/        Codex rollouts, completed operations and per-response/cumulative usage
    claude_code/  everything that knows Claude Code's layout and format
      discovery.py  where the files are, and what a scan reads from one
      events.py     transcript lines -> events
  hooks/          the one thing we write into the user's world, and how to undo it
    __init__.py       install, uninstall and inspect the settings entries
    policy.py         agent-specific event selection and observation normalization
    prudence-hook.sh  the POSIX shell hook itself, shipped as package data
  store/          Prudence's own record
    identity.py   which repository a directory belongs to
    repos.py      which repository a directory belongs to when it no longer exists
    db.py         the one SQLite file: connection, file mode, archive migrations
    archive.py    the agent's bytes, compressed, unmodified, appended incrementally
    derived.py    the versioned tables, built from the events one adapter yields over
                   the archive and nothing else; owner of the capture level, of the
                   pairing of a call with its result, and of which session a record
                   belongs to
    parse_plan.py   which sessions a parse reads, in reading order, each resolved to its
                   repository before any is read; for an ingest, which inputs moved
    parse_state.py  what the last parse read (each file's generation, size and digest,
                   under which parser) and which sessions depend on which, so that an
                   ingest reads only what changed; bookkeeping, read by no surface
    parse_pool.py   archived files into events in worker processes (spawn, so any
                   platform), handed back in the order asked for; writes nothing
    agent_turns.py  which turn a subagent's records belong to: the turn whose call
                   dispatched the agent, resolved once a session's every file is read
    buckets.py    what one response did (change, run, read, talk), from its tool calls
                   alone: the tool lists, the read-only shell parser and the precedence,
                   as data with `BUCKET_RULE_VERSION` and a table of cases
    edits.py      what one tool call did: lines changed, what a command was for
    lines.py      one normalisation and one keyed hash, used by both sides of a match
    commits.py    what each commit added, harvested from the repository itself
    attribution.py  which session produced which commit, and how sure we are
    rewritten.py  commits a rebase renamed, or a quiet `git commit` never named, found
                   again by timing and overlapping lines
    outcomes.py   what became of each attributed line: presence at 7, 30, 90 days and at
                   HEAD, blame as the check, and rework by the author's own later commit;
                   a mark already measured is kept in `outcome_mark`, HEAD never is
    observations.py  the join: for one behaviour and one threshold, the median outcome of
                   the sessions above it against the sessions below, inside one project;
                   a fact with no threshold is named in `NOT_SPLIT` on purpose
    spool.py      what the hooks saw, folded from the archived spool into hook_event
    erase.py      taking a session or a repository back out, archive included
    transfer.py   the whole store as one .tar.gz, and back into an empty one
    sampling.py   the precision sample: the hard quarter, drawn, and every method's score
    labels.py     the founder's own verdict on a sampled commit; user-authored, never rebuilt
    pipeline.py   the order the eleven steps run in, so ingest and rebuild agree, and
                   the record of the last run of each that `prudence status` prints
    checks.py     the self-checks run after the last step: named predicates over the
                   tables just written, each with the numbers it compared
    run_warnings.py  what a run met and kept going past (unknown record types, lines
                   that are not records, undispatched subagents, guessed buckets, failed
                   checks), as kinds, counts and shape-only samples
    runlog.py     `logs/runs.jsonl`: a start line and an end line per command that
                   changes something, folded by `run_id`; rotation, reading, states
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
                  a word per session from its tool mix, never a number.
                  test_fix_loops.py, reread_files.py, giant_turns.py and
                  changes_after_compaction.py are the waste facts over `response`
                  (docs/reference/usage-buckets.md): counts of what tokens went into,
                  which overlap and are never summed with each other
  cli/            one file per command; thin, calls the engine. `recording.py` is the
                   one place a command meets the run log (`with recorded() as run:`)
  mcp/            the MCP server: server.py (FastMCP, stdio), the only place `mcp` is
                   imported; started by `cli/mcp.py`
apps/desktop/     the desktop app (Rust shell, HTML frontend): the menu-bar panel and
                  the window, for macOS and Windows from one codebase, reading the
                  `app_*` views and owning no numbers (apps/desktop/README.md).
                  It replaced the earlier Swift macOS app (retired from master in
                  2026-09; its commits stay in the history), which had replaced the
                  Python `rumps` prototype in M3;
                  `prudence menubar` prints one line saying where the menu bar went.
plugin/           the Claude Code plugin: `.claude-plugin/plugin.json`, `.mcp.json`
                  wiring the `prudence mcp` command, `hooks/` (a copy of the hook set,
                  see plugin/README.md), and six skills: `skills/sessions`,
                  `skills/recall`, `skills/outcomes`, `skills/usage`, `skills/review`,
                  `skills/ask`
tests/            pytest; fixtures are synthetic, one file per observed format version
docs/reference/store-schema.md   every table and column, with its trust level
```

## The units of the record

project (a git repository, keyed by its root commit) > session (one conversation; forks
and resumes resolved by the ownership rule below) > turn (one prompt of the person, until
the next) > response (one reply of the model: the records that share one message id).
A subagent's responses belong to the turn whose tool call dispatched the agent
(`store/agent_turns.py`), not to the turn its own records name.

Usage is classified at the response and nowhere else: `store/buckets.py` gives each one of
four buckets from its tool calls, with no text read and no threshold, and every level
above is a sum of responses (the `response` table, and `app_usage_by_bucket_day` for the
app). The tokens that rest on a guess from a tool's name and the tokens in records that
could not be read are carried beside the sums, never folded into a bucket.

## What an ingest reads again, and what it keeps

`prudence rebuild` reads the whole archive and measures everything. `prudence ingest`
must leave the same tables behind and does less work to get there, in four places only.

- **The parse** (`store/parse_plan.py`, `store/parse_state.py`, `store/derived.py`). A
  session is read again when anything its rows are a function of has moved: the bytes
  of one of its files (a
  new file, a file that grew, a file archived again), the set of its files, its
  repository or the rule that found it, its capture level, a worktree root one of its
  edits sits under, or the parser or any version beneath it (the last is a full parse).
  So is every session linked to one of those: an orphan and the forks that carry it, two
  sessions that wrote the same turn, call or response id, and the sessions that lost a
  record or reply to it. A session read again that meets a record a kept session claims
  from later in the reading order sends that session to be read too, and the parse runs
  again with it, until nothing new is sent. The rows of every other session are kept as
  they are; the ones read again are replaced in one transaction, with their bookkeeping.
  (A rebuild still builds every table under a new name and swaps it in, also in one
  transaction; an ingest replaces rows rather than tables, because a swap would copy
  every kept row on every run.)
  Every session is resolved to its repository before any is read, so an edit's path is
  relative to the same roots whichever session taught them. The files that are read are
  read by `store/parse_pool.py` in `--workers` processes; the fold stays in one process,
  in one order.
- **The commit harvest** (`store/commits.py`). A commit is immutable, so one already
  stored is not read again; `git rev-list --all` names the commits to read and the stored
  ones to drop because no ref reaches them any more. A repository is read whole when its
  capture level, the line-hash key or the fact version changed.
- **The outcome marks** (`store/outcomes.py`). A 7, 30 or 90-day mark already measured is
  kept in `outcome_mark` and not measured again, unless the commit's attribution rows or
  the fact version changed. HEAD presence, HEAD blame and rework are measured for every
  counted commit on every run, and nothing is cached under HEAD.
- **The archive** (`store/archive.py`). An unchanged file is a `stat`; a grown one is
  checked at three windows against the archive's own bytes, and only its new bytes are
  read.

Everything else is rebuilt on every run, as before. The guard is `tests/test_incremental.py`:
after sequences of ingests over a changing machine (a new session, a grown transcript,
a late subagent log, a fork before and after its parent, a re-stamped resume in both
orders, a changed capture level, a worktree learned later, a mark kept then invalidated,
a commit added and one rewritten away) every table the pipeline writes is compared, row
by row and in any order, with what a
rebuild of the same archive writes. A table a later step adds is compared from the day it
appears unless it is named, with the reason, in that module's `NOT_DERIVED`. The one
difference a rebuild may show on real data is a kept mark whose history before the mark
was rewritten since it was measured: the ingest keeps the first reading, as intended, and
a rebuild reads the rewritten history.

## The run log, warnings and self-checks

Every command that changes something (`ingest`, `rebuild`, `review`, `init` when it
changes the config, `hooks install` and `uninstall`, `export`, `import`) leaves a record in
`<data dir>/logs/runs.jsonl` (`store/runlog.py`), written through `cli/recording.py`. The
record is two appended lines with one `run_id`: the first when the command starts, with
`ended_at` null, the second when it leaves, however it leaves (a return, a `ctx.exit`, an
exception, Ctrl-C), with the exit code and, on failure, the error's type, message and
traceback as `file:line in function`. A process killed outright writes no second line, so
its record keeps `ended_at` null and `prudence logs` shows it as interrupted (or running,
while its process is). The first line is appended rather than rewritten in place because
several processes write the file, and a rewrite would lose a line another one appended
in between. The file is renamed to `runs.1.jsonl` at 8 MB and two files are kept.

A record carries the command and its arguments, the engine, parser, bucket rule and app
contract versions, the machine (operating system, architecture, Python, cores), the
store's size, each step's seconds and counts, the warnings and the self-checks. Warnings
(`store/run_warnings.py`) are collected by the steps through one `Warnings` object on
the pipeline's result and printed by nothing: `unknown_record_type` (per type, the union
of the records' keys two levels deep, first seen, count), `unreadable_line` (session,
file id, offset), `unattached_subagent` (agent, session, reason), `heuristic_bucket`
(tool, calls, tokens resting on the guess) and `check_failed`. They describe what this
run read: an ingest that parsed nothing new warns about nothing, and a rebuild reports
the whole archive. The self-checks (`store/checks.py`) run after the last step of every
ingest and rebuild: token totals agree across `usage`, `response` and
`app_usage_by_bucket_day`; every response has a turn; every subagent token is attached;
every `app_*` view answers with its contract's columns; the stored contract version is
the code's; a session has no repository only when the parse found none; and every derived
row carries this code's versions. A failure is a bug in the pipeline, not in the data; it
is a `check_failed` warning and the last line of the summary, and `--strict` makes it
exit code 3.

**The log holds no text.** Nothing read from a transcript is written to it: counts, ids,
names, keys, offsets and timings only. A name a transcript supplies (a record type, a
key, a tool) is written only if it looks like an identifier and as `<other>` otherwise, a
file is named by a hash of its archive path, every string has the home directory written
as `~`, and the one free-form string, an error's message, is Prudence's or a library's
own, cut at 500 characters. `tests/test_runlog.py` plants one sentinel string in every
place a transcript can carry text and asserts it never reaches the log, and that every
string in a record is a timestamp, a name or one of the few fields free by design.

`prudence logs` prints one line per run, newest first (`--last`, `--json`,
`--interrupted`). `prudence diagnose` writes `<data dir>/diagnose/<time>/` with the last
20 records, `status --json`, the config and the machine with the home directory stripped,
the tail of the app's `logs/app.log` when there is one, and a README; it refuses to copy
the store, the spool or anything under the agent's own directory.

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
   A response's bucket is the same kind of word, on the `response` row with its
   `bucket_rule_version`: tokens are summed by it, and the bucket itself is never scored.
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
14. **The app reads only `app_*` views.** A screen that needs a number the engine
   does not compute gets a new view in `store/app_views.py`, never a join in the app;
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
17. **The store imports no agent module.** An agent's file layout and log format live in
   `sources/<agent>/` and nowhere else. `store/derived.py` builds its tables from the
   events `sources/base.py` defines, asks `sources/__init__.py` for an adapter and never
   names one; `tests/test_sources.py` asserts that no module under `store/` reaches into
   an agent's package. Three consequences, because they are where the boundary would
   otherwise leak back:
   - **The capture level is the store's, not an adapter's.** An adapter reports what the
     format says, text included (a prompt's length, an edit's lines, a command); the code
     that writes the row decides what becomes a count, a keyed hash or nothing. One rule
     for every source, and no adapter is trusted with a promise made to the user.
   - **Pairing and ownership are the store's.** A tool call and its result can be records
     or files apart, and which session a record belongs to is a question about all the
     files together, so both are settled in `store/derived.py` over the event stream.
   - **A file is not a session.** A record belongs to the session it declares, which for a
     record copied into a fork is the parent's. When two sessions each declare the same
     record as their own, the session whose transcript begins earlier owns it and a tie
     breaks on the archive path, which is what reading the files in that order does. Both
     halves of that key are read out of the files, so the order they were ingested in
     cannot change the answer. An adapter for an agent with no fork concept never reports
     a foreign session id, and neither rule does anything.
   The one exception today: `store/edits.py` still reads Claude Code's own field names
   (`structuredPatch`, `toolUseResult`, `gitOperation`). It is called from the adapter and
   not from the store, and it stays put because it also holds the `EDIT_FACT_VERSION` and
   `COMMAND_FACT_VERSION` the store writes into rows; splitting the format readers out of
   it belongs with the commit that adds the second adapter.

   **Known compromise: a re-stamped copy is recognised by timing, not by the record.**
   Some resumed transcripts carry the copied lines with the *new* session's id written
   over them, so the record itself says nothing about where it came from and the repeated
   record id is the only trace. The second ownership rule then decides by which
   transcript begins earlier.
   - *What it assumes:* the session that originally wrote a record has a transcript that
     begins before any transcript that copied it. True whenever a resume happens after
     the sitting it resumes, which is what a resume is.
   - *What the user sees when the assumption is false:* the copy owns the shared records.
     The original session then looks shorter than it was and the copy looks longer, the
     same way round as the fork bug did before parser version 5. Token totals stay
     correct either way, because a record is still counted once.
   - *Also out of reach:* a copied record that carries no identifier of its own cannot be
     recognised as a copy at all, since the id derived for it names the file it sits in.
   - *Removal condition:* lineage for re-stamped copies, inferred rather than declared
     (comparing the two transcripts' shared records and their times, and writing the
     result to `forked_from` like a declared fork). That is a feature of its own, not a
     parser fix, and it needs the founder's decision on what to do when the inference is
     ambiguous.

## Adding a source

A second agent is a new package under `sources/`, and nothing else. What it has to do:

1. **One package, two modules.** `sources/<agent>/discovery.py` answers where the files
   are; `sources/<agent>/events.py` answers what a line of one means. Nothing else in the
   tree may read the agent's field names.
2. **Implement `sources.base.Source`.** `kind` (the word that goes into
   `session.source`), `session_files()`, `companion_files(session)`, `head(lines)` and
   `events(lines, path, file_session_id, agent_id)`. Register the instance in
   `sources/__init__.py`.
3. **Yield one `Event` per record of the agent's log**, in file order, with the payloads
   that record holds. Fill only what a derived table already uses; a field no table reads
   does not belong in `Event`. The two fields that are easy to get wrong:
   - `session_id` is the session the record **declares**, not the file it came from. None
     when the record names no session. Report what the format says and nothing else; the
     ownership rule is the store's.
   - `record_id` must be stable and unique across the whole source. When the format has
     no identifier of its own (Codex's rollout items do not), derive one from the file and
     the line and set `stable_id=False`, so the store knows the id names that copy of the
     record rather than the record.
4. **Be lenient, always.** A line that will not parse is skipped; a field of the wrong
   shape is absent; a record type the adapter does not know is reported with
   `known_type=False` and becomes a row in `unknown_record_type` rather than an error.
   Every agent's log format is internal to it: Claude Code's changed 24 times in five
   months on the founder's machine, and one local check found 32 distinct Codex
   `cli_version` strings in 234 files.
5. **Teach the archive which agent wrote a file.** With one adapter, the store can assume
   the registry's only entry. A second one needs an `agent` column on `archive_file`,
   behind an `ARCHIVE_SCHEMA_VERSION` bump and a step in `store/db.migrate`, because
   `store/derived.py` reads files out of the archive long after the scan that found them.
   This is the only change outside `sources/` that a second adapter should need.
6. **Bring a fixture per observed format version**, synthetic, under
   `tests/fixtures/<agent>/`, and a test module beside `tests/test_sources.py`. A number
   a fixture asserts is a number somebody counted by hand.
7. **Say what the source cannot answer.** A fact an agent does not record is absent, not
   zero: a session with no token counts has no `usage` rows, and a surface prints a dash.
   Do not fabricate a figure from an external table inside an adapter.

## Adding things

- A new agent: see "Adding a source" above.
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

### Current capture limits

Codex log parsing does not evaluate `functions.exec` JavaScript. Structured completed
inner operations supply command and patch evidence; wrappers without that evidence
leave a response coverage gap. Shell reads do not reliably identify file paths, so
Codex's unread-edit and repeated-file-read facts remain unknown. A fork marker alone
does not establish which records were replayed; without matching record or response
identity, the parser reports incomplete coverage rather than deleting presumed history.

Source-location membership survives ordinary export through `session_source`, without
requiring archived transcript bytes. New observations update that membership without
removing prior imported locations; forgetting the session removes it. Hook policy is
independent from history parsing. Its normalized observation carries capture version,
agent kind, location ID and tool name, so future event-selection changes need not
change transcript adapters.
