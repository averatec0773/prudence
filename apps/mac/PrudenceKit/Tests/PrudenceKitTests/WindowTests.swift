import Foundation
import Testing

@testable import PrudenceModels
@testable import PrudenceStore

/// One outcome row built by hand, so the gap rule can be checked without a database.
func outcomeRow(
    project: String,
    week: String,
    lines: Int?,
    measured30: Int?,
    alive30: Int?,
    reworked: Int?,
    coverage: Double? = 0.9
) -> AppOutcomesByWeekRow {
    func number(_ value: Int?) -> String { value.map(String.init) ?? "null" }
    let json = """
        {"repo_key": "r", "project": "\(project)", "week_start": "\(week)",
         "commits": 1, "commits_fact": 1, "commits_inferred": 0,
         "lines": \(number(lines)),
         "measured_7d": null, "alive_7d": null,
         "measured_30d": \(number(measured30)), "alive_30d": \(number(alive30)),
         "measured_90d": null, "alive_90d": null,
         "alive_head": null, "alive_head_anywhere": null, "blame_head": null,
         "reworked": \(number(reworked)),
         "coverage": \(coverage.map { String($0) } ?? "null")}
        """
    return try! JSONDecoder().decode(AppOutcomesByWeekRow.self, from: Data(json.utf8))
}

func sessionRow(_ id: String, project: String, startedAt: String?) -> AppSessionListRow {
    let started = startedAt.map { "\"\($0)\"" } ?? "null"
    let json = """
        {"session_id": "\(id)", "repo_key": "r", "project": "\(project)",
         "started_at": \(started), "ended_at": null, "purpose": "development",
         "total_tokens": 10, "commits_fact": 0, "commits_inferred": 0,
         "commits_uncertain": 0, "coverage": null, "sittings": 1,
         "capture_level": "full", "content_archived": 1, "edits": 3}
        """
    return try! JSONDecoder().decode(AppSessionListRow.self, from: Data(json.utf8))
}

// MARK: - the review payload

@Suite("Decoding a review's sections")
struct ReviewPayloadTests {

    /// A real row off the founder's own store, not one written for the test. It holds only
    /// numbers, labels and the notes that explain them, which is what a review row is.
    static func real() throws -> ReviewPayload {
        try #require(ReviewPayload.decode(Fixture.reviewSections))
    }

    @Test("Every section kind a real review carries decodes, in the order it was written")
    func everyKind() throws {
        let payload = try Self.real()
        let kinds = payload.sections.map(\.kind)
        #expect(
            payload.sections.map(\.key)
                == ["did", "became", "observations", "compared", "suggestions"])
        #expect(kinds == [.did, .became, .observations, .compared, .suggestions])
        #expect(kinds.filter(\.isKnown).count == 5)
        #expect(payload.reviewVersion == 1)
        #expect(payload.projectName == "prudence")
        #expect(payload.versions?["parser"] != nil)
    }

    @Test("A section with a table keeps its headers, its rows and its notes")
    func table() throws {
        let did = try #require(try Self.real().section(.did))
        #expect(did.heading == "What you did")
        #expect(did.headers == ["purpose", "sessions", "tokens", "active h"])
        #expect(did.hasTable)
        #expect(did.rows.last?.first == "all purposes")
        #expect(did.rows.allSatisfy { $0.count == did.headers.count })
        #expect(did.notes.count == 3)
        #expect(did.empty == nil)
        // The whole-range figures the Review screen shows as cards.
        #expect(did.numbers.contains { $0.key == "did.commits" })
    }

    @Test("A section with nothing to say carries the sentence instead of an empty table")
    func emptySection() throws {
        let became = try #require(try Self.real().section(.became))
        #expect(became.hasTable == false)
        #expect(became.rows.isEmpty)
        #expect(became.empty?.isEmpty == false)
        #expect(became.notes.count == 1, "it still says what it looked at")
    }

    @Test("The comparison keeps its four columns and its signed change cells")
    func compared() throws {
        let compared = try #require(try Self.real().section(.compared))
        #expect(compared.headers == ["figure", "this period", "previous period", "change"])
        #expect(compared.rows.contains { $0.first == "sessions" })
        let sessions = try #require(compared.rows.first { $0.first == "sessions" })
        #expect(sessions[3].hasPrefix("+") || sessions[3].hasPrefix("-"))
    }

    @Test("Every figure on the page is in the numbers list, with its text")
    func numbers() throws {
        let payload = try Self.real()
        #expect(payload.numbers.count == 26)
        let coverage = payload.numbers.first { $0.key == "did.coverage" }
        #expect(coverage?.text.hasSuffix("%") == true)
        #expect(coverage?.coverage != nil)
    }

    @Test("A section kind this build has never heard of is kept, not dropped")
    func unknownKind() throws {
        let json = """
            {"review_version": 9,
             "sections": [
               {"key": "did", "title": "What you did", "headers": ["purpose"],
                "rows": [["development"]], "notes": [], "numbers": [], "empty": null},
               {"key": "mood", "title": "How it felt", "headers": ["week", "mood"],
                "rows": [["2026-09-08", "steady"]], "notes": ["A new section."],
                "numbers": [], "empty": null, "a_field_from_the_future": 7}
             ],
             "numbers": []}
            """
        let payload = try #require(ReviewPayload.decode(json))
        #expect(payload.sections.count == 2)
        let mood = payload.sections[1]
        #expect(mood.kind == .other("mood"))
        #expect(mood.kind.isKnown == false)
        #expect(mood.heading == "How it felt")
        #expect(mood.hasTable, "it is drawn as the table it brought with it")
        // The generic renderer labels each cell with the header that came with it.
        #expect(mood.pairs(of: mood.rows[0]).map(\.0) == ["week", "mood"])
        #expect(mood.pairs(of: ["a", "b", "c"]).map(\.0) == ["week", "mood", "field 3"])
    }

    @Test("A payload missing every optional key still decodes")
    func minimal() throws {
        let payload = try #require(ReviewPayload.decode("{}"))
        #expect(payload.sections.isEmpty)
        #expect(payload.numbers.isEmpty)
        #expect(payload.window == nil)
    }

    @Test("A payload that is not JSON is a missing value, not a crash")
    func unreadable() {
        #expect(ReviewPayload.decode("not json") == nil)
        #expect(LatestReviewModel.firstSectionTitle(of: "not json") == nil)
        #expect(LatestReviewModel.firstSectionTitle(of: "{\"sections\": []}") == nil)
    }

    @Test("The stored review reads back as a whole page, with its segment and its credit")
    func wholeReview() throws {
        let row = try #require(try Fixture.store().latestReview())
        let model = ReviewModel(row: row)
        let newest = try Fixture.count("SELECT MAX(id) FROM review")
        let id = String(newest)
        #expect(model.id == newest)
        #expect(model.scope == (try Fixture.text("SELECT project FROM app_review WHERE id = ?", [id])))
        #expect(model.payloadUnreadable == false)
        // Every section and every figure the row carries, counted by SQL inside the JSON
        // rather than by hand: a decoder that dropped one would be caught.
        #expect(
            model.sections.count
                == (try Fixture.count(
                    "SELECT json_array_length(sections) FROM app_review WHERE id = ?", [id])))
        #expect(
            model.numbers.count
                == (try Fixture.count(
                    "SELECT json_array_length(numbers) FROM app_review WHERE id = ?", [id])))
        let coverage = try #require(
            try Fixture.number("SELECT coverage FROM app_review WHERE id = ?", [id]))
        #expect(model.coverageText == Formatting.percent(coverage))
        // `app_review` carries the range but not the window the payload was built from, so the
        // line is the range and nothing in brackets. A review read from the `review` table
        // would add `(the last 14d)`; no screen in this app reads that table.
        let range = try #require(
            try Fixture.text(
                """
                SELECT 'Range ' || substr(range_start, 1, 10)
                       || ' to ' || substr(range_end, 1, 10) || '.'
                  FROM app_review WHERE id = ?
                """, [id]))
        #expect(model.rangeLine == range)
        let outcomeStart = try #require(
            try Fixture.text(
                "SELECT substr(outcome_range_start, 1, 10) FROM app_review WHERE id = ?", [id]))
        #expect(model.outcomeLine?.contains(outcomeStart) == true)
        let segment = try #require(model.segment)
        #expect(
            segment.credit
                == "Written by \(try #require(try Fixture.text("SELECT segment_model FROM review WHERE id = ?", [id])))"
        )
        #expect(segment.text.isEmpty == false)
    }

    @Test(
        "A review with no segment simply has none; the page is still whole",
        .enabled(
            if: Fixture.has("SELECT COUNT(*) FROM review WHERE segment_text IS NULL"),
            """
            every review in the fixture carries a model segment, so there is no row here that \
            could show one missing. tests/mac_fixture.py would have to insert a second review \
            and not call schema.store_segment on it.
            """)
    )
    func noSegment() throws {
        let rows = try Fixture.store().reviews()
        let without = try #require(rows.first { $0.segmentText == nil })
        #expect(ReviewModel(row: without).segment == nil)
        #expect(ReviewModel(row: without).payloadUnreadable == false, "the page is still whole")
    }
}

// MARK: - the bars

@Suite("Weekly bucketing")
struct WeeklyUsageTests {

    var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    @Test("Every day of a week lands on that week's Monday")
    func mondays() {
        // 2026-09-07 is a Monday; 2026-09-13 is the Sunday that closes the same week.
        for day in ["2026-09-07", "2026-09-08", "2026-09-11", "2026-09-13"] {
            #expect(Formatting.isoWeekStart(of: day, calendar: calendar) == "2026-09-07", "\(day)")
        }
        #expect(Formatting.isoWeekStart(of: "2026-09-14", calendar: calendar) == "2026-09-14")
        #expect(Formatting.isoWeekStart(of: "2026-09-06", calendar: calendar) == "2026-08-31")
    }

    @Test("Tokens are summed into weeks by purpose, biggest purpose first")
    func buckets() {
        let model = WeeklyUsageModel(
            rows: [
                usageRow("2026-09-07", "development", 100),
                usageRow("2026-09-09", "development", 300),
                usageRow("2026-09-09", "research", 50),
                usageRow("2026-09-14", "development", 200),
                usageRow("2026-09-15", "debugging", 700),
            ],
            calendar: calendar
        )
        #expect(model.weeks.map(\.weekStart) == ["2026-09-07", "2026-09-14"])
        #expect(model.weeks[0].total == 450)
        #expect(model.weeks[1].total == 900)
        #expect(model.weeks[0].slices.map(\.purpose) == ["development", "research"])
        #expect(model.weeks[0].slices.map(\.tokens) == [400, 50])
        // The stack order is the same in every week: the biggest purpose over the whole
        // range first, so a bar cannot reorder itself between two weeks.
        #expect(model.purposes == ["debugging", "development", "research"])
        #expect(model.peak == 900)
    }

    @Test("A week with no measured tokens is not a bar, and an empty range is not a chart")
    func emptyWeeks() {
        let model = WeeklyUsageModel(
            rows: [usageRow("2026-09-07", "development", 0)], calendar: calendar)
        #expect(model.isEmpty)
        #expect(WeeklyUsageModel(rows: []).isEmpty)
    }

    @Test("A tie between two purposes breaks on the name, so the order does not flicker")
    func stableOrder() {
        let model = WeeklyUsageModel(
            rows: [
                usageRow("2026-09-07", "research", 100),
                usageRow("2026-09-07", "development", 100),
            ],
            calendar: calendar
        )
        #expect(model.purposes == ["development", "research"])
    }

    /// Every Monday the fixture has tokens on, computed the way `app_outcomes_by_week` does
    /// its own `week_start` rather than the way `Formatting.isoWeekStart` does: two routes to
    /// the same Monday, which is what makes comparing them worth anything.
    static let weeksOfUsage = """
        SELECT DISTINCT date(day, '-' || ((strftime('%w', day) + 6) % 7) || ' days') AS week
          FROM app_usage_by_purpose_day WHERE COALESCE(total_tokens, 0) > 0 ORDER BY week
        """

    @Test("The whole fixture buckets into the weeks the charts draw")
    func fixture() throws {
        let rows = try Fixture.store().usageByPurposeDay(since: "0000-01-01")
        let model = WeeklyUsageModel(rows: rows, calendar: calendar)
        #expect(model.weeks.map(\.weekStart) == (try Fixture.texts(Self.weeksOfUsage)))
        #expect(
            model.weeks.reduce(0) { $0 + $1.total }
                == (try Fixture.count(
                    """
                    SELECT SUM(total_tokens) FROM app_usage_by_purpose_day
                     WHERE COALESCE(total_tokens, 0) > 0
                    """)))
        // Each bar is its own week's tokens, not a running total.
        for week in model.weeks {
            #expect(
                week.total
                    == (try Fixture.count(
                        """
                        SELECT SUM(total_tokens) FROM app_usage_by_purpose_day
                         WHERE date(day, '-' || ((strftime('%w', day) + 6) % 7) || ' days') = ?
                        """, [week.weekStart])), "\(week.weekStart)")
        }
    }

    @Test(
        "Each purpose is its own slice of its own week, and the tallest week is the peak",
        .enabled(
            if: Fixture.has("SELECT COUNT(*) FROM (\(WeeklyUsageTests.weeksOfUsage)) HAVING COUNT(*) >= 3"),
            """
            the fixture has fewer than three weeks of usage rows, so a chart of one bar cannot \
            show that weeks are kept apart or that the peak is the tallest of several. \
            tests/mac_fixture.py would have to record sessions in at least three separate ISO \
            weeks, with more than one purpose in at least two of them.
            """)
    )
    func severalWeeks() throws {
        let rows = try Fixture.store().usageByPurposeDay(since: "0000-01-01")
        let model = WeeklyUsageModel(rows: rows, calendar: calendar)
        #expect(model.peak == model.weeks.map(\.total).max())
        for week in model.weeks {
            #expect(
                week.slices.count
                    == (try Fixture.count(
                        """
                        SELECT COUNT(DISTINCT purpose) FROM app_usage_by_purpose_day
                         WHERE COALESCE(total_tokens, 0) > 0
                           AND date(day, '-' || ((strftime('%w', day) + 6) % 7) || ' days') = ?
                        """, [week.weekStart])), "\(week.weekStart)")
        }
    }
}

// MARK: - the lines

@Suite("Survival and rework, with the gaps")
struct OutcomeChartTests {

    @Test("A share is the two columns of its own row, and carries the denominator")
    func shares() {
        let row = outcomeRow(
            project: "alpha", week: "2026-09-07", lines: 1000, measured30: 800, alive30: 600,
            reworked: 250)
        let alive = OutcomeMetric.aliveAt30Days.share(of: row)
        #expect(alive?.value == 0.75)
        #expect(alive?.over == 800, "the denominator is measured_30d, not lines")
        let rework = OutcomeMetric.rework.share(of: row)
        #expect(rework?.value == 0.25)
        #expect(rework?.over == 1000, "rework is over every line followed")
    }

    @Test("A week whose 30-day mark has not arrived has no point at all, never a zero")
    func unmeasuredIsNotZero() {
        let waiting = outcomeRow(
            project: "alpha", week: "2026-09-14", lines: 500, measured30: 0, alive30: 0,
            reworked: 10)
        #expect(OutcomeMetric.aliveAt30Days.share(of: waiting) == nil)
        // Rework has nothing to wait for, so that one is still measured.
        #expect(OutcomeMetric.rework.share(of: waiting)?.value == 0.02)

        let nothingFollowed = outcomeRow(
            project: "alpha", week: "2026-09-14", lines: 0, measured30: nil, alive30: nil,
            reworked: nil)
        #expect(OutcomeMetric.rework.share(of: nothingFollowed) == nil)
    }

    @Test("A gap cuts the line into two series, so nothing is drawn across the hole")
    func gapsCutTheLine() {
        let weeks = [
            outcomeRow(project: "a", week: "2026-08-24", lines: 100, measured30: 100, alive30: 80, reworked: 20),
            outcomeRow(project: "a", week: "2026-08-31", lines: 100, measured30: 100, alive30: 70, reworked: 30),
            outcomeRow(project: "a", week: "2026-09-07", lines: 100, measured30: 0, alive30: 0, reworked: 40),
            outcomeRow(project: "a", week: "2026-09-14", lines: 100, measured30: 50, alive30: 45, reworked: 10),
        ]
        let runs = OutcomeChartModel.runs(of: weeks, metric: .aliveAt30Days)
        #expect(runs.count == 2, "one run before the hole, one after")
        #expect(runs[0].map(\.weekStart) == ["2026-08-24", "2026-08-31"])
        #expect(runs[1].map(\.weekStart) == ["2026-09-14"])
        #expect(runs.flatMap { $0 }.allSatisfy { $0.value > 0 })
        // Rework is measured in all four, so that line is unbroken.
        #expect(OutcomeChartModel.runs(of: weeks, metric: .rework).count == 1)
    }

    @Test("Two projects are two sets of lines, each with its own coverage")
    func twoProjects() {
        let model = OutcomeChartModel(rows: [
            outcomeRow(project: "beta", week: "2026-09-07", lines: 10, measured30: 10, alive30: 5, reworked: 2, coverage: 0.7),
            outcomeRow(project: "alpha", week: "2026-09-07", lines: 10, measured30: 10, alive30: 9, reworked: 1, coverage: 0.9),
        ])
        #expect(model.projects == ["alpha", "beta"], "sorted, so the colours are stable")
        #expect(model.series.count == 4, "two metrics for each of two projects")
        #expect(model.bands.map(\.project) == ["alpha", "beta"])
        #expect(model.bands[0].points.first?.value == 0.9)
        #expect(model.weeks == ["2026-09-07"])
        #expect(model.isEmpty == false)
    }

    @Test("A point prints its share with the number it is over")
    func denominatorTravels() {
        let point = OutcomePoint(weekStart: "2026-09-07", value: 0.786, over: 1180, coverage: 0.82)
        #expect(point.withDenominator == "79% of 1180")
    }

    /// The weeks whose 30-day mark has arrived, and the weeks it has not. A chart can only
    /// show a gap when there is a measured week on each side of an unmeasured one.
    static let gapInTheFixture = """
        SELECT COUNT(*) FROM app_outcomes_by_week a
         WHERE COALESCE(a.measured_30d, 0) > 0
           AND EXISTS (SELECT 1 FROM app_outcomes_by_week b
                        WHERE b.project = a.project AND b.week_start > a.week_start
                          AND COALESCE(b.measured_30d, 0) = 0)
           AND EXISTS (SELECT 1 FROM app_outcomes_by_week c
                        WHERE c.project = a.project AND c.week_start > a.week_start
                          AND COALESCE(c.measured_30d, 0) > 0)
        """

    @Test("The fixture draws a point for every week it measured, and none for the rest")
    func fixturePoints() throws {
        let model = OutcomeChartModel(rows: try Fixture.store().outcomesByWeek())
        #expect(model.projects == (try Fixture.texts(
            "SELECT DISTINCT project FROM app_outcomes_by_week ORDER BY project")))
        #expect(model.weeks == (try Fixture.texts(
            "SELECT DISTINCT week_start FROM app_outcomes_by_week ORDER BY week_start")))
        for project in model.projects {
            let alive = try #require(
                model.series.first { $0.project == project && $0.metric == .aliveAt30Days })
            #expect(
                alive.points.map(\.weekStart)
                    == (try Fixture.texts(
                        """
                        SELECT week_start FROM app_outcomes_by_week
                         WHERE project = ? AND COALESCE(measured_30d, 0) > 0
                         ORDER BY week_start
                        """, [project])), "\(project)")
            // Rework has nothing to wait for: every week with lines followed has a point.
            let rework = try #require(
                model.series.first { $0.project == project && $0.metric == .rework })
            #expect(
                rework.points.map(\.weekStart)
                    == (try Fixture.texts(
                        """
                        SELECT week_start FROM app_outcomes_by_week
                         WHERE project = ? AND COALESCE(lines, 0) > 0 AND reworked IS NOT NULL
                         ORDER BY week_start
                        """, [project])), "\(project)")
        }
    }

    @Test(
        "The fixture's survival line is cut where its 30-day mark has not arrived",
        .enabled(
            if: Fixture.has(OutcomeChartTests.gapInTheFixture),
            """
            no project in the fixture has a measured week, then an unmeasured one, then another \
            measured one, so there is no hole for the chart to leave open. tests/mac_fixture.py \
            would have to record commits in at least three ISO weeks and follow the lines of the \
            first and the last far enough for their 30-day mark to arrive, leaving the middle \
            week at measured_30d = 0.
            """)
    )
    func fixtureGap() throws {
        let model = OutcomeChartModel(rows: try Fixture.store().outcomesByWeek())
        let project = try #require(
            try Fixture.text(
                """
                SELECT a.project FROM app_outcomes_by_week a
                 WHERE COALESCE(a.measured_30d, 0) > 0
                   AND EXISTS (SELECT 1 FROM app_outcomes_by_week b
                                WHERE b.project = a.project AND b.week_start > a.week_start
                                  AND COALESCE(b.measured_30d, 0) = 0)
                   AND EXISTS (SELECT 1 FROM app_outcomes_by_week c
                                WHERE c.project = a.project AND c.week_start > a.week_start
                                  AND COALESCE(c.measured_30d, 0) > 0)
                 LIMIT 1
                """))
        let alive = try #require(
            model.series.first { $0.project == project && $0.metric == .aliveAt30Days })
        #expect(alive.gaps >= 1, "the hole is not drawn across")
        #expect(alive.segments.allSatisfy { !$0.isEmpty })
        #expect(
            alive.points.map(\.weekStart)
                == (try Fixture.texts(
                    """
                    SELECT week_start FROM app_outcomes_by_week
                     WHERE project = ? AND COALESCE(measured_30d, 0) > 0 ORDER BY week_start
                    """, [project])))
    }

    @Test("Nothing measured anywhere is an empty chart, not a chart of zeroes")
    func nothingMeasured() {
        let model = OutcomeChartModel(rows: [
            outcomeRow(project: "a", week: "2026-09-07", lines: 0, measured30: 0, alive30: 0, reworked: 0)
        ])
        #expect(model.isEmpty)
    }
}

// MARK: - the pickers

@Suite("The project and range pickers")
struct FilterTests {

    var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    @Test("The project list is the distinct projects of the session list, in order")
    func distinctProjects() {
        let rows = [
            sessionRow("1", project: "beta", startedAt: "2026-09-01T09:00:00"),
            sessionRow("2", project: "alpha", startedAt: "2026-09-02T09:00:00"),
            sessionRow("3", project: "beta", startedAt: "2026-09-03T09:00:00"),
            sessionRow("4", project: "alpha", startedAt: nil),
        ]
        #expect(ProjectFilter.projects(in: rows) == ["alpha", "beta"])
        #expect(ProjectFilter.projects(in: []) == [])
    }

    @Test("The fixture's picker offers every project it has a session for")
    func fixtureProjects() throws {
        let rows = try Fixture.store().sessions()
        #expect(
            ProjectFilter.projects(in: rows)
                == (try Fixture.texts(
                    """
                    SELECT DISTINCT project FROM app_session_list
                     WHERE project <> '' ORDER BY project
                    """)))
    }

    @Test("Eight weeks is the default, and every range knows its first day")
    func ranges() throws {
        let now = try #require(Formatting.timestamp("2026-09-15T12:00:00"))
        #expect(ChartRange.allCases.map(\.label) == ["8 weeks", "90 days", "All"])
        #expect(ChartRange.eightWeeks.firstDay(now: now, calendar: utc) == "2026-07-22")
        #expect(ChartRange.ninetyDays.firstDay(now: now, calendar: utc) == "2026-06-18")
        #expect(ChartRange.all.firstDay(now: now, calendar: utc) == nil)
        #expect(ChartRange.all.describe(now: now, calendar: utc) == "every day on record")
    }

    @Test("A range keeps the weeks its first day falls in, so bars and lines end together")
    func filterKeepsTheWholeWeek() throws {
        let now = try #require(Formatting.timestamp("2026-09-15T12:00:00"))
        let filter = WindowFilter(project: nil, range: .eightWeeks, now: now, calendar: utc)
        #expect(filter.firstDay == "2026-07-22")
        #expect(filter.firstWeek == "2026-07-20", "the Monday of the week the range opens in")
    }

    /// Noon on the fixture's last day of usage, whichever day that turns out to be, so a
    /// regenerated store moves these tests with it instead of emptying them.
    static func noon() throws -> Date {
        let day = try #require(try Fixture.text("SELECT MAX(day) FROM app_usage_by_purpose_day"))
        return try #require(Formatting.timestamp("\(day)T12:00:00"))
    }

    @Test("Choosing a project keeps that project's rows in every view at once, and nothing else")
    func projectFilter() throws {
        let store = try Fixture.store()
        let data = try WindowData.read(from: store)
        let now = try Self.noon()
        let all = WindowFilter(project: nil, range: .all, now: now, calendar: utc).apply(to: data)
        #expect(all.sessions.count == (try Fixture.count("SELECT COUNT(*) FROM app_session_list")))

        let name = try #require(ProjectFilter.projects(in: data.sessions).first)
        let one = WindowFilter(project: name, range: .all, now: now, calendar: utc).apply(to: data)
        #expect(
            one.sessions.count
                == (try Fixture.count(
                    "SELECT COUNT(*) FROM app_session_list WHERE project = ?", [name])))
        #expect(
            one.usage.count
                == (try Fixture.count(
                    "SELECT COUNT(*) FROM app_usage_by_purpose_day WHERE project = ?", [name])))
        #expect(
            one.outcomes.count
                == (try Fixture.count(
                    "SELECT COUNT(*) FROM app_outcomes_by_week WHERE project = ?", [name])))
        #expect(
            one.commits.count
                == (try Fixture.count(
                    "SELECT COUNT(*) FROM app_commits_by_day WHERE project = ?", [name])))
        #expect(one.sessions.allSatisfy { $0.project == name })
        // The reviews are documents with their own scope printed on them, so the project
        // picker does not hide any of them.
        #expect(one.reviews.count == all.reviews.count)
    }

    @Test(
        "A project the picker did not choose is left out",
        .enabled(
            if: Fixture.has(
                "SELECT COUNT(DISTINCT project) FROM app_session_list HAVING COUNT(DISTINCT project) >= 2"
            ),
            """
            the fixture has sessions in one project only, so choosing it cannot drop anything \
            and the filter would pass whatever it did. tests/mac_fixture.py would have to \
            record sessions against a second repository, with usage, a commit and an \
            observation of its own.
            """)
    )
    func projectFilterExcludes() throws {
        let data = try WindowData.read(from: Fixture.store())
        let now = try Self.noon()
        let names = ProjectFilter.projects(in: data.sessions)
        let first = try #require(names.first)
        let one = WindowFilter(project: first, range: .all, now: now, calendar: utc).apply(to: data)
        let all = WindowFilter(project: nil, range: .all, now: now, calendar: utc).apply(to: data)
        #expect(one.sessions.count < all.sessions.count)
        #expect(one.sessions.allSatisfy { $0.project == first })
    }

    @Test("The cards are sums of view columns and nothing else")
    func cards() throws {
        let store = try Fixture.store()
        let data = try WindowData.read(from: store)
        let now = try Self.noon()
        let filter = WindowFilter(project: nil, range: .eightWeeks, now: now, calendar: utc)
        let rows = filter.apply(to: data)
        let cards = SummaryCards(
            sessions: rows.sessions, usage: rows.usage, commits: rows.commits)
        // The same range, stated once in SQL: the day-grained views from the first day of it,
        // the session list from the same day, both as the filter cut them.
        let firstDay = try #require(filter.firstDay)

        #expect(
            cards.sessions
                == (try Fixture.count(
                    """
                    SELECT COUNT(*) FROM app_session_list
                     WHERE started_at IS NOT NULL AND date(started_at, 'localtime') >= ?
                    """, [firstDay])))
        #expect(
            cards.commits
                == (try Fixture.count(
                    "SELECT SUM(commits) FROM app_commits_by_day WHERE day >= ?", [firstDay])))
        #expect(cards.commits == cards.commitsFact + cards.commitsInferred)
        // The split is the two columns beside it, never `uncertain` folded in.
        #expect(
            cards.methodText
                == (try #require(
                    try Fixture.text(
                        """
                        SELECT SUM(commits_fact) || ' fact, ' || SUM(commits_inferred) || ' inferred'
                          FROM app_commits_by_day WHERE day >= ?
                        """, [firstDay]))))
        // Active hours are minutes summed off the usage view and divided by sixty, which is
        // the one division the card does. The sum is checked before the rounding, because a
        // figure printed to one decimal hides a wrong minute inside a tenth of an hour.
        let minutes = try #require(
            try Fixture.number(
                "SELECT SUM(active_minutes) FROM app_usage_by_purpose_day WHERE day >= ?",
                [firstDay]))
        #expect(abs(cards.activeMinutes - minutes) < 0.000_001)
        #expect(cards.activeHoursText == String(format: "%.1f", minutes / 60))
        #expect(
            cards.edits
                == (try Fixture.count(
                    """
                    SELECT SUM(edits) FROM app_session_list
                     WHERE started_at IS NOT NULL AND date(started_at, 'localtime') >= ?
                    """, [firstDay])))
    }

    @Test("A range with nothing in it is empty, not zero")
    func emptyRange() throws {
        let data = try WindowData.read(from: Fixture.store())
        let future = try #require(Formatting.timestamp("2027-06-01T12:00:00"))
        let rows = WindowFilter(project: nil, range: .eightWeeks, now: future, calendar: utc)
            .apply(to: data)
        #expect(rows.sessions.isEmpty)
        #expect(WeeklyUsageModel(rows: rows.usage).isEmpty)
        #expect(OutcomeChartModel(rows: rows.outcomes).isEmpty)
    }
}
