"""Reading a question with rules, so that retrieval is narrowed before a model is involved.

Journey decision D2 puts the rules first on purpose: "why do my refactors on beatos keep
getting reverted" contains a project, a time frame and a topic, and every one of them
that a regular expression can find is one the retrieval does not have to guess and the
model does not have to be trusted with. What is left over after the rules have taken
their parts is the search text.

Every rule is a row in `RULES`: a name, a pattern, and a function turning the match into
a field of the parsed question. Adding "in Q3" or "before the release" is a row, not a
branch, and each row's examples are the test cases. The rules are deliberately shallow:
they recognise the handful of shapes people actually type and leave everything else
alone rather than trying to be a date parser.

Time is resolved against a `now` the caller passes, so a test is not a clock race.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

STAMP = "%Y-%m-%dT%H:%M:%S"

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
UNITS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}
WORD_COUNTS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "couple": 2}

# Words that carry no signal for a path or command search. Not a linguistic stop list:
# the words a developer's questions are made of, plus the ones the rules already ate.
NOISE = {
    "a",
    "about",
    "after",
    "all",
    "am",
    "an",
    "and",
    "any",
    "anything",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "being",
    "but",
    "by",
    "can",
    "did",
    "do",
    "does",
    "doing",
    "for",
    "from",
    "get",
    "getting",
    "go",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "keep",
    "keeps",
    "last",
    "lot",
    "many",
    "me",
    "much",
    "my",
    "of",
    "on",
    "or",
    "over",
    "should",
    "since",
    "so",
    "some",
    "spend",
    "spent",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "up",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "work",
    "working",
    "would",
    "you",
    "your",
}


@dataclass
class Question:
    """One question, with whatever the rules could take out of it."""

    text: str
    since: str | None = None
    until: str | None = None
    range_label: str | None = None
    project: str | None = None
    path: str | None = None
    extension: str | None = None
    quoted: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)

    @property
    def search(self) -> str:
        """The single term `views.search_sessions` is given: a path, else the best word.

        The search matches file paths and command classes, not prose, so handing it a
        sentence returns nothing. One term, chosen by the rules, is honest about that.
        """
        if self.path:
            return self.path
        if self.extension:
            return self.extension
        return self.terms[0] if self.terms else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "since": self.since,
            "until": self.until,
            "range": self.range_label,
            "project": self.project,
            "path": self.path,
            "extension": self.extension,
            "quoted": self.quoted,
            "terms": self.terms,
            "rules": self.matched,
        }


@dataclass(frozen=True)
class Rule:
    """One thing a question may contain, and how to take it out."""

    name: str
    pattern: re.Pattern[str]
    apply: Callable[[Question, re.Match[str], datetime], None]


def _day(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT00:00:00")


def _last_week(question: Question, match: re.Match[str], now: datetime) -> None:
    """The seven-day-block before the one we are in, Monday to Monday."""
    monday = now - timedelta(days=now.weekday())
    question.since = _day(monday - timedelta(days=7))
    question.until = _day(monday)
    question.range_label = "last week"


def _this_week(question: Question, match: re.Match[str], now: datetime) -> None:
    monday = now - timedelta(days=now.weekday())
    question.since = _day(monday)
    question.until = now.strftime(STAMP)
    question.range_label = "this week"


def _yesterday(question: Question, match: re.Match[str], now: datetime) -> None:
    question.since = _day(now - timedelta(days=1))
    question.until = _day(now)
    question.range_label = "yesterday"


def _today(question: Question, match: re.Match[str], now: datetime) -> None:
    question.since = _day(now)
    question.until = now.strftime(STAMP)
    question.range_label = "today"


def _counted(question: Question, match: re.Match[str], now: datetime) -> None:
    """ "last 30 days", "the last two weeks", "past 3 months"."""
    raw = (match.group("count") or "1").lower()
    count = WORD_COUNTS.get(raw, 0) or _int(raw) or 1
    days = count * UNITS[match.group("unit").lower()]
    question.since = (now - timedelta(days=days)).strftime(STAMP)
    question.until = now.strftime(STAMP)
    question.range_label = f"the last {days} days"


def _in_month(question: Question, match: re.Match[str], now: datetime) -> None:
    """ "in August" means the most recent August that has already begun."""
    month = MONTHS[match.group("month").lower()]
    year = now.year if month <= now.month else now.year - 1
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=UTC)
    question.since = start.strftime(STAMP)
    question.until = min(end, now).strftime(STAMP)
    question.range_label = start.strftime("%B %Y")


def _since_weekday(question: Question, match: re.Match[str], now: datetime) -> None:
    """ "since Monday" means the most recent one, today counting as itself."""
    target = WEEKDAYS[match.group("weekday").lower()]
    back = (now.weekday() - target) % 7
    question.since = _day(now - timedelta(days=back))
    question.until = now.strftime(STAMP)
    question.range_label = f"since {match.group('weekday').lower()}"


def _since_date(question: Question, match: re.Match[str], now: datetime) -> None:
    question.since = f"{match.group('date')}T00:00:00"
    question.until = now.strftime(STAMP)
    question.range_label = f"since {match.group('date')}"


def _path(question: Question, match: re.Match[str], now: datetime) -> None:
    question.path = match.group(0)


def _extension(question: Question, match: re.Match[str], now: datetime) -> None:
    question.extension = match.group(0)


def _quoted(question: Question, match: re.Match[str], now: datetime) -> None:
    question.quoted.append(match.group("quoted"))


# Order matters: the first rule to match a span takes it, and a later rule never sees
# what an earlier one consumed. Time before paths, because "last 30 days" holds a number
# that a path rule would otherwise be tempted by.
RULES: tuple[Rule, ...] = (
    Rule("quoted", re.compile(r"[\"'](?P<quoted>[^\"']{3,120})[\"']"), _quoted),
    Rule("last week", re.compile(r"\blast week\b", re.I), _last_week),
    Rule("this week", re.compile(r"\bthis week\b", re.I), _this_week),
    Rule("yesterday", re.compile(r"\byesterday\b", re.I), _yesterday),
    Rule("today", re.compile(r"\btoday\b", re.I), _today),
    Rule(
        "counted range",
        re.compile(
            r"\b(?:last|past)\s+(?P<count>\d+|a|one|two|three|four|six|couple(?:\s+of)?)\s+"
            r"(?P<unit>days?|weeks?|months?)\b",
            re.I,
        ),
        _counted,
    ),
    Rule(
        "since date",
        re.compile(r"\bsince\s+(?P<date>\d{4}-\d{2}-\d{2})\b", re.I),
        _since_date,
    ),
    Rule(
        "since weekday",
        re.compile(rf"\bsince\s+(?P<weekday>{'|'.join(WEEKDAYS)})\b", re.I),
        _since_weekday,
    ),
    Rule("in month", re.compile(rf"\bin\s+(?P<month>{'|'.join(MONTHS)})\b", re.I), _in_month),
    Rule("path", re.compile(r"\b[\w.-]+/[\w./-]+\.\w{1,6}\b"), _path),
    Rule(
        "extension",
        re.compile(r"(?<![\w.])\.(?:py|ts|tsx|js|swift|go|rs|rb|md|sql|toml)\b"),
        _extension,
    ),
)


def parse(
    text: str, now: datetime | None = None, projects: dict[str, str] | None = None
) -> Question:
    """One question, with its time range, project, path and quoted text taken out.

    `projects` maps repository key to display name; a question naming one of those names
    (or keys) is scoped to it, which is how principle 2's "a finding about one project
    never appears in another" reaches `ask`.
    """
    moment = now or datetime.now(UTC)
    question = Question(text=text.strip())
    remaining = text

    for rule in RULES:
        match = rule.pattern.search(remaining)
        if match is None:
            continue
        rule.apply(question, match, moment)
        question.matched.append(rule.name)
        remaining = remaining[: match.start()] + " " + remaining[match.end() :]

    question.project = _project(remaining, projects or {})
    if question.project is not None:
        question.matched.append("project")
        name = (projects or {}).get(question.project, question.project)
        remaining = re.sub(re.escape(name), " ", remaining, flags=re.I)

    question.terms = _terms(remaining)
    return question


def _project(text: str, projects: dict[str, str]) -> str | None:
    """The longest project name the question contains, or None.

    Longest so that a repository called `app` does not win over `app-server` in a
    question that names the second.
    """
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for key, name in projects.items():
        for token in (name, key):
            if not token or len(token) < 3:
                continue
            if re.search(rf"\b{re.escape(token.lower())}\b", lowered) and (
                best is None or len(token) > best[0]
            ):
                best = (len(token), key)
    return best[1] if best else None


def _terms(text: str) -> list[str]:
    """What is left after the rules, longest first: the words worth searching on."""
    words = [word.lower().strip(".,?!:;") for word in re.findall(r"[\w.\-/]{3,}", text)]
    kept = [word for word in words if word and word not in NOISE and not word.isdigit()]
    seen: set[str] = set()
    unique = [word for word in kept if not (word in seen or seen.add(word))]
    return sorted(unique, key=len, reverse=True)


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0
