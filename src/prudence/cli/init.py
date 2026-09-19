from __future__ import annotations

from datetime import datetime

import click

from prudence.scan import NO_REPOSITORY, ScanResult, scan


@click.command()
@click.option("--scan", "scan_only", is_flag=True, help="List the history found; change nothing.")
def init(scan_only: bool) -> None:
    """Choose which repositories Prudence records. Nothing is enabled until you say so."""
    if not scan_only:
        raise click.UsageError("Only `prudence init --scan` exists yet; enabling comes next.")
    result = scan()
    click.echo(render(result))


def render(result: ScanResult) -> str:
    lines = [
        f"Claude Code history in {result.projects_dir}: "
        f"{result.total_sessions} sessions, {_size(result.total_bytes)}.",
        "",
        f"{'repository':<32} {'sessions':>8} {'first':>10} {'last':>10} {'size':>9}",
    ]
    for group in result.groups:
        name = group.name if group.key != NO_REPOSITORY else NO_REPOSITORY
        if group.key == NO_REPOSITORY:
            name = f"{NO_REPOSITORY} ({len(group.directories)} directories)"
        lines.append(
            f"{name[:32]:<32} {group.sessions:>8} {_date(group.first_at):>10} "
            f"{_date(group.last_at):>10} {_size(group.size_bytes):>9}"
        )
    lines.append("")
    oldest = _date(result.oldest)
    lines.append(
        f"Claude Code deletes transcripts after {result.cleanup_period_days} days "
        f"(cleanupPeriodDays). History on this machine goes back to {oldest}. "
        "Prudence keeps its own copy from the day a repository is enabled."
    )
    lines.append("Nothing is enabled yet. Nothing was written.")
    return "\n".join(lines)


def _date(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value else "?"


def _size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
