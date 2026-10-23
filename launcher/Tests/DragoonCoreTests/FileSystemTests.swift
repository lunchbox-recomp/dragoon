import DragoonCore
import Foundation
import Testing

/// A tree to check a FileSystem against, made on disk for the real one and in memory for the fake.
private protocol Tree {
    var fs: any FileSystem { get }
    var root: String { get }
    func file(_ path: String, _ text: String) throws
    func symlink(_ path: String, to target: String) throws
}

private struct DiskTree: Tree {
    let fs: any FileSystem = SystemFileSystem()
    let root: String

    init() throws {
        let made = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon tests \(UUID().uuidString)")
        try FileManager.default.createDirectory(at: made, withIntermediateDirectories: true)
        root = SystemFileSystem().resolvingSymlinks(at: made.path)
    }

    func file(_ path: String, _ text: String) throws {
        try FileManager.default.createDirectory(
            atPath: (path as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
        try Data(text.utf8).write(to: URL(fileURLWithPath: path))
    }

    func symlink(_ path: String, to target: String) throws {
        try FileManager.default.createSymbolicLink(atPath: path, withDestinationPath: target)
    }
}

private struct MemoryTree: Tree {
    let fake = FakeFileSystem()
    var fs: any FileSystem { fake }
    let root = "/Users/player/Library/Application Support/Dragoon"

    init() { fake.addDirectory(root) }

    func file(_ path: String, _ text: String) throws { fake.addFile(path, Data(text.utf8)) }

    func symlink(_ path: String, to target: String) throws { fake.addSymlink(path, to: target) }
}

enum Kind: String, CaseIterable {
    case real, fake
}

private func makeTree(_ kind: Kind) throws -> any Tree {
    switch kind {
    case .real: return try DiskTree()
    case .fake: return MemoryTree()
    }
}

private func cleanUp(_ tree: any Tree) {
    if tree is DiskTree {
        try? FileManager.default.removeItem(atPath: tree.root)
    }
}

@Suite struct FileSystemTests {
    @Test(arguments: Kind.allCases)
    func writeMakesTheDirectoryAndReplacesWhatWasThere(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        let path = tree.root + "/a dir/toolchain.json"
        try tree.fs.writeData(Data("one".utf8), to: path)
        try tree.fs.writeData(Data("two".utf8), to: path)
        #expect(try tree.fs.readData(at: path) == Data("two".utf8))
        #expect(tree.fs.isDirectory(at: tree.root + "/a dir"))
        #expect(!tree.fs.isDirectory(at: path))
        #expect(tree.fs.fileExists(at: path))
    }

    @Test(arguments: Kind.allCases)
    func aDirectoryListsItsNamesSorted(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        try tree.file(tree.root + "/SDKs/MacOSX27.0.sdk/SDKSettings.json", "{}")
        try tree.file(tree.root + "/SDKs/MacOSX26.5.sdk/SDKSettings.json", "{}")
        try tree.symlink(tree.root + "/SDKs/MacOSX.sdk", to: "MacOSX27.0.sdk")
        #expect(try tree.fs.contentsOfDirectory(at: tree.root + "/SDKs")
                == ["MacOSX.sdk", "MacOSX26.5.sdk", "MacOSX27.0.sdk"])
    }

    @Test(arguments: Kind.allCases)
    func symlinksResolveWhetherRelativeOrAbsolute(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        let sdks = tree.root + "/SDKs"
        try tree.file(sdks + "/MacOSX26.5.sdk/SDKSettings.json", "{}")
        try tree.symlink(sdks + "/MacOSX26.sdk", to: "MacOSX26.5.sdk")
        try tree.symlink(sdks + "/MacOSX.sdk", to: sdks + "/MacOSX26.sdk")
        #expect(tree.fs.resolvingSymlinks(at: sdks + "/MacOSX.sdk") == sdks + "/MacOSX26.5.sdk")
        #expect(tree.fs.isDirectory(at: sdks + "/MacOSX.sdk"))
        #expect(try tree.fs.readData(at: sdks + "/MacOSX.sdk/SDKSettings.json") == Data("{}".utf8))
    }

    @Test(arguments: Kind.allCases)
    func whatIsntThereIsReportedSo(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        let missing = tree.root + "/no such file"
        #expect(!tree.fs.fileExists(at: missing))
        #expect(!tree.fs.isDirectory(at: missing))
        #expect(tree.fs.resolvingSymlinks(at: missing) == missing)
        #expect(throws: (any Error).self) { try tree.fs.readData(at: missing) }
        #expect(throws: (any Error).self) { try tree.fs.contentsOfDirectory(at: missing) }
    }
}
