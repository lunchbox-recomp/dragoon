import Foundation

/// What a finished process printed, and how it ended.
public struct ProcessResult: Equatable, Sendable {
    /// The exit code, or the signal number when a signal ended it.
    public var status: Int32
    public var stdout: String
    public var stderr: String

    public init(status: Int32, stdout: String = "", stderr: String = "") {
        self.status = status
        self.stdout = stdout
        self.stderr = stderr
    }
}

/// What a process that outlasted its timeout leaves behind. It was killed.
public struct ProcessTimeout: Error, Equatable, Sendable {
    public var executable: String
    public var seconds: TimeInterval

    public init(executable: String, seconds: TimeInterval) {
        self.executable = executable
        self.seconds = seconds
    }
}

/// Runs a process to completion. Arguments go to it as a list, never through a shell, so a
/// path with spaces stays one argument.
public protocol ProcessRunner: Sendable {
    /// Runs `executable`, a full path, with `arguments`. A nil `environment` passes this
    /// process's own. A nil `timeout` waits as long as the process takes. Otherwise a process
    /// still running after that many seconds, or one that has left something running that
    /// still holds its output open, is killed with its helpers and `ProcessTimeout` is thrown.
    /// Cancelling the calling task stops the process and its helpers with SIGTERM, then SIGKILL
    /// 10 seconds later if any are left, and throws `CancellationError` once they are gone.
    /// Throws when the executable can't be started or its exit can't be collected.
    func run(
        _ executable: String, _ arguments: [String], environment: [String: String]?,
        timeout: TimeInterval?
    ) async throws -> ProcessResult
}

extension ProcessRunner {
    public func run(_ executable: String, _ arguments: [String], environment: [String: String]?)
        async throws -> ProcessResult
    {
        try await run(executable, arguments, environment: environment, timeout: nil)
    }

    public func run(_ executable: String, _ arguments: [String]) async throws -> ProcessResult {
        try await run(executable, arguments, environment: nil, timeout: nil)
    }
}

/// The real ProcessRunner. Each process leads a process group of its own, which is what a
/// timeout or a cancelled task stops.
public struct SystemProcessRunner: ProcessRunner {
    private let killGrace: TimeInterval

    /// `killGrace` is the seconds between the SIGTERM and the SIGKILL of a cancelled run, which
    /// is 10 unless a test shortens it.
    public init(killGrace: TimeInterval? = nil) {
        self.killGrace = killGrace ?? ProcessGroup.killGrace
    }

    public func run(
        _ executable: String, _ arguments: [String], environment: [String: String]?,
        timeout: TimeInterval?
    ) async throws -> ProcessResult {
        let out = Collected()
        let err = Collected()
        let outcome = try await ProcessGroup.run(
            executable, arguments, environment: environment, timeout: timeout,
            killGrace: killGrace, onStdout: out.append, onStderr: err.append)
        if outcome.timedOut {
            throw ProcessTimeout(executable: executable, seconds: timeout ?? 0)
        }
        if outcome.cancelled { throw CancellationError() }
        return ProcessResult(
            status: outcome.status, stdout: out.text, stderr: err.text)
    }
}

/// What one pipe delivered. Appended to by that pipe's reader thread.
private final class Collected: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()

    @Sendable func append(_ more: Data) {
        lock.withLock { data.append(more) }
    }

    var text: String {
        lock.withLock { String(decoding: data, as: UTF8.self) }
    }
}
