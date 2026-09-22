# Prudence (Claude Code plugin)

Brings your own Prudence-recorded session history into a Claude Code session: a
`/prudence:sessions` skill that shows this week's sessions without leaving the
terminal, a `/prudence:outcomes` skill for what became of the code, a `/prudence:usage`
skill for where the tokens and time went, a `/prudence:recall` skill that asks the
agent to search your history for prior work, a `/prudence:review` skill that reads your
latest stored review, a `/prudence:ask` skill that answers a question about your own
work from the computed evidence, and the `prudence` MCP server (`search_sessions`,
`show_session`, `session_outcomes`, `usage_summary`, `observations`, `status`,
`latest_review`, `ask`) that any of the skills, or any other prompt, can call directly.

`ask` returns the evidence and stops there: the caller is already a model, so the tool
does not make a second model call, and it writes nothing to the store. Run
`prudence ask "<question>"` in a terminal for a written answer over the same rows, with
the engine's number and tone guards applied to it.

## Requirements

The Prudence CLI must already be installed and on `PATH` before this plugin is any
use: `uv tool install prudence-core`. This plugin does not install or bundle the CLI;
`.mcp.json` runs the `prudence mcp` command by name, so if `prudence` is not found on
`PATH`, the MCP server will not start. Also run `prudence init` and `prudence ingest`
at least once, so there is something to show.

## Install locally

From this repository:

```
claude --plugin-dir ./plugin
```

That starts Claude Code with this plugin loaded for the session, without installing it
into your regular plugin set, which is the right way to try it before installing it for
real.

## What it ships

- `.claude-plugin/plugin.json`: the plugin manifest.
- `.mcp.json`: wires the `prudence` MCP server to the `prudence mcp` command.
- `hooks/hooks.json` and `hooks/prudence-hook.sh`: the same six hook entries
  `prudence hooks install` writes into `~/.claude/settings.json` directly, but scoped to
  this plugin, so a plugin user needs no separate settings edit. **The two copies of
  `prudence-hook.sh`** (here, and in the `prudence-core` package at
  `src/prudence/hooks/prudence-hook.sh`) **must stay byte-identical.** A test
  (`tests/test_plugin_files.py`) checks this on every change; if you edit one, copy it
  to the other.
- `skills/sessions/SKILL.md`: `/prudence:sessions`.
- `skills/outcomes/SKILL.md`: `/prudence:outcomes`.
- `skills/usage/SKILL.md`: `/prudence:usage`.
- `skills/recall/SKILL.md`: `/prudence:recall`.
- `skills/review/SKILL.md`: `/prudence:review`.
- `skills/ask/SKILL.md`: `/prudence:ask`.

## Privacy

No message text ever leaves the local store, at any capture level: neither the MCP
tools nor the hooks read or transmit prompt or response text. The MCP server runs as a
local process over stdio; it is not a network service and nothing it reads leaves this
machine except through Claude Code itself, the same as any other local MCP server.
