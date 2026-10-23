import DragoonCore
import Foundation

/// A ProcessRunner for tests that answers from a script and records every call.
final class FakeProcessRunner: ProcessRunner, @unchecked Sendable {
    struct Call: Equatable {
        var executable: String
        var arguments: [String]
        var environment: [String: String]?
    }

    /// A call the script has no answer for.
    struct Unscripted: Error, Equatable {
        var command: [String]
    }

    private let lock = NSLock()
    private var script: [[String]: ProcessResult] = [:]
    private var recorded: [Call] = []

    /// Every call so far, in order.
    var calls: [Call] { lock.withLock { recorded } }

    func respond(to executable: String, _ arguments: [String], with result: ProcessResult) {
        lock.withLock { script[[executable] + arguments] = result }
    }

    func run(_ executable: String, _ arguments: [String], environment: [String: String]?)
        async throws -> ProcessResult
    {
        try lock.withLock {
            recorded.append(Call(executable: executable, arguments: arguments, environment: environment))
            guard let result = script[[executable] + arguments] else {
                throw Unscripted(command: [executable] + arguments)
            }
            return result
        }
    }
}
