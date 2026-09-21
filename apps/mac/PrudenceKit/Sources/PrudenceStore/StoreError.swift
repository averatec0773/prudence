import Foundation

/// Everything that can stop the app reading the store, each with the sentence the user sees.
///
/// A contract mismatch carries both numbers because the message has to say which side to
/// update, and only the two versions together decide that.
public enum StoreError: Error, Equatable, Sendable {

    /// No `prudence.db` at the resolved path: nothing has been ingested here yet.
    case databaseMissing(path: String)

    /// `meta.app_contract_version` is not the one this build compiles against.
    /// `found` is nil when the store predates the `meta` table entirely.
    case contractMismatch(found: String?, expected: String)

    /// SQLite or GRDB refused, with its own words kept verbatim.
    case unreadable(String)

    /// A view named in the contract is not in the store, usually an interrupted ingest.
    case viewMissing(String)

    public var message: String {
        switch self {
        case let .databaseMissing(path):
            return "No store at \(path). Run `prudence ingest`."
        case let .contractMismatch(found, expected):
            guard let found else {
                return "This store predates the app contract. Run `prudence ingest` to add it."
            }
            if let foundNumber = Int(found), let expectedNumber = Int(expected),
                foundNumber > expectedNumber
            {
                return
                    "The Prudence engine is newer than this app (contract \(found), app knows \(expected)). Update Prudence.app."
            }
            return
                "This app is newer than the Prudence engine (contract \(found), app needs \(expected)). Run `uv tool upgrade prudence-dev`, then `prudence ingest`."
        case let .unreadable(detail):
            return "The store could not be read: \(detail)"
        case let .viewMissing(name):
            return "The store has no \(name) view. Run `prudence ingest`."
        }
    }
}
