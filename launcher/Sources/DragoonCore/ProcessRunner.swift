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

/// Runs a process to completion. Arguments go to it as a list, never through a shell, so a
/// path with spaces stays one argument.
public protocol ProcessRunner: Sendable {
    /// Runs `executable`, a full path, with `arguments`. A nil `environment` passes this
    /// process's own. Throws when the executable can't be started.
    func run(_ executable: String, _ arguments: [String], environment: [String: String]?)
        async throws -> ProcessResult
}

extension ProcessRunner {
    public func run(_ executable: String, _ arguments: [String]) async throws -> ProcessResult {
        try await run(executable, arguments, environment: nil)
    }
}

/// The real ProcessRunner, on Foundation's Process.
public struct SystemProcessRunner: ProcessRunner {
    public init() {}

    public func run(_ executable: String, _ arguments: [String], environment: [String: String]?)
        async throws -> ProcessResult
    {
        // Process blocks until its pipes close, so it runs off the concurrency pool.
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global().async {
                continuation.resume(with: Result {
                    try Self.runBlocking(executable, arguments, environment)
                })
            }
        }
    }

    private static func runBlocking(
        _ executable: String, _ arguments: [String], _ environment: [String: String]?
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
        // Both pipes are drained at once, so a child that fills one never waits on the other.
        let errText = Collected()
        let errHandle = err.fileHandleForReading
        let draining = DispatchGroup()
        draining.enter()
        DispatchQueue.global().async {
            errText.data = errHandle.readDataToEndOfFile()
            draining.leave()
        }
        let outData = out.fileHandleForReading.readDataToEndOfFile()
        draining.wait()
        process.waitUntilExit()
        return ProcessResult(
            status: process.terminationStatus,
            stdout: String(decoding: outData, as: UTF8.self),
            stderr: String(decoding: errText.data, as: UTF8.self))
    }
}

/// Written by one thread before the DispatchGroup it leaves is waited on, then read.
private final class Collected: @unchecked Sendable {
    var data = Data()
}
