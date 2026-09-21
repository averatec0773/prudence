import Foundation
import PrudenceStore

/// One observation in plain words, composed from the row's own columns, in the language the
/// interface is in.
///
/// This is the one place the app puts words around numbers the engine computed, and it exists
/// because a sentence cannot be translated: `store/observations.sentence` writes English prose
/// from seven columns, and Chinese puts those same seven pieces in a different order with
/// different joins. Translating the finished English string would translate the accident of
/// one row's numbers. So the shape is a template per language per outcome, and the pieces are
/// filled in from the row.
///
/// The rule set, all of it a restatement of `store/observations.py`:
///
/// - **Where.** A pooled row (`repo_key = '*'`) says "Across your projects"; any other says
///   "In <project>", falling back to the repo key when the view has no name, which is what
///   `sentence(row, name)` does with `name or row['repo_key']`.
/// - **The with-side phrase.** A fact beginning `purpose:` is "labelled <label>"; one of the
///   twelve facts in `SPLITS` uses that split's own `did` text; anything else falls back to
///   "with <fact>", which is the engine's own fallback for a fact it does not know.
/// - **The without-side phrase.** "that did not" for a fact, "labelled otherwise" for a
///   purpose, "without it" for an unknown fact. The same three the engine has.
/// - **The outcome clause.** `rework` reads "reworked X of their lines (median)"; every other
///   outcome reads "still have X of their lines at head (median)", which is the else-branch of
///   `_outcome_words` rather than a second special case.
/// - **The figures.** Shares through `%.0f%%` and counts as plain integers with no grouping,
///   because English output has to equal `app_observation.sentence` word for word. A test
///   asserts exactly that over every row of the fixture.
///
/// Nothing here computes: every number is a column, and the only arithmetic is the `* 100` a
/// percentage is.
public enum ObservationText {

    /// The prefix the engine gives a purpose label used as a fact.
    public static let purposePrefix = "purpose:"

    /// The repo key of a row pooled over every project.
    public static let pooledKey = "*"

    /// The twelve behaviour facts, in `SPLITS` order, each with the phrase that names its
    /// with-side. A test pins that this table covers every fact the fixture carries.
    public static let splitPhrases: [(fact: String, phrase: Str)] = [
        ("sittings", .observationSplitSittings),
        ("files_edited_unread", .observationSplitFilesEditedUnread),
        ("formatter_runs", .observationSplitFormatterRuns),
        ("test_runs", .observationSplitTestRuns),
        ("tests_before_commit", .observationSplitTestsBeforeCommit),
        ("commit_attempts_per_commit", .observationSplitCommitAttempts),
        ("repeated_errors", .observationSplitRepeatedErrors),
        ("subagent_used", .observationSplitSubagentUsed),
        ("compactions", .observationSplitCompactions),
        ("context_resets", .observationSplitContextResets),
        ("prompts_per_active_hour", .observationSplitPromptsPerHour),
        ("hand_edits_between_turns", .observationSplitHandEdits),
    ]

    private static let byFact = Dictionary(
        uniqueKeysWithValues: splitPhrases.map { ($0.fact, $0.phrase) })

    /// The columns a sentence is built from, and nothing else. A value type so a test can
    /// build one by hand and the render harness can draw a row with no database behind it.
    public struct Input: Equatable, Sendable {
        public let fact: String
        public let outcome: String
        public let withN: Int
        public let withoutN: Int
        public let withValue: Double
        public let withoutValue: Double
        public let isPooled: Bool
        public let project: String?

        public init(
            fact: String,
            outcome: String,
            withN: Int,
            withoutN: Int,
            withValue: Double,
            withoutValue: Double,
            isPooled: Bool,
            project: String?
        ) {
            self.fact = fact
            self.outcome = outcome
            self.withN = withN
            self.withoutN = withoutN
            self.withValue = withValue
            self.withoutValue = withoutValue
            self.isPooled = isPooled
            self.project = project
        }

        public init(row: AppObservationRow) {
            self.init(
                fact: row.fact,
                outcome: row.outcome,
                withN: row.withN,
                withoutN: row.withoutN,
                withValue: row.withValue,
                withoutValue: row.withoutValue,
                // The flag and the key say the same thing; both are checked, because a store
                // whose `pooled` column disagrees with its `repo_key` should still read right.
                isPooled: row.isPooled || row.repoKey == pooledKey,
                project: row.project == pooledKey ? nil : (row.project ?? row.repoKey)
            )
        }
    }

    // MARK: - the sentence

    public static func sentence(_ input: Input) -> String {
        let template: Str =
            input.outcome == "rework" ? .observationSentenceRework : .observationSentenceAlive
        let sides = phrases(for: input.fact)
        return template(
            place(input),
            Fmt.plain(input.withN),
            sides.did,
            Fmt.percent(input.withValue),
            Fmt.plain(input.withoutN),
            sides.didNot,
            Fmt.percent(input.withoutValue)
        )
    }

    public static func sentence(row: AppObservationRow) -> String {
        sentence(Input(row: row))
    }

    /// `coverage 90%, method: 4 fact, 3 inferred`, beside the sentence and never a section
    /// away (principle 3).
    public static func caveat(row: AppObservationRow) -> String {
        Str.observationMethodLine(
            Fmt.percent(row.coverage),
            Fmt.count(row.factCommits),
            Fmt.count(row.inferredCommits)
        )
    }

    // MARK: - the pieces

    /// "Across your projects", or "In <project>".
    static func place(_ input: Input) -> String {
        guard !input.isPooled, let project = input.project, !project.isEmpty else {
            return Str.observationWherePooled.text
        }
        return Str.observationWhereProject(project)
    }

    /// How the two sides of one split are named. The counterpart of
    /// `store/observations.phrases`.
    public static func phrases(for fact: String) -> (did: String, didNot: String) {
        if fact.hasPrefix(purposePrefix) {
            let label = String(fact.dropFirst(purposePrefix.count))
            return (
                Str.observationSplitPurpose(Fmt.purposeInSentence(label)),
                Str.observationSplitPurposeDidNot.text
            )
        }
        if let phrase = byFact[fact] {
            return (phrase.text, Str.observationDidNot.text)
        }
        return (Str.observationSplitUnknown(fact), Str.observationSplitUnknownDidNot.text)
    }
}
