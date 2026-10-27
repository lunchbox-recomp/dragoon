import Foundation

/// How the game's process ended.
public enum GameExit: Equatable, Sendable {
    /// It exited with this code, which is 0 for a clean exit.
    case status(Int32)
    /// This signal stopped it.
    case signal(Int32)

    /// The signal's name as macOS spells it, such as SIGSEGV, or nil for an exit code or a
    /// number macOS has no name for.
    public var signalName: String? {
        guard case .signal(let number) = self, number > 0, number < NSIG else { return nil }
        // sys_signame is the C library's table of names, such as "segv", indexed by number.
        let name = withUnsafeBytes(of: sys_signame) { table in
            table.load(
                fromByteOffset: Int(number) * MemoryLayout<UnsafePointer<CChar>?>.stride,
                as: UnsafePointer<CChar>?.self)
        }
        return name.map { "SIG" + String(cString: $0).uppercased() }
    }
}

/// Why the game couldn't be started.
public enum GameStartFailure: Equatable, Sendable {
    /// Nothing is at the game's executable, `path`.
    case missing(path: String)
    /// The process couldn't be started, for the reason the system gave.
    case failed(reason: String)
}

/// How one launch of the game ended.
public enum GameResult: Equatable, Sendable {
    /// The game ran and ended. `panic` is the text of the `panic.txt` the runtime wrote, which is
    /// read only after an ending that isn't a clean exit.
    case exited(GameExit, panic: String?)
    case couldNotStart(GameStartFailure)
}

/// One launch of the game. It gives exactly one result, once the game has ended or couldn't
/// start, and then finishes.
public typealias GameSession = AsyncStream<GameResult>

/// Starts the game the recipe built, with `Process`.
public final class GameLauncher: Sendable {
    /// What the runtime writes in its working directory when the game panics.
    static let panicName = "panic.txt"

    private let fs: any FileSystem
    private let logFolder: String
    private let now: @Sendable () -> Date

    public init(
        fs: any FileSystem = SystemFileSystem(), logFolder: String = LogFolder.defaultPath,
        now: @escaping @Sendable () -> Date = { Date() }
    ) {
        self.fs = fs
        self.logFolder = logFolder
        self.now = now
    }

    /// Starts `<game>/Contents/MacOS/dragoon`, where `game` is the built `Dragoon.app`. The disc
    /// image at `disc` is its one argument and `data` is its working directory, since the runtime
    /// finds `saves/` and writes `panic.txt` relative to that. What it prints on stdout and
    /// stderr goes to `game-<time>.log` in the log folder, and the newest `LogFolder.kept` game
    /// logs stay.
    ///
    /// After an ending that isn't a clean exit, the result carries the text of `<data>/panic.txt`
    /// when there is one, and that file moves to the log folder as `panic-<time>.txt`. A
    /// `panic.txt` that's there before the game starts is an earlier run's, so it moves there
    /// first and is never shown.
    public func play(game: String, disc: String, data: String) -> GameSession {
        let (session, results) = GameSession.makeStream()
        let end = { @Sendable (result: GameResult) in
            results.yield(result)
            results.finish()
        }
        let panic = data + "/" + Self.panicName
        if fs.fileExists(at: panic) { movePanic(panic) }
        let executable = game + "/Contents/MacOS/dragoon"
        guard fs.fileExists(at: executable) else {
            end(.couldNotStart(.missing(path: executable)))
            return session
        }
        let logName = "game-" + LogFolder.stamp(now()) + ".log"
        let log = openLog(logFolder + "/" + logName)
        // The game has its own copy once it's started, or none when it couldn't be.
        defer { try? log?.close() }
        LogFolder.prune(logFolder, kind: "game", keeping: logName, fs: fs)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = [disc]
        process.currentDirectoryURL = URL(fileURLWithPath: data, isDirectory: true)
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = log ?? FileHandle.nullDevice
        process.standardError = log ?? FileHandle.nullDevice
        process.terminationHandler = { [self] ended in
            let ending: GameExit =
                ended.terminationReason == .uncaughtSignal
                ? .signal(ended.terminationStatus) : .status(ended.terminationStatus)
            end(.exited(ending, panic: ending == .status(0) ? nil : takePanic(panic)))
        }
        do {
            try process.run()
        } catch {
            end(.couldNotStart(.failed(reason: error.localizedDescription)))
        }
        return session
    }

    /// The log at `path` opened for appending, with its folder made first, or nil when it can't
    /// be. A log that can't be written doesn't stop the game.
    private func openLog(_ path: String) -> FileHandle? {
        guard (try? fs.appendData(Data(), to: path)) != nil else { return nil }
        let descriptor = open(path, O_WRONLY | O_APPEND | O_CLOEXEC)
        return descriptor < 0 ? nil : FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    }

    /// The text of the `panic.txt` at `path`, which then moves to the log folder, or nil when
    /// there's none.
    private func takePanic(_ path: String) -> String? {
        guard let bytes = try? fs.readData(at: path) else { return nil }
        movePanic(path)
        return String(decoding: bytes, as: UTF8.self)
    }

    /// Moves the `panic.txt` at `path` to the log folder as `panic-<time>.txt`, or as
    /// `panic-<time>-<n>.txt` while that name is taken, so it never replaces another file. It
    /// stays where it is when it can't be moved.
    private func movePanic(_ path: String) {
        let stamp = LogFolder.stamp(now())
        for attempt in 0..<100 {
            let name = "panic-" + stamp + (attempt == 0 ? "" : "-\(attempt)") + ".txt"
            do {
                try fs.moveItem(at: path, to: logFolder + "/" + name)
                return
            } catch let error as POSIXError where error.code == .EEXIST {
                continue
            } catch {
                return
            }
        }
    }
}
