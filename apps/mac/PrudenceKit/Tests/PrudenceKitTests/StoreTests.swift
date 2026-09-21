import Foundation
import GRDB
import Testing

@testable import PrudenceStore

/// The fixture is a store the engine itself wrote, at app contract 2, and nothing else.
///
/// `tests/conftest.py`'s synthetic machine is ingested by the engine, given the few rows that
/// small a scenario cannot produce on its own (observations need five sessions a side, a review
/// needs a range), and `VACUUM INTO`'d into the test bundle by `tests/mac_fixture.py`:
///
///     MAC_FIXTURE_TARGET=apps/mac/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db \
///         uv run pytest tests/mac_fixture.py -q
///
/// **No test below hard-codes a number out of it.** The store is regenerated whenever
/// `store/app_views.py` changes, and an expectation typed from one generation of it is a test
/// that fails on the next for no reason anybody can read. Each test therefore computes what it
/// expects with `Fixture.count` and friends — plain SQL over the same file, through a second
/// connection that knows nothing about `Store`, `Rows` or the view models — and compares that
/// with what the code under test answered. A sum compared with the same sum computed the same
/// way would prove nothing, so the SQL aggregates by a different route than the Swift does:
/// over the base tables where the view's own SELECT is short enough to be honest about, and
/// otherwise over view columns the model does not itself read.
enum Fixture {
    static var url: URL {
        guard let url = Bundle.module.url(forResource: "Fixtures/store", withExtension: "db") else {
            fatalError("the fixture store is missing from the test bundle")
        }
        return url
    }

    /// One real `review.sections` payload, copied off the founder's own store. It holds
    /// nothing but numbers, labels and the notes that explain them.
    static var reviewSections: String {
        guard
            let url = Bundle.module.url(
                forResource: "Fixtures/review-sections", withExtension: "json"),
            let text = try? String(contentsOf: url, encoding: .utf8)
        else {
            fatalError("the review payload fixture is missing from the test bundle")
        }
        return text
    }

    static func store() throws -> Store { try Store(url: url) }

    // MARK: - what a test expects, asked of the file directly

    /// A connection onto the same file that is not the code under test. Read-only, opened per
    /// query: the fixture is a third of a megabyte and a test suite is not a hot path.
    private static func connection() throws -> DatabaseQueue {
        var configuration = Configuration()
        configuration.readonly = true
        return try DatabaseQueue(path: url.path, configuration: configuration)
    }

    /// One whole number, or 0 when the query answers with no row at all. `SUM` over no rows is
    /// NULL in SQLite, and a count of nothing is what a test that asks for it means.
    static func count(_ sql: String, _ arguments: [String] = []) throws -> Int {
        try connection().read { try Int.fetchOne($0, sql: sql, arguments: StatementArguments(arguments)) ?? 0 }
    }

    static func number(_ sql: String, _ arguments: [String] = []) throws -> Double? {
        try connection().read { try Double.fetchOne($0, sql: sql, arguments: StatementArguments(arguments)) }
    }

    static func text(_ sql: String, _ arguments: [String] = []) throws -> String? {
        try connection().read { try String.fetchOne($0, sql: sql, arguments: StatementArguments(arguments)) }
    }

    static func texts(_ sql: String, _ arguments: [String] = []) throws -> [String] {
        try connection().read { try String.fetchAll($0, sql: sql, arguments: StatementArguments(arguments)) }
    }

    static func ints(_ sql: String, _ arguments: [String] = []) throws -> [Int] {
        try connection().read { try Int.fetchAll($0, sql: sql, arguments: StatementArguments(arguments)) }
    }

    /// True when the fixture can say anything at all about the thing a test is for. The ones
    /// that ask are gated with `.enabled(if:)` and skip with a sentence naming what
    /// `tests/mac_fixture.py` would have to record for the test to mean something.
    static func has(_ sql: String, _ arguments: [String] = []) -> Bool {
        ((try? count(sql, arguments)) ?? 0) > 0
    }
}

@Suite("The contract")
struct ContractTests {

    /// Contract 3 is additive — four optional columns and three optional payload fields — so
    /// this build renders 2 and 3 from one code path and refusing either would be refusing a
    /// store it can draw completely. Whichever the fixture is at, it opens.
    @Test("Both supported contracts open, and the store says which one it was")
    func opensAtEitherSupportedVersion() throws {
        let store = try Store(url: Fixture.url)
        #expect(Contract.supported == ["2", "3"])
        #expect(Contract.newest == "3")
        #expect(Contract.supported.contains(store.contractVersion))
        #expect(try store.status()?.appContractVersion == store.contractVersion)
    }

    @Test("Contract 1 is refused, and the refusal says the engine is the old one")
    func refusesOne() throws {
        // The fixture is written at the engine's current contract; the refusal names it.
        let fixtureVersion = try Fixture.text("SELECT value FROM meta WHERE key = 'app_contract_version'")
        #expect(throws: StoreError.contractMismatch(found: fixtureVersion, expected: ["1"])) {
            _ = try Store(url: Fixture.url, supporting: ["1"])
        }
        let refusal = StoreError.contractMismatch(found: "1", expected: Contract.supported)
        #expect(refusal.message.contains("contract 1"))
        #expect(refusal.message.contains("needs 2 or 3"))
        #expect(refusal.message.contains("newer than the Prudence engine"))
    }

    @Test("Contract 4 is refused, and that refusal says the app is the old one")
    func refusesFour() throws {
        let fixtureVersion = try Fixture.text("SELECT value FROM meta WHERE key = 'app_contract_version'")
        #expect(throws: StoreError.contractMismatch(found: fixtureVersion, expected: ["4"])) {
            _ = try Store(url: Fixture.url, supporting: ["4"])
        }
        let refusal = StoreError.contractMismatch(found: "4", expected: Contract.supported)
        #expect(refusal.message.contains("contract 4"))
        #expect(refusal.message.contains("app knows 2 or 3"))
        #expect(refusal.message.contains("newer than this app"))
    }

    @Test("A store with no meta table at all is a sentence, not a crash")
    func refusesAncient() {
        let ancient = StoreError.contractMismatch(found: nil, expected: Contract.supported)
        #expect(ancient.message.contains("prudence ingest"))
    }

    @Test("A missing database is a sentence, not a crash")
    func missingDatabase() {
        let path = "/nowhere/prudence.db"
        #expect(throws: StoreError.databaseMissing(path: path)) {
            _ = try Store(url: URL(fileURLWithPath: path))
        }
    }

    /// The case that broke the first build of this app against a real store: the engine had
    /// closed cleanly, so `prudence.db-wal` and `prudence.db-shm` were gone, and a connection
    /// opened `SQLITE_OPEN_READONLY` cannot create the wal-index it needs to read a WAL
    /// database. A healthy store nobody is writing to must still open.
    @Test("A WAL store with no side files open still opens, and still refuses writes")
    func walStoreWithoutSideFiles() throws {
        let directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("prudence-wal-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let copy = directory.appendingPathComponent("prudence.db")
        try FileManager.default.copyItem(at: Fixture.url, to: copy)
        // Put it into WAL mode and close cleanly, which removes -wal and -shm.
        let writer = try DatabaseQueue(path: copy.path)
        try writer.inDatabase { try $0.execute(sql: "PRAGMA journal_mode = WAL") }
        try writer.close()
        #expect(
            FileManager.default.fileExists(atPath: copy.path + "-shm") == false,
            "the interesting case is precisely when the wal-index is gone")

        let store = try Store(url: copy)
        #expect(try store.status()?.sessions == (try Fixture.count("SELECT COUNT(*) FROM session")))
        #expect(throws: DatabaseError.self) {
            try store.writeAttemptForTesting()
        }
    }

    /// Every view answers with exactly the columns `APP_VIEWS` names, at whichever contract
    /// the fixture is at.
    ///
    /// The set has to match exactly — a renamed or dropped column is the thing this test is
    /// for — and the **contract 2 columns have to still be in their contract 2 order**, so a
    /// reordering that would break a positional read still fails. Where contract 3 puts its
    /// four additions in the list is the Python side's business and not something this app can
    /// assert from the outside; it is the only part left loose, and deliberately.
    @Test("Every view answers with exactly the columns APP_VIEWS names")
    func columnsMatch() throws {
        let store = try Fixture.store()
        let expected = Contract.columns(at: store.contractVersion)
        for view in Contract.View.allCases {
            let actual = try store.columns(of: view)
            let wanted = expected[view] ?? []
            #expect(Set(actual) == Set(wanted), "\(view.rawValue)")
            let shared = Contract.columnsAtTwo[view] ?? []
            #expect(actual.filter(shared.contains) == shared, "\(view.rawValue), order")
        }
    }

    /// Contract 3's own lists are contract 2's plus four columns, and nothing is lost on the
    /// way: a table built by insertion can silently drop the anchor it inserts after.
    @Test("Contract 3 is contract 2 plus four columns and nothing else")
    func threeIsTwoPlusFour() {
        for view in Contract.View.allCases {
            let two = Contract.columnsAtTwo[view] ?? []
            let three = Contract.columnsAtThree[view] ?? []
            #expect(three.filter(two.contains) == two, "\(view.rawValue)")
        }
        let observation = Contract.columnsAtThree[.observation] ?? []
        #expect(observation.contains("threshold_value"))
        #expect(observation.contains("threshold_op"))
        #expect(Contract.columnsAtThree[.review]?.contains("segment_language") == true)
        let added = Contract.View.allCases.reduce(0) { total, view in
            total + (Contract.columnsAtThree[view] ?? []).count
                - (Contract.columnsAtTwo[view] ?? []).count
        }
        #expect(added == 3, "contract 3 adds three view columns, not \(added)")
    }

    @Test("Contract 2 names seven views, the five of contract 1 plus commits and reviews")
    func sevenViews() {
        #expect(Contract.View.allCases.count == 7)
        #expect(Contract.View.allCases.contains(.commitsByDay))
        #expect(Contract.View.allCases.contains(.review))
    }
}

@Suite("Row decoding")
struct RowTests {

    @Test("app_status is one row with the versions behind it")
    func status() throws {
        let row = try #require(try Fixture.store().status())
        #expect(!row.engineVersion.isEmpty)
        #expect(row.appContractVersion == (try Fixture.text("SELECT value FROM meta WHERE key = 'app_contract_version'")))
        // Two views of the same store have to agree about how much is in it: the number on
        // the status line is the number of sessions the session list will hand a screen.
        #expect(row.sessions == (try Fixture.count("SELECT COUNT(*) FROM app_session_list")))
        // A project the picker can offer is a project with a session, so the store's count of
        // projects is never below the number of distinct projects in that list.
        #expect(
            row.projects
                >= (try Fixture.count("SELECT COUNT(DISTINCT project) FROM app_session_list")))
        #expect(row.lastIngestAt != nil)
        #expect((row.parserVersion ?? 0) >= 1)
    }

    @Test("app_usage_by_purpose_day decodes a day, a purpose and its tokens")
    func usage() throws {
        let since = "2026-09-01"
        let rows = try Fixture.store().usageByPurposeDay(since: since)
        #expect(
            rows.count
                == (try Fixture.count(
                    "SELECT COUNT(*) FROM app_usage_by_purpose_day WHERE day >= ?", [since])))
        let busiest = try #require(rows.max { ($0.totalTokens ?? 0) < ($1.totalTokens ?? 0) })
        // `total_tokens` is the four kinds of token added up. Summing the four columns in SQL
        // is the same figure by another road, which is the only way this assertion says
        // anything: reading `total_tokens` back would compare the column with itself.
        #expect(
            busiest.totalTokens
                == (try Fixture.count(
                    """
                    SELECT input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens
                      FROM app_usage_by_purpose_day WHERE day = ? AND purpose = ?
                    """, [busiest.day, busiest.purpose])))
        #expect(busiest.sessions >= 1)
        #expect(busiest.activeMinutes != nil)
    }

    @Test("app_session_list decodes a session with its purpose, its commits and its edits")
    func sessions() throws {
        let rows = try Fixture.store().sessions()
        #expect(rows.count == (try Fixture.count("SELECT COUNT(*) FROM session")))
        let committed = try #require(rows.first { $0.countedCommits > 0 })
        #expect(committed.project.isEmpty == false)
        #expect(committed.sittings >= 1)
        // `edits` is the contract-2 column the dropdown's "today" line was missing. The view
        // counts the `edit` table per session, so every edit in the store is in the column
        // exactly once and no session's count was dropped on the way through the join.
        #expect(
            rows.compactMap(\.edits).reduce(0, +)
                == (try Fixture.count("SELECT COUNT(*) FROM edit")))
    }

    @Test("app_commits_by_day counts a commit once, split by how it was established")
    func commitsByDay() throws {
        let rows = try Fixture.store().commitsByDay()
        #expect(!rows.isEmpty)
        for row in rows {
            #expect(row.commits == row.commitsFact + row.commitsInferred, "\(row.day)")
        }
        let counted = rows.reduce(0) { $0 + $1.commits }
        // The point of the view: one row in `commit` is one commit here, however many
        // attributions were written for it.
        #expect(
            counted
                == (try Fixture.count(
                    """
                    SELECT COUNT(DISTINCT a.commit_hash) FROM attribution a
                      JOIN "commit" c ON c.commit_hash = a.commit_hash
                     WHERE c.is_merge = 0 AND c.committer_at IS NOT NULL
                    """)))
        // And the reason it exists: summing the session list instead counts a commit once per
        // session credited with it, which is an upper bound and never below this figure.
        #expect(
            counted
                <= (try Fixture.count(
                    "SELECT SUM(commits_fact + commits_inferred) FROM app_session_list")))
    }

    @Test("app_observation decodes both sides of a split, its coverage and its own sentence")
    func observations() throws {
        let rows = try Fixture.store().observations()
        #expect(rows.count == (try Fixture.count("SELECT COUNT(*) FROM observation")))
        // The engine's own order: a project's own rows first, the pooled ones last.
        #expect(
            rows.filter(\.isPooled).count
                == (try Fixture.count("SELECT COUNT(*) FROM observation WHERE repo_key = '*'")))
        #expect(rows.last?.isPooled == true)
        let first = try #require(rows.first)
        #expect(first.observationId > 0)
        #expect(first.withN > 0 && first.withoutN > 0)
        #expect(first.coverage != nil)
        #expect(first.factVersion >= 1)
        // Contract 2 carries the prose, so no surface has to restate the phrase table. The
        // sentences live in their own table and the view joins them on `observation_id`; every
        // row having one means that join lined up for all of them.
        #expect(
            rows.compactMap(\.sentence).filter { !$0.isEmpty }.count
                == (try Fixture.count("SELECT COUNT(*) FROM app_observation_text")))
    }

    @Test("app_outcomes_by_week decodes, even with nothing measured yet")
    func outcomes() throws {
        let rows = try Fixture.store().outcomesByWeek()
        #expect(rows.count == (try Fixture.count("SELECT COUNT(*) FROM app_outcomes_by_week")))
        #expect(!rows.isEmpty)
        for row in rows {
            #expect(row.commits == (row.commitsFact ?? 0) + (row.commitsInferred ?? 0))
        }
        // A week whose 30-day mark has not arrived is the interesting one, and it must decode
        // as the zero the view wrote rather than as a missing row.
        #expect(
            rows.filter { ($0.measured30d ?? 0) == 0 }.count
                == (try Fixture.count(
                    "SELECT COUNT(*) FROM app_outcomes_by_week WHERE COALESCE(measured_30d, 0) = 0")
                ))
    }

    @Test("The newest review comes from app_review, not the raw table")
    func review() throws {
        let store = try Fixture.store()
        let row = try #require(try store.latestReview())
        let newest = try Fixture.count("SELECT MAX(id) FROM review")
        #expect(row.id == newest)
        // Every column of the row against the `review` table it was built from, so a view that
        // mixed two reviews up or shifted a column would be caught here.
        let id = String(newest)
        #expect(row.rangeStart == (try Fixture.text("SELECT range_start FROM review WHERE id = ?", [id])))
        #expect(row.headline?.contains("Review \(newest)") == true)
        #expect(row.segmentText == (try Fixture.text("SELECT segment_text FROM review WHERE id = ?", [id])))
        #expect(row.segmentModel == (try Fixture.text("SELECT segment_model FROM review WHERE id = ?", [id])))
        // `app_review.sections` is the section list out of the stored payload, so the first
        // section's title is in it and the keys the payload wrapped it in are not.
        let firstTitle = try #require(
            try Fixture.text(
                "SELECT json_extract(sections, '$.sections[0].title') FROM review WHERE id = ?",
                [id]))
        #expect(row.sections.contains(firstTitle))
        #expect(
            try store.reviews().map(\.id) == (try Fixture.ints("SELECT id FROM review ORDER BY id DESC")),
            "newest first")
    }
}

@Suite("Where the store is")
struct StoreLocationTests {

    let home = URL(fileURLWithPath: "/Users/someone")

    @Test("PRUDENCE_DATA_DIR wins, so the app can be pointed at a copy")
    func environmentWins() {
        let located = StoreLocation.locate(
            settingsOverride: "/elsewhere/other.db",
            environment: ["PRUDENCE_DATA_DIR": "/copy"],
            home: home
        )
        #expect(located.url.path == "/copy/prudence.db")
        #expect(located.source == .environment)
    }

    @Test("Then the Settings override, expanded")
    func settingsNext() {
        let located = StoreLocation.locate(
            settingsOverride: "~/elsewhere/other.db", environment: [:], home: home)
        #expect(located.url.path == "/Users/someone/elsewhere/other.db")
        #expect(located.source == .settings)
    }

    @Test("Then the standard location paths.py returns on macOS")
    func standardLast() {
        let located = StoreLocation.locate(environment: [:], home: home)
        #expect(
            located.url.path == "/Users/someone/Library/Application Support/prudence/prudence.db")
        #expect(located.source == .standard)
    }

    @Test("An empty override is not an override")
    func emptyIgnored() {
        let located = StoreLocation.locate(
            settingsOverride: "  ", environment: ["PRUDENCE_DATA_DIR": ""], home: home)
        #expect(located.source == .standard)
    }
}
