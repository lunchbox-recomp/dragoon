@testable import DragoonCore
import Foundation
import Testing

/// Cancelling the task that waits on a process stops the process and everything it started, for
/// the runner the tools check uses as much as for the one the build uses.
@Suite struct ProcessGroupTests {
    /// The start of a shell script that writes its pid to its first argument and a helper's to
    /// its second. The tests add what follows, which is `wait` for the helper.
    private let hanging = """
        echo $$ > "$1"
        /bin/sleep 30 &
        echo $! > "$2"

        """

    private struct Files {
        var pid: String
        var helper: String
        var note: String
        var directory: String
    }

    private func scratch() throws -> Files {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon group tests \(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return Files(
            pid: directory.path + "/pid.txt", helper: directory.path + "/helper pid.txt",
            note: directory.path + "/note.txt", directory: directory.path)
    }

    @Test func theGraceBetweenSigtermAndSigkillIsTenSeconds() {
        #expect(ProcessGroup.killGrace == 10)
    }

    @Test func cancellingARunStopsTheChildAndItsHelpers() async throws {
        let files = try scratch()
        defer { try? FileManager.default.removeItem(atPath: files.directory) }
        let started = ContinuousClock.now
        let task = Task {
            try await SystemProcessRunner().run(
                "/bin/sh", ["-c", hanging + "wait", "sh", files.pid, files.helper])
        }
        let helper = try #require(await Processes.waitForPid(inFile: files.helper))
        let pgid = try #require(Processes.pid(inFile: files.pid))
        defer { Processes.killGroup(pgid) }

        task.cancel()
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(ContinuousClock.now - started < .seconds(8))
        #expect(await Processes.eventually { !Processes.groupExists(pgid) })
        #expect(await Processes.eventually { !Processes.exists(helper) })
    }

    @Test func aCancelledRunGetsSigtermBeforeAnythingStrongerSoItCanCleanUp() async throws {
        let files = try scratch()
        defer { try? FileManager.default.removeItem(atPath: files.directory) }
        let script = "trap 'echo got term > \"$3\"; exit 143' TERM\n" + hanging + "wait"
        let task = Task {
            try await SystemProcessRunner().run(
                "/bin/sh", ["-c", script, "sh", files.pid, files.helper, files.note])
        }
        _ = try #require(await Processes.waitForPid(inFile: files.helper))
        let pgid = try #require(Processes.pid(inFile: files.pid))
        defer { Processes.killGroup(pgid) }

        task.cancel()
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(try String(contentsOfFile: files.note, encoding: .utf8) == "got term\n")
    }

    @Test func aRunThatIgnoresSigtermIsKilledOnceTheGraceRunsOut() async throws {
        let files = try scratch()
        defer { try? FileManager.default.removeItem(atPath: files.directory) }
        let script = "trap '' TERM\n" + hanging + "wait"
        let task = Task {
            try await SystemProcessRunner(killGrace: 1.5).run(
                "/bin/sh", ["-c", script, "sh", files.pid, files.helper])
        }
        _ = try #require(await Processes.waitForPid(inFile: files.helper))
        let pgid = try #require(Processes.pid(inFile: files.pid))
        defer { Processes.killGroup(pgid) }
        let cancelled = ContinuousClock.now
        task.cancel()

        try await Task.sleep(for: .milliseconds(300))
        #expect(Processes.groupExists(pgid))
        let gone = await Processes.eventually(timeout: 8) { !Processes.groupExists(pgid) }
        #expect(gone)
        // With no SIGKILL the task would wait for good, so a failing run ends the group here.
        Processes.killGroup(pgid)
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(ContinuousClock.now - cancelled >= .milliseconds(1400))
    }

    @Test func aTaskCancelledBeforeItStartsARunRunsNothing() async throws {
        let files = try scratch()
        defer { try? FileManager.default.removeItem(atPath: files.directory) }
        let task = Task {
            while !Task.isCancelled { await Task.yield() }
            return try await SystemProcessRunner().run(
                "/bin/sh", ["-c", "echo started > \"$1\"", "sh", files.note])
        }
        task.cancel()
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(!FileManager.default.fileExists(atPath: files.note))
    }

    @Test func cancellingTheToolsCheckStopsTheCommandItIsWaitingOn() async throws {
        let files = try scratch()
        defer { try? FileManager.default.removeItem(atPath: files.directory) }
        // The first command the check runs becomes a long wait that starts a helper.
        let runner = Stalling(script: hanging + "wait", files: [files.pid, files.helper])
        let started = ContinuousClock.now
        let check = Task { await Toolchain.detect(runner: runner, fs: FakeFileSystem()) }
        let helper = try #require(await Processes.waitForPid(inFile: files.helper))
        let pgid = try #require(Processes.pid(inFile: files.pid))
        defer { Processes.killGroup(pgid) }

        check.cancel()
        let status = await check.value
        #expect(ContinuousClock.now - started < .seconds(8))
        #expect(status == .missing)
        #expect(await Processes.eventually { !Processes.groupExists(pgid) })
        #expect(await Processes.eventually { !Processes.exists(helper) })
        #expect(runner.commands == 1)
    }
}

/// Runs the script in place of whatever command it's asked for, on the real runner, and counts
/// the commands it was asked for.
private final class Stalling: ProcessRunner, @unchecked Sendable {
    private let inner = SystemProcessRunner(killGrace: 0.5)
    private let script: String
    private let files: [String]
    private let lock = NSLock()
    private var asked = 0

    init(script: String, files: [String]) {
        self.script = script
        self.files = files
    }

    var commands: Int { lock.withLock { asked } }

    func run(
        _ executable: String, _ arguments: [String], environment: [String: String]?,
        timeout: TimeInterval?
    ) async throws -> ProcessResult {
        lock.withLock { asked += 1 }
        return try await inner.run(
            "/bin/sh", ["-c", script, "sh"] + files, environment: nil, timeout: timeout)
    }
}
