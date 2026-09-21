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

    @Test("Today counts sessions from one view, commits from another and edits from a third")
    func today() throws {
        let store = try Fixture.store()
        // "Today" is whichever day the fixture last committed on; which day that is belongs to
        // the fixture, not to this test.
        let day = try #require(try Fixture.text("SELECT MAX(day) FROM app_commits_by_day"))
        let start = "\(day)T00:00:00"
        let end = "\(day)T23:59:59"
        let sessions = try store.sessions(startedBetween: start, and: end)
        // `app_commits_by_day` counts a commit once. Summing `app_session_list` over the same
        // day would count a commit credited to two sessions twice, which is what contract 1
        // forced the dropdown to do.
        let commits = try store.commitsByDay(since: day).filter { $0.day == day }
        let model = TodayModel(sessions: sessions, commits: commits)

        let expectedSessions = try Fixture.count(
            "SELECT COUNT(*) FROM app_session_list WHERE started_at >= ? AND started_at < ?",
            [start, end])
        let expectedCommits = try Fixture.count(
            "SELECT SUM(commits) FROM app_commits_by_day WHERE day = ?", [day])
        let expectedEdits = try Fixture.count(
            "SELECT SUM(edits) FROM app_session_list WHERE started_at >= ? AND started_at < ?",
            [start, end])

        #expect(model.sessions == expectedSessions)
        #expect(model.commits == expectedCommits)
        #expect(
            model.commits <= sessions.reduce(0) { $0 + $1.countedCommits },
            "the session list is the upper bound this view exists to undercut")
        #expect(model.edits == expectedEdits, "contract 2 carries edits per session")
        #expect(
            model.line
                == "\(expectedSessions) sessions, \(expectedEdits) edits, \(expectedCommits) commits"
        )
    }

    @Test("A day where nothing measured any edit leaves edits out of the line, not at zero")
    func editsMissing() {
        let model = TodayModel(sessions: 2, commits: 1, edits: nil)
        #expect(model.line == "2 sessions, 1 commits")
    }

    @Test("The sentence is read from the view, never built in Swift")
    func sentenceComesFromTheView() throws {
        let rows = try Fixture.store().observations()
        let first = try #require(rows.first)
        let model = ObservationModel(row: first)
        #expect(model.sentence == first.sentence)
        // The prose is a row of `app_observation_text` and nothing else: not a phrase table
        // restated in Swift, and not the sentence of the row next to it.
        #expect(
            model.sentence
                == (try Fixture.text(
                    "SELECT sentence FROM app_observation_text WHERE observation_id = ?",
                    [String(first.observationId)])))
        // The caveat is the only text this app assembles, out of three columns of that same
        // row, so it is checked against those three read off the `observation` table.
        let coverage = try #require(
            try Fixture.number(
                "SELECT coverage FROM observation WHERE fact = ? AND outcome = ?",
                [first.fact, first.outcome]))
        let method = try #require(
            try Fixture.text(
                """
                SELECT fact_commits || ' fact, ' || inferred_commits || ' inferred'
                  FROM observation WHERE fact = ? AND outcome = ?
                """, [first.fact, first.outcome]))
        #expect(model.caveat == "(coverage: \(Formatting.percent(coverage)), method: \(method))")
    }

    @Test("The latest observation is the first row of the view, cut for the dropdown")
    func observation() throws {
        let rows = try Fixture.store().observations()
        let model = try #require(LatestObservationModel(rows: rows))
        let sentence = try #require(rows.first?.sentence)
        #expect(model.sentence == sentence)
        if sentence.count > 80 {
            #expect(model.short.count == 80)
            #expect(model.short.hasSuffix("..."))
        } else {
            #expect(model.short == sentence, "nothing to cut")
        }
    }

    @Test("A pooled observation says 'across your projects' and never names a project")
    func pooledObservation() throws {
        let pooled = try #require(try Fixture.store().observations().first { $0.isPooled })
        let model = ObservationModel(row: pooled)
        #expect(model.sentence.hasPrefix("Across your projects,"))
        // Not one of the project names this store knows, whatever they happen to be called.
        for name in try Fixture.texts("SELECT name FROM repository WHERE name IS NOT NULL") {
            #expect(model.sentence.contains(name) == false, "\(name)")
        }
        #expect(model.isPooled)
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
        // The same four parts, spelled out in SQL: the id, the two range days cut to ten
        // characters, the project name the view resolved, and the title of the first section
        // inside the stored JSON.
        let expected = try #require(
            try Fixture.text(
                """
                SELECT 'Review ' || id
                       || ', ' || substr(range_start, 1, 10)
                       || ' to ' || substr(range_end, 1, 10)
                       || ', ' || project
                       || ': ' || json_extract(sections, '$[0].title')
                  FROM app_review ORDER BY id DESC LIMIT 1
                """))
        #expect(model.headline == expected)
    }

    @Test("Sections that cannot be read leave the headline without a title, not without a row")
    func unreadableSections() {
        #expect(LatestReviewModel.firstSectionTitle(of: "not json") == nil)
        #expect(LatestReviewModel.firstSectionTitle(of: "{\"sections\": []}") == nil)
    }

    @Test("A whole snapshot reads from the fixture in one pass")
    func snapshot() throws {
        // Noon on the fixture's own last day of usage, so "today" and "this week" have
        // something in them whenever the store is regenerated.
        let day = try #require(try Fixture.text("SELECT MAX(day) FROM app_usage_by_purpose_day"))
        let noon = try #require(Formatting.timestamp("\(day)T12:00:00"))
        let snapshot = try Snapshot.read(from: Fixture.store(), now: noon)
        #expect(snapshot.storeError == nil)
        #expect(snapshot.status?.sessions == (try Fixture.count("SELECT COUNT(*) FROM session")))
        // The reader's own midnight, which is what the dropdown means by "today" and the only
        // part of this the test takes from the code rather than from the store.
        let bounds = Formatting.localDayBoundsUTC(noon)
        #expect(
            snapshot.today.sessions
                == (try Fixture.count(
                    "SELECT COUNT(*) FROM app_session_list WHERE started_at >= ? AND started_at < ?",
                    [bounds.start, bounds.end])))
        // `Snapshot.read` asks for the last seven local days, today included.
        #expect(
            snapshot.week.total
                == (try Fixture.count(
                    """
                    SELECT SUM(total_tokens) FROM app_usage_by_purpose_day
                     WHERE day >= date(?, '-6 days')
                    """, [day])))
        #expect(snapshot.observation != nil)
        #expect(snapshot.review?.id == (try Fixture.count("SELECT MAX(id) FROM review")))
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
