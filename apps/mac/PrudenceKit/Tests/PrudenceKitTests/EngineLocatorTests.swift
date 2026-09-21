import Foundation
import Testing

@testable import PrudenceEngine

/// A filesystem with exactly the paths a test says it has, so the locator's order can be
/// checked without a `prudence` anywhere near the machine running the test.
struct FakeFileProbe: FileProbing {
    let executables: Set<String>
    func isExecutableFile(atPath path: String) -> Bool { executables.contains(path) }
}

struct FakeShell: LoginShellProbing {
    let answer: String?
    func locate(timeout: TimeInterval) -> String? { answer }
}

/// Counts how often the shell was asked, so the cache can be proved rather than assumed.
final class CountingShell: LoginShellProbing, @unchecked Sendable {
    let answer: String?
    private let lock = NSLock()
    private var _calls = 0
    var calls: Int {
        lock.lock()
        defer { lock.unlock() }
        return _calls
    }

    init(answer: String?) { self.answer = answer }

    func locate(timeout: TimeInterval) -> String? {
        lock.lock()
        _calls += 1
        lock.unlock()
        return answer
    }
}

@Suite("Finding the engine")
struct EngineLocatorTests {

    let home = "/Users/someone"

    func locator(
        executables: Set<String>,
        environment: [String: String] = [:],
        shell: LoginShellProbing = FakeShell(answer: nil)
    ) -> EngineLocator {
        EngineLocator(
            probe: FakeFileProbe(executables: executables),
            shell: shell,
            environment: environment,
            home: home
        )
    }

    @Test("The Settings path wins over everything, when it is really there")
    func settingsFirst() {
        let found = locator(
            executables: ["/opt/custom/prudence", "\(home)/.local/bin/prudence"]
        ).locate(settingsOverride: "/opt/custom/prudence")
        #expect(found?.path == "/opt/custom/prudence")
        #expect(found?.source == .settings)
    }

    @Test("A Settings path that is not executable falls through rather than failing")
    func settingsIgnoredWhenAbsent() {
        let found = locator(executables: ["\(home)/.local/bin/prudence"])
            .locate(settingsOverride: "/opt/gone/prudence")
        #expect(found?.path == "\(home)/.local/bin/prudence")
    }

    @Test("uv's documented order comes before Homebrew")
    func uvBeforeHomebrew() {
        let found = locator(
            executables: ["\(home)/.local/bin/prudence", "/opt/homebrew/bin/prudence"]
        ).locate()
        #expect(found?.path == "\(home)/.local/bin/prudence")
        #expect(found?.source == .knownDirectory("\(home)/.local/bin"))
    }

    @Test("UV_TOOL_BIN_DIR comes before ~/.local/bin")
    func uvToolBinDirFirst() {
        let found = locator(
            executables: ["/uvbin/prudence", "\(home)/.local/bin/prudence"],
            environment: ["UV_TOOL_BIN_DIR": "/uvbin"]
        ).locate()
        #expect(found?.path == "/uvbin/prudence")
    }

    @Test("XDG_DATA_HOME resolves to its sibling bin, as uv documents")
    func xdgDataHomeSibling() {
        let found = locator(
            executables: ["/xdg/bin/prudence"],
            environment: ["XDG_DATA_HOME": "/xdg/share"]
        ).locate()
        #expect(found?.path == "/xdg/bin/prudence")
    }

    @Test("Apple silicon Homebrew before /usr/local")
    func homebrewOrder() {
        let found = locator(
            executables: ["/opt/homebrew/bin/prudence", "/usr/local/bin/prudence"]
        ).locate()
        #expect(found?.path == "/opt/homebrew/bin/prudence")
    }

    @Test("The login shell is the last resort, and only its answer is trusted")
    func shellLast() {
        let found = locator(
            executables: ["/somewhere/odd/prudence"],
            shell: FakeShell(answer: "/somewhere/odd/prudence")
        ).locate()
        #expect(found?.path == "/somewhere/odd/prudence")
        #expect(found?.source == .loginShell)
    }

    @Test("A shell answer pointing at nothing is not an answer")
    func shellAnswerVerified() {
        let found = locator(executables: [], shell: FakeShell(answer: "/gone/prudence")).locate()
        #expect(found == nil)
    }

    @Test("locateWithoutShell never runs the shell, so it is safe on the main thread")
    func withoutShell() {
        let shell = CountingShell(answer: "/somewhere/odd/prudence")
        let found = locator(executables: [], shell: shell).locateWithoutShell()
        #expect(found == nil)
        #expect(shell.calls == 0)
    }

    @Test("The shell is asked once per launch, even when it knows nothing")
    func shellCached() {
        let shell = CountingShell(answer: nil)
        let subject = locator(executables: [], shell: shell)
        _ = subject.locate()
        _ = subject.locate()
        _ = subject.locate()
        #expect(shell.calls == 1)
    }

    @Test("Nothing found is a sentence with somewhere to go")
    func notFoundMessage() {
        #expect(EngineError.notFound.message.contains("Settings"))
    }
}
