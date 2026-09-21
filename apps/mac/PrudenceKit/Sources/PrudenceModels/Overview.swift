import Foundation
import PrudenceStore

/// What the Overview draws, and the only arithmetic the app is allowed to do to get there.
///
/// Rule 8 draws the line and it is narrow on purpose: a screen may **sum** view columns into
/// a bucket and take the **ratio** of two view columns. It may not compute a fact. So the
/// weekly bars are sums of `total_tokens`, the survival line is `alive_30d / measured_30d`
/// and the rework line is `reworked / lines` — each a ratio of two columns of the same row of
/// `app_outcomes_by_week` — and every one of them carries its denominator, because a share
/// without the number it is over is the thing principle 3 forbids.
///
/// Nothing here has an opinion about colour or shape; that is the view's job. These are
/// values, so a test can build one by hand and the render harness can draw a screen without
/// a database.

// MARK: - the range picker

/// How far back the Overview looks. Eight weeks is the accepted default (M3 plan, open
/// question 6); the other two are the ones the founder asked to be able to pick.
public enum ChartRange: String, CaseIterable, Identifiable, Sendable {
    case eightWeeks
    case ninetyDays
    case all

    public var id: String { rawValue }

    public var label: String {
        switch self {
        case .eightWeeks: return "8 weeks"
        case .ninetyDays: return "90 days"
        case .all: return "All"
        }
    }

    public var days: Int? {
        switch self {
        case .eightWeeks: return 56
        case .ninetyDays: return 90
        case .all: return nil
        }
    }

    /// The first local day in the range, `yyyy-MM-dd`, or nil for all of it.
    public func firstDay(now: Date, calendar: Calendar = .current) -> String? {
        guard let days else { return nil }
        guard let start = calendar.date(byAdding: .day, value: -(days - 1), to: now) else {
            return nil
        }
        return Formatting.day(start, calendar: calendar)
    }

    /// `since 2026-07-27`, for the line under the cards.
    public func describe(now: Date, calendar: Calendar = .current) -> String {
        guard let first = firstDay(now: now, calendar: calendar) else {
            return "every day on record"
        }
        return "since \(first)"
    }
}

// MARK: - the project picker

public enum ProjectFilter {

    public static let allProjectsLabel = "All projects"

    /// The distinct project names in the session list, in alphabetical order.
    ///
    /// The picker is built from `app_session_list` rather than from the repository table
    /// because a project with no session is a project the person cannot be shown anything
    /// about, and an entry that answers with an empty screen is worse than no entry.
    public static func projects(in rows: [AppSessionListRow]) -> [String] {
        var seen = Set<String>()
        var names: [String] = []
        for row in rows where !row.project.isEmpty {
            if seen.insert(row.project).inserted { names.append(row.project) }
        }
        return names.sorted()
    }
}

// MARK: - the stacked bars

/// One week of tokens, split by purpose.
public struct UsageWeek: Equatable, Sendable, Identifiable {
    /// The Monday the week starts on, `yyyy-MM-dd`. Also the bar's label and its identity.
    public let weekStart: String
    public let slices: [Slice]

    public var id: String { weekStart }
    public var total: Int { slices.reduce(0) { $0 + $1.tokens } }

    public struct Slice: Equatable, Sendable, Identifiable {
        public let purpose: String
        public let tokens: Int
        public var id: String { purpose }

        public init(purpose: String, tokens: Int) {
            self.purpose = purpose
            self.tokens = tokens
        }
    }

    public init(weekStart: String, slices: [Slice]) {
        self.weekStart = weekStart
        self.slices = slices
    }

    /// `8 Sep`, the short label under a bar.
    public var label: String { Formatting.shortDay(weekStart) }
}

/// The stacked bar chart: `app_usage_by_purpose_day`, summed into ISO weeks by purpose.
public struct WeeklyUsageModel: Equatable, Sendable {
    public let weeks: [UsageWeek]
    /// Every purpose that appears anywhere in the range, so the colour scale and the legend
    /// stay the same as the reader moves between projects.
    public let purposes: [String]

    public init(weeks: [UsageWeek], purposes: [String]) {
        self.weeks = weeks
        self.purposes = purposes
    }

    public var isEmpty: Bool { weeks.isEmpty }

    /// The tallest bar, which the y axis is scaled to.
    public var peak: Int { weeks.map(\.total).max() ?? 0 }

    public init(rows: [AppUsageByPurposeDayRow], calendar: Calendar = .current) {
        var buckets: [String: [String: Int]] = [:]
        var purposeTotals: [String: Int] = [:]
        for row in rows {
            let tokens = row.totalTokens ?? 0
            guard tokens > 0 else { continue }
            let week = Formatting.isoWeekStart(of: row.day, calendar: calendar) ?? row.day
            buckets[week, default: [:]][row.purpose, default: 0] += tokens
            purposeTotals[row.purpose, default: 0] += tokens
        }
        // Biggest purpose first, ties on the name, so the stack order and the legend never
        // flicker between two refreshes of the same data.
        let order = purposeTotals.sorted {
            $0.value == $1.value ? $0.key < $1.key : $0.value > $1.value
        }.map(\.key)
        let weeks = buckets.keys.sorted().map { week -> UsageWeek in
            let slices = order.compactMap { purpose -> UsageWeek.Slice? in
                guard let tokens = buckets[week]?[purpose], tokens > 0 else { return nil }
                return UsageWeek.Slice(purpose: purpose, tokens: tokens)
            }
            return UsageWeek(weekStart: week, slices: slices)
        }
        self.init(weeks: weeks, purposes: order)
    }
}

// MARK: - the outcome lines

/// Which line is being drawn. Both are ratios of two columns of the same row, and both print
/// their denominator.
public enum OutcomeMetric: String, CaseIterable, Sendable, Identifiable {
    case aliveAt30Days
    case rework

    public var id: String { rawValue }

    public var label: String {
        switch self {
        case .aliveAt30Days: return "alive at 30 days"
        case .rework: return "reworked later"
        }
    }

    /// The numerator and denominator on one week's row, or nil when the week has nothing to
    /// say. `measured_30d = 0` means the mark has not arrived, which is a gap in the line and
    /// never a zero: a line that fell to the floor would read as work that died.
    public func share(of row: AppOutcomesByWeekRow) -> (value: Double, over: Int)? {
        switch self {
        case .aliveAt30Days:
            guard let measured = row.measured30d, measured > 0, let alive = row.alive30d else {
                return nil
            }
            return (Double(alive) / Double(measured), measured)
        case .rework:
            guard let lines = row.lines, lines > 0, let reworked = row.reworked else { return nil }
            return (Double(reworked) / Double(lines), lines)
        }
    }
}

/// One week of one project's outcomes: the share, what it is over, and the coverage behind it.
public struct OutcomePoint: Equatable, Sendable, Identifiable {
    public let weekStart: String
    public let value: Double
    public let over: Int
    public let coverage: Double?

    public var id: String { weekStart }

    public init(weekStart: String, value: Double, over: Int, coverage: Double?) {
        self.weekStart = weekStart
        self.value = value
        self.over = over
        self.coverage = coverage
    }

    public var label: String { Formatting.shortDay(weekStart) }

    /// `79% of 1180 lines`, which is the tooltip principle 3 asks for: never a share alone.
    public var withDenominator: String {
        "\(Formatting.percent(value)) of \(over)"
    }
}

/// One project's one metric, already cut into the runs the chart may join with a line.
///
/// Swift Charts joins consecutive marks of the same series, so a week with nothing measured
/// cannot simply be left out: the line would be drawn straight across it as though the
/// measurement existed. Each run of consecutive measured weeks is therefore its own series,
/// and the gap between two runs is a gap on the screen.
public struct OutcomeSeries: Equatable, Sendable, Identifiable {
    public let project: String
    public let metric: OutcomeMetric
    public let segments: [[OutcomePoint]]

    public var id: String { "\(project)|\(metric.rawValue)" }

    public init(project: String, metric: OutcomeMetric, segments: [[OutcomePoint]]) {
        self.project = project
        self.metric = metric
        self.segments = segments
    }

    public var points: [OutcomePoint] { segments.flatMap { $0 } }
    public var isEmpty: Bool { points.isEmpty }
    public var gaps: Int { max(0, segments.count - 1) }
}

/// One project's coverage by week, drawn under the lines as a translucent band.
public struct CoverageBand: Equatable, Sendable, Identifiable {
    public let project: String
    public let points: [OutcomePoint]
    public var id: String { project }

    public init(project: String, points: [OutcomePoint]) {
        self.project = project
        self.points = points
    }
}

public struct OutcomeChartModel: Equatable, Sendable {
    public let series: [OutcomeSeries]
    public let bands: [CoverageBand]
    public let projects: [String]
    /// Every week that has a row, measured or not, so the axis spans the whole range rather
    /// than only the weeks that happen to have a number.
    public let weeks: [String]

    public init(
        series: [OutcomeSeries], bands: [CoverageBand], projects: [String], weeks: [String]
    ) {
        self.series = series
        self.bands = bands
        self.projects = projects
        self.weeks = weeks
    }

    public var isEmpty: Bool { series.allSatisfy(\.isEmpty) }

    public init(rows: [AppOutcomesByWeekRow]) {
        let byProject = Dictionary(grouping: rows, by: \.project)
        let projects = byProject.keys.sorted()
        var series: [OutcomeSeries] = []
        var bands: [CoverageBand] = []
        for project in projects {
            let weeks = (byProject[project] ?? []).sorted { $0.weekStart < $1.weekStart }
            for metric in OutcomeMetric.allCases {
                series.append(
                    OutcomeSeries(
                        project: project,
                        metric: metric,
                        segments: Self.runs(of: weeks, metric: metric)
                    )
                )
            }
            bands.append(
                CoverageBand(
                    project: project,
                    points: weeks.compactMap { row in
                        row.coverage.map {
                            OutcomePoint(
                                weekStart: row.weekStart, value: $0, over: row.commits,
                                coverage: $0)
                        }
                    }
                )
            )
        }
        self.init(
            series: series,
            bands: bands,
            projects: projects,
            weeks: Set(rows.map(\.weekStart)).sorted()
        )
    }

    /// Consecutive measured weeks, each run on its own. An unmeasured week ends a run.
    static func runs(
        of weeks: [AppOutcomesByWeekRow], metric: OutcomeMetric
    ) -> [[OutcomePoint]] {
        var runs: [[OutcomePoint]] = []
        var current: [OutcomePoint] = []
        for row in weeks {
            guard let share = metric.share(of: row) else {
                if !current.isEmpty { runs.append(current) }
                current = []
                continue
            }
            current.append(
                OutcomePoint(
                    weekStart: row.weekStart, value: share.value, over: share.over,
                    coverage: row.coverage)
            )
        }
        if !current.isEmpty { runs.append(current) }
        return runs
    }
}

// MARK: - the three cards

/// Sessions, active hours and commits in the range. Three sums of view columns, no more.
public struct SummaryCards: Equatable, Sendable {
    public let sessions: Int
    public let activeMinutes: Double
    public let commits: Int
    public let commitsFact: Int
    public let commitsInferred: Int
    public let edits: Int?

    public init(
        sessions: Int, activeMinutes: Double, commits: Int, commitsFact: Int,
        commitsInferred: Int, edits: Int? = nil
    ) {
        self.sessions = sessions
        self.activeMinutes = activeMinutes
        self.commits = commits
        self.commitsFact = commitsFact
        self.commitsInferred = commitsInferred
        self.edits = edits
    }

    public init(
        sessions rows: [AppSessionListRow],
        usage: [AppUsageByPurposeDayRow],
        commits commitRows: [AppCommitsByDayRow]
    ) {
        let measuredEdits = rows.compactMap(\.edits)
        self.init(
            sessions: rows.count,
            activeMinutes: usage.reduce(0) { $0 + ($1.activeMinutes ?? 0) },
            commits: commitRows.reduce(0) { $0 + $1.commits },
            commitsFact: commitRows.reduce(0) { $0 + $1.commitsFact },
            commitsInferred: commitRows.reduce(0) { $0 + $1.commitsInferred },
            edits: measuredEdits.isEmpty ? nil : measuredEdits.reduce(0, +)
        )
    }

    /// `41.5`, hours to one decimal, the way `prudence usage` prints them.
    public var activeHoursText: String { String(format: "%.1f", activeMinutes / 60) }

    /// `13 fact, 5 inferred`, the split that never folds `uncertain` in.
    public var methodText: String { "\(commitsFact) fact, \(commitsInferred) inferred" }
}
