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
}
