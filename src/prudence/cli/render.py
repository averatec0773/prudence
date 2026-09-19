"""Shared formatting for the commands. Numbers the founder reads, nothing else."""

from __future__ import annotations

from datetime import datetime


def date(value: datetime | str | None) -> str:
    if value is None:
        return "?"
    if isinstance(value, str):
        return value[:10] or "?"
    return value.strftime("%Y-%m-%d")


def size(num: int) -> str:
    amount = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} GB"
