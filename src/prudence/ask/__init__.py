"""`prudence ask`: one question, answered from the record (journey decision D2).

This is a package rather than a module in `reviews/` because it is a different shape of
work with a different failure mode. A review is a range turned into a page: the range is
given and every figure is computed. A question is a sentence turned into a query: it has
to be read (`parse`), turned into rows (`retrieve`), and only then written up (`answer`),
and the interesting failures are "the rules read the question wrong" and "retrieval found
the wrong sessions", neither of which a review can have. Three small modules that can be
tested separately beat one file where a parsing bug and a prompt bug look alike.

What each module holds:

- `parse` - the rules that take a time range, a project, a path and quoted text out of a
  question. Rules are rows in a table; their examples are the tests.
- `retrieve` - the sessions, usage, outcomes and observations that answer it, with the
  limits as constants and the transcript excerpts behind `--with-content`.
- `answer` - one model call over that evidence, with the number guard, plus `render`.
- `schema` - the `question` table: what was asked, what it stood on, what was said.

`answer.ask(...)` is the single entry point, so the CLI and the MCP tool that batch 3
adds cannot drift apart.
"""

from __future__ import annotations

# The shape of a stored answer. Bumped when the `question` row's columns change.
ASK_VERSION = 1
