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
    pipeline.py   the order the five steps run in, so ingest and rebuild agree
  facts/          (next) one function per derived fact, each versioned
  cli/            one file per command; thin, calls the engine
plugin/           (next) the Claude Code plugin: skills, hooks, .mcp.json
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
   among the candidates, and its coverage. A surface may present a guess, never as a
   fact.

## Adding things

- A new agent: one module in `sources/` that finds the agent's files and yields records.
- A new derived table or column: `store/derived.py`, then bump `PARSER_VERSION` and
  document the change in `docs/reference/store-schema.md`. Never write a migration.
- A new table harvested from git rather than from the archive: its own module under
  `store/`, a `FACT_VERSION`, a step in `store/pipeline.py`, and a section in the
  schema document. Read-only git commands only: `log`, `show`, `rev-parse`,
  `rev-list`, `notes`, `cat-file`, `blame`, `worktree list`, `patch-id`.
- A new derived fact computed from those tables: one function in `facts/` with a version
  and its test cases as data. `derived.py` builds the tables; `facts/` reads them.
- A new archive column: `store/db.py`, with `ARCHIVE_SCHEMA_VERSION` bumped and a step in
  `migrate`. Archive tables are the only ones that are migrated rather than rebuilt.
- A new setting the user chooses: `config.py`, and show it in `prudence status`.
- A new command: one file in `cli/`, registered in `cli/__init__.py`.
- A new surface: reads the store; puts nothing in `src/prudence/` except a thin adapter.

## Privacy rules for contributors

- Never commit real transcripts. Fixtures are synthetic or anonymised, and the anonymiser
  lives in the repository.
- Tests never read `~/.claude`; they build their own files under a temporary directory and
  point Prudence at it with `CLAUDE_CONFIG_DIR`.
