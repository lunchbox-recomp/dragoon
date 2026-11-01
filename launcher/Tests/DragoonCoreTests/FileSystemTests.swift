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
    func appendMakesTheFileAndItsDirectoryAndKeepsWhatWasThere(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        let path = tree.root + "/Logs dir/build.log"
        try tree.fs.appendData(Data("one\n".utf8), to: path)
        try tree.fs.appendData(Data("two\n".utf8), to: path)
        try tree.fs.appendData(Data(), to: path)
        #expect(try tree.fs.readData(at: path) == Data("one\ntwo\n".utf8))
        #expect(tree.fs.isDirectory(at: tree.root + "/Logs dir"))
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
    func removeTakesAFileAndThenADirectoryWithEverythingInIt(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        try tree.file(tree.root + "/probe dir/a.cpp", "a")
        try tree.file(tree.root + "/probe dir/deeper/b.cpp", "b")
        try tree.file(tree.root + "/toolchain.json", "{}")

        try tree.fs.removeItem(at: tree.root + "/probe dir/a.cpp")
        #expect(!tree.fs.fileExists(at: tree.root + "/probe dir/a.cpp"))
        #expect(tree.fs.fileExists(at: tree.root + "/probe dir/deeper/b.cpp"))

        try tree.fs.removeItem(at: tree.root + "/probe dir")
        #expect(!tree.fs.fileExists(at: tree.root + "/probe dir"))
        #expect(!tree.fs.fileExists(at: tree.root + "/probe dir/deeper/b.cpp"))
        #expect(tree.fs.fileExists(at: tree.root + "/toolchain.json"))
    }

    @Test(arguments: Kind.allCases)
    func removingALinkLeavesWhatItPointsTo(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        try tree.file(tree.root + "/SDKs/MacOSX26.5.sdk/SDKSettings.json", "{}")
        try tree.symlink(tree.root + "/SDKs/MacOSX.sdk", to: "MacOSX26.5.sdk")

        try tree.fs.removeItem(at: tree.root + "/SDKs/MacOSX.sdk")
        #expect(tree.fs.fileExists(at: tree.root + "/SDKs/MacOSX26.5.sdk/SDKSettings.json"))
        #expect(try tree.fs.contentsOfDirectory(at: tree.root + "/SDKs") == ["MacOSX26.5.sdk"])
    }

    @Test(arguments: Kind.allCases)
    func removingWhatIsntThereThrows(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        #expect(throws: (any Error).self) { try tree.fs.removeItem(at: tree.root + "/no such file") }
    }

    @Test(arguments: Kind.allCases)
    func moveMakesTheDirectoryAndNeverReplacesWhatsThere(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        let panic = tree.root + "/panic.txt"
        let moved = tree.root + "/Logs dir/panic one.txt"
        try tree.file(panic, "first")
        try tree.fs.moveItem(at: panic, to: moved)
        #expect(!tree.fs.fileExists(at: panic))
        #expect(try tree.fs.readData(at: moved) == Data("first".utf8))

        try tree.file(panic, "second")
        #expect(throws: POSIXError(.EEXIST)) { try tree.fs.moveItem(at: panic, to: moved) }
        #expect(try tree.fs.readData(at: panic) == Data("second".utf8))
        #expect(try tree.fs.readData(at: moved) == Data("first".utf8))

        try tree.fs.removeItem(at: panic)
        #expect(throws: (any Error).self) {
            try tree.fs.moveItem(at: panic, to: tree.root + "/Logs dir/panic two.txt")
        }
        #expect(!tree.fs.fileExists(at: tree.root + "/Logs dir/panic two.txt"))
    }

    @Test(arguments: Kind.allCases)
    func aReaderGivesTheBytesAtAnOffsetAndFewerOnlyAtTheEnd(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        let path = tree.root + "/a dir/disc (USA).gcm"
        try tree.file(path, "0123456789")
        let reader = try tree.fs.openReader(at: path)

        #expect(try reader.read(at: 3, count: 4) == Data("3456".utf8))
        #expect(try reader.read(at: 0, count: 10) == Data("0123456789".utf8))
        #expect(try reader.read(at: 8, count: 5) == Data("89".utf8))
        #expect(try reader.read(at: 10, count: 1).isEmpty)
        #expect(try reader.read(at: 1 << 40, count: 1).isEmpty)
        #expect(try reader.read(at: UInt64.max, count: 8).isEmpty)
        #expect(try reader.read(at: 2, count: 0).isEmpty)
    }

    @Test(arguments: Kind.allCases)
    func aReaderOfWhatCantBeReadThrows(_ kind: Kind) throws {
        let tree = try makeTree(kind)
        defer { cleanUp(tree) }
        try tree.file(tree.root + "/a dir/disc.gcm", "0123456789")
        #expect(throws: (any Error).self) {
            try tree.fs.openReader(at: tree.root + "/no such file")
        }
        #expect(throws: (any Error).self) {
            try tree.fs.openReader(at: tree.root + "/a dir").read(at: 0, count: 1)
        }
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

@Suite struct FakeFileSystemTests {
    @Test func aWriteThatIsToldToFailThrowsAndLeavesNothing() {
        let fake = FakeFileSystem()
        fake.failWrites(with: CocoaError(.fileWriteNoPermission))
        #expect(throws: CocoaError(.fileWriteNoPermission)) {
            try fake.writeData(Data("x".utf8), to: "/a/b")
        }
        #expect(!fake.fileExists(at: "/a/b"))
        #expect(fake.writes.isEmpty)
    }

    @Test func writesStayRecordedAfterTheFileIsRemoved() throws {
        let fake = FakeFileSystem()
        try fake.writeData(Data("x".utf8), to: "/a/b")
        try fake.removeItem(at: "/a/b")
        #expect(!fake.fileExists(at: "/a/b"))
        #expect(fake.writes == [.init(path: "/a/b", data: Data("x".utf8))])
    }
}
