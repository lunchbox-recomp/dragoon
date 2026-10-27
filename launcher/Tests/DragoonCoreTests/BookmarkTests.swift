import DragoonCore
import Foundation
import Testing

@Suite struct BookmarkTests {
    @Test func aBookmarkLeadsToItsFileUntilTheFileIsGone() throws {
        let scratch = try ScratchDirectory()
        defer { scratch.remove() }
        let disc = scratch.path + "/Kirby Air Ride (USA).gcm"
        try Data("GKYE01".utf8).write(to: URL(fileURLWithPath: disc))
        let bookmark = try Bookmark.make(for: disc)
        #expect(Bookmark.resolve(bookmark, fs: SystemFileSystem()) == .found(disc))
        try FileManager.default.removeItem(atPath: disc)
        #expect(Bookmark.resolve(bookmark, fs: SystemFileSystem()) == .missing)
    }

    @Test func aBookmarkThatIsntOneIsMissing() {
        #expect(Bookmark.resolve(Data("not a bookmark".utf8), fs: SystemFileSystem()) == .missing)
    }
}
