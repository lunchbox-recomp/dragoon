import DragoonCore
import Foundation
import Testing

@Suite struct VolumeTests {
    @Test func freeSpaceIsMeasuredWhereTheFolderWillBe() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        let space = Volume.freeSpace(at: scratch.data)
        #expect(space.available > 0)
        #expect(!space.volume.isEmpty)
        #expect(!FileManager.default.fileExists(atPath: scratch.data))
    }

    @Test func theSystemVolumeIsReadOnlyAndTheTemporaryDirectoryIsnt() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        #expect(Volume.isReadOnly("/System/Library"))
        #expect(!Volume.isReadOnly(scratch.path))
    }
}
