"""Which language a model writes in: a table of codes, never a branch on one.

Only the prose a model writes is translated. Everything the engine computes stays in
English (M4 scope item 3): the CLI, the review page, the observation sentences and the
column names are the open-source product's own language, and a surface that wants a
localised sentence composes it from the row's numbers rather than asking for a translated
one. So a language here is exactly two things: a code a user can set, and the one line
that tells a model which language to answer in, written in that language.

Adding a language is one entry in `LANGUAGES` plus, if that language needs it, a word
list in `tone.WORDS_BY_LANGUAGE`; nothing else in the codebase learns a language name.
`LANGUAGE_VERSION` is bumped when an instruction changes, because a stored segment
carries the code it was written in and the instruction behind that code has to be
identifiable later.

`system` is the default and resolves from the environment **at the moment of the call**,
not when the config was written: a user who switches their machine's locale gets the new
language on the next review without editing a file.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# Bumped whenever an entry's `instruction` changes. The prompt versions in
# `reviews/explain.py` and `ask/answer.py` are bumped with it, since the line is part of
# their system prompt.
LANGUAGE_VERSION = 1

SYSTEM = "system"
DEFAULT = "en"


@dataclass(frozen=True)
class Language:
    """One language a model may be asked to write in.

    `instruction` is written in the language it names, on purpose: an instruction a model
    has to translate before obeying is one more step than one it can simply follow.
    """

    code: str
    name: str
    instruction: str


LANGUAGES: dict[str, Language] = {
    "en": Language(code="en", name="English", instruction="Write in English."),
    "zh-Hans": Language(
        code="zh-Hans",
        name="Simplified Chinese",
        instruction="用简体中文写。",
    ),
}

# What `--language` and `[model] language` accept. `system` is not a language; it is the
# instruction to look one up when the call is made.
CODES: tuple[str, ...] = (SYSTEM, *LANGUAGES)

# A POSIX locale, lower-cased, to a code. A row matches the whole locale or the locale
# up to its region (`zh_cn` matches `zh_cn`, `zh` matches `zh` and `zh_yue`), and the
# first matching row wins, so the traditional-Chinese rows have to come before the `zh`
# one. They resolve to English on purpose: there is no zh-Hant entry in `LANGUAGES`, and
# writing simplified Chinese at a reader who set their machine to traditional would be a
# worse answer than the language the engine's own sentences are in. Add the entry and
# these rows change with it. A locale no row matches is English for the same reason.
LOCALES: tuple[tuple[str, str], ...] = (
    ("zh_hant", DEFAULT),
    ("zh_tw", DEFAULT),
    ("zh_hk", DEFAULT),
    ("zh_mo", DEFAULT),
    ("zh_hans", "zh-Hans"),
    ("zh_cn", "zh-Hans"),
    ("zh_sg", "zh-Hans"),
    ("zh", "zh-Hans"),
    ("en", DEFAULT),
)

# Read in this order, which is the order POSIX gives them.
ENVIRONMENT: tuple[str, ...] = ("LC_ALL", "LC_MESSAGES", "LANG")


def resolve(code: str | None, environ: Mapping[str, str] | None = None) -> str:
    """The language this call writes in: a code from `LANGUAGES`, always.

    An empty value and `system` both mean "ask the environment". A code nobody knows is
    English rather than an error (architecture rule 3): an unreadable setting must not
    stop a review being written, and the language it is written in is visible in the
    "Sending" line either way.
    """
    if not code or code == SYSTEM:
        return from_environment(environ)
    return code if code in LANGUAGES else DEFAULT


def from_environment(environ: Mapping[str, str] | None = None) -> str:
    """The language the machine is set to, read now rather than remembered."""
    source = os.environ if environ is None else environ
    for name in ENVIRONMENT:
        value = (source.get(name) or "").strip()
        if not value or value.upper() in {"C", "POSIX"}:
            continue
        locale = value.split(".")[0].split("@")[0].lower()
        for prefix, code in LOCALES:
            if locale == prefix or locale.startswith(prefix + "_"):
                return code
    return DEFAULT


def of(code: str | None) -> Language:
    """The entry for a resolved code. Unknown codes fall back the way `resolve` does."""
    return LANGUAGES.get(code or DEFAULT, LANGUAGES[DEFAULT])


def instruction(code: str | None) -> str:
    """The one line a system prompt gains, in the language it names."""
    return of(code).instruction


def name_of(code: str | None) -> str:
    """The English name, for a line a user reads (`prudence config model`)."""
    return of(code).name


__all__ = [
    "CODES",
    "DEFAULT",
    "ENVIRONMENT",
    "LANGUAGES",
    "LANGUAGE_VERSION",
    "LOCALES",
    "SYSTEM",
    "Language",
    "from_environment",
    "instruction",
    "name_of",
    "of",
    "resolve",
]
