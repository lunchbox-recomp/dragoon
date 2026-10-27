import DragoonCore
import Foundation

/// A scratch directory with spaces in its name that holds a built game, the player's data
/// directory and the logs folder. The game's executable is a shell script a test writes, and
/// `<data>/game/current` links to its build as the recipe's swap leaves it.
final class GameFixture: @unchecked Sendable {
    let root: String

    var data: String { root + "/Library/Application Support/Dragoon" }
    var logs: String { root + "/Library/Logs/Dragoon" }
    var game: String { data + "/game/current/Dragoon.app" }
    var executable: String { game + "/Contents/MacOS/dragoon" }
    var disc: String { root + "/Kirby Air Ride (USA).gcm" }
    var panic: String { data + "/panic.txt" }
    /// Where the fake game writes its arguments, one per line, its working directory and a note.
    var argumentsFile: String { root + "/game arguments.txt" }
    var directoryFile: String { root + "/game directory.txt" }
    var noteFile: String { root + "/note.txt" }

    /// The clock the tests run on, so the names in the logs folder are known. It's 2027-01-15
    /// 08:00:00 UTC.
    static let clock = Date(timeIntervalSince1970: 1_800_000_000)
    static let stamp = "2027-01-15T08-00-00.000Z"
    static let logName = "game-\(stamp).log"
    var logPath: String { logs + "/" + Self.logName }

    init() throws {
        let made = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon game tests \(UUID().uuidString)")
        try FileManager.default.createDirectory(at: made, withIntermediateDirectories: true)
        root = SystemFileSystem().resolvingSymlinks(at: made.path)
        try FileManager.default.createDirectory(
            atPath: data + "/game/build one", withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(
            atPath: data + "/game/current", withDestinationPath: "build one")
    }

    deinit { try? FileManager.default.removeItem(atPath: root) }

    /// Installs `body` as the game. Before it runs, the script writes its arguments and its
    /// working directory.
    func install(_ body: String) throws {
        try installScript(
            """
            printf '%s\\n' "$@" > \(shellWord(argumentsFile))
            /bin/pwd -P > \(shellWord(directoryFile))
            \(body)
            """)
    }

    /// Installs `body` as the whole game, run by sh.
    func installScript(_ body: String) throws {
        try write(executable, "#!/bin/sh\n" + body + "\n")
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable)
    }

    func play() -> GameSession {
        GameLauncher(logFolder: logs, now: { GameFixture.clock })
            .play(game: game, disc: disc, data: data)
    }

    /// The names of the files in the logs folder.
    var logNames: [String] {
        (try? FileManager.default.contentsOfDirectory(atPath: logs))?.sorted() ?? []
    }

    func write(_ path: String, _ text: String) throws {
        try FileManager.default.createDirectory(
            atPath: (path as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
        try Data(text.utf8).write(to: URL(fileURLWithPath: path))
    }

    /// The file at `path` as text, or nil when there's none.
    func text(_ path: String) -> String? {
        try? String(contentsOfFile: path, encoding: .utf8)
    }

    func lines(_ path: String) -> [String] {
        (text(path) ?? "").split(separator: "\n").map(String.init)
    }
}

/// Every result a session gave, in order.
func results(of session: GameSession) async -> [GameResult] {
    var all: [GameResult] = []
    for await result in session { all.append(result) }
    return all
}
