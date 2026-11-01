import Foundation

/// `<data>/game.pid`, which names the game a launcher started, so a launcher opened while that
/// game runs knows it's running. The start time tells the game from a later process that has
/// the same pid.
public struct GameRecord: Codable, Sendable {
    static let fileName = "game.pid"

    var pid: Int32
    /// When the game's process started, in microseconds since 1970.
    var started: UInt64

    /// Writes the record of the game running as `pid`. A game that has ended already gets none.
    static func write(pid: pid_t, data: String, fs: any FileSystem) {
        guard let started = LiveProcess.startTime(of: pid) else { return }
        try? fs.writeData(encodeJSON(GameRecord(pid: pid, started: started)), to: path(data))
    }

    static func remove(data: String, fs: any FileSystem) {
        try? fs.removeItem(at: path(data))
    }

    /// The pid of the game the record in `data` names, while that process runs with the record's
    /// start time and with the installed game in `game` as its executable. A record that's
    /// garbled, whose pid is gone, or whose start time or executable differs is removed and
    /// gives nil.
    public static func runningGame(game: String, data: String, fs: any FileSystem) -> pid_t? {
        guard let bytes = try? fs.readData(at: path(data)) else { return nil }
        if let record = try? JSONDecoder().decode(GameRecord.self, from: bytes),
            LiveProcess.startTime(of: record.pid) == record.started,
            LiveProcess.executable(of: record.pid)
                == fs.resolvingSymlinks(at: GameLauncher.executable(in: game))
        {
            return record.pid
        }
        remove(data: data, fs: fs)
        return nil
    }

    private static func path(_ data: String) -> String {
        data + "/" + fileName
    }
}
