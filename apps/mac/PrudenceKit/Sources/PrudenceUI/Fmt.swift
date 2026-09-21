import Foundation
import PrudenceModels

/// Numbers and dates on their way to a screen, through `Locale`.
///
/// `PrudenceModels.Formatting` is the engine-facing half: it parses the engine's UTC stamps
/// and prints the shapes the CLI prints. This is the reader-facing half: the same values in
/// the reader's own language and calendar. Two of them deliberately do not go through
/// `Locale`, and both are marked: the percentage and the plain integer inside an observation
/// sentence, which have to match `store/observations.py` character for character.
public enum Fmt {

    // MARK: - counts

    /// `1,248`, `1 248`, `1,248` — whatever the locale groups with.
    public static func count(_ value: Int, locale: Locale = Localization.locale) -> String {
        let formatter = NumberFormatter()
        formatter.locale = locale
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    /// The same integer with no grouping at all. Used only inside an observation sentence,
    /// where the engine writes `f"{n}"` and the English output has to equal it.
    public static func plain(_ value: Int) -> String { String(value) }

    /// `1.2M`, `43.1k`, `812`. The unit letters are not translated: they are the same in both
    /// languages the app ships, and the mockups print them the same way.
    public static func tokens(_ value: Int, locale: Locale = Localization.locale) -> String {
        if value >= 1_000_000 {
            return decimal(Double(value) / 1_000_000, places: 1, locale: locale) + "M"
        }
        if value >= 1_000 {
            return decimal(Double(value) / 1_000, places: 1, locale: locale) + "k"
        }
        return count(value, locale: locale)
    }

    /// `4.5`, one decimal, locale-aware separator.
    public static func hours(_ value: Double, locale: Locale = Localization.locale) -> String {
        decimal(value, places: 1, locale: locale)
    }

    public static func decimal(
        _ value: Double, places: Int, locale: Locale = Localization.locale
    ) -> String {
        let formatter = NumberFormatter()
        formatter.locale = locale
        formatter.numberStyle = .decimal
        formatter.minimumFractionDigits = places
        formatter.maximumFractionDigits = places
        return formatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    // MARK: - shares

    /// `88%`, the way the CLI prints a share, and the way an observation sentence must.
    /// Deliberately not `NumberFormatter.percent`, which would write `88 %` in some locales
    /// and break the word-for-word test.
    public static func percent(_ share: Double?) -> String {
        guard let share else { return Str.commonDash.text }
        return String(format: "%.0f%%", share * 100)
    }

    /// The distance between two shares, in points. Neutral: a gap has no sign and no colour.
    public static func points(_ gap: Double) -> String {
        String(format: "%.0f", abs(gap) * 100)
    }

    /// The same distance as a whole number, for the plural rule to choose on.
    public static func pointsValue(_ gap: Double) -> Int { Int((abs(gap) * 100).rounded()) }

    // MARK: - time

    /// `20 Sep 18:04`, or `9月20日 18:04`, in the reader's own time zone and calendar.
    public static func stamp(
        _ date: Date, locale: Locale = Localization.locale, zone: TimeZone = .current
    ) -> String {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = zone
        formatter.setLocalizedDateFormatFromTemplate("d MMM HH:mm")
        return formatter.string(from: date)
    }

    /// `4 minutes ago`, `4 分钟前`, `never`.
    public static func relative(
        _ date: Date?, now: Date = Date(), locale: Locale = Localization.locale
    ) -> String {
        guard let date else { return Str.menuNever.text }
        let seconds = now.timeIntervalSince(date)
        if seconds < 60 { return Str.menuJustNow.text }
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = locale
        formatter.unitsStyle = .full
        return formatter.localizedString(for: date, relativeTo: now)
    }

    /// A `yyyy-MM-dd` day as the reader writes it: `20 Sep 2026`, `2026年9月20日`.
    public static func day(_ day: String, locale: Locale = Localization.locale) -> String {
        guard let date = Formatting.date(day) else { return day }
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = .current
        formatter.setLocalizedDateFormatFromTemplate("d MMM y")
        return formatter.string(from: date)
    }

    /// The axis form: `8 Sep`, `9月8日`. No year, because every axis here spans weeks.
    public static func shortDay(_ day: String, locale: Locale = Localization.locale) -> String {
        guard let date = Formatting.date(day) else { return day }
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = .current
        formatter.setLocalizedDateFormatFromTemplate("d MMM")
        return formatter.string(from: date)
    }

    // MARK: - phrases built from a count

    /// The four that carry a count go through the catalog's plural entries, so English says
    /// "1 session" and "3 sessions" and Chinese says "1 个会话" either way.
    public static func sessions(_ value: Int) -> String { Str.unitSessions.plural(value) }
    public static func commits(_ value: Int) -> String { Str.unitCommits.plural(value) }
    public static func edits(_ value: Int) -> String { Str.unitEdits.plural(value) }
    public static func projects(_ value: Int) -> String { Str.unitProjects.plural(value) }

    /// These two carry a measure rather than a count: `6.2k tokens`, `0.1 hours`. A plural
    /// rule has nothing to choose on once the value has been rounded to `6.2k`, so they stay
    /// plain, which is also how the mockups print them.
    public static func tokenPhrase(_ value: Int) -> String { Str.unitTokens(tokens(value)) }
    public static func hourPhrase(_ value: Double) -> String { Str.unitHours(hours(value)) }

    /// Join phrases the way the language joins a list: `a, b, c` and `a，b，c`.
    public static func list(_ parts: [String]) -> String {
        parts.joined(separator: Str.commonListSeparator.text)
    }

    /// The range picker's three labels and the line under the title.
    ///
    /// `ChartRange` lives in `PrudenceModels`, which knows nothing about the interface
    /// language and should not; its `label` and `describe` stay as the English the CLI-facing
    /// layer uses, and the interface says them its own way here.
    public static func range(_ range: ChartRange) -> String {
        switch range {
        case .eightWeeks: return Str.rangeEightWeeks.text
        case .ninetyDays: return Str.rangeNinetyDays.text
        case .all: return Str.rangeAll.text
        }
    }

    public static func rangeDescription(_ range: ChartRange, now: Date) -> String {
        guard let first = range.firstDay(now: now) else { return Str.rangeEveryDay.text }
        return Str.rangeSince(day(first))
    }

    /// The purpose the reader sees. `unknown` is "other", never "unknown".
    public static func purpose(_ key: String) -> String {
        switch key {
        case "development": return Str.purposeDevelopment.text
        case "research": return Str.purposeResearch.text
        case "debugging": return Str.purposeDebugging.text
        case "conversation": return Str.purposeConversation.text
        case "mixed": return Str.purposeMixed.text
        case "unknown": return Str.purposeUnknown.text
        default: return key
        }
    }

    /// The purpose as it appears **inside an observation sentence**.
    ///
    /// English keeps the engine's own label, because that sentence has to equal
    /// `app_observation.sentence` word for word and the engine writes `labelled unknown`
    /// where the interface elsewhere says "other". Every other language gets the reader's
    /// word, since there is no English string to match there.
    public static func purposeInSentence(_ key: String) -> String {
        Localization.running == .english ? key : purpose(key)
    }
}
