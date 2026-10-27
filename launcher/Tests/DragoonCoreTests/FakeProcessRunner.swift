import DragoonCore
import Foundation

/// A ProcessRunner for tests that answers from a script and records every call.
final class FakeProcessRunner: ProcessRunner, @unchecked Sendable {
    struct Call: Equatable {
        var executable: String
        var arguments: [String]
        var environment: [String: String]?
        var timeout: TimeInterval?

        init(
            executable: String, arguments: [String], environment: [String: String]? = nil,
            timeout: TimeInterval? = nil
        ) {
            self.executable = executable
            self.arguments = arguments
            self.environment = environment
            self.timeout = timeout
        }
    }

    /// A call the script has no answer for.
    struct Unscripted: Error, Equatable {
        var command: [String]
    }

    private let lock = NSLock()
    private var script: [[String]: Result<ProcessResult, any Error>] = [:]
    private var recorded: [Call] = []

    /// Every call so far, in order.
    var calls: [Call] { lock.withLock { recorded } }

    func respond(to executable: String, _ arguments: [String], with result: ProcessResult) {
        lock.withLock { script[[executable] + arguments] = .success(result) }
    }

    /// Makes a call throw `error`, as the real runner does when it can't start the executable or
    /// when the process outlasts its timeout.
    func fail(_ executable: String, _ arguments: [String], with error: any Error) {
        lock.withLock { script[[executable] + arguments] = .failure(error) }
    }

    func run(
        _ executable: String, _ arguments: [String], environment: [String: String]?,
        timeout: TimeInterval?
    ) async throws -> ProcessResult {
        try lock.withLock {
            recorded.append(
                Call(executable: executable, arguments: arguments, environment: environment,
                     timeout: timeout))
            guard let answer = script[[executable] + arguments] else {
                throw Unscripted(command: [executable] + arguments)
            }
            return try answer.get()
        }
    }
}
