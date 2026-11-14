import DragoonViews
import Foundation
import SwiftUI
import Testing

/// Each screen through `ImageRenderer`, against its PNG in `Snapshots/`. Run with `RECORD=1` to
/// write the PNGs again after a change to how a screen looks, and look at each one before
/// committing it.
@MainActor
struct SnapshotTests {
    static func render(_ fixture: ScreenFixture) -> Bitmap? {
        Snapshot.render(
            LauncherView(state: fixture.state, send: { _ in })
                .environment(\.reducesMotion, fixture.reduceMotion),
            size: fixture.size)
    }

    static func file(_ name: String) -> URL {
        Snapshot.directory.appendingPathComponent(name + ".png")
    }

    @Test(arguments: screenFixtures)
    func screenLooksAsRecorded(_ fixture: ScreenFixture) throws {
        try Self.expectAsRecorded(try #require(Self.render(fixture)), name: fixture.name)
    }

    /// Writes `image` as the PNG called `name` when recording, and otherwise compares the two.
    /// A render that fails is written in `failures` under the same name.
    static func expectAsRecorded(
        _ image: Bitmap, name: String, failures: URL = Snapshot.failures
    ) throws {
        let file = Self.file(name)
        if Snapshot.recording {
            try FileManager.default.createDirectory(
                at: Snapshot.directory, withIntermediateDirectories: true)
            try image.rounded(to: Snapshot.recordStep).write(to: file)
            return
        }
        let recorded = try #require(
            Bitmap.read(file), "No snapshot at \(file.path). Run with RECORD=1 to write it.")
        let differing = image.differingPixels(from: recorded, tolerance: Snapshot.channelTolerance)
        let allowed = Snapshot.allowedPixels
        guard let differing, differing <= allowed else {
            try FileManager.default.createDirectory(at: failures, withIntermediateDirectories: true)
            let actual = failures.appendingPathComponent(name + ".png")
            try image.write(to: actual)
            let found = differing.map { "\($0) pixels differ" } ?? "it's another size"
            Issue.record(
                "\(name) isn't as recorded: \(found), and \(allowed) may. This run's image is at \(actual.path).")
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
        #expect(differing > Snapshot.allowedPixels)
    }

    /// A failing render goes in the package's `.build`, never the temporary directory every
    /// program shares.
    @Test func failingRendersGoInThePackagesBuildFolder() {
        #expect(Snapshot.failures.standardized.path.hasSuffix("/launcher/.build/snapshot-failures"))
        #expect(!Snapshot.failures.path.hasPrefix(FileManager.default.temporaryDirectory.path))
    }

    @Test(.disabled(if: Snapshot.recording))
    func aFailingRenderIsWrittenUnderItsName() throws {
        let folder = Snapshot.failures.appendingPathComponent("test \(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: folder) }
        let width = Int(Snapshot.size.width), height = Int(Snapshot.size.height)
        let white = Bitmap(
            width: width, height: height, bytes: [UInt8](repeating: 255, count: width * height * 4))
        withKnownIssue {
            try Self.expectAsRecorded(white, name: "disc-checking", failures: folder)
        }
        #expect(Bitmap.read(folder.appendingPathComponent("disc-checking.png")) == white)
    }

    /// One word changed on a button, as Quit to Exit on the must-move screen, is past what may
    /// differ.
    @Test func oneWordChangedOnAButtonDoesNotPass() throws {
        let quit = try #require(Snapshot.render(Button("Quit") {}))
        let exit = try #require(Snapshot.render(Button("Exit") {}))
        let differing = try #require(
            quit.differingPixels(from: exit, tolerance: Snapshot.channelTolerance))
        #expect(differing > Snapshot.allowedPixels)
    }
}
