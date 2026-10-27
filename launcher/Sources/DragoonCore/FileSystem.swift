import Foundation

/// The file operations the launcher makes. Paths are full POSIX paths.
public protocol FileSystem: Sendable {
    /// Whether anything is at `path`, following symlinks.
    func fileExists(at path: String) -> Bool
    /// Whether a directory is at `path`, following symlinks.
    func isDirectory(at path: String) -> Bool
    /// The names in the directory at `path`, sorted.
    func contentsOfDirectory(at path: String) throws -> [String]
    /// `path` with every symlink in it resolved, or `path` itself when nothing is there.
    func resolvingSymlinks(at path: String) -> String
    func readData(at path: String) throws -> Data
    /// Replaces the file at `path` whole or not at all, making its directory first.
    func writeData(_ data: Data, to path: String) throws
    /// Removes the file or link at `path`, or the directory and everything in it. A link goes
    /// without what it points to. Throws when nothing is there.
    func removeItem(at path: String) throws
}

/// The real FileSystem, on FileManager.
public struct SystemFileSystem: FileSystem {
    public init() {}

    public func fileExists(at path: String) -> Bool {
        FileManager.default.fileExists(atPath: path)
    }

    public func isDirectory(at path: String) -> Bool {
        var isDirectory: ObjCBool = false
        return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
            && isDirectory.boolValue
    }

    public func contentsOfDirectory(at path: String) throws -> [String] {
        try FileManager.default.contentsOfDirectory(atPath: path).sorted()
    }

    public func resolvingSymlinks(at path: String) -> String {
        // realpath(3) rather than URL's resolvingSymlinksInPath, which drops a leading
        // /private and so names /var/folders where the file is in /private/var/folders.
        guard let resolved = realpath(path, nil) else { return path }
        defer { free(resolved) }
        return String(cString: resolved)
    }

    public func readData(at path: String) throws -> Data {
        try Data(contentsOf: URL(fileURLWithPath: path))
    }

    public func writeData(_ data: Data, to path: String) throws {
        let url = URL(fileURLWithPath: path)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: url, options: .atomic)
    }

    public func removeItem(at path: String) throws {
        try FileManager.default.removeItem(atPath: path)
    }
}
