import Foundation

/// The folder that holds the launcher's logs, `~/Library/Logs/Dragoon`. Each build writes a
/// `build-<time>.log` there and each run of the game a `game-<time>.log`, and the newest `kept` of
/// each kind stay.
public enum LogFolder {
    /// How many logs of each kind are kept, the newest.
    public static let kept = 10

    public static var defaultPath: String {
        NSHomeDirectory() + "/Library/Logs/Dragoon"
    }

    /// Removes all but the newest `kept` files in `folder` named `<kind>-*.log`. The log named
    /// `current` is kept even if a clock set back makes it look old, and it counts as one of the
    /// newest.
    static func prune(_ folder: String, kind: String, keeping current: String, fs: any FileSystem) {
        let logs = ((try? fs.contentsOfDirectory(at: folder)) ?? [])
            .filter { $0.hasPrefix(kind + "-") && $0.hasSuffix(".log") }
            .sorted()
        let room = kept - (logs.contains(current) ? 1 : 0)
        for name in logs.filter({ $0 != current }).dropLast(room) {
            try? fs.removeItem(at: folder + "/" + name)
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
