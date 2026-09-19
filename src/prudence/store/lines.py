"""One normalisation, one keyed hash: the unit on which edits and commits meet.

A line is the smallest thing both sides of the attribution join can agree on, so the
rule that turns a line of code into a key has to live in exactly one place. The same
function normalises what a session wrote and what a commit added, or the two sides
never meet and every measurement silently reads zero.

Nothing here stores code. A line becomes an HMAC-SHA256 digest keyed with 32 random
bytes generated once per install, so the store holds no recoverable text, a dictionary
of likely lines cannot be tested against it, and two machines' stores cannot be joined
line by line. The key lives beside the config, not in the database.

The normalisation drops what matching cannot use: blank, tiny and punctuation-only
lines, plus a short list of tokens every file repeats. It stays small on purpose:
round two of the attribution spike measured that normalising harder recovers 0.25% of
the drift, because what a formatter does is move line boundaries, which no per-line
rule can survive.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

from prudence.paths import line_hash_key_file

KEY_BYTES = 32
KEY_MODE = 0o600
MIN_CHARS = 4
DIGEST_CHARS = 16

_WHITESPACE = re.compile(r"\s+")

# Lines that carry no identity: every file has them, so a match on one means nothing.
TRIVIAL_LINES = frozenset(
    {
        "{",
        "}",
        ");",
        "});",
        "};",
        "];",
        "*/",
        "/*",
        "end",
        "end;",
        "else",
        "else {",
        "} else {",
        "return",
        "return;",
        "pass",
        "break",
        "break;",
        "continue",
        "continue;",
        "done",
        "esac",
        "then",
        "fi",
        "try:",
        "try {",
        "finally",
        "endif",
    }
)


def normalise(line: str) -> str | None:
    """The comparable form of a line, or None when the line carries no identity."""
    text = _WHITESPACE.sub(" ", line.strip())
    if len(text) < MIN_CHARS:
        return None
    if not any(character.isalnum() for character in text):
        return None
    if text in TRIVIAL_LINES:
        return None
    return text


def hash_line(key: bytes, line: str) -> str | None:
    """The keyed digest of one line, or None when normalisation dropped it."""
    text = normalise(line)
    if text is None:
        return None
    digest = hmac.new(key, text.encode("utf-8", "surrogatepass"), hashlib.sha256)
    return digest.hexdigest()[:DIGEST_CHARS]


def hash_lines(key: bytes, lines: list[str]) -> list[str]:
    """The distinct digests of a block of lines, in the order they first appeared."""
    seen: dict[str, None] = {}
    for line in lines:
        digest = hash_line(key, line)
        if digest is not None:
            seen.setdefault(digest, None)
    return list(seen)


def load_key(path: Path | None = None) -> bytes:
    """Read the per-install key, creating it at mode 0600 the first time."""
    target = path or line_hash_key_file()
    if target.exists():
        data = target.read_bytes()
        if len(data) == KEY_BYTES:
            return data
    target.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(KEY_BYTES)
    handle = os.open(target, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, KEY_MODE)
    try:
        os.write(handle, key)
    finally:
        os.close(handle)
    os.chmod(target, KEY_MODE)
    return key
