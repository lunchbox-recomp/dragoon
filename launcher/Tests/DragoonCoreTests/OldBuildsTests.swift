import DragoonCore
import Foundation
import Testing

private let games = fakeData + "/game"

@Suite struct OldBuildsTests {
    @Test func everythingButTheCurrentBuildIsDeleted() throws {
        let fs = FakeFileSystem()
        for build in ["b1", "b2", "b3"] { fs.addFile(games + "/" + build + "/stamp.json") }
        fs.addSymlink(games + "/current", to: "b2")
        fs.addSymlink(games + "/.current.123.partial", to: "b3")
        let removed = OldBuilds.delete(dataDirectory: fakeData, fs: fs)
        #expect(Set(removed) == [".current.123.partial", "b1", "b3"])
        #expect(try fs.contentsOfDirectory(at: games) == ["b2", "current"])
        #expect(fs.fileExists(at: games + "/current/stamp.json"))
    }

    @Test func nothingIsDeletedWithoutACurrentBuild() throws {
        let fs = FakeFileSystem()
        fs.addFile(games + "/b1/stamp.json")
        #expect(OldBuilds.delete(dataDirectory: fakeData, fs: fs) == [])
        fs.addSymlink(games + "/current", to: "gone")
        #expect(OldBuilds.delete(dataDirectory: fakeData, fs: fs) == [])
        #expect(try fs.contentsOfDirectory(at: games) == ["b1", "current"])
    }

    @Test func aCurrentLinkOutsideTheGameDirectoryDeletesNothing() throws {
        let fs = FakeFileSystem()
        fs.addFile(games + "/b1/stamp.json")
        fs.addDirectory("/elsewhere/b9")
        fs.addSymlink(games + "/current", to: "/elsewhere/b9")
        #expect(OldBuilds.delete(dataDirectory: fakeData, fs: fs) == [])
        #expect(try fs.contentsOfDirectory(at: games) == ["b1", "current"])
    }

    @Test func oldBuildsAreDeletedOnDiskTooAndTheCurrentOneStays() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        let onDisk = scratch.data + "/game"
        for build in ["20270101-000000-aaaa", "20270102-000000-bbbb"] {
            try FileManager.default.createDirectory(
                atPath: onDisk + "/" + build + "/Dragoon.app/Contents",
                withIntermediateDirectories: true)
        }
        try FileManager.default.createSymbolicLink(
            atPath: onDisk + "/current", withDestinationPath: "20270102-000000-bbbb")
        let removed = OldBuilds.delete(dataDirectory: scratch.data, fs: SystemFileSystem())
        #expect(removed == ["20270101-000000-aaaa"])
        #expect(try FileManager.default.contentsOfDirectory(atPath: onDisk).sorted()
            == ["20270102-000000-bbbb", "current"])
    }
}
