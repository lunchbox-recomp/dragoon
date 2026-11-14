import Foundation

/// What the game's ready file says so far. With `GCN_READY_FILE` set, the engine appends
/// `window <ms>` at the first frame its window shows and `frame <ms>` at the game's first frame,
/// each once, in milliseconds since its process started (gcn-recomp `runtime/ready_file.h`).
/// Without a splash both go in at the game's first frame. An engine from before that writes
/// nothing.
public struct ReadyMarks: Equatable, Sendable {
    /// Milliseconds from the game's start to the first frame its window showed.
    public var window: Int?
    /// Milliseconds from the game's start to the game's own first frame.
    public var frame: Int?

    public init(window: Int? = nil, frame: Int? = nil) {
        self.window = window
        self.frame = frame
    }

    /// Both lines are in, so there's nothing more to wait for.
    public var isComplete: Bool { window != nil && frame != nil }

    /// The marks in `bytes`. Only lines that end in a newline count, so one still being written
    /// waits for the next read. A line that isn't `window` or `frame`, one space and a whole
    /// number of milliseconds is skipped, and the first line for each word is the one kept.
    public static func parse(_ bytes: some Collection<UInt8>) -> ReadyMarks {
        var marks = ReadyMarks()
        var lines = bytes.split(separator: 0x0A, omittingEmptySubsequences: false)
        // What follows the last newline is a line not yet finished, or nothing.
        lines.removeLast()
        for line in lines {
            guard let text = String(bytes: line, encoding: .utf8) else { continue }
            let fields = text.split(separator: " ", omittingEmptySubsequences: false)
            guard fields.count == 2, fields[1].utf8.allSatisfy({ (0x30...0x39).contains($0) }),
                let ms = Int(fields[1])
            else { continue }
            switch fields[0] {
            case "window" where marks.window == nil: marks.window = ms
            case "frame" where marks.frame == nil: marks.frame = ms
            default: continue
            }
        }
        return marks
    }
}

/// The file the launcher hands the game as `GCN_READY_FILE`.
public enum ReadyFile {
    /// The variable the engine reads.
    public static let variable = "GCN_READY_FILE"
    /// The file's name in the data directory.
    public static let name = "ready.txt"
    /// The most of the file that's read. Two lines are under 40 bytes.
    static let limit = 4096

    /// The marks in the file at `path`, or nil when no regular file is there.
    public static func read(at path: String) -> ReadyMarks? {
        RegularFile.read(at: path, limit: limit).map { ReadyMarks.parse($0.bytes) }
    }

    /// Removes the file at `path` and the `.tmp` the engine writes it through, so the next run
    /// starts with neither. An earlier run's file stays until the next run's first line replaces
    /// it, so the launcher removes it first.
    static func remove(_ path: String, fs: any FileSystem) {
        try? fs.removeItem(at: path)
        try? fs.removeItem(at: path + ".tmp")
    }
}
