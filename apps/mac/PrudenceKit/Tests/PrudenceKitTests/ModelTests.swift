import Foundation
import Testing

@testable import PrudenceModels
@testable import PrudenceStore

/// Building a usage row by hand, so the top-three rule can be checked without a database.
func usageRow(_ day: String, _ purpose: String, _ tokens: Int) -> AppUsageByPurposeDayRow {
    let json = """
        {"day": "\(day)", "repo_key": "r", "project": "p", "purpose": "\(purpose)",
         "input_tokens": \(tokens), "output_tokens": 0, "cache_read_tokens": 0,
         "cache_creation_tokens": 0, "total_tokens": \(tokens), "active_minutes": 1.0,
         "sessions": 1, "measured_sessions": 1}
        """
    return try! JSONDecoder().decode(
        AppUsageByPurposeDayRow.self, from: Data(json.utf8))
}

@Suite("This week by purpose")
struct WeekUsageTests {

    @Test("The top three purposes by tokens, with their share of the whole week")
    func topThree() {
        let model = WeekUsageModel(rows: [
            usageRow("2026-09-15", "development", 800),
            usageRow("2026-09-16", "development", 200),
            usageRow("2026-09-15", "research", 500),
            usageRow("2026-09-15", "debugging", 300),
            usageRow("2026-09-15", "planning", 200),
        ])
        #expect(model.total == 2000)
        #expect(model.top.map(\.purpose) == ["development", "research", "debugging"])
        #expect(model.top.map(\.tokens) == [1000, 500, 300])
        #expect(model.line == "development 50%, research 25%, debugging 15%")
    }

    @Test("Fewer than three purposes is fewer than three lines, not padding")
    func fewerThanThree() {
        let model = WeekUsageModel(rows: [
            usageRow("2026-09-15", "development", 880),
            usageRow("2026-09-15", "research", 120),
        ])
        #expect(model.line == "development 88%, research 12%")
    }

    @Test("A week with no tokens says so rather than showing 0%")
    func emptyWeek() {
        #expect(WeekUsageModel(rows: []).line == "no tokens yet")
        #expect(WeekUsageModel(rows: [usageRow("2026-09-15", "development", 0)]).line
            == "no tokens yet")
    }

    @Test("A tie breaks on the name, so the order does not flicker between refreshes")
    func stableTies() {
        let model = WeekUsageModel(rows: [
            usageRow("2026-09-15", "research", 100),
            usageRow("2026-09-15", "development", 100),
            usageRow("2026-09-15", "planning", 100),
            usageRow("2026-09-15", "review", 100),
        ])
        #expect(model.top.map(\.purpose) == ["development", "planning", "research"])
    }
}

@Suite("The dropdown's other lines")
struct DropdownModelTests {

    @Test("Today counts the sessions it was given and the commits credited to them")
    func today() throws {
        let rows = try Fixture.store().sessions(
            startedBetween: "2026-09-01T00:00:00", and: "2026-10-01T00:00:00")
        let model = TodayModel(rows: rows)
        #expect(model.sessions == 4)
        #expect(model.commits >= 1)
        #expect(model.edits == nil, "no app_* view carries edits per day at contract 1")
        #expect(model.line == "4 sessions, \(model.commits) commits")
    }

    /// Word for word what `store/observations.sentence` printed for these same three rows,
    /// captured by running the Python side over this fixture. The wording is restated in
    /// Swift only because contract 1 has no `sentence` column; this test is what keeps the
    /// two from drifting apart in silence.
    static let pythonSentences = [
        "In alpha, your 6 sessions that ran over three or more sittings still have 71% of their lines at head (median); the 11 that did not, 54%.",
        "In alpha, your 7 sessions that ran tests reworked 12% of their lines (median); the 9 that did not, 31%.",
        "Across your projects, your 8 sessions that dispatched a subagent reworked 22% of their lines (median); the 14 that did not, 40%.",
    ]
    static let pythonCaveats = [
        "(coverage: 90%, method: 4 fact, 3 inferred)",
        "(coverage: 86%, method: 5 fact, 2 inferred)",
        "(coverage: 77%, method: 6 fact, 5 inferred)",
    ]

    @Test("Every sentence is the one the CLI prints, word for word")
    func sentencesMatchThePythonSide() throws {
        let rows = try Fixture.store().observations()
        #expect(rows.map(ObservationSentence.sentence(for:)) == Self.pythonSentences)
        #expect(rows.map(ObservationSentence.caveat(for:)) == Self.pythonCaveats)
    }

    @Test("The latest observation is the first row of the view, cut for the dropdown")
    func observation() throws {
        let rows = try Fixture.store().observations()
        let model = try #require(LatestObservationModel(rows: rows))
        #expect(model.sentence == Self.pythonSentences[0])
        #expect(model.caveat == Self.pythonCaveats[0])
        #expect(model.short.count == 80)
        #expect(model.short.hasSuffix("..."))
    }

    @Test("A pooled observation says 'across your projects' and never names a project")
    func pooledObservation() throws {
        let pooled = try #require(try Fixture.store().observations().first { $0.isPooled })
        #expect(ObservationSentence.sentence(for: pooled).hasPrefix("Across your projects,"))
        #expect(ObservationSentence.sentence(for: pooled).contains("alpha") == false)
    }

    @Test("The dropdown line is cut at 80 characters, the full text stays for the tooltip")
    func truncation() {
        let long = String(repeating: "a", length: 200)
        #expect(Formatting.truncate(long).count == 80)
        #expect(Formatting.truncate(long).hasSuffix("..."))
        #expect(Formatting.truncate("short") == "short")
        #expect(Formatting.truncate(nil) == "none yet")
    }

    @Test("The review headline is id, range, scope and the first section")
    func reviewHeadline() throws {
        let row = try #require(try Fixture.store().latestReview())
        let model = LatestReviewModel(row: row)
        #expect(model.headline == "Review 1, 2026-09-08 to 2026-09-15: What you did")
    }

    @Test("Sections that cannot be read leave the headline without a title, not without a row")
    func unreadableSections() {
        #expect(LatestReviewModel.firstSectionTitle(of: "not json") == nil)
        #expect(LatestReviewModel.firstSectionTitle(of: "{\"sections\": []}") == nil)
    }

    @Test("A whole snapshot reads from the fixture in one pass")
    func snapshot() throws {
        let noon = Formatting.timestamp("2026-09-15T12:00:00")!
        let snapshot = try Snapshot.read(from: Fixture.store(), now: noon)
        #expect(snapshot.storeError == nil)
        #expect(snapshot.status?.sessions == 4)
        #expect(snapshot.today.sessions >= 1)
        #expect(snapshot.week.total > 0)
        #expect(snapshot.observation != nil)
        #expect(snapshot.review?.id == 1)
    }
}

@Suite("Formatting")
struct FormattingTests {

    @Test("An engine timestamp with microseconds and an offset still parses")
    func timestamps() {
        #expect(Formatting.timestamp("2026-09-21T01:08:15.804495+00:00") != nil)
        #expect(Formatting.timestamp("2026-09-21T01:08:15") != nil)
        #expect(Formatting.timestamp(nil) == nil)
        #expect(Formatting.timestamp("") == nil)
    }

    @Test("Never is a word, not a blank")
    func never() {
        #expect(Formatting.relative(nil) == "never")
        let status = StatusModel(
            engineVersion: "0.2.0", contractVersion: "1", lastIngest: nil, sessions: 0, projects: 0)
        #expect(status.lastIngestText() == "never")
    }

    @Test("Shares and token counts read the way the CLI prints them")
    func numbers() {
        #expect(Formatting.percent(0.875) == "88%")
        #expect(Formatting.tokens(812) == "812")
        #expect(Formatting.tokens(43_120) == "43.1k")
        #expect(Formatting.tokens(1_200_000) == "1.2M")
    }

    @Test("Today's bounds are the reader's own midnight, converted to the store's UTC")
    func dayBounds() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let noon = Formatting.timestamp("2026-09-15T12:00:00")!
        let bounds = Formatting.localDayBoundsUTC(noon, calendar: calendar)
        #expect(bounds.start == "2026-09-15T00:00:00")
        #expect(bounds.end == "2026-09-16T00:00:00")
    }
}

extension String {
    init(repeating character: String, length: Int) {
        self = String(repeating: character, count: length)
    }
}
