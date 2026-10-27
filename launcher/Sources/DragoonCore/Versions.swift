import Foundation

/// The Dragoon and gcn-recomp commits a source snapshot holds, or a built game was built from.
/// A snapshot's `source-info.json` and a game's `stamp.json` both keep them as `dragoon` and
/// `gcn-recomp`.
public struct Commits: Equatable, Sendable {
    public var dragoon: String
    public var gcnRecomp: String

    public init(dragoon: String, gcnRecomp: String) {
        self.dragoon = dragoon
        self.gcnRecomp = gcnRecomp
    }

    /// The two commits in the JSON file at `path`, or nil when it can't be read or either one
    /// isn't forty of 0-9 and a-f. Any other field is ignored.
    public static func read(at path: String, fs: any FileSystem) -> Commits? {
        guard let data = try? fs.readData(at: path),
            let fields = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
            let dragoon = fields["dragoon"] as? String, isCommit(dragoon),
            let gcnRecomp = fields["gcn-recomp"] as? String, isCommit(gcnRecomp)
        else { return nil }
        return Commits(dragoon: dragoon, gcnRecomp: gcnRecomp)
    }

    private static func isCommit(_ value: String) -> Bool {
        value.utf8.count == 40 && value.utf8.allSatisfy { (0x30...0x39).contains($0) || (0x61...0x66).contains($0) }
    }
}

/// What the app's source snapshot builds: the commits it holds and the disc it needs.
public struct SourceInfo: Equatable, Sendable {
    public var commits: Commits
    public var disc: ExpectedDisc

    public init(commits: Commits, disc: ExpectedDisc) {
        self.commits = commits
        self.disc = disc
    }

    /// The snapshot's `source-info.json` at `path`, or nil when it can't be used.
    public static func read(at path: String, fs: any FileSystem) -> SourceInfo? {
        guard let commits = Commits.read(at: path, fs: fs),
            let disc = try? ExpectedDisc.read(at: path, fs: fs)
        else { return nil }
        return SourceInfo(commits: commits, disc: disc)
    }
}

/// The game the player has built, which `<data>/game/current` points at.
public struct InstalledGame: Equatable, Sendable {
    /// The commits in the game's `stamp.json`, or nil when it can't be read.
    public var stamp: Commits?

    public init(stamp: Commits?) {
        self.stamp = stamp
    }

    /// The game in `<dataDirectory>/game/current`, or nil when there is none.
    public static func read(dataDirectory: String, fs: any FileSystem) -> InstalledGame? {
        let current = dataDirectory + "/game/current"
        guard fs.isDirectory(at: current + "/Dragoon.app") else { return nil }
        return InstalledGame(stamp: Commits.read(at: current + "/stamp.json", fs: fs))
    }
}
