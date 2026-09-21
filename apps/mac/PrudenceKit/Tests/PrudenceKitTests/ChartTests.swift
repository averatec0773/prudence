import Foundation
import SwiftUI
import Testing

@testable import PrudenceEngine
@testable import PrudenceModels
@testable import PrudenceStore
@testable import PrudenceUI

/// The seven chart components, and the three things about them that a screenshot cannot show:
/// what order the marks are in, where a line is allowed to break, and which bucket a row landed
/// in. A chart whose colours moved between two runs, or whose line was drawn straight across a
/// month nobody measured, looks perfectly fine in a PNG.
///
/// Each one is checked against the fixture wherever the fixture can mean anything, and against
/// a handful of rows built by hand where the question is about a shape rather than about data.

// MARK: - ordering

@Suite("Ordering: the same colour in the same place, whatever arrives first")
struct ChartOrderTests {

    /// The stacked bars put the slices into `Purpose.order` however they arrived, and a slice
    /// of nothing is not drawn at all.
    @Test func stackedBarsUseTheFixedOrderAndDropTheEmptySlices() {
        let column = StackedBarsChart.Column(
            key: "2026-09-07",
            label: "7 Sep",
            slices: [
                .init(purpose: "mixed", value: 10),
                .init(purpose: "development", value: 30),
                .init(purpose: "research", value: 0),
                .init(purpose: "debugging", value: 5),
            ]
        )
        #expect(column.slices.map(\.purpose) == ["development", "debugging", "mixed"])
        #expect(column.total == 45)
    }

    /// A purpose this build has never heard of is drawn after the known ones rather than
    /// dropped, which is the rule `Purpose.scale` sets for every chart in the app.
    @Test func anUnknownPurposeKeepsItsSliceAtTheEnd() {
        let column = StackedBarsChart.Column(
            key: "w", label: "w",
            slices: [.init(purpose: "quantum-tunnelling", value: 4), .init(purpose: "mixed", value: 1)]
        )
        #expect(column.slices.map(\.purpose) == ["mixed", "quantum-tunnelling"])
    }

    /// The donut uses the same order and computes a share over its own total, never over a
    /// number from somewhere else.
    @Test @MainActor func theDonutOrdersItsSlicesAndSharesOverItsOwnTotal() {
        let donut = DonutChart(
            slices: [
                .init(purpose: "debugging", value: 25),
                .init(purpose: "development", value: 75),
                .init(purpose: "conversation", value: 0),
            ],
            centreValue: "10", centreLabel: "sessions", valueText: { "\(Int($0))" }
        )
        #expect(donut.slices.map(\.purpose) == ["development", "debugging"])
        #expect(donut.total == 100)
        #expect(donut.share(of: donut.slices[0]) == 0.75)
    }

    /// Nothing measured is not a division by zero.
    @Test @MainActor func aDonutOverNothingHasNoShares() {
        let donut = DonutChart(
            slices: [.init(purpose: "development", value: 0)],
            centreValue: "0", centreLabel: "sessions", valueText: { "\(Int($0))" }
        )
        #expect(donut.slices.isEmpty)
        #expect(donut.total == 0)
    }

    /// The fixture's own purposes, bucketed into weeks by the model and then handed to the
    /// chart, come out in the fixed order in every single week.
    @Test func everyWeekOfTheFixtureIsInTheFixedOrder() throws {
        let rows = try Fixture.store().usageByPurposeDay(since: "0000-01-01")
        let weeks = WeeklyUsageModel(rows: rows).weeks
        try #require(!weeks.isEmpty)
        for week in weeks {
            let column = StackedBarsChart.Column(
                key: week.weekStart,
                label: week.label,
                slices: week.slices.map { .init(purpose: $0.purpose, value: $0.tokens) }
            )
            #expect(
                column.slices.map(\.purpose) == Purpose.ordered(column.slices.map(\.purpose)),
                "the week of \(week.weekStart) is not in the fixed purpose order")
            #expect(column.total == week.total)
        }
    }
}

// MARK: - gaps

@Suite("Gap handling: a hole is a hole, never a zero")
struct ChartGapTests {

    private func points(_ values: [Double?]) -> [LinesWithGaps.Point] {
        values.enumerated().map { LinesWithGaps.Point(label: "w\($0.offset)", value: $0.element) }
    }

    @Test func aNilCutsTheLineIntoTwoRuns() {
        let runs = LinesWithGaps.runs(of: points([0.7, 0.6, nil, 0.5, 0.4]))
        #expect(runs.count == 2)
        #expect(runs[0].map(\.label) == ["w0", "w1"])
        #expect(runs[1].map(\.label) == ["w3", "w4"])
        #expect(LinesWithGaps.gaps(in: points([0.7, 0.6, nil, 0.5, 0.4])) == 1)
    }

    @Test func leadingAndTrailingHolesAreNotRuns() {
        #expect(LinesWithGaps.runs(of: points([nil, nil, 0.5, nil])).count == 1)
        #expect(LinesWithGaps.gaps(in: points([nil, nil, 0.5, nil])) == 0)
    }

    @Test func nothingMeasuredIsNoRunsAtAll() {
        #expect(LinesWithGaps.runs(of: points([nil, nil])).isEmpty)
        #expect(LinesWithGaps.gaps(in: points([nil, nil])) == 0)
    }

    @Test func oneMeasuredWeekBetweenTwoHolesIsItsOwnRun() {
        let runs = LinesWithGaps.runs(of: points([nil, 0.42, nil]))
        #expect(runs.count == 1)
        #expect(runs[0].count == 1)
    }

    /// The fixture's own outcome rows, cut the way the screen cuts them: the runs the chart
    /// draws must add up to exactly the weeks the store measured, and no more.
    @Test func theFixturesLinesBreakAtEveryWeekItDidNotMeasure() throws {
        let rows = try Fixture.store().outcomesByWeek()
        let model = OutcomeChartModel(rows: rows)
        try #require(!model.weeks.isEmpty)
        for series in model.series {
            let measured = Set(series.points.map(\.weekStart))
            let points = model.weeks.map { week in
                LinesWithGaps.Point(label: week, value: measured.contains(week) ? 1 : nil)
            }
            let drawn = LinesWithGaps.runs(of: points).flatMap { $0 }.map(\.label)
            #expect(
                Set(drawn) == measured,
                "\(series.id) would draw \(drawn.count) points over \(measured.count) measured weeks"
            )
            // The model's own count of holes and the chart's must agree, or one of the two is
            // drawing through something the other left out.
            #expect(LinesWithGaps.gaps(in: points) == series.gaps, "\(series.id)")
        }
    }
}

// MARK: - bucketing

@Suite("Bucketing: every day in the right cell")
struct ChartBucketTests {

    /// Seven days a week, Monday first, and every week between the first and the last present
    /// whether or not anything happened in it.
    @Test func daysLandOnTheirWeekdayAndTheWeeksAreContiguous() throws {
        let rows = try Fixture.store().usageByPurposeDay(since: "0000-01-01")
        let heat = ActiveHoursHeat(rows: rows)
        try #require(!heat.weeks.isEmpty)
        var calendar = Calendar(identifier: .iso8601)
        calendar.timeZone = Calendar.current.timeZone
        for week in heat.weeks {
            #expect(week.days.count == 7, "the week of \(week.weekStart) is not seven days")
            for (index, day) in week.days.enumerated() {
                #expect(
                    Formatting.isoWeekStart(of: day.day) == week.weekStart,
                    "\(day.day) is in the wrong week")
                let date = try #require(Formatting.date(day.day))
                // 1 = Sunday, so Monday is 2 and index 0; Sunday is 1 and index 6.
                let weekday = calendar.component(.weekday, from: date)
                #expect((weekday + 5) % 7 == index, "\(day.day) is on the wrong row")
            }
        }
        for (previous, next) in zip(heat.weeks, heat.weeks.dropFirst()) {
            let expected = Formatting.date(previous.weekStart).map {
                Formatting.day(calendar.date(byAdding: .day, value: 7, to: $0) ?? $0)
            }
            #expect(next.weekStart == expected, "a week is missing after \(previous.weekStart)")
        }
    }

    /// The minutes in the cells are the minutes in the view, summed per day and not once more.
    @Test func theCellsAddUpToTheViewsOwnActiveMinutes() throws {
        let rows = try Fixture.store().usageByPurposeDay(since: "0000-01-01")
        let heat = ActiveHoursHeat(rows: rows)
        let fromView = try Fixture.number(
            "SELECT SUM(active_minutes) FROM app_usage_by_purpose_day") ?? 0
        let fromCells = heat.weeks.reduce(0.0) { $0 + $1.minutes }
        #expect(abs(fromCells - fromView) < 0.001)
        #expect(heat.peakMinutes > 0)
    }

    /// A day with no row is nil, not zero: the strip cannot tell "did not work" from "was not
    /// recorded" and does not pretend to.
    @Test func aDayWithNoRowIsMissingRatherThanZero() {
        let heat = ActiveHoursHeat(rows: [])
        #expect(heat.weeks.isEmpty)
        #expect(heat.isEmpty)
    }

    /// One clicked week narrows the cards and nothing else.
    @Test func aWeekSliceKeepsOnlyThatWeeksRows() throws {
        let store = try Fixture.store()
        let data = try WindowData.read(from: store)
        let week = try #require(
            WeeklyUsageModel(rows: data.usage).weeks.first?.weekStart)
        let sliced = WeekSlice.apply(week, to: data)
        #expect(!sliced.usage.isEmpty)
        for row in sliced.usage {
            #expect(Formatting.isoWeekStart(of: row.day) == week)
        }
        for row in sliced.commits {
            #expect(Formatting.isoWeekStart(of: row.day) == week)
        }
        #expect(sliced.outcomes.allSatisfy { $0.weekStart == week })
        // nil is the whole range, untouched.
        #expect(WeekSlice.apply(nil, to: data).usage.count == data.usage.count)
    }
}

// MARK: - the shapes the charts are drawn to

@Suite("Scales, clamps and the gap in points")
struct ChartScaleTests {

    @Test func thePairedBarsScaleStepsRatherThanFittingItself() {
        #expect(PairedBarsChart.niceMaxShare(0.01) == 0.25)
        #expect(PairedBarsChart.niceMaxShare(0.25) == 0.25)
        #expect(PairedBarsChart.niceMaxShare(0.26) == 0.5)
        #expect(PairedBarsChart.niceMaxShare(0.5) == 0.5)
        #expect(PairedBarsChart.niceMaxShare(0.51) == 0.75)
        #expect(PairedBarsChart.niceMaxShare(0.9) == 1)
    }

    /// The gap is taken over the two shares **as printed**, so a reader who subtracts the two
    /// cells on the screen gets the number under them. 0.194 and 0.086 print as 19% and 9%.
    @Test func theGapIsTheDifferenceOfWhatTheReaderCanSee() {
        #expect(PairedBarsChart.gapPoints(0.194, 0.086) == 10)
        #expect(PairedBarsChart.gapPoints(0.086, 0.194) == 10)
        #expect(PairedBarsChart.gapPoints(0.5, 0.5) == 0)
    }

    /// Every row of the fixture agrees with `Fmt.percent`, which is what the bars print.
    @Test func theFixturesGapsMatchTheSharesTheBarsPrint() throws {
        let rows = try Fixture.store().observations()
        try #require(!rows.isEmpty)
        for row in rows {
            let printed = PairedBarsChart.gapPoints(row.withValue, row.withoutValue)
            let with = try #require(Int(Fmt.percent(row.withValue).dropLast()))
            let without = try #require(Int(Fmt.percent(row.withoutValue).dropLast()))
            #expect(printed == abs(with - without), "observation \(row.observationId)")
        }
    }

    @Test func aShareOutsideItsTrackIsClampedAndTheTextIsNot() {
        #expect(ShareWithCoverageBar.clamp(1.4) == 1)
        #expect(ShareWithCoverageBar.clamp(-0.2) == 0)
        #expect(ShareWithCoverageBar.clamp(0.42) == 0.42)
    }

    @Test @MainActor func noCoverageMeansNoUnderlayRatherThanAnUnderlayOfZero() {
        let bar = ShareWithCoverageBar(
            label: "alive at 30 days", value: 0.7, coverage: nil, valueText: "70% (100)",
            tint: Outcome.alive)
        #expect(!bar.hasCoverage)
    }

    /// The compare card's twin bars read the leading figure out of the cell the engine printed,
    /// because `reviews/build._compared` stores those figures as text alone.
    @Test @MainActor func theCompareCardReadsTheEnginesOwnCells() {
        #expect(CompareCard.numeric("12") == 12)
        #expect(CompareCard.numeric("4.3") == 4.3)
        #expect(CompareCard.numeric("71% (1180)") == 71)
        #expect(CompareCard.numeric("43k") == 43_000)
        #expect(CompareCard.numeric("-") == nil)
        #expect(CompareCard.numeric("") == nil)
        #expect(CompareCard.numeric("+2 points") == 2)
    }
}

// MARK: - the project scale

@Suite("The project colour scale")
struct ProjectPaletteTests {

    /// A project's colour is its place in the **sorted** list, so it does not move when the
    /// caller's own ordering changes or when a project drops out of a shorter range.
    @Test @MainActor func aProjectKeepsItsColourWhateverOrderItArrivesIn() {
        let projects = ["beatos", "prudence", "aardvark"]
        for project in projects {
            #expect(
                ProjectPalette.colour(project, in: projects).prudenceHex(dark: false)?.hex
                    == ProjectPalette.colour(project, in: projects.reversed())
                    .prudenceHex(dark: false)?.hex)
        }
        #expect(ProjectPalette.index(of: "aardvark", in: projects) == 0)
        #expect(ProjectPalette.index(of: "prudence", in: projects) == 2)
    }

    /// It is an identity scale, not a verdict and not a purpose: none of its six is a colour
    /// the purpose palette or the outcome pair already means something with.
    @Test @MainActor func noProjectColourIsAPurposeOrAnOutcome() {
        let taken = Set(
            (Purpose.order.map { Purpose.colour($0) } + [Outcome.alive, Outcome.rework])
                .compactMap { $0.prudenceHex(dark: false)?.hex })
        for index in 0..<ProjectPalette.count {
            let hex = ProjectPalette.colour(index: index).prudenceHex(dark: false)?.hex
            #expect(hex != nil)
            #expect(!taken.contains(hex ?? ""), "project colour \(index) is already a meaning")
        }
    }

    /// Past the end of the table the colours repeat rather than crash, and a negative index
    /// cannot happen but is answered anyway.
    @Test @MainActor func thePaletteWrapsRatherThanRunningOut() {
        #expect(
            ProjectPalette.colour(index: ProjectPalette.count).prudenceHex(dark: false)?.hex
                == ProjectPalette.colour(index: 0).prudenceHex(dark: false)?.hex)
        #expect(ProjectPalette.colour(index: -1).prudenceHex(dark: false) != nil)
    }
}

// MARK: - a stored review, read as charts

@Suite("A review's sections, read as the shapes the charts draw")
struct ReviewChartTests {

    private func payload() throws -> ReviewPayload {
        try #require(ReviewPayload.decode(Fixture.reviewSections))
    }

    /// The donut's slices are the purpose rows and **not** the engine's own "all purposes"
    /// total, which is told apart by having no `did.tokens.<label>` number of its own.
    @Test func thePurposeSlicesLeaveOutTheEnginesTotalRow() throws {
        let section = try #require(payload().section(.did))
        let slices = ReviewCharts.purposeSlices(of: section)
        try #require(!slices.isEmpty)
        #expect(slices.count == section.rows.count - 1, "the total row was kept or a row lost")
        #expect(!slices.contains { $0.purpose == "all purposes" })
        for slice in slices {
            let number = section.numbers.first { $0.key == ReviewCharts.tokensKey(slice.purpose) }
            #expect(number?.value == slice.tokens)
            #expect(slice.tokensText == number?.text)
        }
    }

    /// The outcome section's bars are its shares, and its counts are not bars.
    @Test func onlyTheSharesOfTheOutcomeSectionBecomeBars() throws {
        let section = try #require(payload().section(.became))
        let rows = ReviewCharts.shareRows(of: section)
        guard !rows.isEmpty else { return }
        for row in rows {
            #expect(row.label == (section.rows.first { $0.first == row.label }?.first))
            if row.isShare {
                let value = try #require(row.value)
                #expect(value >= 0 && value <= 1)
                #expect(row.valueText.contains("%"))
            }
        }
        // "lines followed" is a count of lines, not a share of them.
        if let lines = rows.first(where: { $0.key.contains("lines_followed") }) {
            #expect(!lines.isShare)
        }
        // Rework is found by the engine's own key, which is stable English, not by a label.
        for row in rows where row.label.contains("rework") {
            #expect(row.isRework)
        }
    }

    /// Each observation's two medians are paired on the engine's key, and each pair keeps the
    /// prose of the row the engine wrote beside it.
    @Test func eachObservationKeepsItsOwnTwoMediansAndItsOwnSentence() throws {
        let section = try #require(payload().section(.observations))
        let pairs = ReviewCharts.observationPairs(of: section)
        guard !pairs.isEmpty else { return }
        #expect(pairs.count == section.rows.count)
        for (index, pair) in pairs.enumerated() {
            #expect(pair.sentence == section.rows[index].first)
            #expect(pair.caveat == section.rows[index][1])
            let with = section.numbers.first {
                $0.key == "observation.\(pair.key)\(ReviewCharts.withSuffix)"
            }
            #expect(with?.value == pair.withValue)
            // The outcome is the last field of `repo_key|fact|outcome`.
            #expect(["rework", "alive_head"].contains(pair.outcome), "\(pair.key)")
        }
    }

    /// The comparison rows are four strings and the engine stores no raw value for them, which
    /// is why the card parses its own bars. If a future engine adds one, this test says so.
    @Test func theComparisonIsFourStringsAndNoStoredValue() throws {
        let section = try #require(payload().section(.compared))
        let rows = ReviewCharts.compareRows(of: section)
        guard !rows.isEmpty else { return }
        #expect(rows.count == section.rows.count)
        for row in rows {
            #expect(!row.change.isEmpty)
        }
        let stored = section.numbers.filter { $0.key.hasPrefix("compared.") && $0.value != nil }
        #expect(
            stored.isEmpty,
            "the engine now stores compared.* values; CompareCard should read them instead of parsing the printed cell"
        )
    }
}

// MARK: - the language flag

@Suite("The CLI's language flag, guarded")
struct EngineLanguageTests {

    /// The probe is one string test over the help text `prudence review --help` prints.
    @Test func theProbeFindsTheFlagInRealHelpText() {
        let modern = """
            Options:
              --force                         Write the review even when the rule says wait.
              --language [system|en|zh-Hans]  Language for the model segment only.
            """
        let older = """
            Options:
              --force   Write the review even when the rule says wait.
              --json    The stored row as JSON, not Markdown.
            """
        #expect(Engine.helpMentionsLanguage(modern))
        #expect(!Engine.helpMentionsLanguage(older))
    }

    /// An engine that has never heard of the flag is not sent it: an unknown option would turn
    /// "write me a review" into an error about a word the user never typed.
    ///
    /// The locator here finds nothing at all, which is the same road a `prudence` too old to
    /// answer `--help` goes down: the probe throws, the answer is false, and the flag is left
    /// off rather than guessed at.
    @Test func noCodeAndNoSupportMeansNoFlag() {
        let engine = Engine(
            locator: EngineLocator(
                probe: FakeFileProbe(executables: []),
                shell: FakeShell(answer: nil),
                environment: [:],
                home: "/nowhere"
            ),
            environment: [:],
            settingsOverride: { nil }
        )
        #expect(engine.languageArguments(nil).isEmpty)
        #expect(engine.languageArguments("").isEmpty)
        // The probe cannot run at all here, so it answers false and the flag is left off.
        #expect(engine.languageArguments("zh-Hans").isEmpty)
        #expect(!engine.supportsLanguage())
    }

    /// The three values the picker offers are the three the CLI accepts, spelled the same way.
    @Test func thePickersValuesAreTheFlagsValues() {
        #expect(Language.allCases.map(\.rawValue) == ["system", "en", "zh-Hans"])
    }

    /// `PrudenceUI` owns the language picker and `PrudenceModels` reads the same key to hand
    /// the CLI a `--language`. They are two constants because the dependency only goes one
    /// way; this is what keeps them one string.
    @Test func theLanguageKeyIsTheSameOnBothSidesOfTheDependency() {
        #expect(AppSettings.Key.language == Localization.languageKey)
    }

    /// An app that has never had a language chosen asks the CLI for `system`, which is the
    /// CLI's own word for "use `model.language` from the config".
    @Test @MainActor func anUnsetLanguageAsksForSystem() {
        let suite = "dev.prudence.test.language.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        let settings = AppSettings(defaults: defaults)
        #expect(settings.storedLanguageCode() == "system")
        Localization.store(.chineseSimplified, in: defaults)
        #expect(settings.storedLanguageCode() == "zh-Hans")
    }
}

// MARK: - the strings the charts brought with them

@Suite("The batch 2 strings")
struct ChartStringTests {

    /// The heat strip's seven rows are seven different words in both languages.
    @Test func everyWeekdayIsItsOwnWord() {
        for language in [Language.english, .chineseSimplified] {
            Localization.withLanguage(language) {
                let names = HeatStrip.weekdayKeys.map { Str.weekday($0) }
                #expect(Set(names).count == 7, "\(language.rawValue): \(names)")
                #expect(!names.contains { $0.isEmpty })
                // A key outside the seven answers with itself rather than with nothing.
                #expect(Str.weekday("caturday") == "caturday")
            }
        }
    }

    /// **The Chinese for `head` is 当前版本, not the English word.** The M4 plan's batch 2
    /// inputs asked for a Chinese term; the card heading and the sentence under it use the
    /// same one, so the two cannot say different things.
    @Test func theChineseSentenceAndTheChineseHeadingAgreeAboutHead() {
        Localization.withLanguage(.chineseSimplified) {
            let heading = ObservationText.outcomeLabel("alive_head")
            #expect(heading.contains("当前版本"))
            #expect(!heading.contains("head"))
            #expect(Str.observationSentenceAlive.text.contains("当前版本"))
            #expect(!Str.observationSentenceAlive.text.contains("head"))
        }
        // The English composer is untouched: it still has to equal the engine's own sentence.
        Localization.withLanguage(.english) {
            #expect(Str.observationSentenceAlive.text.contains("at head"))
        }
    }

    /// Every behaviour the engine can split on has a short name for a bar label, and each one
    /// is really translated.
    @Test func everySplitHasAShortNameInBothLanguages() {
        #expect(
            ObservationText.shortPhrases.map(\.fact) == ObservationText.splitPhrases.map(\.fact))
        for language in [Language.english, .chineseSimplified] {
            Localization.withLanguage(language) {
                for entry in ObservationText.shortPhrases {
                    let text = ObservationText.shortLabel(for: entry.fact)
                    #expect(text != entry.fact, "\(entry.fact) has no short name")
                    #expect(text.count < 30, "\(entry.fact) is too long for a bar label")
                }
            }
        }
        // A behaviour this build has never heard of falls back to the engine's key.
        #expect(ObservationText.shortLabel(for: "moon-phase") == "moon-phase")
    }

    /// Where the store is, in the reader's own language rather than in the enum's English.
    @Test func theStoreSourceIsTranslated() {
        for source in StoreLocation.Source.allCases {
            Localization.withLanguage(.chineseSimplified) {
                let text = Fmt.storeSource(source)
                #expect(!text.isEmpty)
                #expect(text != source.label, "\(source) still prints the English")
            }
            Localization.withLanguage(.english) {
                #expect(!Fmt.storeSource(source).isEmpty)
            }
        }
    }

    /// A stored review's date is written the reader's way, with how long ago it was beside it.
    @Test func aReviewsDateIsLocalisedOnBothHalves() {
        let now = Formatting.timestamp("2026-09-21T09:00:00") ?? Date()
        Localization.withLanguage(.english) {
            let text = ReviewText.written("2026-09-20", now: now)
            #expect(text.contains("Sep"))
            #expect(text.contains("("))
        }
        Localization.withLanguage(.chineseSimplified) {
            let text = ReviewText.written("2026-09-20", now: now)
            #expect(text.contains("9"))
            #expect(!text.contains("Sep"))
        }
    }

    /// A review with no project says so in the reader's language; a named one is a name.
    @Test func theScopeOfAReviewIsTranslatedAndAProjectNameIsNot() {
        Localization.withLanguage(.chineseSimplified) {
            #expect(ReviewText.scope(nil) == Str.reviewScopeEveryProject.text)
            #expect(ReviewText.scope("prudence") == "prudence")
        }
    }

    /// The language a model segment is in, read off the prose, because the store has no column
    /// for it.
    @Test func aSegmentsLanguageIsReadOffItsOwnWords() {
        #expect(ReviewText.segmentLanguage(of: "You worked in bursts this week.") == .english)
        #expect(ReviewText.segmentLanguage(of: "这一周你的工作是分段进行的。") == .chineseSimplified)
        #expect(ReviewText.segmentLanguage(of: "") == .english)
    }
}
