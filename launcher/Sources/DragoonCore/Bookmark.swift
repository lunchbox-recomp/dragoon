import Foundation

/// Where a bookmark to the player's disc led.
public enum BookmarkResolution: Equatable, Sendable {
    /// The disc image is at `path`.
    case found(String)
    /// macOS found the file, but says the bookmark is out of date, as it is after a move.
    case stale
    /// Nothing is there, or the drive it was on isn't plugged in.
    case missing
}

/// The launcher keeps a bookmark to the player's disc image rather than a copy of it.
public enum Bookmark {
    public static func make(for path: String) throws -> Data {
        try URL(fileURLWithPath: path).bookmarkData()
    }

    /// Resolves `bookmark` without showing anything or mounting a volume.
    public static func resolve(_ bookmark: Data, fs: any FileSystem) -> BookmarkResolution {
        var stale = false
        guard
            let url = try? URL(
                resolvingBookmarkData: bookmark, options: [.withoutUI, .withoutMounting],
                relativeTo: nil, bookmarkDataIsStale: &stale)
        else { return .missing }
        if stale { return .stale }
        return fs.fileExists(at: url.path) ? .found(url.path) : .missing
    }
}
