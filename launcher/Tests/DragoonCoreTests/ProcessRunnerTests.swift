import DragoonCore
import Foundation
import Testing

@Suite struct SystemProcessRunnerTests {
    let runner = SystemProcessRunner()

    @Test func eachArgumentArrivesWholeWithItsSpaces() async throws {
        let result = try await runner.run("/usr/bin/printf", ["%s|", "Application Support", "a b c"])
        #expect(result == ProcessResult(status: 0, stdout: "Application Support|a b c|"))
    }

    @Test func theEnvironmentIsExactlyTheOneGiven() async throws {
        let result = try await runner.run("/usr/bin/env", [], environment: ["A": "b c"])
        #expect(result.stdout == "A=b c\n")
    }

    @Test func bothPipesDrainSoABigOutputNeverBlocks() async throws {
        // 2 MiB is 32 times a pipe's buffer, and dd's summary goes to stderr meanwhile.
        let result = try await runner.run("/bin/dd", ["if=/dev/zero", "bs=65536", "count=32"])
        #expect(result.status == 0)
        #expect(result.stdout.utf8.count == 2_097_152)
        #expect(result.stderr.contains("2097152 bytes"))
    }

    @Test func aFailureGivesItsStatusAndStderr() async throws {
        let result = try await runner.run("/bin/ls", ["/no such path"])
        #expect(result.status == 1)
        #expect(result.stdout == "")
        #expect(result.stderr.contains("/no such path"))
    }

    @Test func aMissingExecutableThrows() async {
        await #expect(throws: (any Error).self) {
            try await runner.run("/no/such/tool", [])
        }
    }

    @Test func aProcessThatFinishesInTimeReturnsNormally() async throws {
        let result = try await runner.run("/usr/bin/printf", ["%s", "done"], environment: nil, timeout: 30)
        #expect(result == ProcessResult(status: 0, stdout: "done"))
    }

    @Test func aSleepingChildIsKilledAtItsTimeoutAndTheRunnerThrows() async {
        let started = ContinuousClock.now
        await #expect(throws: ProcessTimeout(executable: "/bin/sleep", seconds: 0.3)) {
            try await runner.run("/bin/sleep", ["60"], environment: nil, timeout: 0.3)
        }
        #expect(ContinuousClock.now - started < .seconds(20))
    }

    @Test func aTimeoutKillsTheHelpersTheChildStartedAndNotJustTheChild() async throws {
        // The shell starts a sleep that inherits both pipes and writes its pid to a file, then
        // waits for it. Killing only the shell would leave the sleep running for a minute.
        let pidFile = Self.pidFile()
        defer { try? FileManager.default.removeItem(atPath: pidFile) }
        await #expect(throws: ProcessTimeout(executable: "/bin/sh", seconds: 0.5)) {
            try await runner.run(
                "/bin/sh", ["-c", "/bin/sleep 60 & echo $! > \"$1\"; wait", "sh", pidFile],
                environment: nil, timeout: 0.5)
        }
        #expect(await Self.helperIsGone(pidFile))
    }

    @Test func aChildThatExitsLeavingAHelperOnItsPipesIsStillBoundByTheTimeout() async throws {
        // The shell exits at once, and the sleep it started still holds stdout.
        let pidFile = Self.pidFile()
        defer { try? FileManager.default.removeItem(atPath: pidFile) }
        let started = ContinuousClock.now
        await #expect(throws: ProcessTimeout(executable: "/bin/sh", seconds: 0.5)) {
            try await runner.run(
                "/bin/sh", ["-c", "/bin/sleep 60 & echo $! > \"$1\"; exit 0", "sh", pidFile],
                environment: nil, timeout: 0.5)
        }
        #expect(ContinuousClock.now - started < .seconds(20))
        #expect(await Self.helperIsGone(pidFile))
    }

    @Test func aChildThatExitsAndLeavesNothingBehindReturnsItsOutputBeforeTheTimeout() async throws {
        let result = try await runner.run(
            "/bin/sh", ["-c", "echo done; exit 3"], environment: nil, timeout: 30)
        #expect(result == ProcessResult(status: 3, stdout: "done\n"))
    }

    private static func pidFile() -> String {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon helper \(UUID().uuidString).pid").path
    }

    /// Whether the process whose pid is in `pidFile` is gone, after giving init a moment to reap it.
    /// A helper that is still there is killed so a failing test leaves nothing running.
    private static func helperIsGone(_ pidFile: String) async -> Bool {
        guard let text = try? String(contentsOfFile: pidFile, encoding: .utf8),
            let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines))
        else { return false }
        for _ in 0..<100 {
            if kill(pid, 0) == -1 && errno == ESRCH { return true }
            try? await Task.sleep(for: .milliseconds(50))
        }
        kill(pid, SIGKILL)
        return false
    }

    @Test func aTimeoutDoesNotCutOutputShortOfIt() async throws {
        let result = try await runner.run(
            "/bin/dd", ["if=/dev/zero", "bs=65536", "count=32"], environment: nil, timeout: 60)
        #expect(result.stdout.utf8.count == 2_097_152)
    }
}

@Suite struct FakeProcessRunnerTests {
    @Test func answersFromItsScriptAndRecordsTheCall() async throws {
        let runner = FakeProcessRunner()
        runner.respond(to: "/usr/bin/xcode-select", ["-p"],
                       with: ProcessResult(status: 0, stdout: "/Library/Developer/CommandLineTools\n"))
        let result = try await runner.run("/usr/bin/xcode-select", ["-p"], environment: ["A": "b"])
        #expect(result.stdout == "/Library/Developer/CommandLineTools\n")
        #expect(runner.calls == [.init(executable: "/usr/bin/xcode-select", arguments: ["-p"],
                                       environment: ["A": "b"])])
    }

    @Test func recordsTheTimeoutAndThrowsTheErrorItWasToldTo() async {
        let runner = FakeProcessRunner()
        let timeout = ProcessTimeout(executable: "/bin/sleep", seconds: 5)
        runner.fail("/bin/sleep", ["60"], with: timeout)
        await #expect(throws: timeout) {
            try await runner.run("/bin/sleep", ["60"], environment: nil, timeout: 5)
        }
        #expect(runner.calls == [.init(executable: "/bin/sleep", arguments: ["60"], timeout: 5)])
    }

    @Test func aCallOffTheScriptThrowsAndIsStillRecorded() async {
        let runner = FakeProcessRunner()
        await #expect(throws: FakeProcessRunner.Unscripted(command: ["/usr/bin/xcrun", "--find", "clang"])) {
            try await runner.run("/usr/bin/xcrun", ["--find", "clang"])
        }
        #expect(runner.calls.map(\.arguments) == [["--find", "clang"]])
    }
}
