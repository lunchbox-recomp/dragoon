import Foundation

/// The end of a build log, which a failed build shows.
public enum LogTail {
    /// How many lines a failed build shows.
    public static let lineCount = 20

    /// The last `count` lines of the file at `path` that aren't empty, oldest first, or none when
    /// it can't be read.
    public static func lastLines(
        of path: String, count: Int = LogTail.lineCount, fs: any FileSystem
    ) -> [String] {
        guard let data = try? fs.readData(at: path) else { return [] }
        let lines = String(decoding: data, as: UTF8.self)
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        return Array(lines.suffix(count))
    }
}
