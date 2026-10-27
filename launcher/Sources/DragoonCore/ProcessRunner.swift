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
    /// process's own. A nil `timeout` waits as long as the process takes, and otherwise a
    /// process still running after that many seconds is killed and `ProcessTimeout` is thrown.
    /// Throws when the executable can't be started.
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

/// The real ProcessRunner, on Foundation's Process.
public struct SystemProcessRunner: ProcessRunner {
    public init() {}

    public func run(
        _ executable: String, _ arguments: [String], environment: [String: String]?,
        timeout: TimeInterval?
    ) async throws -> ProcessResult {
        // Process blocks until its pipes close, so it runs off the concurrency pool.
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global().async {
                continuation.resume(with: Result {
                    try Self.runBlocking(executable, arguments, environment, timeout)
                })
            }
        }
    }

    private static func runBlocking(
        _ executable: String, _ arguments: [String], _ environment: [String: String]?,
        _ timeout: TimeInterval?
    ) throws -> ProcessResult {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        if let environment {
            process.environment = environment
        }
        let out = Pipe()
        let err = Pipe()
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = out
        process.standardError = err
        try process.run()
        let watchdog = Watchdog(process)
        if let timeout { watchdog.arm(after: timeout) }
        // Both pipes are drained at once, so a child that fills one never waits on the other.
        let outText = Collected()
        let errText = Collected()
        let draining = DispatchGroup()
        for (pipe, text) in [(out, outText), (err, errText)] {
            let handle = pipe.fileHandleForReading
            draining.enter()
            DispatchQueue.global().async {
                text.data = handle.readDataToEndOfFile()
                draining.leave()
            }
        }
        process.waitUntilExit()
        if watchdog.disarm() {
            // Anything the child started that still holds a pipe can't keep this waiting long.
            _ = draining.wait(timeout: .now() + 1)
            throw ProcessTimeout(executable: executable, seconds: timeout ?? 0)
        }
        draining.wait()
        return ProcessResult(
            status: process.terminationStatus,
            stdout: String(decoding: outText.data, as: UTF8.self),
            stderr: String(decoding: errText.data, as: UTF8.self))
    }
}

/// Written by one thread before the DispatchGroup it leaves is waited on, then read.
private final class Collected: @unchecked Sendable {
    var data = Data()
}

/// Kills a process that is still running when its timer fires.
private final class Watchdog: @unchecked Sendable {
    private let lock = NSLock()
    private let process: Process
    private var timer: DispatchWorkItem?
    private var finished = false
    private var killed = false

    init(_ process: Process) {
        self.process = process
    }

    func arm(after seconds: TimeInterval) {
        let timer = DispatchWorkItem { [self] in fire() }
        lock.withLock { self.timer = timer }
        DispatchQueue.global().asyncAfter(deadline: .now() + seconds, execute: timer)
    }

    /// Stops the timer, and says whether it already killed the process.
    func disarm() -> Bool {
        lock.withLock {
            finished = true
            timer?.cancel()
            return killed
        }
    }

    private func fire() {
        lock.withLock {
            guard !finished, process.isRunning else { return }
            killed = true
            let pid = process.processIdentifier
            // A child that leads its own process group takes the helpers it started with it.
            if getpgid(pid) == pid {
                killpg(pid, SIGKILL)
            } else {
                kill(pid, SIGKILL)
            }
        }
    }
}
