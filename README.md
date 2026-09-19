# Prudence

Prudence is a local-first, open-source growth coach for developers who build with AI coding agents. It records how you actually worked with your agent and links that record to what became of the code in git, so you get the feedback a colleague or a code review would normally give you.

## Status

Pre-alpha. Nothing usable yet. M1 (the first demo skeleton) is in progress.

## Principles we build on

- The record is yours and stays on your machine.
- Capture is opt-in per repository, with a metadata-only mode.
- Secrets never leave the store.
- Findings, not scores.
- Sources on everything.

## Platforms

macOS and Linux. Windows is untested.

## Install

Not yet published.

```
uv tool install prudence-coach
```

## Privacy

Raw session data is archived unmodified on your disk, in a store with owner-only file permissions. It is never uploaded anywhere. If you plan to enable Prudence on a work repository, check your employer's policy first.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
