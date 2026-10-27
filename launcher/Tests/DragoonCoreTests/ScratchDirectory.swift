import DragoonCore
import Foundation

/// A directory of its own under the temporary directory, never the player's real one. `remove()`
/// deletes it.
struct ScratchDirectory {
    let path: String

    init() throws {
        let made = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon window tests \(UUID().uuidString)")
        try FileManager.default.createDirectory(at: made, withIntermediateDirectories: true)
        path = SystemFileSystem().resolvingSymlinks(at: made.path)
    }

    /// The data directory under it, whose path has the space `Application Support` has.
    var data: String { path + "/Application Support/Dragoon" }

    func remove() {
        try? FileManager.default.removeItem(atPath: path)
    }
}

/// Where the launcher keeps its data on the test player's Mac, for the fake file system.
let fakeData = flowHome + "/Library/Application Support/Dragoon"
