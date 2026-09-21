import Foundation
import GRDB

/// A read-only door onto one `prudence.db`, opened once and kept.
///
/// Read-only is not a style choice. The engine is the only writer (ARCHITECTURE: one engine,
/// several surfaces), so nothing here may write and a statement that tried would fail loudly
/// rather than quietly corrupt somebody's record.
///
/// It is opened in two attempts, and the second one is the interesting one. SQLite's WAL
/// documentation says a reader "must have write privileges for the `-shm` wal-index shared
/// memory file ... or else write access on the directory containing the database file": a
/// connection opened with `SQLITE_OPEN_READONLY` can *use* an existing wal-index but cannot
/// create one. The engine deletes both side files when it closes cleanly, so a perfectly
/// healthy store that nobody is writing to at this moment refuses a read-only connection with
/// SQLITE_CANTOPEN. The fallback therefore opens the file read-write, which is only about the
/// filesystem, and forbids writing inside SQLite with `PRAGMA query_only = 1`. Every write
/// then fails with SQLITE_READONLY, which is the guarantee that matters.
///
/// This is also the reason the app cannot be sandboxed: a sandboxed process has neither the
/// directory nor the file, whatever the user grants it.
///
/// The contract version is checked in `init`, before a single row is read, so no screen can
/// ever render half of a schema it does not understand.
public final class Store: @unchecked Sendable {

    public let url: URL
    /// Which contract this store turned out to be at. The rows decode the same either way;
    /// a screen that wants to know whether a stored figure can be there at all asks this.
    public let contractVersion: String
    private let queue: DatabaseQueue

    /// Open the store at `url` and refuse it unless `meta.app_contract_version` is one this
    /// build renders.
    ///
    /// Two versions rather than one, because contract 3 is additive: every column it adds is
    /// optional in `Rows.swift` and used only where it is present, so refusing a contract 2
    /// store would be refusing a store this app can draw completely.
    public init(url: URL, supporting versions: [String] = Contract.supported) throws {
        self.url = url
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw StoreError.databaseMissing(path: url.path)
        }
        queue = try Self.open(path: url.path)
        let found = try Self.contractVersion(in: queue)
        guard let found, versions.contains(found) else {
            throw StoreError.contractMismatch(found: found, expected: versions)
        }
        contractVersion = found
    }

    /// Open whatever `StoreLocation` resolves to.
    public convenience init(
        settingsOverride: String? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) throws {
        let located = StoreLocation.locate(
            settingsOverride: settingsOverride, environment: environment)
        try self.init(url: located.url)
    }

    /// Read-only if SQLite will have it, `query_only` if it will not. See the type's comment.
    private static func open(path: String) throws -> DatabaseQueue {
        var readOnly = Configuration()
        readOnly.readonly = true
        do {
            return try DatabaseQueue(path: path, configuration: readOnly)
        } catch let error as DatabaseError where error.resultCode == .SQLITE_CANTOPEN {
            var queryOnly = Configuration()
            queryOnly.readonly = false
            queryOnly.prepareDatabase { database in
                try database.execute(sql: "PRAGMA query_only = 1")
            }
            do {
                return try DatabaseQueue(path: path, configuration: queryOnly)
            } catch {
                throw StoreError.unreadable(String(describing: error))
            }
        } catch {
            throw StoreError.unreadable(String(describing: error))
        }
    }

    // MARK: - the contract

    /// The version in the store, or nil when the `meta` table is not there at all.
    ///
    /// A store written before `store/meta.py` existed has no such table, and a missing value
    /// is a state, not an error (ARCHITECTURE rule 3): the caller turns it into a sentence.
    static func contractVersion(in queue: DatabaseQueue) throws -> String? {
        do {
            return try queue.read { database in
                try String.fetchOne(
                    database,
                    sql: "SELECT value FROM meta WHERE key = ?",
                    arguments: [Contract.versionKey]
                )
            }
        } catch let error as DatabaseError where error.resultCode == .SQLITE_ERROR {
            return nil  // no `meta` table: an old store, not a broken one
        } catch {
            throw StoreError.unreadable(String(describing: error))
        }
    }

    /// The columns a view actually answers with, for the contract test.
    public func columns(of view: Contract.View) throws -> [String] {
        try read { database in
            try Row.fetchAll(database, sql: "PRAGMA table_info(\(view.rawValue))")
                .compactMap { $0["name"] as String? }
        }
    }

    // MARK: - the seven views

    public func status() throws -> AppStatusRow? {
        try fetchOne(.status, sql: "SELECT * FROM app_status")
    }

    /// Usage rows from `day` onwards, `day` being a local calendar day, `yyyy-MM-dd`.
    public func usageByPurposeDay(since day: String) throws -> [AppUsageByPurposeDayRow] {
        try fetchAll(
            .usageByPurposeDay,
            sql: "SELECT * FROM app_usage_by_purpose_day WHERE day >= ? ORDER BY day, project",
            arguments: [day]
        )
    }

    /// Sessions whose first record falls in `[start, end)`, both UTC `yyyy-MM-ddTHH:mm:ss`.
    public func sessions(startedBetween start: String, and end: String) throws
        -> [AppSessionListRow]
    {
        try fetchAll(
            .sessionList,
            sql:
                "SELECT * FROM app_session_list WHERE started_at >= ? AND started_at < ? ORDER BY started_at DESC",
            arguments: [start, end]
        )
    }

    /// Every session, newest first. The window reads the lot once and filters in memory: the
    /// view is one row per session (148 of them on the founder's store), so a range picker
    /// that re-queried would cost more than it saved.
    public func sessions() throws -> [AppSessionListRow] {
        try fetchAll(.sessionList, sql: "SELECT * FROM app_session_list ORDER BY started_at DESC")
    }

    public func observations() throws -> [AppObservationRow] {
        try fetchAll(.observation, sql: "SELECT * FROM app_observation")
    }

    public func outcomesByWeek() throws -> [AppOutcomesByWeekRow] {
        try fetchAll(.outcomesByWeek, sql: "SELECT * FROM app_outcomes_by_week")
    }

    /// Every day's commits, counted once. `day` is a local calendar day, `yyyy-MM-dd`.
    public func commitsByDay() throws -> [AppCommitsByDayRow] {
        try fetchAll(.commitsByDay, sql: "SELECT * FROM app_commits_by_day ORDER BY day")
    }

    /// Commits from `day` onwards, for a range the window already decided.
    public func commitsByDay(since day: String) throws -> [AppCommitsByDayRow] {
        try fetchAll(
            .commitsByDay,
            sql: "SELECT * FROM app_commits_by_day WHERE day >= ? ORDER BY day",
            arguments: [day]
        )
    }

    // MARK: - the stored reviews

    /// Every review, newest first. The review screen shows the first and lists the rest.
    public func reviews() throws -> [AppReviewRow] {
        try fetchAll(.review, sql: "SELECT * FROM app_review ORDER BY id DESC")
    }

    /// The newest review, or nil when none has been written (or the view is not there yet).
    ///
    /// A missing `app_review` is a state, not a failure: a store where `prudence review` has
    /// never run is perfectly healthy and the screens say "no review yet" (rule 3).
    public func latestReview() throws -> AppReviewRow? {
        do {
            return try read { database in
                try AppReviewRow.fetchOne(
                    database, sql: "SELECT * FROM app_review ORDER BY id DESC LIMIT 1")
            }
        } catch let error as DatabaseError where error.resultCode == .SQLITE_ERROR {
            return nil
        }
    }

    // MARK: - plumbing

    private func fetchOne<T: FetchableRecord & Decodable>(
        _ view: Contract.View, sql: String, arguments: StatementArguments = []
    ) throws -> T? {
        do {
            return try read { try T.fetchOne($0, sql: sql, arguments: arguments) }
        } catch let error as DatabaseError where error.resultCode == .SQLITE_ERROR {
            throw StoreError.viewMissing(view.rawValue)
        }
    }

    private func fetchAll<T: FetchableRecord & Decodable>(
        _ view: Contract.View, sql: String, arguments: StatementArguments = []
    ) throws -> [T] {
        do {
            return try read { try T.fetchAll($0, sql: sql, arguments: arguments) }
        } catch let error as DatabaseError where error.resultCode == .SQLITE_ERROR {
            throw StoreError.viewMissing(view.rawValue)
        }
    }

    /// Only the tests call this, and only to prove that a write is refused whichever of the
    /// two ways the connection was opened.
    func writeAttemptForTesting() throws {
        try queue.read { database in
            try database.execute(sql: "CREATE TABLE the_app_must_never_do_this(x)")
        }
    }

    private func read<T>(_ body: (Database) throws -> T) throws -> T {
        do {
            return try queue.read(body)
        } catch let error as DatabaseError {
            throw error
        } catch let error as StoreError {
            throw error
        } catch {
            throw StoreError.unreadable(String(describing: error))
        }
    }
}
