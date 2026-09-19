"""`prudence sample`: draw the hard quarter, label it, and score every method against it.

Release waits on this. Spike round two measured attribution against commits the agent
committed itself, where the answer is nearly a tautology; the commits that matter, made
by hand hours or days after the code was written, have no ground truth at all. This
draws exactly that population, shows the founder the same evidence every method saw,
and stores the verdict so `--report` can score line matching against the two time
windows honestly.

Nothing shown here is a message or a line of code: times, counts, file counts, session
ids, the repository name, the commit hash and its committer time. That is what the
labelling has to work from, same as the model would.
"""

from __future__ import annotations

import sqlite3

import click

from prudence.paths import database_file
from prudence.store import db, labels, sampling

PROMPT = "Which session made this commit? (number, n for none, s to skip, q to quit) "


@click.command()
@click.option(
    "--commits", "n", default=50, show_default=True, type=int, help="How many commits to draw."
)
@click.option(
    "--seed", "seed", type=int, default=None, help="Random seed, for a reproducible draw."
)
@click.option(
    "--label",
    "label_args",
    nargs=2,
    metavar="HASH SESSION_ID|none",
    help="Label one commit without the interactive loop.",
)
@click.option(
    "--report",
    "want_report",
    is_flag=True,
    help="Print precision, recall and abstention by method.",
)
def sample(n: int, seed: int | None, label_args: tuple[str, str] | None, want_report: bool) -> None:
    """Draw the hard quarter, label it, and score line matching against the time windows."""
    if not database_file().exists():
        raise click.ClickException("Nothing ingested yet. Run `prudence ingest`.")
    connection = db.connect()
    try:
        if want_report:
            click.echo(render_report(connection))
        elif label_args:
            _label_one(connection, *label_args)
        else:
            _draw_and_label(connection, n, seed)
    except sqlite3.OperationalError as error:
        raise click.ClickException(
            f"The derived tables are not built yet ({error}). Run `prudence ingest`."
        ) from error
    finally:
        connection.close()


def _label_one(connection: sqlite3.Connection, commit_hash: str, token: str) -> None:
    session_id = None if token.strip().lower() == "none" else token
    labels.write(connection, commit_hash, session_id)
    click.echo(f"Labelled {commit_hash[:10]} as {session_id[:8] if session_id else 'none'}.")


def _draw_and_label(connection: sqlite3.Connection, n: int, seed: int | None) -> None:
    items = sampling.draw_sample(connection, n=n, seed=seed)
    if not items:
        click.echo(
            "No hard-quarter commit found: nothing unattributed by in_session with two or "
            "more sessions active within 24 hours of it."
        )
        return
    click.echo(f"Drew {len(items)} commits from the hard quarter (seed={seed}).")
    click.echo("")
    for item in items:
        for line in render_item(item):
            click.echo(line)
        click.echo("")

    already = labels.labelled_hashes(connection)
    for item in items:
        if item.commit_hash in already:
            continue
        for line in render_item(item):
            click.echo(line)
        try:
            answer = input(PROMPT).strip().lower()
        except EOFError:
            click.echo("")
            break
        if answer in ("q", "quit"):
            break
        if answer in ("n", "none"):
            labels.write(connection, item.commit_hash, None)
            click.echo("Labelled: none of these.")
        elif answer.isdigit() and 1 <= int(answer) <= len(item.candidates):
            chosen = item.candidates[int(answer) - 1]
            labels.write(connection, item.commit_hash, chosen.session_id)
            click.echo(f"Labelled: {chosen.session_id[:8]}.")
        elif answer in ("", "s", "skip"):
            continue
        else:
            click.echo("Not understood; skipped.")
        click.echo("")


def render_item(item: sampling.SampleItem) -> list[str]:
    """Everything a label needs, and nothing else: no code, no transcript text."""
    lines = [
        f"commit {item.commit_hash[:10]}  repo {item.repo_name}  committer {item.committer_at}"
        f"  +{item.added_lines} lines, {item.files_changed} files",
    ]
    for index, candidate in enumerate(item.candidates, start=1):
        lines.append(f"  {index}) {_candidate(candidate)}")
    lines.append(
        f"  time window picks: 4h -> {_short(item.pick_4h)}, 24h -> {_short(item.pick_24h)}"
    )
    return lines


def render_report(connection: sqlite3.Connection) -> str:
    scores = sampling.score(connection)
    total = len(labels.all_labels(connection))
    lines = [
        f"{'method':<12} {'labelled':>8} {'answered':>8} {'precision':>10} "
        f"{'recall':>8} {'abstention':>10}"
    ]
    for name in sampling.METHOD_NAMES:
        stat = scores[name]
        lines.append(
            f"{name:<12} {stat.labelled:>8} {stat.answered:>8} {_percent(stat.precision):>10} "
            f"{_percent(stat.recall):>8} {_percent(stat.abstention_rate):>10}"
        )
    lines.append("")
    lines.append(f"{total} commits labelled so far.")
    return "\n".join(lines)


def _candidate(candidate: sampling.Candidate) -> str:
    detail = (
        f"{candidate.session_id[:8]}  {candidate.first_at or '?'} to {candidate.last_at or '?'}"
    )
    detail += f"  edits={candidate.edits}"
    if candidate.line_match_rank is not None:
        detail += f"  line_match rank {candidate.line_match_rank} ({candidate.lines_matched} lines)"
    return detail


def _short(session_id: str | None) -> str:
    return session_id[:8] if session_id else "none"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"
