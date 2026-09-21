import Foundation

/// Turning the engine's strings and numbers into the words on the screen. No arithmetic that
/// is not presentation: a percentage of two numbers the engine gave us is formatting, a
/// median is not, and anything in the second class belongs in a view in Python.
public enum Formatting {

    /// The engine writes timestamps as UTC `yyyy-MM-dd'T'HH:mm:ss`, sometimes with fractions.
    public static func timestamp(_ text: String?) -> Date? {
        guard let text, !text.isEmpty else { return nil }
        let trimmed = String(text.prefix(19))
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter.date(from: trimmed)
    }

    /// `20 Sep 2026 at 18:04`, in the reader's own time zone. A stored UTC string shown as
    /// UTC would be a small lie every evening after five.
    public static func localTime(_ date: Date, locale: Locale = .current, zone: TimeZone = .current)
        -> String
    {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = zone
        formatter.dateFormat = "d MMM HH:mm"
        return formatter.string(from: date)
    }

    /// `4 minutes ago`, `never`.
    public static func relative(_ date: Date?, now: Date = Date()) -> String {
        guard let date else { return "never" }
        let seconds = now.timeIntervalSince(date)
        if seconds < 0 { return "just now" }
        if seconds < 60 { return "just now" }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        return formatter.localizedString(for: date, relativeTo: now)
    }

    /// The local calendar day as the usage view spells it, `yyyy-MM-dd`.
    public static func day(_ date: Date, calendar: Calendar = .current) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = calendar.timeZone
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    /// The reader's local midnight and the next one, as the UTC strings the store sorts by.
    /// The same conversion `menubar/summary.py` does, so the two surfaces agree on "today".
    public static func localDayBoundsUTC(_ date: Date, calendar: Calendar = .current) -> (
        start: String, end: String
    ) {
        let startOfDay = calendar.startOfDay(for: date)
        let nextDay =
            calendar.date(byAdding: .day, value: 1, to: startOfDay) ?? startOfDay.addingTimeInterval(86_400)
        return (utcStamp(startOfDay), utcStamp(nextDay))
    }

    static func utcStamp(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter.string(from: date)
    }

    /// `88%`, the way the CLI prints a share.
    public static func percent(_ share: Double) -> String {
        String(format: "%.0f%%", share * 100)
    }

    /// `1.2M`, `43.1k`, `812`.
    public static func tokens(_ value: Int) -> String {
        if value >= 1_000_000 { return String(format: "%.1fM", Double(value) / 1_000_000) }
        if value >= 1_000 { return String(format: "%.1fk", Double(value) / 1_000) }
        return "\(value)"
    }

    /// The observation line in the dropdown: one sentence, cut at `limit`, full text on hover.
    /// The same 80 characters and the same ellipsis as the rumps prototype's `_truncate`.
    public static func truncate(_ text: String?, limit: Int = 80) -> String {
        guard let text, !text.isEmpty else { return "none yet" }
        guard text.count > limit else { return text }
        let head = String(text.prefix(limit - 3))
        return head.trimmingCharacters(in: .whitespaces) + "..."
    }
}
