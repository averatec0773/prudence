import Foundation
import PrudenceStore

/// One observation row in plain words.
///
/// Every number in the sentence comes from the row; only the wording is here. That split is
/// deliberate and is stated in `store/app_views.py`: "The sentence a surface prints is prose
/// built by `store/observations.sentence`, so it is not here; the numbers behind it are."
///
/// The phrase table below is copied from `SPLITS` in `src/prudence/store/observations.py` and
/// is the one piece of the Python side this app restates. That is a contract request, not a
/// design: an `app_observation.sentence` column would delete this file. Until then the wording
/// is pinned by a test against the same rows the CLI prints, so a drift shows up in `swift
/// test` rather than in the dropdown.
public enum ObservationSentence {

    static let purposePrefix = "purpose:"
    static let pooledKey = "*"

    /// `did` and `did_not` for one behaviour fact, in the order `SPLITS` lists them.
    static let phrases: [String: (did: String, didNot: String)] = [
        "sittings": ("that ran over three or more sittings", "that did not"),
        "files_edited_unread": (
            "that edited more files before reading them than your median here", "that did not"
        ),
        "formatter_runs": ("that ran a formatter", "that did not"),
        "test_runs": ("that ran tests", "that did not"),
        "tests_before_commit": (
            "that ran tests before at least half of their commits", "that did not"
        ),
        "commit_attempts_per_commit": (
            "that attempted more than two commits for each commit counted", "that did not"
        ),
        "repeated_errors": ("that hit the same error three times or more", "that did not"),
        "subagent_used": ("that dispatched a subagent", "that did not"),
        "compactions": ("that compacted their context", "that did not"),
        "context_resets": ("that replayed an earlier session's records", "that did not"),
        "prompts_per_active_hour": (
            "that prompted more often per active hour than your median here", "that did not"
        ),
        "hand_edits_between_turns": (
            "that changed the tree by hand between two turns the hooks saw", "that did not"
        ),
    ]

    public static func sentence(for row: AppObservationRow) -> String {
        let where_ =
            row.isPooled ? "Across your projects" : "In \(row.project ?? row.repoKey)"
        let (did, didNot) = phrase(for: row.fact)
        return
            "\(where_), your \(row.withN) sessions \(did) "
            + "\(outcomeWords(row.outcome, row.withValue)); "
            + "the \(row.withoutN) \(didNot), \(Formatting.percent(row.withoutValue))."
    }

    /// The coverage and method mix behind the sentence, which principle 3 says travels with it.
    public static func caveat(for row: AppObservationRow) -> String {
        let coverage = row.coverage.map { Formatting.percent($0) } ?? "-"
        return
            "(coverage: \(coverage), method: \(row.factCommits) fact, \(row.inferredCommits) inferred)"
    }

    static func phrase(for fact: String) -> (did: String, didNot: String) {
        if fact.hasPrefix(purposePrefix) {
            return ("labelled \(String(fact.dropFirst(purposePrefix.count)))", "labelled otherwise")
        }
        return phrases[fact] ?? ("with \(fact)", "without it")
    }

    static func outcomeWords(_ outcome: String, _ value: Double) -> String {
        if outcome == "rework" {
            return "reworked \(Formatting.percent(value)) of their lines (median)"
        }
        return "still have \(Formatting.percent(value)) of their lines at head (median)"
    }
}
