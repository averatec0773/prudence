"""`store/buckets.py`: the rule's own table of responses, and the answer each must get."""

from __future__ import annotations

import pytest

from prudence.store import buckets


@pytest.mark.parametrize("case", buckets.CASES, ids=[case.name for case in buckets.CASES])
def test_each_case_gets_its_bucket(case: buckets.Case) -> None:
    kinds = [buckets.call_kind(name, command) for name, command in case.calls]
    assert buckets.bucket_of(kinds) == (case.bucket, case.heuristic)


def test_the_buckets_are_in_precedence_order() -> None:
    assert buckets.BUCKETS == ("change", "run", "read", "talk")
    for higher, lower in zip(buckets.BUCKETS, buckets.BUCKETS[1:], strict=False):
        assert buckets.bucket_of([(higher, False), (lower, False)])[0] == higher


def test_an_empty_or_missing_command_is_not_read_only() -> None:
    """A shell call whose command could not be read did something nobody can see."""
    assert buckets.call_kind("Bash", None) == ("run", False)
    assert buckets.call_kind("Bash", "   ") == ("run", False)
