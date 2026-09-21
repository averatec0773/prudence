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

    /// The language a stored model segment is written in: the column when there is one, and
    /// the prose when there is not.
    ///
    /// Contract 3 answers the batch 2 request and stores `app_review.segment_language`, the
    /// code `--language` was given. Where it is there this is a **read**. Where it is not —
    /// a contract 2 store, or a row written before the column existed — it falls back to the
    /// reading below, so an older review still says which language it is in.
    ///
    /// A stored code this app does not ship a language for is not trusted over the prose: the
    /// chip says what the reader is looking at, and a row claiming `fr` over English text
    /// would be a label that contradicts the paragraph under it.
    /// `system` is not a language either: it is the CLI's word for "whatever `model.language`
    /// says", so a row stamped with it is a row that did not record one and falls back too.
    public static func segmentLanguage(stored code: String?, of text: String) -> Language {
        if let code, let language = Language(rawValue: code), language != .system {
            return language
        }
        return segmentLanguage(of: text)
    }

    /// The same, **read off the segment itself**.
    ///
    /// A segment containing Han characters is Chinese and anything else is English, which is
    /// exact for the two languages this app ships and is a property of the stored text rather
    /// than a guess at what the setting was on the day it was written.
    public static func segmentLanguage(of text: String) -> Language {
        let han = text.unicodeScalars.contains { scalar in
            (0x4E00...0x9FFF).contains(scalar.value)
                || (0x3400...0x4DBF).contains(scalar.value)
        }
        return han ? .chineseSimplified : .english
    }
}
