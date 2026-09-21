"""The review: the store turned into a page, and the rows that page leaves behind.

A review is not a report generator. It is a row: one range, one project scope, the
sections as JSON, and every figure that appears in it listed beside them. The Markdown
the terminal prints is a rendering of that row, and so is the app's review screen later
(P18, journey decision E). Nothing here computes a number of its own: every figure comes
from `store/views`, which is the same code `prudence usage`, `prudence outcomes` and
`prudence observations` print, so a number in a review can be re-derived by running one
of those commands.

The package sits beside `store/` rather than inside it because a review is not derived
data. `rebuild` drops and rebuilds every derived table from the archive; a review is the
user's own history of what they were told, closer to `store/labels.py` than to
`attribution`, and it is never rebuilt and never dropped.

What each module holds:

- `schema` - the `review` and `suggestion` tables, the `meta` marker helpers, and the
  reads over them. Created `IF NOT EXISTS`, never dropped.
- `ranges` - which range a review covers and which commits its outcome section is about.
- `readiness` - whether enough has happened since the last review to write another one.
- `build` - the sections, from the existing views and nothing else.
- `render` - one stored review as Markdown.
- `suggestions` - the rows a review leaves open, and what became of the last ones.
- `first_look` - the ranked candidate facts printed after the first `ingest`.
"""

from __future__ import annotations

# The shape of a stored review's `sections` JSON. Bumped when the section list, the
# number list or their keys change, so a surface can refuse a payload it cannot read.
# 2 (M4 batch 3): a number may carry `with_n`, `without_n` and `previous_value` beside
# the text it is printed as. Every key that existed at version 1 is still written and
# still means the same thing, so a version 1 row renders unchanged and the three new keys
# are optional wherever they are read.
REVIEW_VERSION = 2
