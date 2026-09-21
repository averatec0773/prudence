# Prudence

Prudence is a local-first, open-source growth coach for developers who build with AI coding agents. It records how you actually worked with your agent and links that record to what became of the code in git, so you get the feedback a colleague or a code review would normally give you.

## Status

0.3.0: it captures your sessions, links them to your commits, follows what became of
the code and where the tokens went, and writes a review of it: every number computed
from your own record, with an optional model-written paragraph on top that may only
quote those numbers. A native macOS menu-bar app (`apps/mac`) shows the same record
with charts. `prudence ask` answers a question from the record.

## Principles we build on

- The record is yours and stays on your machine.
- Capture is opt-in per repository, with a metadata-only mode.
- Secrets never leave the store.
- Findings, not scores.
- Sources on everything.

## Platforms

macOS and Linux. Windows is untested.

## Install

Prudence needs Python 3.12 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/).
If you don't have Python yet, uv can install it for you.

```
uv tool install --python 3.12 prudence-dev
```

Optional extras:

- `prudence-dev[mcp]` adds the `prudence mcp` server used by the Claude Code plugin.
- `prudence-dev[model]` adds the Anthropic SDK, for `prudence review --explain` and the
  prose half of `prudence ask`.

```
uv tool install --python 3.12 "prudence-dev[mcp,model]"
```

The menu bar is a native macOS app now rather than a Python extra; see
[apps/mac/README.md](apps/mac/README.md).

## Quick start

```
prudence init --scan
prudence init --enable <repo> --level full
prudence ingest
prudence sessions --last 30d
prudence outcomes --project <repo>
prudence usage --last 30d
prudence observations --project <repo>
prudence show --session <id>
prudence facts --last 30d
prudence review --project <repo>
prudence review --explain
prudence ask "what did I spend tokens on last week"
prudence hooks install
prudence export
```

`init --scan` lists the repositories found in your agent history without changing
anything. `init --enable` turns recording on for one repository at a time, at
`full` capture or `metadata-only` (use `--level metadata-only` for a repository whose
content you would rather not store). `ingest` reads what the agent recorded since the
last run. `sessions` lists what happened; `outcomes` follows the commits each session
produced forward, to what survived; `usage` follows the tokens and active time back, to
what they were for; `observations` joins the two, inside one project, when your own
data supports it. `show` prints one session's full record; `facts` prints the behaviour
counts every session was scored on. `hooks install` adds the git-state hooks Prudence
uses to catch what happens around each turn; it edits Claude Code's settings file, shows
the diff first, and `prudence hooks uninstall` reverses it. `review` stores a review of
the period since the last one (or `--last 14d`, `--month 2026-09`) and prints it; it
refuses to write an empty one until enough new sessions and matured commits exist
(`--force` overrides). `--explain` adds a model-written paragraph, only when a model is
configured (`prudence config model`); the paragraph is checked against the review's own
numbers and refused if it invents one or grades you. `ask` retrieves the sessions the
question is about and, unless you pass `--no-model`, asks the model to answer from that
evidence alone. Before every model call Prudence prints what it is about to send.

The first completed `ingest` ends with a "first look": three to five facts about the
history it just read, each with the command that shows more.

## What it can tell you today

- `prudence outcomes --project <repo>`: "62% of the lines from your last 90 days are
  still in the tree at head, with 78% coverage (41 fact-attributed commits, 12
  inferred)."
- `prudence usage --last 30d`: "development 55%, research 25%, conversation 15%,
  debugging 5% of this week's tokens."
- An observation at the end of `outcomes`: "In one project, your sessions that ran a
  formatter still had more lines at head than the ones that did not (88% vs 74%, 14
  sessions each side)."

## Claude Code plugin

Prudence also ships a Claude Code plugin that brings your recorded history into a
session: `/prudence:sessions`, `/prudence:outcomes`, `/prudence:usage`,
`/prudence:recall`, `/prudence:review` and `/prudence:ask` skills, and an MCP server an
agent can query directly (`ask` there returns the evidence only, because the agent
calling it is already a model). See
[plugin/README.md](plugin/README.md). To try it from this repository without
installing it:

```
claude --plugin-dir ./plugin
```

## What it records and what it never records

Raw session data (transcripts, tool results, file-history snapshots) is archived
unmodified, byte for byte, in a local store with owner-only file permissions
(mode 0600). Derived tables built from that archive hold counts, classes, and keyed
line hashes, never message text: no prompt or response text is written to any derived
table, at any capture level.

`metadata-only` withholds more: file paths and line hashes are not stored, so that
level records shape (how much changed, when, in which class of command) without a
fingerprint of the content itself.

Nothing Prudence records is uploaded anywhere. If you plan to enable it on a work
repository, check your employer's policy first. Observations, the correlations between
your own behaviour and your own outcomes, are computed the same way: they never leave
this machine, and they never compare you with anyone else, only with yourself.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
