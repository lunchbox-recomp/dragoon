import DragoonCore
import Foundation

/// An in-memory FileSystem for tests. Add files, directories and symlinks, then hand it to the
/// code under test. Symlink targets may be relative to the link's directory, as real ones are.
final class FakeFileSystem: FileSystem, @unchecked Sendable {
    private let lock = NSLock()
    private var files: [String: Data] = [:]
    private var directories: Set<String> = ["/"]
    private var links: [String: String] = [:]

    func addDirectory(_ path: String) {
        lock.withLock { makeDirectories(path) }
    }

    func addFile(_ path: String, _ data: Data = Data()) {
        lock.withLock {
            makeDirectories(Self.parent(path))
            files[path] = data
        }
    }

    func addSymlink(_ path: String, to target: String) {
        lock.withLock {
            makeDirectories(Self.parent(path))
            links[path] = target
        }
    }

    func fileExists(at path: String) -> Bool {
        lock.withLock { exists(resolve(path)) }
    }

    func isDirectory(at path: String) -> Bool {
        lock.withLock { directories.contains(resolve(path)) }
    }

    func contentsOfDirectory(at path: String) throws -> [String] {
        try lock.withLock {
            let directory = resolve(path)
            guard directories.contains(directory) else { throw CocoaError(.fileReadNoSuchFile) }
            let prefix = directory == "/" ? "/" : directory + "/"
            let everything = Set(files.keys).union(directories).union(links.keys)
            return everything
                .filter { $0.hasPrefix(prefix) && $0 != directory }
                .map { String($0.dropFirst(prefix.count)) }
                .filter { !$0.contains("/") }
                .sorted()
        }
    }

    func resolvingSymlinks(at path: String) -> String {
        lock.withLock {
            let resolved = resolve(path)
            return exists(resolved) ? resolved : path
        }
    }

    func readData(at path: String) throws -> Data {
        try lock.withLock {
            guard let data = files[resolve(path)] else { throw CocoaError(.fileReadNoSuchFile) }
            return data
        }
    }

    func writeData(_ data: Data, to path: String) throws {
        lock.withLock {
            let resolved = resolve(path)
            makeDirectories(Self.parent(resolved))
            files[resolved] = data
        }
    }

    private func exists(_ path: String) -> Bool {
        files[path] != nil || directories.contains(path)
    }

    private func makeDirectories(_ path: String) {
        var current = ""
        for part in path.split(separator: "/") {
            current += "/" + part
            directories.insert(current)
        }
    }

    /// PATH with each symlink along it replaced by its target, as realpath(3) does.
    private func resolve(_ path: String) -> String {
        var resolved: [String] = []
        var remaining = path.split(separator: "/").map(String.init)
        var hops = 0
        while !remaining.isEmpty {
            let part = remaining.removeFirst()
            if part == "." { continue }
            if part == ".." {
                _ = resolved.popLast()
                continue
            }
            let next = "/" + (resolved + [part]).joined(separator: "/")
            if let target = links[next], hops < 32 {
                hops += 1
                if target.hasPrefix("/") { resolved = [] }
                remaining = target.split(separator: "/").map(String.init) + remaining
            } else {
                resolved.append(part)
            }
        }
        return "/" + resolved.joined(separator: "/")
    }

    private static func parent(_ path: String) -> String {
        (path as NSString).deletingLastPathComponent
    }
}
