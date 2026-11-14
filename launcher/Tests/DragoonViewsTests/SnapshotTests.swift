import DragoonViews
import Foundation
import Testing

/// Each screen through `ImageRenderer`, against its PNG in `Snapshots/`. Run with `RECORD=1` to
/// write the PNGs again after a change to how a screen looks, and look at each one before
/// committing it.
@MainActor
struct SnapshotTests {
    static func render(_ fixture: ScreenFixture) -> Bitmap? {
        Snapshot.render(LauncherView(state: fixture.state, send: { _ in }))
    }

    static func file(_ name: String) -> URL {
        Snapshot.directory.appendingPathComponent(name + ".png")
    }

    @Test(arguments: screenFixtures)
    func screenLooksAsRecorded(_ fixture: ScreenFixture) throws {
        let image = try #require(Self.render(fixture))
        let file = Self.file(fixture.name)
        if Snapshot.recording {
            try FileManager.default.createDirectory(
                at: Snapshot.directory, withIntermediateDirectories: true)
            try image.write(to: file)
            return
        }
        let recorded = try #require(
            Bitmap.read(file), "No snapshot at \(file.path). Run with RECORD=1 to write it.")
        let differing = image.differingPixels(from: recorded, tolerance: Snapshot.channelTolerance)
        let allowed = Snapshot.allowedPixels(image)
        guard let differing, differing <= allowed else {
            let actual = FileManager.default.temporaryDirectory
                .appendingPathComponent("Dragoon snapshot \(fixture.name).png")
            try image.write(to: actual)
            let found = differing.map { "\($0) pixels differ" } ?? "it's another size"
            Issue.record(
                "\(fixture.name) isn't as recorded: \(found), and \(allowed) may. This run's image is at \(actual.path).")
            return
        }
    }

    /// Two screens laid out alike, with other text and another step current, are far apart.
    @Test func aScreenWithOtherTextDoesNotPass() throws {
        let fixture = try #require(screenFixtures.first { $0.name == "build-preparing" })
        let image = try #require(Self.render(fixture))
        let other = try #require(Bitmap.read(Self.file("disc-checking")))
        let differing = try #require(
            image.differingPixels(from: other, tolerance: Snapshot.channelTolerance))
        #expect(differing > Snapshot.allowedPixels(image))
    }
}
