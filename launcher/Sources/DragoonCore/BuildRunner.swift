import Foundation

/// What one build needs. The recipe and the engine kit are read from the app bundle, where
/// `bundle-manifest.txt` puts them.
public struct BuildRequest: Equatable, Sendable {
    public var toolchain: Toolchain
    /// The app bundle, `Dragoon.app`.
    public var bundle: String
    /// The player's disc image.
    public var disc: String
    public var data: String
    public var cache: String
    /// Skips the shader warm-up, which is the recipe's `--no-warmup`.
    public var noWarmup: Bool
    /// Keeps `<cache>/build`, which is the recipe's `--keep-build`.
    public var keepBuild: Bool

    public init(
        toolchain: Toolchain, bundle: String, disc: String,
        data: String = Toolchain.defaultDataDirectory,
        cache: String = Toolchain.defaultCacheDirectory, noWarmup: Bool = false,
        keepBuild: Bool = false
    ) {
        self.toolchain = toolchain
        self.bundle = bundle
        self.disc = disc
        self.data = data
        self.cache = cache
        self.noWarmup = noWarmup
        self.keepBuild = keepBuild
    }

    var source: String { bundle + "/Contents/Resources/source" }
    var kit: String { bundle + "/Contents/Resources/kit" }
    var recipe: String { source + "/tools/launcher_build.py" }

    /// What follows the python3 on the command line. `-B` keeps `__pycache__` out of the signed
    /// bundle.
    func arguments(log: String) -> [String] {
        var arguments = [
            "-B", recipe,
            "--source", source, "--kit", kit, "--disc", disc, "--data", data, "--cache", cache,
            "--make", toolchain.make, "--cc", toolchain.clang, "--cxx", toolchain.clangxx,
            "--python", toolchain.python3, "--sdk", toolchain.sdk, "--log", log,
        ]
        if noWarmup { arguments.append("--no-warmup") }
        if keepBuild { arguments.append("--keep-build") }
        return arguments
    }
}

/// One line of the recipe's JSON output.
public enum BuildEvent: Equatable, Sendable {
    /// A step began. The steps are recompile, compile, warmup, package and swap.
    case step(String)
    case progress(step: String, done: Int, total: Int)
    /// The new game is current, at `game`.
    case done(game: String)
    /// A step failed. The stream ends with `BuildFailure.failed` right after it. Nothing else
    /// yields this: an error the recipe reports as it refuses its arguments or finds another build
    /// running is left to `BuildFailure.refused` or `alreadyRunning`.
    case error(step: String, message: String, log: String)
}

extension BuildEvent {
    /// The event a line of stdout holds, or nil when the line isn't a JSON object the recipe
    /// prints.
    init?(line: String) {
        guard
            let object = try? JSONSerialization.jsonObject(with: Data(line.utf8))
                as? [String: Any],
            let kind = object["event"] as? String
        else { return nil }
        switch kind {
        case "step":
            guard let step = object["step"] as? String else { return nil }
            self = .step(step)
        case "progress":
            guard let step = object["step"] as? String, let done = object["done"] as? Int,
                let total = object["total"] as? Int
            else { return nil }
            self = .progress(step: step, done: done, total: total)
        case "done":
            guard let game = object["game"] as? String else { return nil }
            self = .done(game: game)
        case "error":
            guard let step = object["step"] as? String, let message = object["message"] as? String,
                let log = object["log"] as? String
            else { return nil }
            self = .error(step: step, message: message, log: log)
        default:
            return nil
        }
    }
}

/// Why a build's stream ended without the new game being current. The texts are drafts.
public enum BuildFailure: Error, Equatable, Sendable {
    /// Another build holds the recipe's lock, so this one touched nothing.
    case alreadyRunning
    /// The recipe refused its arguments, or the engine kit that came with the source.
    case refused(message: String, log: String)
    /// A step failed, or the recipe ended in a way it didn't explain, in which case `step` is nil.
    case failed(step: String?, message: String, log: String)
    /// `cancel()` stopped it.
    case cancelled
    /// The recipe's python3 couldn't be started.
    case couldNotStart(String)
}

extension BuildFailure: LocalizedError {
    public var message: String {
        switch self {
        case .alreadyRunning:
            return "a build is already running"
        case .refused(let message, let log), .failed(_, let message, let log):
            return "\(message). The log is at \(log)."
        case .cancelled:
            return "the build was cancelled"
        case .couldNotStart(let reason):
            return "the build couldn't be started: \(reason)"
        }
    }

    public var errorDescription: String? { message }
}

/// Runs the Python build recipe, `<bundle>/Contents/Resources/source/tools/launcher_build.py`,
/// as a process group of its own, so the recipe, make, clang and the warm-up's game all stop
/// together.
public final class BuildRunner: @unchecked Sendable {
    /// How many `build-*.log` files are kept, the newest.
    public static let keptLogs = 10

    public static var defaultLogDirectory: String {
        NSHomeDirectory() + "/Library/Logs/Dragoon"
    }

    private let fs: any FileSystem
    private let logDirectory: String
    let killGrace: TimeInterval
    private let now: @Sendable () -> Date
    private let lock = NSLock()
    private var current: Task<Void, Never>?

    /// `killGrace` is the seconds between the SIGTERM and the SIGKILL of a cancelled build, which
    /// is 10 unless a test shortens it.
    public init(
        fs: any FileSystem = SystemFileSystem(), logDirectory: String = BuildRunner.defaultLogDirectory,
        killGrace: TimeInterval? = nil, now: @escaping @Sendable () -> Date = { Date() }
    ) {
        self.fs = fs
        self.logDirectory = logDirectory
        self.killGrace = killGrace ?? ProcessGroup.killGrace
        self.now = now
    }

    /// Starts the build, which runs whether or not anyone is iterating yet. The stream ends
    /// normally once the new game is current, and with a `BuildFailure` when it isn't. Dropping
    /// or cancelling the stream cancels the build, as `cancel()` does. While a build is running
    /// this starts nothing: its stream throws `alreadyRunning` and `cancel()` still stops the
    /// build that is running.
    ///
    /// The recipe's `--log` is `build-<time>.log` in the log directory. Its stdout lines that
    /// aren't events and everything on its stderr go in that log too, beside what the recipe
    /// writes, and the newest `keptLogs` logs stay.
    public func run(_ request: BuildRequest) -> AsyncThrowingStream<BuildEvent, Error> {
        AsyncThrowingStream { continuation in
            // The task is made under the lock, so it can't end before it is recorded.
            let started: Task<Void, Never>? = lock.withLock {
                guard current == nil else { return nil }
                let task = Task {
                    let failure = await perform(request, continuation)
                    // Cleared before the stream ends, so a run right after it is accepted.
                    lock.withLock { current = nil }
                    continuation.finish(throwing: failure)
                }
                current = task
                return task
            }
            guard let task = started else {
                continuation.finish(throwing: BuildFailure.alreadyRunning)
                return
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// Stops the running build's process group with SIGTERM, then with SIGKILL 10 seconds later if
    /// anything is left. The stream ends with `BuildFailure.cancelled` once the group is gone,
    /// unless the recipe finished first.
    public func cancel() {
        lock.withLock { current }?.cancel()
    }

    private func perform(
        _ request: BuildRequest, _ continuation: AsyncThrowingStream<BuildEvent, Error>.Continuation
    ) async -> BuildFailure? {
        let logName = "build-" + Self.stamp(now()) + ".log"
        let logPath = logDirectory + "/" + logName
        let fs = fs
        // A log that can't be written to doesn't stop the build.
        let write = { @Sendable (line: String) -> Void in
            _ = try? fs.appendData(Data((line + "\n").utf8), to: logPath)
        }
        let state = RunState()
        let stdout = LineSplitter { line in
            if let event = BuildEvent(line: line) {
                // An error waits for the exit code, which says whether the stream should show it.
                if case .error = event { state.note(event) } else { continuation.yield(event) }
            } else if !line.isEmpty {
                write("[stdout] " + line)
            }
        }
        let stderr = LineSplitter { line in
            guard !line.isEmpty else { return }
            state.noteStderr(line)
            write("[stderr] " + line)
        }

        let failure: BuildFailure?
        do {
            let outcome = try await ProcessGroup.run(
                request.toolchain.python3, request.arguments(log: logPath),
                environment: Self.environment(for: request.toolchain), timeout: nil,
                killGrace: killGrace, onStdout: stdout.feed, onStderr: stderr.feed)
            stdout.flush()
            stderr.flush()
            failure = Self.failure(for: outcome, state, logPath, write, yield: { continuation.yield($0) })
        } catch is CancellationError {
            failure = .cancelled
        } catch let lost as ProcessWaitFailure {
            stdout.flush()
            stderr.flush()
            let message = "the recipe's exit couldn't be read (error \(lost.code))"
            write("[launcher] " + message)
            failure = .failed(step: nil, message: message, log: logPath)
        } catch {
            failure = .couldNotStart(error.localizedDescription)
        }
        pruneLogs(keeping: logName)
        return failure
    }

    /// The recipe's own tools get a fixed PATH from the recipe. This keeps what the player's
    /// shell has, such as PYTHONPATH or Homebrew's directories, out of the recipe's Python.
    static func environment(for toolchain: Toolchain) -> [String: String] {
        [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": NSHomeDirectory(),
            "TMPDIR": NSTemporaryDirectory(),
            "LANG": "en_US.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "DEVELOPER_DIR": toolchain.developerDirectory,
        ]
    }

    /// Nil when the new game is current. Otherwise why not, from the recipe's exit code.
    private static func failure(
        for outcome: ProcessGroupOutcome, _ state: RunState, _ logPath: String,
        _ write: @Sendable (String) -> Void, yield: (BuildEvent) -> Void
    ) -> BuildFailure? {
        if !outcome.signaled && outcome.status == 0 { return nil }
        if outcome.cancelled { return .cancelled }
        // The log gets a line for an ending the recipe didn't explain, so the log it names does.
        func unexplained(_ message: String) -> BuildFailure {
            write("[launcher] " + message)
            return .failed(step: nil, message: message, log: logPath)
        }
        if outcome.signaled {
            return unexplained("the recipe was stopped by signal \(outcome.status)")
        }
        let recipeError = state.recipeError
        switch outcome.status {
        case 1:
            if let recipeError {
                yield(.error(
                    step: recipeError.step, message: recipeError.message, log: recipeError.log))
                return .failed(
                    step: recipeError.step, message: recipeError.message, log: recipeError.log)
            }
            return unexplained("the build stopped without saying why")
        case 2:
            let message =
                recipeError?.message ?? state.lastStderr ?? "the recipe refused its arguments"
            return .refused(message: message, log: logPath)
        case 3:
            return .alreadyRunning
        default:
            return unexplained("the recipe ended with status \(outcome.status)")
        }
    }

    /// Removes all but the newest `keptLogs` files named `build-*.log`. This build's log is
    /// kept even if a clock set back makes it look old, and it counts as one of the newest.
    private func pruneLogs(keeping current: String) {
        let logs = ((try? fs.contentsOfDirectory(at: logDirectory)) ?? [])
            .filter { $0.hasPrefix("build-") && $0.hasSuffix(".log") }
            .sorted()
        let room = Self.keptLogs - (logs.contains(current) ? 1 : 0)
        for name in logs.filter({ $0 != current }).dropLast(room) {
            try? fs.removeItem(at: logDirectory + "/" + name)
        }
    }

    /// UTC, so names sort by time even across a change of clocks, with no colons.
    static func stamp(_ date: Date) -> String {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.timeZone = TimeZone(identifier: "UTC")
        format.dateFormat = "yyyy-MM-dd'T'HH-mm-ss.SSS'Z'"
        return format.string(from: date)
    }
}

/// What the two output threads learned, for the exit code to be read against.
private final class RunState: @unchecked Sendable {
    struct RecipeError {
        var step: String
        var message: String
        var log: String
    }

    private let lock = NSLock()
    private var error: RecipeError?
    private var stderrLine: String?

    var recipeError: RecipeError? { lock.withLock { error } }
    var lastStderr: String? { lock.withLock { stderrLine } }

    func note(_ event: BuildEvent) {
        guard case .error(let step, let message, let log) = event else { return }
        lock.withLock { error = RecipeError(step: step, message: message, log: log) }
    }

    func noteStderr(_ line: String) {
        lock.withLock { stderrLine = line }
    }
}

/// Cuts what a pipe delivers into lines. A last line with no newline counts when `flush` is called.
private final class LineSplitter: @unchecked Sendable {
    private let lock = NSLock()
    private let handle: @Sendable (String) -> Void
    private var pending = Data()

    init(_ handle: @escaping @Sendable (String) -> Void) {
        self.handle = handle
    }

    @Sendable func feed(_ data: Data) {
        let lines: [String] = lock.withLock {
            pending.append(data)
            var lines: [String] = []
            var start = pending.startIndex
            while let newline = pending[start...].firstIndex(of: 0x0A) {
                lines.append(Self.text(pending[start..<newline]))
                start = newline + 1
            }
            pending.removeSubrange(pending.startIndex..<start)
            return lines
        }
        lines.forEach(handle)
    }

    func flush() {
        let rest: Data = lock.withLock {
            defer { pending = Data() }
            return pending
        }
        if !rest.isEmpty { handle(Self.text(rest)) }
    }

    private static func text(_ bytes: Data) -> String {
        var line = String(decoding: bytes, as: UTF8.self)
        if line.hasSuffix("\r") { line.removeLast() }
        return line
    }
}
