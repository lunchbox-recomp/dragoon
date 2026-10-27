import Foundation

/// The builds the recipe left in `<data>/game` beside the current one.
public enum OldBuilds {
    /// Removes everything in `<dataDirectory>/game` but `current` and the build it points at,
    /// and returns the names it removed. It removes nothing when `current` doesn't point at a
    /// build, so a missing link never costs the player a game. Run it only while no game and no
    /// build is running.
    @discardableResult
    public static func delete(dataDirectory: String, fs: any FileSystem) -> [String] {
        let games = dataDirectory + "/game"
        let current = games + "/current"
        let target = fs.resolvingSymlinks(at: current)
        guard target != current, fs.isDirectory(at: target),
            (target as NSString).deletingLastPathComponent == fs.resolvingSymlinks(at: games)
        else { return [] }
        let keep: Set = ["current", (target as NSString).lastPathComponent]
        var removed: [String] = []
        for name in (try? fs.contentsOfDirectory(at: games)) ?? [] where !keep.contains(name) {
            if (try? fs.removeItem(at: games + "/" + name)) != nil { removed.append(name) }
        }
        return removed
    }
}
