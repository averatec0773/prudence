# Prudence

Prudence is a local-first, open-source growth coach for developers who build with AI coding agents. It records how you actually worked with your agent and links that record to what became of the code in git, so you get the feedback a colleague or a code review would normally give you.

## Status

0.1.0, a recorder: it captures your sessions and links them to your commits.
Outcomes and reviews come next.

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
uv tool install --python 3.12 prudence-coach
```

Optional extras:

- `prudence-coach[mcp]` adds the `prudence mcp` server used by the Claude Code plugin.
- `prudence-coach[menubar]` adds the macOS menu-bar prototype (`prudence menubar`).

```
uv tool install --python 3.12 "prudence-coach[mcp,menubar]"
```

## Quick start

```
prudence init --scan
prudence init --enable <repo> --level full
prudence ingest
prudence sessions --last 30d
prudence show --session <id>
prudence hooks install
prudence forget --session <id>
prudence export
```

`init --scan` lists the repositories found in your agent history without changing
anything. `init --enable` turns recording on for one repository at a time, at
`full` capture or `metadata-only` (use `--level metadata-only` for a repository whose
content you would rather not store). `ingest` reads what the agent recorded since the
last run. `hooks install` adds the git-state hooks Prudence uses to catch what happens
around each turn; it edits Claude Code's settings file, shows the diff first, and
`prudence hooks uninstall` reverses it.

## Claude Code plugin

Prudence also ships a Claude Code plugin that brings your recorded history into a
session: a `/prudence:sessions` skill, a `/prudence:recall` skill, and an MCP server
an agent can query directly. See [plugin/README.md](plugin/README.md). To try it from
this repository without installing it:

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
repository, check your employer's policy first.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
