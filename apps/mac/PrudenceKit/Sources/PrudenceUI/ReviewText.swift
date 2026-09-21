import Foundation
import PrudenceModels
import PrudenceStore

/// The review headline, composed in the interface language.
///
/// `app_review.headline` is built in SQL and is therefore always English, exactly as
/// `app_observation.sentence` is. The same rule applies: the app rebuilds it from the row's
/// own fields rather than translating the finished string, so it follows the language the
/// reader chose. Unlike an observation sentence there is no word-for-word test against the
/// engine here, because the headline is a label for a document rather than a claim about the
/// reader's work; the document's own figures come from the stored payload and are not
/// restated.
public enum ReviewText {

    /// `Review 3, 8 Sep 2026 to 15 Sep 2026, prudence: What you did`.
    public static func headline(_ review: LatestReviewModel) -> String {
        let id = Fmt.plain(review.id)
        let start = Fmt.day(review.rangeStart)
        let end = Fmt.day(review.rangeEnd)
        let stem: String
        if let project = review.project, !project.isEmpty {
            stem = Str.reviewHeadlineProject(id, start, end, project)
        } else {
            stem = Str.reviewHeadline(id, start, end)
        }
        guard let section = review.firstSection, !section.isEmpty else { return stem }
        return Str.reviewHeadlineSection(stem, section)
    }

    /// What the picker prints for one stored review: `Review 3 - 15 Sep 2026`.
    public static func option(id: Int, rangeEnd: String) -> String {
        Str.reviewOption(Fmt.plain(id), Fmt.day(rangeEnd))
    }

    /// Who a review is about, in the reader's own language.
    ///
    /// `ReviewModel.scope` answers `"every project"` in English for a review with no project,
    /// which is one of the app's own strings rather than the engine's and therefore belongs
    /// here. A named project is a name and is not translated.
    public static func scope(_ project: String?) -> String {
        guard let project, !project.isEmpty else { return Str.reviewScopeEveryProject.text }
        return project
    }

    /// When a review was written: the date the reader writes plus how long ago it was.
    public static func written(_ day: String, now: Date = Date()) -> String {
        Fmt.writtenOn(day, now: now)
    }

    /// `Written by claude-sonnet-4-5`.
    public static func credit(model: String) -> String { Str.reviewWrittenBy(model) }

    /// The language a stored model segment is written in, **read off the segment itself**.
    ///
    /// `app_review` has no column for it: `--language` reaches the prompt and the answer is
    /// stored as text, so the only record of which language was asked for is the prose. A
    /// segment containing Han characters is Chinese and anything else is English, which is
    /// exact for the two languages this app ships and is a property of the stored text rather
    /// than a guess at what the setting was on the day it was written. A `segment_language`
    /// column would make this a read instead of a reading; it is one of the contract requests
    /// in `apps/mac/DESIGN.md`.
    public static func segmentLanguage(of text: String) -> Language {
        let han = text.unicodeScalars.contains { scalar in
            (0x4E00...0x9FFF).contains(scalar.value)
                || (0x3400...0x4DBF).contains(scalar.value)
        }
        return han ? .chineseSimplified : .english
    }
}
