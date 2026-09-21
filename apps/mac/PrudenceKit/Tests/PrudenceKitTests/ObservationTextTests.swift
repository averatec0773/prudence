import Foundation
import Testing

@testable import PrudenceStore
@testable import PrudenceUI

/// The one test that keeps the app and the CLI from wording the same finding differently.
///
/// `ObservationText` composes an observation from the row's own columns so that the sentence
/// can be Chinese when the interface is Chinese. The risk that buys is drift: the app's
/// English could wander a comma away from `store/observations.sentence` and nobody would
/// notice until a founder held a screenshot beside `prudence observations`. So the English
/// output is checked against `app_observation.sentence`, which is the engine's own prose,
/// stored on every row of the fixture, word for word and character for character.
@Suite("Observation sentences")
struct ObservationTextTests {

    /// Every row of the fixture, in English, must equal the sentence the engine wrote.
    @Test func englishEqualsTheEnginesOwnSentenceForEveryRow() throws {
        let rows = try Fixture.store().observations()
        #expect(!rows.isEmpty, "the fixture has no observations to check against")
        Localization.withLanguage(.english) {
            for row in rows {
                guard let engine = row.sentence else {
                    Issue.record("row \(row.observationId) has no stored sentence")
                    continue
                }
                #expect(
                    ObservationText.sentence(row: row) == engine,
                    """
                    row \(row.observationId) (\(row.fact) / \(row.outcome))
                    app:    \(ObservationText.sentence(row: row))
                    engine: \(engine)
                    """
                )
            }
        }
    }

    /// The Chinese is a different sentence, not the English with the numbers left in it, and
    /// it still carries every figure the English does.
    @Test func theChineseCarriesTheSameFiguresInItsOwnShape() throws {
        let rows = try Fixture.store().observations()
        for row in rows {
            let english = Localization.withLanguage(.english) {
                ObservationText.sentence(row: row)
            }
            let chinese = Localization.withLanguage(.chineseSimplified) {
                ObservationText.sentence(row: row)
            }
            #expect(chinese != english)
            for figure in [
                String(row.withN), String(row.withoutN),
                Fmt.percent(row.withValue), Fmt.percent(row.withoutValue),
            ] {
                #expect(chinese.contains(figure), "the Chinese sentence lost \(figure)")
            }
        }
    }

    /// The twelve facts of `store/observations.SPLITS` each have a phrase, in both languages,
    /// and none of them falls through to the "with <fact>" escape hatch.
    @Test func everySplitHasItsOwnPhraseInBothLanguages() {
        for language in [Language.english, .chineseSimplified] {
            Localization.withLanguage(language) {
                for entry in ObservationText.splitPhrases {
                    let sides = ObservationText.phrases(for: entry.fact)
                    #expect(sides.did == entry.phrase.text)
                    #expect(
                        sides.did != Str.observationSplitUnknown(entry.fact),
                        "\(entry.fact) fell through to the unknown-fact phrasing")
                    #expect(sides.didNot == Str.observationDidNot.text)
                }
            }
        }
    }

    /// A purpose used as a fact is named the way the engine names it, and its without-side is
    /// "labelled otherwise" rather than "that did not".
    @Test func aPurposeFactIsPhrasedAsALabel() {
        Localization.withLanguage(.english) {
            let sides = ObservationText.phrases(for: "purpose:development")
            #expect(sides.did == "labelled development")
            #expect(sides.didNot == "labelled otherwise")
            // The engine writes the raw label, so English keeps `unknown` rather than the
            // interface's "other". Chinese has no English string to match, so it translates.
            #expect(ObservationText.phrases(for: "purpose:unknown").did == "labelled unknown")
        }
        Localization.withLanguage(.chineseSimplified) {
            #expect(ObservationText.phrases(for: "purpose:unknown").did == "标记为 其他")
        }
    }

    /// A fact this build has never heard of still makes a sentence, with the engine's own
    /// fallback phrasing, rather than an empty string or a crash.
    @Test func anUnknownFactStillMakesASentence() {
        Localization.withLanguage(.english) {
            let input = ObservationText.Input(
                fact: "moon_phase",
                outcome: "rework",
                withN: 6,
                withoutN: 9,
                withValue: 0.12,
                withoutValue: 0.31,
                isPooled: false,
                project: "alpha"
            )
            #expect(
                ObservationText.sentence(input)
                    == "In alpha, your 6 sessions with moon_phase reworked 12% of their lines "
                    + "(median); the 9 without it, 31%."
            )
        }
    }

    /// An outcome the engine grows later reads with the survival wording, which is the
    /// else-branch of `_outcome_words` rather than a second special case.
    @Test func anOutcomeThatIsNotReworkReadsAsSurvival() {
        Localization.withLanguage(.english) {
            let input = ObservationText.Input(
                fact: "test_runs", outcome: "alive_head", withN: 7, withoutN: 9,
                withValue: 0.71, withoutValue: 0.54, isPooled: true, project: nil)
            #expect(
                ObservationText.sentence(input)
                    == "Across your projects, your 7 sessions that ran tests still have 71% of "
                    + "their lines at head (median); the 9 that did not, 54%."
            )
        }
    }

    /// The caveat is three columns of the same row in a fixed shape, and it follows the
    /// interface language like everything else on the screen.
    @Test func theCaveatIsLocalisedToo() throws {
        guard let row = try Fixture.store().observations().first else { return }
        let english = Localization.withLanguage(.english) { ObservationText.caveat(row: row) }
        let chinese = Localization.withLanguage(.chineseSimplified) {
            ObservationText.caveat(row: row)
        }
        #expect(english.hasPrefix("coverage "))
        #expect(chinese.hasPrefix("覆盖率 "))
    }
}
