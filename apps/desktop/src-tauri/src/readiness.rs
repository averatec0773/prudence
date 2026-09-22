//! Whether a review is ready, and the engine's own sentence for it.
//!
//! `prudence review` declines when there is not enough new work, and until now the only
//! way to learn that from the app was to press the button and be refused. The engine
//! carries the answer without being asked to write anything: `prudence status --json` has
//! a `readiness` block, and `prudence status` prints a `review:` line with the rule's own
//! sentence.
//!
//! **Two reads, and the second one only when it is needed.** The numbers come from the
//! JSON, because a sentence cannot be recomposed in the reader's language out of English;
//! the sentence comes from the text, because when a review *is* ready the engine's own
//! words are the thing to say and nothing in the JSON carries them. The text status is
//! asked for only in that case, which is the one where it is printed.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// `status --json`'s `readiness` block, as the engine wrote it.
///
/// Every field is optional in the same sense the scan's are: a store from an engine that
/// counts something else tomorrow still answers the one question this is for.
#[derive(Debug, Clone, Default, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Readiness {
    #[serde(default)]
    pub ready: bool,
    #[serde(default, alias = "new_sessions")]
    pub new_sessions: i64,
    #[serde(default, alias = "required_sessions")]
    pub required_sessions: i64,
    #[serde(default, alias = "matured_commits")]
    pub matured_commits: i64,
    #[serde(default, alias = "required_commits")]
    pub required_commits: i64,
    /// What the counts are since: the last review's end, or nothing at all where there
    /// has never been one.
    #[serde(default)]
    pub since: Option<String>,
    /// The project these counts are for, or nothing for the whole store.
    #[serde(default)]
    pub project: Option<String>,
    /// The engine's own sentence, from the `review:` line of `prudence status`. Filled in
    /// by the shell rather than by the engine's JSON, which carries no sentence.
    #[serde(default)]
    pub sentence: Option<String>,
}

/// The `readiness` block of `prudence status --json`.
///
/// A status without one is not an error: an older engine simply does not answer this
/// question, and the interface then says nothing rather than saying "not ready".
pub fn parse(printed: &str) -> Option<Readiness> {
    let json = serde_json::from_str::<Value>(printed).ok()?;
    serde_json::from_value(json.get("readiness")?.clone()).ok()
}

/// The prefix `prudence status` puts on the line that carries the rule's own sentence.
const REVIEW_LINE: &str = "review:";

/// The engine's own sentence about a review, out of `prudence status`'s own output.
pub fn review_line(printed: &str) -> Option<String> {
    printed
        .lines()
        .map(str::trim)
        .find_map(|line| line.strip_prefix(REVIEW_LINE))
        .map(str::trim)
        .filter(|sentence| !sentence.is_empty())
        .map(str::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `prudence status --json`'s readiness, copied from a run against a copy of the
    /// founder's store on 2026-09-22.
    const PRINTED: &str = r#"{
      "engine_version": "0.1.0",
      "readiness": {
        "ready": true, "new_sessions": 151, "required_sessions": 5,
        "matured_commits": 697, "required_commits": 1, "since": null,
        "project": null,
        "projects": [
          {"ready": false, "new_sessions": 3, "required_sessions": 5,
           "matured_commits": 0, "required_commits": 1,
           "since": "2026-09-21T00:01:34", "project": "root:df801c8e"}
        ]
      }
    }"#;

    #[test]
    fn the_numbers_are_the_engines_own() {
        let found = parse(PRINTED).expect("a readiness block");
        assert!(found.ready);
        assert_eq!(found.new_sessions, 151);
        assert_eq!(found.required_sessions, 5);
        assert_eq!(found.matured_commits, 697);
        assert_eq!(found.required_commits, 1);
        assert_eq!(found.since, None);
        assert_eq!(found.project, None);
        // The shell fills this in from the text status, and only when it is printed.
        assert_eq!(found.sentence, None);
    }

    #[test]
    fn a_status_with_no_readiness_is_no_answer_rather_than_a_wrong_one() {
        assert_eq!(parse(r#"{"engine_version": "0.1.0"}"#), None);
        assert_eq!(parse("not json"), None);
        assert_eq!(parse(""), None);
    }

    /// The sentence is the engine's, printed as it came. Both shapes of the line, copied
    /// from `prudence status` with a ready store and with one that is not.
    #[test]
    fn the_sentence_is_the_line_the_engine_prints() {
        let ready = "\
observations: 8 in a project, 0 pooled across your projects
review: A review is ready: 151 new sessions so far and 697 commits crossed their 7-day mark.
sessions mapped by a fallback: 29 by worktree-pattern
";
        assert_eq!(
            review_line(ready).as_deref(),
            Some("A review is ready: 151 new sessions so far and 697 commits crossed their 7-day mark.")
        );

        let waiting = "review: not ready: 2 new sessions so far (needs 5).\n";
        assert_eq!(
            review_line(waiting).as_deref(),
            Some("not ready: 2 new sessions so far (needs 5).")
        );

        // A status that prints no such line, and one that prints an empty one.
        assert_eq!(review_line("derived: 151 sessions\n"), None);
        assert_eq!(review_line("review:   \n"), None);
    }
}
