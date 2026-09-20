"""`prudence classify --model`: the optional model label. Designed, not implemented.

The rules in `facts/purpose.py` are tier 1 of proposal v2 section 4.11: counts, no text.
They cannot recover what the founder could say in one sentence about his own sessions
(one repository is job applications, another moved from a demo to a talk), because the
only place that lives is the conversation. Tier 3, a model reading redacted text, can,
and the M2 plan makes it a separate task that only starts if the rules leave too much
`unknown`. This command exists so that the design is written down where it would be
implemented, and so that invoking it says no rather than nothing.

Where the implementation would go, in order:

1. **Redaction first.** The store holds no message text at all, so this command would
   read the archive directly through `store/archive.py`, redact each prompt (paths,
   secrets, identifiers) and send only the redacted text. A repository at
   `metadata-only` capture is skipped entirely; that level promises shape only.
2. **Explicit and off by default.** Nothing here runs during `ingest` or `rebuild`. The
   user names the sessions, sees the estimated cost, and agrees to the call.
3. **Cached per session, versioned by prompt.** The answer would be written to
   `session_label` beside the rule label, under a different `name` (`purpose_model`) and
   with the prompt version in `rule_version`, so the two never overwrite each other and
   a surface can show both. A session already labelled at the current prompt version is
   not sent again.
4. **Still a label.** Principle 2: a model never produces the number a finding rests on.
   The rule label stays the one the tables group by; the model label is shown beside it,
   named as a model's reading, and a disagreement between them is information about the
   rules rather than a correction to apply silently.
"""

from __future__ import annotations

import click


@click.command()
@click.option("--model", "with_model", is_flag=True, help="Classify with a model instead of rules.")
@click.option("--session", "token", metavar="ID", help="One session, by id or prefix.")
def classify(with_model: bool, token: str | None) -> None:
    """Label sessions with a model. Not implemented; the rules run in `prudence rebuild`."""
    if not with_model:
        raise click.UsageError(
            "Rule-based purposes are computed by `prudence ingest` and `prudence rebuild`, "
            "and printed by `prudence usage` and `prudence sessions`. This command exists "
            "only for the optional model label, which needs --model."
        )
    raise click.ClickException(
        "Model classification is not implemented. The rule-based purpose label is computed "
        "for every session already; see `prudence usage` for the breakdown and this module's "
        "docstring for the design a model label would follow (redaction first, off by "
        "default, cached per session, the prompt version stored beside the label)."
    )
