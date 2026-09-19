"""The one comparison both sides of attribution depend on: normalise, then hash."""

from __future__ import annotations

from pathlib import Path

from prudence.store import lines


def test_normalisation_keeps_content_and_drops_noise() -> None:
    assert lines.normalise("  def parse(self):  ") == "def parse(self):"
    assert lines.normalise("a\t=\t  b + 1") == "a = b + 1"
    assert lines.normalise("") is None
    assert lines.normalise("   ") is None
    assert lines.normalise("})") is None, "too short to identify anything"
    assert lines.normalise("############") is None, "no alphanumeric character"
    assert lines.normalise("return") is None, "every file has one"
    assert lines.normalise("} else {") is None
    assert lines.normalise("return value") is not None


def test_the_same_line_hashes_the_same_and_whitespace_does_not_matter(tmp_path: Path) -> None:
    key = lines.load_key(tmp_path / "one.key")
    assert lines.hash_line(key, "value = compute(x)") == lines.hash_line(
        key, "  value  = compute(x)"
    )
    assert lines.hash_line(key, "value = compute(x)") != lines.hash_line(key, "value = compute(y)")
    assert lines.hash_line(key, "}") is None


def test_another_install_key_gives_another_hash(tmp_path: Path) -> None:
    first = lines.load_key(tmp_path / "one.key")
    second = lines.load_key(tmp_path / "two.key")
    assert first != second
    assert lines.hash_line(first, "value = compute(x)") != lines.hash_line(
        second, "value = compute(x)"
    )


def test_the_key_is_created_once_and_kept_private(tmp_path: Path) -> None:
    path = tmp_path / "line-hash.key"
    key = lines.load_key(path)
    assert len(key) == lines.KEY_BYTES
    assert path.stat().st_mode & 0o777 == 0o600
    assert lines.load_key(path) == key, "a second read must not roll a new key"


def test_hashing_a_block_returns_each_line_once(tmp_path: Path) -> None:
    key = lines.load_key(tmp_path / "one.key")
    digests = lines.hash_lines(key, ["alpha = 1", "", "}", "alpha = 1", "beta = 2"])
    assert len(digests) == 2
