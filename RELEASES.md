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
   - PyPI project name: `prudence-coach`
   - Owner: `averatec0773`
   - Repository name: `prudence`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. Save it. The first push of tag `v0.1.0` that runs `.github/workflows/release.yml`
   will then be allowed to publish without any stored password or API token: GitHub
   Actions gets a short-lived OpenID Connect token, scoped to this repository and this
   workflow, and PyPI exchanges it for a publish permission.

Nothing else needs a secret. There is no `PYPI_API_TOKEN` to create or rotate.

## 0.1.0 - 2026-09-19

M1: the first demo skeleton, released publicly as a recorder. Prudence records your
Claude Code sessions (opt-in, per repository, at `full` or `metadata-only` capture),
archives the raw session data unmodified, and links it to the commits it produced,
reachable from the terminal, from inside a Claude Code session (a skill and an MCP
tool), and from a macOS menu-bar prototype. No model calls, no outcomes, no review yet.

What's included:

- `prudence init --scan` / `prudence init --enable <repo> --level full|metadata-only`
- `prudence ingest`
- `prudence sessions --last 30d`
- `prudence show --session <id>`
- `prudence hooks install` / `prudence hooks uninstall`
- `prudence forget --session <id>` / `prudence forget --project <name>`
- `prudence export` / `prudence import`
- `prudence menubar` (macOS, optional `[menubar]` extra)
- `prudence mcp` and the Claude Code plugin in `plugin/` (optional `[mcp]` extra)

Known limits:

- Attribution precision (line_match 97% when it answers, window methods 98%) was
  measured on one machine and one developer's history. It has not been checked on a
  second machine or a different working style.
- Windows is untested.
- No outcomes or reviews yet; this release is a recorder only.
