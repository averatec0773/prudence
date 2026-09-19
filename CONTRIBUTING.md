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

The repository is English only: code, comments, commit messages, issues, and pull requests.

## Style

No em dashes in prose.
