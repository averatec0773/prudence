# Contributing

## Setup

```
uv sync --group dev
```

## Checks

Run these before opening a pull request:

```
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

## Sign-off (DCO)

Every commit must be signed off under the Developer Certificate of Origin: https://developercertificate.org/

```
git commit -s
```

## Commit messages

Please use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, and so on).

## AI-assisted contributions

Contributions written with AI assistance are welcome. Disclose it in the pull request, and make sure a human who understands the change is the one submitting it and can answer questions about it.

## Language

The repository is English only: code, comments, commit messages, issues, and pull requests. The one exception is `README.zh-CN.md`, a Simplified Chinese translation of the README kept in step with it; when you change `README.md`, change the translation too or say in the pull request that it needs updating.

## Style

No em dashes in prose.

## Releasing

Release notes live in `RELEASES.md`, not `CHANGELOG.md`: that name is reserved for a
private, harness-internal file and must never appear in this public repository (the
`leak-guard` job in CI fails the build if it ever does).

To cut a release:

1. `python3 scripts/version.py --set X.Y.Z`. The engine, the desktop app and the plugin
   share one number, written in eight files; the script is the only thing that edits
   them, and CI fails if any two disagree. The READMEs do not carry the number.
2. Add an entry to `RELEASES.md` for the new version: what changed, in a short
   paragraph, plus any known limits.
3. Commit those changes.
4. Tag the commit and push the tag:
   ```
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. Pushing the tag runs `.github/workflows/release.yml`, which builds the package,
   publishes it to PyPI with trusted publishing (no token needed, see `RELEASES.md`
   for the one-time setup), and creates the GitHub release.

## Versioning

Prudence follows [SemVer](https://semver.org/), with one version number for the engine
(`prudence-core` on PyPI), the desktop app and the Claude Code plugin, so a release is
one tag and `scripts/version.py --check` is what "one number" means. While the version stays `0.x`, a
minor bump may change the store schema in a way that only a rebuild (`prudence
rebuild`), not a migration, can carry forward: the store's own stability promise (see
`ARCHITECTURE.md`) is that raw bytes survive, not that every derived table's layout
does.
