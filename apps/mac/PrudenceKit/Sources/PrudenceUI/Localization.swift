import Foundation
import SwiftUI

/// Every user-facing string in the app, and the one place a locale is decided.
///
/// The strings live in `Resources/Localizable.xcstrings`, a String Catalog with English and
/// Simplified Chinese. SwiftPM compiles it into `en.lproj` and `zh-Hans.lproj` inside this
/// target's resource bundle, which the app, the tests and the render harness all reach the
/// same way through `Bundle.module`.
///
/// Two rules the rest of the app has to keep:
///
/// 1. **A composed sentence is composed in each language, never translated.** An observation
///    is seven numbers and two phrases in a shape; `ObservationText` builds it from the row's
///    own columns in whichever language is in force. The engine's English sentence stays on
///    the row as the thing to check against, and a test asserts the English output equals it
///    word for word. A fixed string that happened to hold the numbers of one row would be a
///    translation of an accident.
/// 2. **Numbers and dates go through `Locale`.** The one exception is the figures inside an
///    observation sentence, which use the engine's own `%.0f%%` and plain integers, because
///    that sentence has to match the CLI's character for character.
public enum Str: String, CaseIterable, Sendable {
    /// `Try again`
    case commonTryAgain = "common.tryAgain"
    /// `Cancel`
    case commonCancel = "common.cancel"
    /// `Choose...`
    case commonChoose = "common.choose"
    /// `Clear`
    case commonClear = "common.clear"
    /// `none`
    case commonNone = "common.none"
    /// `-`
    case commonDash = "common.dash"
    /// `Dismiss`
    case commonDismiss = "common.dismiss"
    /// `%1$@ (%2$@)` — a date and how long ago it was.
    case commonDateWithRelative = "common.dateWithRelative"
    /// `development`
    case purposeDevelopment = "purpose.development"
    /// `research`
    case purposeResearch = "purpose.research"
    /// `debugging`
    case purposeDebugging = "purpose.debugging"
    /// `conversation`
    case purposeConversation = "purpose.conversation"
    /// `mixed`
    case purposeMixed = "purpose.mixed"
    /// `other`
    case purposeUnknown = "purpose.unknown"
    /// `%1$@ tokens`
    case unitTokens = "unit.tokens"
    /// `%1$@ hours`
    case unitHours = "unit.hours"
    /// `, ` — how a list of phrases is joined in each language.
    case commonListSeparator = "common.listSeparator"
    /// `Today`
    case menuToday = "menu.today"
    /// `This week`
    case menuThisWeek = "menu.thisWeek"
    /// `Latest observation`
    case menuLatestObservation = "menu.latestObservation"
    /// `Last ingest`
    case menuLastIngest = "menu.lastIngest"
    /// `Last review`
    case menuLastReview = "menu.lastReview"
    /// `No session recorded today`
    case menuNoSessionsToday = "menu.noSessionsToday"
    /// `No tokens measured this week`
    case menuNoTokensThisWeek = "menu.noTokensThisWeek"
    /// `No observation yet`
    case menuNoObservation = "menu.noObservation"
    /// `No review yet`
    case menuNoReview = "menu.noReview"
    /// `never`
    case menuNever = "menu.never"
    /// `just now`
    case menuJustNow = "menu.justNow"
    /// `checking...`
    case menuEngineChecking = "menu.engineChecking"
    /// `engine not found`
    case menuEngineMissing = "menu.engineMissing"
    /// `%1$@ (%2$@)`
    case menuStamped = "menu.stamped"
    /// `Open Prudence`
    case menuOpenPrudence = "menu.openPrudence"
    /// `Review now`
    case menuReviewNow = "menu.reviewNow"
    /// `Ingest now`
    case menuIngestNow = "menu.ingestNow"
    /// `Settings...`
    case menuSettings = "menu.settings"
    /// `Quit`
    case menuQuit = "menu.quit"
    /// `Ingesting...`
    case menuIngesting = "menu.ingesting"
    /// `Writing a review...`
    case menuWritingReview = "menu.writingReview"
    /// `Ingest finished.`
    case menuIngestFinished = "menu.ingestFinished"
    /// `Ingest finished: %1$@.`
    case menuIngestFinishedSessions = "menu.ingestFinishedSessions"
    /// `Review written.`
    case menuReviewWritten = "menu.reviewWritten"
    /// `Review %1$@ written.`
    case menuReviewWrittenId = "menu.reviewWrittenId"
    /// `Not enough new work for a review yet.`
    case menuReviewNotReady = "menu.reviewNotReady"
    /// `coverage %1$@, method: %2$@ fact, %3$@ inferred`
    case observationMethodLine = "observation.methodLine"
    /// `Across your projects`
    case observationWherePooled = "observation.where.pooled"
    /// `In %1$@`
    case observationWhereProject = "observation.where.project"
    /// `%1$@, your %2$@ sessions %3$@ reworked %4$@ of their lines (median); the %5$@ %6$@, %7$@.`
    case observationSentenceRework = "observation.sentence.rework"
    /// `%1$@, your %2$@ sessions %3$@ still have %4$@ of their lines at head (median); the %5$@ %6$@, %7$@.`
    case observationSentenceAlive = "observation.sentence.alive"
    /// `that did not`
    case observationDidNot = "observation.didNot"
    /// `that ran over three or more sittings`
    case observationSplitSittings = "observation.split.sittings"
    /// `that edited more files before reading them than your median here`
    case observationSplitFilesEditedUnread = "observation.split.files_edited_unread"
    /// `that ran a formatter`
    case observationSplitFormatterRuns = "observation.split.formatter_runs"
    /// `that ran tests`
    case observationSplitTestRuns = "observation.split.test_runs"
    /// `that ran tests before at least half of their commits`
    case observationSplitTestsBeforeCommit = "observation.split.tests_before_commit"
    /// `that attempted more than two commits for each commit counted`
    case observationSplitCommitAttempts = "observation.split.commit_attempts_per_commit"
    /// `that hit the same error three times or more`
    case observationSplitRepeatedErrors = "observation.split.repeated_errors"
    /// `that dispatched a subagent`
    case observationSplitSubagentUsed = "observation.split.subagent_used"
    /// `that compacted their context`
    case observationSplitCompactions = "observation.split.compactions"
    /// `that replayed an earlier session's records`
    case observationSplitContextResets = "observation.split.context_resets"
    /// `that prompted more often per active hour than your median here`
    case observationSplitPromptsPerHour = "observation.split.prompts_per_active_hour"
    /// `that changed the tree by hand between two turns the hooks saw`
    case observationSplitHandEdits = "observation.split.hand_edits_between_turns"
    /// `labelled %1$@`
    case observationSplitPurpose = "observation.split.purpose"
    /// `labelled otherwise`
    case observationSplitPurposeDidNot = "observation.split.purpose.didNot"
    /// `with %1$@`
    case observationSplitUnknown = "observation.split.unknown"
    /// `without it`
    case observationSplitUnknownDidNot = "observation.split.unknown.didNot"
    /// `%1$@ did, %2$@ did not`
    case observationSessionsDidDidNot = "observation.sessionsDidDidNot"
    /// `across your projects`
    case observationPooledTag = "observation.pooledTag"
    /// `Pooled rows only: ...`
    case observationScopePooled = "observations.scope.pooled"
    /// `Rows computed from this project's own sessions alone.`
    case observationScopeProject = "observations.scope.project"
    /// `An observation splits your own sessions in two at one threshold ...`
    case observationFloor = "observations.floor"
    /// `No pooled observations`
    case observationsEmptyPooledTitle = "observations.empty.pooled.title"
    /// `Nothing yet holds across your projects. ...`
    case observationsEmptyPooledDetail = "observations.empty.pooled.detail"
    /// `No observations for this project`
    case observationsEmptyProjectTitle = "observations.empty.project.title"
    /// `No behaviour here clears both floors: ...`
    case observationsEmptyProjectDetail = "observations.empty.project.detail"
    /// `Review %1$@, %2$@ to %3$@`
    case reviewHeadline = "review.headline"
    /// `Review %1$@, %2$@ to %3$@, %4$@`
    case reviewHeadlineProject = "review.headline.project"
    /// `%1$@: %2$@`
    case reviewHeadlineSection = "review.headline.section"
    /// `Review %1$@ - %2$@`
    case reviewOption = "review.option"
    /// `none stored`
    case reviewNoneStored = "review.noneStored"
    /// `Writing...`
    case reviewWriting = "review.writing"
    /// `No review has been written yet.`
    case reviewNoneYet = "review.subtitle.none"
    /// `%1$@, written %2$@.`
    case reviewScopeWritten = "review.subtitle.scope"
    /// `Overview`
    case sectionOverview = "section.overview"
    /// `Review`
    case sectionReview = "section.review"
    /// `Observations`
    case sectionObservations = "section.observations"
    /// `Settings`
    case sectionSettings = "section.settings"
    /// `All projects`
    case scopeAllProjects = "scope.allProjects"
    /// `Project`
    case scopeProject = "scope.project"
    /// `Range`
    case scopeRange = "scope.range"
    /// `8 weeks`
    case rangeEightWeeks = "range.eightWeeks"
    /// `90 days`
    case rangeNinetyDays = "range.ninetyDays"
    /// `All`
    case rangeAll = "range.all"
    /// `since %1$@`
    case rangeSince = "range.since"
    /// `every day on record`
    case rangeEveryDay = "range.everyDay"
    /// `%1$@, %2$@.`
    case scopeSubtitle = "scope.subtitle"
    /// `Every figure below is for this project alone.`
    case scopeProjectHelp = "scope.project.help"
    /// `How far back the charts look. Eight weeks is the default.`
    case scopeRangeHelp = "scope.range.help"
    /// `Pooled across your projects. Choose a project for its own.`
    case observationsSubtitlePooled = "observations.subtitle.pooled"
    /// `In %1$@.`
    case observationsSubtitleProject = "observations.subtitle.project"
    /// `Sessions in range`
    case overviewSessionsInRange = "overview.sessionsInRange"
    /// `Active hours`
    case overviewActiveHours = "overview.activeHours"
    /// `Commits in range`
    case overviewCommitsInRange = "overview.commitsInRange"
    /// `edits not measured`
    case overviewEditsNotMeasured = "overview.editsNotMeasured"
    /// `sum of each session's sittings`
    case overviewSittingsNote = "overview.sittingsNote"
    /// `%1$@ fact, %2$@ inferred`
    case overviewFactInferred = "overview.factInferred"
    /// `Tokens by purpose, per week`
    case overviewTokensByPurpose = "overview.tokensByPurpose"
    /// `Summed from app_usage_by_purpose_day ...`
    case overviewTokensByPurposeNote = "overview.tokensByPurpose.note"
    /// `What became of each week's work`
    case overviewWhatBecame = "overview.whatBecame"
    /// `alive_30d / measured_30d and reworked / lines ...`
    case overviewWhatBecameNote = "overview.whatBecame.note"
    /// `Week of %1$@`
    case overviewWeekOf = "overview.weekOf"
    /// `all purposes`
    case overviewAllPurposes = "overview.allPurposes"
    /// `solid: alive at 30 days`
    case overviewLegendAlive = "overview.legend.alive"
    /// `dashed: reworked later`
    case overviewLegendRework = "overview.legend.rework"
    /// `pale wide: coverage`
    case overviewLegendCoverage = "overview.legend.coverage"
    /// `No tokens in this range`
    case overviewNoTokensTitle = "overview.noTokens.title"
    /// `Nothing here measured any tokens. ...`
    case overviewNoTokensDetail = "overview.noTokens.detail"
    /// `No outcomes to follow yet`
    case overviewNoOutcomesTitle = "overview.noOutcomes.title"
    /// `No commit in this range is credited with a line ...`
    case overviewNoOutcomesDetail = "overview.noOutcomes.detail"
    /// `Settings`
    case settingsTitle = "settings.title"
    /// `General`
    case settingsGeneral = "settings.general"
    /// `Data`
    case settingsData = "settings.data"
    /// `Prudence engine`
    case settingsEnginePath = "settings.enginePath"
    /// `Looked for in uv's bin directories, then Homebrew, then your login shell.`
    case settingsEnginePathNote = "settings.enginePath.note"
    /// `Overriding the search.`
    case settingsEnginePathOverride = "settings.enginePath.override"
    /// `Database`
    case settingsDatabasePath = "settings.databasePath"
    /// `Reading %1$@ (%2$@).`
    case settingsDatabasePathNote = "settings.databasePath.note"
    /// `found automatically`
    case settingsFoundAutomatically = "settings.foundAutomatically"
    /// `Ingest every 30 minutes`
    case settingsTimedIngest = "settings.timedIngest"
    /// `Runs prudence ingest in the background. ...`
    case settingsTimedIngestNote = "settings.timedIngest.note"
    /// `Open at login`
    case settingsOpenAtLogin = "settings.openAtLogin"
    /// `Language`
    case settingsLanguage = "settings.language"
    /// `System`
    case settingsLanguageSystem = "settings.language.system"
    /// `The app's own strings. ...`
    case settingsLanguageNote = "settings.language.note"
    /// `Takes effect after a relaunch.`
    case settingsLanguageRelaunch = "settings.language.relaunch"
    /// `Relaunch`
    case settingsLanguageRelaunchNow = "settings.language.relaunchNow"
    /// `A per-app language also lives in System Settings > General > Language & Region.`
    case settingsLanguageSystemSettings = "settings.language.systemSettings"
    /// `Store`
    case settingsStore = "settings.store"
    /// `engine %1$@ · app contract %2$@ · %3$@ · %4$@`
    case settingsStoreLine = "settings.store.line"
    /// `not read yet`
    case settingsStoreUnread = "settings.store.unread"
    /// `Allow Prudence in System Settings > General > Login Items.`
    case loginRequiresApproval = "login.requiresApproval"
    /// `Only a copy in /Applications can register itself as a login item.`
    case loginNotAvailable = "login.notAvailable"
    /// `Prudence cannot read this store`
    case contractTitle = "contract.title"
    /// `Nothing is drawn from a schema this build does not understand.`
    case contractNote = "contract.note"

    // --- the charts ----------------------------------------------------------------
    //
    // The first seven are the names a mark's dimensions carry. They are never printed in
    // the layout, but Swift Charts puts them in the accessibility tree, so a screen reader
    // reads them and they are translated like everything else.

    /// `Period`
    case chartPeriod = "chart.period"
    /// `Value`
    case chartValue = "chart.value"
    /// `Purpose`
    case chartPurpose = "chart.purpose"
    /// `Side`
    case chartSide = "chart.side"
    /// `Series`
    case chartSeries = "chart.series"
    /// `Day of the week`
    case chartWeekday = "chart.weekday"
    /// `Active hours`
    case chartHours = "chart.hours"
    /// `n=%1$@`, the count behind one side of a paired-bars comparison.
    case chartSampleSize = "chart.sampleSize"
    /// `coverage %1$@`
    case chartCoverageIs = "chart.coverageIs"
    /// `%1$@ of %2$@` — a share and the number it is over. Never one without the other.
    case chartShareOver = "chart.shareOver"
    /// `sessions`, the word under a donut's middle.
    case chartSessionsShort = "chart.sessionsShort"
    /// What the stacked bars' readout says with nothing under the pointer.
    case chartHintWeeks = "chart.hint.weeks"
    /// The same for the lines.
    case chartHintLines = "chart.hint.lines"
    /// `Mon`
    case weekdayMon = "weekday.mon"
    /// `Tue`
    case weekdayTue = "weekday.tue"
    /// `Wed`
    case weekdayWed = "weekday.wed"
    /// `Thu`
    case weekdayThu = "weekday.thu"
    /// `Fri`
    case weekdayFri = "weekday.fri"
    /// `Sat`
    case weekdaySat = "weekday.sat"
    /// `Sun`
    case weekdaySun = "weekday.sun"
    /// `previous %1$@`
    case comparePrevious = "compare.previous"
    /// `change %1$@`
    case compareChange = "compare.change"
    /// `prev`
    case comparePreviousShort = "compare.previousShort"
    /// `now`
    case compareNowShort = "compare.nowShort"

    // --- where the store is ---------------------------------------------------------

    /// `from %1$@`
    case settingsSourceEnvironment = "settings.source.environment"
    /// `from Settings`
    case settingsSourceSettings = "settings.source.settings"
    /// `the standard location`
    case settingsSourceStandard = "settings.source.standard"

    // --- the Overview's third chart --------------------------------------------------

    /// `Where the hours went`
    case overviewWhereTime = "overview.whereTime"
    /// `Active minutes per local day ...`
    case overviewWhereTimeNote = "overview.whereTime.note"
    /// `No active time in this range`
    case overviewNoHoursTitle = "overview.noHours.title"
    /// `No session in this range recorded any active minutes. ...`
    case overviewNoHoursDetail = "overview.noHours.detail"
    /// `The cards above are the week of %1$@: %2$@ tokens.`
    case overviewWeekFilter = "overview.weekFilter"
    /// `Show the whole range`
    case overviewShowAllWeeks = "overview.showAllWeeks"
    /// `alive at 30 days`, the series name inside a readout.
    case overviewLegendAliveName = "overview.legend.aliveName"
    /// `reworked later`
    case overviewLegendReworkName = "overview.legend.reworkName"
    /// `coverage`
    case overviewLegendCoverageName = "overview.legend.coverageName"

    // --- the Review page --------------------------------------------------------------

    /// `scope`
    case reviewTagScope = "review.tag.scope"
    /// `coverage`
    case reviewTagCoverage = "review.tag.coverage"
    /// `written`
    case reviewTagWritten = "review.tag.written"
    /// `figures`
    case reviewTagFigures = "review.tag.figures"
    /// `Mean coverage`, the heading of the fourth card of "What you did".
    case reviewCardCoverage = "review.card.coverage"
    /// The tooltip on the coverage tag.
    case reviewCoverageHelp = "review.coverageHelp"
    /// The tooltip on the figures tag.
    case reviewFiguresHelp = "review.figuresHelp"
    /// `Every figure above is computed from your own record: %1$@ numbers ...`
    case reviewProvenance = "review.provenance"
    /// `Not ready for a review yet`
    case reviewNotReadyTitle = "review.notReady.title"
    /// `Write anyway`
    case reviewWriteAnyway = "review.writeAnyway"
    /// `This review's sections cannot be read`
    case reviewUnreadableTitle = "review.unreadable.title"
    /// `The stored JSON is not in a shape this build understands. ...`
    case reviewUnreadableDetail = "review.unreadable.detail"
    /// `No review yet`
    case reviewEmptyTitle = "review.empty.title"
    /// `A review is written on demand and kept. ...`
    case reviewEmptyDetail = "review.empty.detail"
    /// `A section this version of the app does not lay out; here it is as stored.`
    case reviewUnknownSection = "review.unknownSection"
    /// `What this means`
    case reviewWhatThisMeans = "review.whatThisMeans"
    /// `Written by %1$@`
    case reviewWrittenBy = "review.writtenBy"
    /// `Every number in it was checked against the review's own figures.`
    case reviewSegmentChecked = "review.segment.checked"
    /// `every project`
    case reviewScopeEveryProject = "review.scope.everyProject"
    /// `The pale underlay behind each bar is that figure's coverage.`
    case reviewCoverageUnderlay = "review.coverageUnderlay"
    /// `This review's coverage is %1$@.`
    case reviewCoverageOfRow = "review.coverageOfRow"

    // --- the Observations page ---------------------------------------------------------

    /// `Threshold: %1$@`
    case observationThreshold = "observations.threshold"
    /// `still at head` — and in Chinese **仍留在当前版本**, never the English word "head".
    case observationOutcomeAlive = "observation.outcome.alive"
    /// `reworked later`
    case observationOutcomeRework = "observation.outcome.rework"
    /// `did`, the with-side of a paired-bars row where the behaviour has no short name.
    case observationSideDid = "observation.side.did"
    /// `did not`, the without-side of every paired-bars row.
    case observationSideDidNot = "observation.side.didNot"
    /// `3+ sittings`
    case observationShortSittings = "observation.short.sittings"
    /// `edited before read`
    case observationShortFilesEditedUnread = "observation.short.files_edited_unread"
    /// `ran a formatter`
    case observationShortFormatterRuns = "observation.short.formatter_runs"
    /// `ran tests`
    case observationShortTestRuns = "observation.short.test_runs"
    /// `tests before commit`
    case observationShortTestsBeforeCommit = "observation.short.tests_before_commit"
    /// `3+ commit attempts`
    case observationShortCommitAttempts = "observation.short.commit_attempts_per_commit"
    /// `same error 3 times`
    case observationShortRepeatedErrors = "observation.short.repeated_errors"
    /// `used a subagent`
    case observationShortSubagentUsed = "observation.short.subagent_used"
    /// `compacted context`
    case observationShortCompactions = "observation.short.compactions"
    /// `replayed records`
    case observationShortContextResets = "observation.short.context_resets"
    /// `above your median`
    case observationShortPromptsPerHour = "observation.short.prompts_per_active_hour"
    /// `hand edits`
    case observationShortHandEdits = "observation.short.hand_edits_between_turns"

    // --- plurals -------------------------------------------------------------------
    //
    // These five carry a count, so they are plural entries in the catalog rather than
    // plain strings: `%lld` with `one` and `other` in English and `other` alone in
    // Chinese, which has no plural category of its own. They are filled through
    // `Str.plural(_:)` with an `Int`, never through `callAsFunction` with a string, or
    // the plural rule would have nothing to choose on.

    /// `%1$lld session` / `%1$lld sessions`
    case unitSessions = "unit.sessions"
    /// `%1$lld commit` / `%1$lld commits`
    case unitCommits = "unit.commits"
    /// `%1$lld edit` / `%1$lld edits`
    case unitEdits = "unit.edits"
    /// `%1$lld project` / `%1$lld projects`
    case unitProjects = "unit.projects"
    /// `gap %1$lld point` / `gap %1$lld points`
    case observationGapPoints = "observation.gapPoints"
}

extension Str {

    /// The string as a `LocalizedStringResource`: the bundle- and locale-carrying form of a
    /// `LocalizedStringKey`, which is what a key in a package's own catalog has to be. A bare
    /// `LocalizedStringKey` would be looked up in `Bundle.main`, where this catalog is not.
    public var resource: LocalizedStringResource {
        LocalizedStringResource(
            String.LocalizationValue(rawValue),
            locale: Localization.locale,
            bundle: Localization.bundle
        )
    }

    /// The string in the language in force, with no arguments.
    public var text: String { String(localized: resource) }

    /// The string with its `%n$@` placeholders filled. The arguments are already formatted,
    /// so that each language decides its own order and each number went through `Fmt` first.
    public func callAsFunction(_ arguments: String...) -> String {
        format(arguments)
    }

    public func format(_ arguments: [String]) -> String {
        guard !arguments.isEmpty else { return text }
        return String(format: text, locale: Localization.locale, arguments: arguments)
    }

    /// The five entries the catalog stores as plural variations.
    ///
    /// They are filled through `plural(_:)`, never `callAsFunction`. `text` on one of them
    /// answers with whatever `String(localized:)` picks with no count to choose on, which is
    /// not a string to put on a screen.
    public static let plurals: Set<Str> = [
        .unitSessions, .unitCommits, .unitEdits, .unitProjects, .observationGapPoints,
    ]

    public var isPlural: Bool { Self.plurals.contains(self) }

    /// The seven rows of a heat strip, Monday first, by the key `HeatStrip.weekdayKeys` uses.
    /// A key outside the seven is answered with itself, which is visible and not a crash.
    public static func weekday(_ key: String) -> String {
        let table: [String: Str] = [
            "mon": .weekdayMon, "tue": .weekdayTue, "wed": .weekdayWed, "thu": .weekdayThu,
            "fri": .weekdayFri, "sat": .weekdaySat, "sun": .weekdaySun,
        ]
        return table[key]?.text ?? key
    }

    /// A plural entry, filled with the count the rule chooses on.
    ///
    /// The number is formatted by `String(format:locale:)` itself rather than handed in as
    /// a string, because a plural rule needs the value and not its rendering. It therefore
    /// also picks up the locale's own grouping separator for free.
    public func plural(_ count: Int) -> String {
        String(format: text, locale: Localization.locale, count)
    }
}

extension Text {
    /// `Text(.menuToday)`, the shorthand for a string with no arguments.
    ///
    /// `Text(verbatim:)` over an already-resolved string rather than `Text(resource)`,
    /// because SwiftUI resolves a `LocalizedStringResource` against the *environment's*
    /// locale at render time and ignores the one the resource carries. That is right for an
    /// app whose language is the system's; it is wrong here, where `Localization.locale` is
    /// the authority and the render harness forces it per shot. Resolving at body-evaluation
    /// time makes every string on a screen answer to the same setting.
    public init(_ key: Str) { self.init(verbatim: key.text) }
}

// MARK: - the language setting

/// System, English, 简体中文. The order is the order the picker shows.
public enum Language: String, CaseIterable, Identifiable, Sendable {
    case system
    case english = "en"
    case chineseSimplified = "zh-Hans"

    public var id: String { rawValue }

    /// What the picker prints. The two real languages are written in themselves, which is the
    /// convention every system language list on macOS follows.
    public var label: String {
        switch self {
        case .system: return Str.settingsLanguageSystem.text
        case .english: return "English"
        case .chineseSimplified: return "简体中文"
        }
    }

    /// The `AppleLanguages` array this choice writes, or nil for "follow the system".
    var appleLanguages: [String]? {
        switch self {
        case .system: return nil
        case .english: return ["en"]
        case .chineseSimplified: return ["zh-Hans"]
        }
    }
}

/// Where the locale comes from, and where the language setting is kept.
///
/// The override is written into the app's own `UserDefaults` under `AppleLanguages`, which is
/// the macOS convention: a per-app language that Cocoa itself reads at launch, and which
/// System Settings > General > Language & Region shows and can change. It therefore takes
/// effect on the next launch, and the Settings screen says so and offers the relaunch.
public enum Localization {

    /// The key Cocoa reads at launch.
    public static let appleLanguagesKey = "AppleLanguages"
    /// Where the user's own choice is kept, so that "System" can be told apart from "English
    /// because the system is English".
    public static let languageKey = "language"

    public static let bundle: LocalizedStringResource.BundleDescription =
        .atURL(Bundle.module.bundleURL)

    private static let overrideKey = "dev.prudence.localeOverride"

    /// Forces a language on **this thread**, for the render harness and the tests. The app
    /// never sets it: it relaunches instead, because that is what `AppleLanguages` means.
    ///
    /// Thread-local rather than global, for two reasons. The test suite runs its cases in
    /// parallel, and a process-wide override would have one test reading another's language
    /// half the time. And AppKit draws on the thread that asked it to, so the render harness
    /// setting a language and then laying a view out stays inside one scope even when
    /// `cacheDisplay` turns the run loop underneath it.
    public static var override: Locale? {
        get {
            guard let identifier = Thread.current.threadDictionary[overrideKey] as? String
            else { return nil }
            return Locale(identifier: identifier)
        }
        set {
            if let newValue {
                Thread.current.threadDictionary[overrideKey] = newValue.identifier
            } else {
                Thread.current.threadDictionary.removeObject(forKey: overrideKey)
            }
        }
    }

    /// The locale every string is resolved in.
    public static var locale: Locale { override ?? .current }

    /// Runs `body` with one language forced, then puts back whatever was there.
    @discardableResult
    public static func withLanguage<T>(_ language: Language, _ body: () throws -> T) rethrows -> T
    {
        let previous = override
        override = language.appleLanguages.map { Locale(identifier: $0[0]) }
        defer { override = previous }
        return try body()
    }

    /// The stored choice, defaulting to System.
    public static func stored(in defaults: UserDefaults) -> Language {
        guard let raw = defaults.string(forKey: languageKey) else { return .system }
        return Language(rawValue: raw) ?? .system
    }

    /// Store the choice and write the `AppleLanguages` override beside it. "System" removes
    /// the override rather than writing the current system language into it, so that a user
    /// who later changes their system language is followed.
    public static func store(_ language: Language, in defaults: UserDefaults) {
        defaults.set(language.rawValue, forKey: languageKey)
        if let languages = language.appleLanguages {
            defaults.set(languages, forKey: appleLanguagesKey)
        } else {
            defaults.removeObject(forKey: appleLanguagesKey)
        }
    }

    /// The language the app is actually running in, whatever the setting says. After a
    /// relaunch the two agree; before it they do not, which is what the Settings note is for.
    public static var running: Language {
        let identifier = locale.identifier
        if identifier.hasPrefix("zh") { return .chineseSimplified }
        return .english
    }
}

// MARK: - the product's own name

/// The one place the product is named in Swift. The other is `CFBundleDisplayName` in
/// `App/Info.plist`. The name research is still open (M4 plan), so it is one constant and one
/// plist entry rather than fifty string literals.
public enum Product {
    public static let name = "Prudence"
}
