"""One token total rule for every derived consumer."""

from __future__ import annotations

from collections.abc import Iterable


def sum_nullable(values: Iterable[int | None]) -> int | None:
    found = [value for value in values if value is not None]
    return sum(found) if found else None


def total_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    input_total = (
        f"COALESCE({prefix}total_input_tokens,"
        f" COALESCE({prefix}input_tokens, 0)"
        f" + COALESCE({prefix}cache_read_tokens, 0)"
        f" + COALESCE({prefix}cache_creation_tokens, 0))"
    )
    return f"({input_total} + COALESCE({prefix}output_tokens, 0))"
