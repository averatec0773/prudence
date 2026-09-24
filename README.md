<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-white.svg">
    <img src="assets/brand/logo.svg" alt="Prudence" width="120">
  </picture>
</p>

<h1 align="center">Prudence</h1>

<p align="center">
  Prudence turns every session with your AI coding agents into a loop of growth:<br>
  understand the code they wrote, see where your time and tokens went and what became of the code they bought,<br>
  learn which ways of working pay off, hand that back to your agents for the next round,<br>
  and keep the record as your own.
</p>

<p align="center">
  <a href="https://pypi.org/project/prudence-core/"><img alt="PyPI" src="https://img.shields.io/pypi/v/prudence-core?label=prudence-core"></a>
  <a href="https://github.com/averatec0773/prudence/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/averatec0773/prudence/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/averatec0773/prudence/actions/workflows/desktop-ci.yml"><img alt="Desktop app" src="https://github.com/averatec0773/prudence/actions/workflows/desktop-ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS 14+" src="https://img.shields.io/badge/macOS-14%2B-000">
</p>

<p align="center">
  English | <a href="README.zh-CN.md">简体中文</a>
</p>

---

## The problem

Developers who build with AI agents ship faster than ever, and many of them are not getting better.

- The code works, but the person who shipped it often cannot explain it.
- Nothing tells them which ways of working lead to code that lasts and which lead to rework and bugs. Solo developers have no colleague, no code review, and often no users, so reality's feedback never reaches them.
- Better methods exist, but they do not know which ones apply to what they are doing this week.
- Their improvement comes mostly from the model getting better, not from themselves, and they can feel it.

## The loop

Every session with your agents feeds the next one.

```
   understand ──► see ──► learn ──► hand back
        ▲                               │
        └──── your record, next round ◄─┘
```

- **Understand the code they wrote.** `prudence ask` answers a question about your own work from your own sessions and cites them; a review says what each period's sessions did and what they were asked for. Reading the agent's work back to you is the roadmap's second promise, and this is where it starts.
- **See where the time and tokens went, and what became of the code.** Tokens by what each response of the model did; every line followed through git: alive at 7, 30 and 90 days, reworked by your own later commits, with the coverage behind every number.
- **Learn which ways of working pay off.** Your sessions with a behaviour against your sessions without it, inside one project, reported only when your own data clears a sample floor and a gap floor.
- **Hand it back to your agents for the next round.** A review each period says what changed and what to try, and the next review says whether it helped; the Claude Code plugin and the MCP server put the record in front of the agent in its next session.
- **Keep the record as your own.** Every session archived on your machine, byte for byte, with `show`, `forget` and `export` for all of it; no vendor holds it.

## What you get

- **Ask.** `prudence ask "why do my refactors on this project keep getting reverted"` answers from retrieved evidence and cites session ids.
- **Reviews.** `prudence review` turns a period into a stored review whose every figure is computed; an optional model-written paragraph on top may only quote those figures and is refused if it invents one or grades you.
- **Outcomes, not impressions.** For each session: lines still alive at 7, 30 and 90 days, lines reworked by your own later commits, with the coverage and the attribution method behind every number.
- **Usage by what was done.** Every response of the model lands in one of four buckets, from its tool calls alone: it changed a file, ran something, only read, or just talked. Tokens are summed by project and by week, so a session that produced no code shows what it spent its tokens on instead of looking like a gap. No text is read and no threshold is involved, so the same history always gives the same split.
- **Observations.** Your sessions with a behaviour against your sessions without it, inside one project: "your 16 sessions that compacted their context reworked 28% of their lines; the 33 that did not, 6%." Reported only when your own data clears a sample floor and a gap floor.
- **Three surfaces.** The CLI, a Claude Code plugin with skills and an MCP server, and a desktop menu-bar app with charts: one codebase, macOS today, Windows to follow.
- **A record you own.** Every session archived locally, byte for byte, with `show`, `forget` and `export` for all of it.

## Where it is going

Three promises shape the roadmap:

1. **Reality's feedback, delivered.** What survived, what was rewritten, what broke, where the time and tokens went: the colleague and the code review you do not have.
2. **Growth that is yours.** How your way of working with AI evolves over months, what you shipped but did not understand, and help closing that gap only when you need it. Suggestions are tracked: the next review says whether one helped, and advice that does not work is retired.
3. **A window to the outside.** Knowing what you are wrestling with right now, it goes out to see how the field solves it today and explains what applies to your project, with sources.

The tools will keep changing; the record is built so that a new agent is a new source, a new way of reading it is a new lens, and a new way of reaching you is a new surface. Three years in, a developer should have an honest, evidence-backed record of every project, how their habits changed, and which advice worked for them, carried across every generation of AI tools they used. They would no more give it up than their git history.

## Principles

1. **The record is yours.** Local, visible, exportable, dependent on no AI vendor.
2. **Your own results are the evidence.** Claims about you come from your own sessions and commits, in the project they came from; a model's impression is not evidence.
3. **Facts with their confidence, never scores.** Counts you can check, each with its coverage and method; no grades, streaks, badges or leaderboards.
4. **Suggestions, never orders.** Prudence never forces a mode, a workflow or a curriculum.

## Install

Prudence needs Python 3.12 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```
uv tool install --python 3.12 "prudence-core[mcp,model]"
```

Extras: `mcp` adds the MCP server the Claude Code plugin uses; `model` adds the Anthropic SDK for `review --explain` and the prose half of `ask`. Without `model`, everything else works and no model is ever called.

The desktop app is a separate download. The DMG ships with 0.1.0 (unsigned until the Developer ID certificate exists; right-click, Open, on first launch); until that release is out, build it yourself from [apps/desktop](apps/desktop/README.md).

## Claude Code and Codex

Prudence reads both agents' local history. The desktop app's Settings > Sources shows
Claude Code and Codex, plus **+ Add source** for an additional named directory with an
explicit agent type. A source is a history location, not an account or a model.

Existing Claude collection remains enabled. Codex starts paused so upgrading does not
silently add a new agent's history to enabled repositories:

```sh
prudence sources
prudence sources set codex --enabled
prudence init --scan
prudence init --enable <repo> --level full
prudence ingest
prudence sessions --source codex --last 30d
prudence sources add --kind claude_code --name Work --home /path/to/claude-home
```

Both the source and repository must be enabled for new collection. Pausing a source
keeps its recorded history. Copied sessions retain their collection locations without
counting their responses twice. The repository screen's session list filters by source
and model; those filters do not change saved reviews or collection settings.

Token totals are total input plus output. Claude's cache reads and writes are added to
its ordinary input; Codex's reported input already includes cached tokens. Reasoning is
a subset of output. Missing breakdowns remain unknown. One completed patch can have
several file changes while remaining one tool call.

Codex can query the same read-only MCP server as Claude Code:

```sh
codex mcp add prudence -- prudence mcp
```

The MCP tools accept recorded evidence from either agent; `search_sessions` also accepts
`source`, `source_id`, and `model` filters. Capturing history does not require MCP or hooks.
For optional git-state observations, run `prudence hooks install --source codex` or
`prudence hooks install --source claude`. Hook installation is a separate, explicit
settings change with a backup and an uninstall command. Codex may require its own hook
trust review. Hook events and field normalization live in `hooks/policy.py`, so capture
policy can change without changing archived transcripts or the analysis rules.

## Quick start

```
prudence init --scan                      # list the repositories in your agent history
prudence init --enable <repo> --level full
prudence ingest                           # read what the agent recorded; first run prints a "first look"
prudence sessions --last 30d
prudence outcomes --project <repo>        # what became of each session's lines
prudence usage --last 30d                 # tokens by change, run, read and talk
prudence observations --project <repo>   # your behaviours against your own outcomes
prudence review --project <repo>          # a stored review of the period since the last one
prudence review --explain                 # plus a model-written paragraph, checked against the numbers
prudence ask "what did I spend tokens on last week"
prudence hooks install                    # optional: turn-level git state through Claude Code hooks
prudence export
```

`init --enable` turns recording on for one repository at a time, at `full` capture or `metadata-only` (shape without content, for a repository whose code you would rather not store). `hooks install` edits Claude Code's settings file, shows the diff first, and `prudence hooks uninstall` reverses it byte for byte. Before every model call Prudence prints what it is about to send: sections, number of figures, no transcript content, size, and the estimated cost.

## Claude Code plugin

```
claude --plugin-dir ./plugin
```

Skills `/prudence:sessions`, `/prudence:outcomes`, `/prudence:usage`, `/prudence:recall`, `/prudence:review`, `/prudence:ask`, and an MCP server an agent can query directly (there, `ask` returns the evidence only, because the agent calling it is already a model). See [plugin/README.md](plugin/README.md).

## The desktop app

A menu-bar icon whose panel shows today, this week's tokens by purpose, the latest observation and the last review; a window with Overview (tokens by purpose per week, survival and rework per project with coverage, where the hours went), Review (the stored review as cards and charts), Observations and Settings. It can find the `prudence` executable and run an ingest or a review for you, and it follows the store, so a run's new numbers arrive on their own.

One codebase for macOS and Windows: a Rust shell around the design system's own HTML, reading the same SQLite store through a versioned set of `app_*` views. **The app never computes a number of its own**: a figure is one the engine produced, a sum of a view's columns, or the ratio of two columns of one row, and nothing else. English and Simplified Chinese, composed per language rather than translated. See [apps/desktop/README.md](apps/desktop/README.md).

## What it records and what it never records

Raw session data is archived unmodified in a local store with owner-only permissions. **That happens at every capture level**: the level decides what is derived from your sessions, not what is kept of them, so a `metadata-only` repository's transcripts are archived in full too.

Derived tables never hold message text, at any capture level. At `full` they do hold the commands that were run, the paths of the files that were edited and the working directory; `metadata-only` derives none of those and no line hashes either, so those tables hold shape and counts only.

Nothing is uploaded by the desktop app, and observations compare you only with yourself. Three CLI commands can reach the model named in your configuration, and each has to be asked for: `prudence review --explain` and `prudence explain` send a review's own figures and no session text, and `prudence ask` sends the evidence it retrieved, plus short excerpts of your transcripts when you pass `--with-content`.

If you plan to enable Prudence on a work repository, check your employer's policy first.

## How it works

```
AI coding-agent transcripts and hooks ──► one local SQLite store (raw archive + derived tables)
        ──► attribution (which session made which commit, with confidence)
        ──► outcomes (survival, rework), facts, observations, reviews
        ──► CLI · Claude Code plugin and MCP · desktop app (app_* views)
```

[ARCHITECTURE.md](ARCHITECTURE.md) has the layout and the rules that keep it easy to change.

## Status

The current version is the latest entry in [RELEASES.md](RELEASES.md) (the engine's earlier releases as `prudence-dev` are summarised at its end). Supported agent source: Claude Code (the source layer is one module per agent). The desktop app is built for macOS today; Windows is untested.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) (DCO sign-off, Conventional Commits, English only, AI-assisted contributions disclosed).

## License

Apache-2.0. See [LICENSE](LICENSE). The Prudence name and mark are not covered by the code licence; see [assets/brand/README.md](assets/brand/README.md).
