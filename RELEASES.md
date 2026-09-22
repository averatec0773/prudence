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
   - PyPI project name: `prudence-core`
   - Owner: `averatec0773`
   - Repository name: `prudence`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. Save it. The first push of tag `v0.1.0` that runs `.github/workflows/release.yml`
   will then be allowed to publish without any stored password or API token: GitHub
   Actions gets a short-lived OpenID Connect token, scoped to this repository and this
   workflow, and PyPI exchanges it for a publish permission.

Nothing else needs a secret. There is no `PYPI_API_TOKEN` to create or rotate.

## 0.1.0 - unreleased

The first release as `prudence-core`, the engine, the desktop app and the Claude Code
plugin under one version number (the engine's earlier releases are summarised at the end
of this file). The desktop
app is one codebase for two systems: the Swift macOS app of the earlier releases is
replaced by `apps/desktop/`, a Rust shell around the design system's own HTML that
builds for macOS today and is written so that Windows needs no second frontend. It reads
the same store through the same versioned `app_*` views and computes no number of its own.
The engine gains source adapters and a correct account of forked sessions (below).

What's included:

- **Four screens.** Overview (three totals, tokens by purpose per week, what became of
  each week's work with its coverage, where the hours went), Review (one stored review as
  the engine wrote it), Observations (one card per behaviour, paired bars, every share
  over its denominator) and Settings (what is recorded and at what level, what is never
  recorded, where the store is, the engine, an about block).
- **One week axis.** Every weekly chart's x axis is the range's complete week list, so a
  week sits at the same place in each chart, and a week nothing was recorded in is an
  empty slot rather than a zero.
- **The engine, from the app.** It finds the `prudence` executable the way a login shell
  would (uv's directories, then Homebrew, then one shell probe), verifies it before
  trusting it, and can run an ingest or a review. A run that the engine declines says why,
  in the engine's own words. There is a picker for an executable in an unusual place.
- **The store is followed.** An ingest that lands while the app is open refreshes the
  pages, whether the app started it or a terminal did.
- **English and Simplified Chinese**, composed per language rather than translated, with
  the engine's own English kept beside a recomposed sentence as the thing to check it
  against.
- **Real Liquid Glass** on macOS 26, on the control and navigation layer only; the content
  layer is opaque, so no figure is read against a moving backdrop.

Not in this release: signing, notarisation and an updater. The app is built from the
terminal and is unsigned.

Engine changes in the same release:

- **A forked session is its own session, and it starts when it was forked.** Claude Code's
  fork (and a resume into a new file) writes the parent's whole history into the new
  transcript, record for record, with the parent's own `sessionId` still on every copied
  line. Prudence read each file as one session named after the file, so a fork took its
  parent's start time and its parent's turns, and which of the two owned a shared record
  depended on which file happened to be read first. A record now belongs to the session it
  declares, whatever file it was read from; copied history is read from the parent's own
  file, or kept under the parent when the agent has already deleted that file. The
  `session` row gains `forked_from` and `fork_point`, the last copied record's own id, so
  the point of divergence can be looked up in the parent's records.

  `derived.PARSER_VERSION` is 5, so **`prudence rebuild` repairs existing history**. On the
  founder's store that found 10 forks and moved 129 turns and 1,194 token-usage rows back
  to the sessions that earned them; store-wide token totals are unchanged, because nothing
  was ever lost, only credited to the wrong session. The `app_*` read contract is
  untouched at version 3: the same columns, with correct values.

- **A source adapter, so a second agent is a new package rather than a new set of
  branches.** `sources/base.py` defines what every source hands the store: one event per
  record of the agent's own log. `sources/claude_code/` is now a package and the only place
  that knows Claude Code's format, and `store/derived.py` names no agent at all, which a
  test asserts. Nothing about the boundary is speculative: the capture level, the pairing
  of a tool call with its result, and the ownership rule above all stay in the store, so
  they mean the same thing for every agent. Codex is not part of this change;
  `ARCHITECTURE.md` has an "adding a source" section for whoever writes it.

- Known, and separate: some older resumed transcripts carry the copied lines re-stamped
  with the **new** session's id, so nothing in the file says which session a shared record
  belongs to. Those records go to the session whose transcript begins earlier, and a tie
  breaks on the archive path. Both halves of that key are read out of the files, so the
  order they were ingested in cannot change the answer, but the answer is timing rather
  than something the record says. 13 sessions on the founder's store are of this shape.
  What the rule assumes and when it would be wrong is registered in `ARCHITECTURE.md`
  under rule 17.

## Before 0.1.0

The engine was first published on PyPI as `prudence-dev`, versions 0.1.0 to 0.4.0, between
2026-09-19 and 2026-09-21, alongside a native Swift menu-bar app for macOS (0.1.0 and
0.2.0, unsigned). Those four releases built, in order: the recorder (`init`, `ingest`,
`sessions`, `show`, `forget`, `export`, the Claude Code plugin and MCP server); outcomes
(line survival and rework with coverage, attribution confidence, usage by purpose, behaviour
facts, observations); reviews and `ask` with the model guards, the `app_*` read contract and
the Swift app; and the app's design system with Liquid Glass, charts and Simplified Chinese.
`prudence-core` 0.1.0 continues that code without a break: the git history is the same,
the store format is the same (a store written by 0.4.0 needs only `prudence rebuild`), and
the `prudence-dev` releases stay on PyPI as they were.
