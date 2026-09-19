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
  scan.py         read-only inventory of agent history on this machine
  sources/        where we see the developer's work: one module per agent
    claude_code.py
  store/          Prudence's own record: repository identity now; the raw archive and
    identity.py   the derived tables next
  facts/          (next) one function per derived fact, each versioned
  cli/            one file per command; thin, calls the engine
plugin/           (next) the Claude Code plugin: skills, hooks, .mcp.json
tests/            pytest; fixtures are anonymised, one directory per observed format version
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

## Adding things

- A new agent: one module in `sources/` that finds the agent's files and yields records.
- A new derived fact: one function in `facts/` with a version and its test cases as data.
- A new command: one file in `cli/`, registered in `cli/__init__.py`.
- A new surface: reads the store; puts nothing in `src/prudence/` except a thin adapter.

## Privacy rules for contributors

- Never commit real transcripts. Fixtures are synthetic or anonymised, and the anonymiser
  lives in the repository.
- Tests never read `~/.claude`; they build their own files under a temporary directory and
  point Prudence at it with `CLAUDE_CONFIG_DIR`.
