import Foundation

/// A file open for reading at any offset, so a big file is read a piece at a time.
public protocol FileReader: Sendable {
    /// The `count` bytes at `offset`. Fewer come back only when the file ends first, and none
    /// when `offset` is at or past the end.
    func read(at offset: UInt64, count: Int) throws -> Data
}

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
    /// Opens the file at `path` for reading, which throws when nothing readable is there.
    func openReader(at path: String) throws -> any FileReader
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

    public func openReader(at path: String) throws -> any FileReader {
        try SystemFileReader(path: path)
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

/// A file opened with open(2) and read with pread(2), which takes its offset as an argument.
/// Reads share no position, so two at once can't disturb each other.
private final class SystemFileReader: FileReader {
    private let descriptor: Int32

    init(path: String) throws {
        descriptor = open(path, O_RDONLY | O_CLOEXEC)
        if descriptor < 0 { throw Self.error(errno) }
    }

    deinit { close(descriptor) }

    func read(at offset: UInt64, count: Int) throws -> Data {
        guard count > 0, offset <= UInt64(Int64.max) - UInt64(count) else { return Data() }
        var data = Data(count: count)
        var filled = 0
        while filled < count {
            let (got, failure) = data.withUnsafeMutableBytes { buffer in
                let got = pread(
                    descriptor, buffer.baseAddress! + filled, count - filled,
                    off_t(offset) + off_t(filled))
                return (got, errno)
            }
            if got < 0 {
                if failure == EINTR { continue }
                throw Self.error(failure)
            }
            if got == 0 { break }
            filled += got
        }
        data.count = filled
        return data
    }

    private static func error(_ code: Int32) -> POSIXError {
        POSIXError(POSIXErrorCode(rawValue: code) ?? .EIO)
    }
}
