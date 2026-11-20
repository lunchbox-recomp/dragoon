@testable import DragoonCore
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

    /// macOS's figure for important use, which at times comes back as nothing or 0, as on CI run
    /// 44491927694, never counts for less than the bytes that are free.
    @Test func aMissingOrZeroFigureForImportantUseCountsTheFreeBytes() {
        #expect(Volume.usable(important: nil, free: 5_000_000_000) == 5_000_000_000)
        #expect(Volume.usable(important: 0, free: 5_000_000_000) == 5_000_000_000)
        #expect(Volume.usable(important: 9_000_000_000, free: 5_000_000_000) == 9_000_000_000)
        #expect(Volume.usable(important: nil, free: nil) == 0)
    }

    @Test func theFreeBytesComeFromTheVolumeOrNotAtAll() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        #expect((Volume.freeBytes(scratch.path) ?? 0) > 0)
        #expect(Volume.freeBytes(scratch.data) == nil)
    }

    /// When macOS throws instead of giving its figures, the free bytes of the folder that exists
    /// still count, and the folder names the volume.
    @Test func aThrownAskStillCountsTheFreeBytes() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        var asked: [String] = []
        let space = Volume.freeSpace(at: scratch.data) { url in
            asked.append(url.path)
            return nil
        }
        #expect(asked == [scratch.path])
        #expect(space.available > 0)
        #expect(space.volume == scratch.path)
    }

    @Test func theSystemVolumeIsReadOnlyAndTheTemporaryDirectoryIsnt() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        #expect(Volume.isReadOnly("/System/Library"))
        #expect(!Volume.isReadOnly(scratch.path))
    }
}
