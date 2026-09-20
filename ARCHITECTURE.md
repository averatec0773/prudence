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
    spool.py      what the hooks saw, folded from the archived spool into hook_event
    erase.py      taking a session or a repository back out, archive included
    transfer.py   the whole store as one .tar.gz, and back into an empty one
    sampling.py   the precision sample: the hard quarter, drawn, and every method's score
    labels.py     the founder's own verdict on a sampled commit; user-authored, never rebuilt
    pipeline.py   the order the seven steps run in, so ingest and rebuild agree
    views.py      the read queries `cli/show.py` and the MCP server share; no formatting
  facts/          (next) one function per derived fact, each versioned
  cli/            one file per command; thin, calls the engine
  menubar/        the macOS menu-bar prototype: summary.py (pure, no rumps) and
                   app.py (the rumps shell, imported only from cli/menubar.py)
  mcp/            the MCP server: server.py (FastMCP, stdio), the only place `mcp` is
                   imported; started by `cli/mcp.py`
plugin/           the Claude Code plugin: `.claude-plugin/plugin.json`, `.mcp.json`
                  wiring the `prudence mcp` command, `hooks/` (a copy of the hook set,
                  see plugin/README.md), `skills/sessions`, `skills/recall`
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
   window's commits carry an author email hash other than the majority's; the flag lives
   on the `repository` row and every surface prints the reason in place of the number.
   Suppression is preferred to a caveat, because a survival percentage that silently
   includes a colleague's work is wrong rather than imprecise.

## Adding things

- A new agent: one module in `sources/` that finds the agent's files and yields records.
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
- A new archive column: `store/db.py`, with `ARCHIVE_SCHEMA_VERSION` bumped and a step in
  `migrate`. Archive tables are the only ones that are migrated rather than rebuilt.
- A new setting the user chooses: `config.py`, and show it in `prudence status`.
- A new command: one file in `cli/`, registered in `cli/__init__.py`.
- A new surface: reads the store; puts nothing in `src/prudence/` except a thin adapter.
  `menubar/summary.py` is the pattern: one pure function per number shown, so a surface's
  own numbers are tested without its GUI toolkit.
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
