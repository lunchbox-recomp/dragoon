import DragoonCore
import DragoonViews
import Foundation
import SwiftUI
import Testing

/// The Settings sheet at each aspect, against its PNG in `Snapshots/`, on `testDisplay`.
struct SettingsFixture: CustomTestStringConvertible, Sendable {
    let name: String
    let picture: PictureSettings
    var failure: PictureSettings.SaveFailure?

    var testDescription: String { name }
}

let settingsFixtures: [SettingsFixture] = [
    SettingsFixture(name: "settings-4x3", picture: PictureSettings(aspect: "4:3")),
    SettingsFixture(name: "settings-16x9", picture: PictureSettings(aspect: "16:9", scale: 3)),
    SettingsFixture(name: "settings-16x10", picture: PictureSettings(aspect: "16:10", scale: 4)),
    SettingsFixture(name: "settings-21x9", picture: PictureSettings(aspect: "21:9", scale: 8)),
    SettingsFixture(name: "settings-window", picture: PictureSettings(aspect: "window", scale: 1)),
    // Fullscreen on a 16:9 display: 4:3 has bars at its sides, 21:9 above and below.
    SettingsFixture(
        name: "settings-4x3-fullscreen", picture: PictureSettings(aspect: "4:3", fullscreen: true)),
    SettingsFixture(
        name: "settings-21x9-fullscreen",
        picture: PictureSettings(aspect: "21:9", fullscreen: true, scale: 6)),
    // A save that failed on a full disk, with the system's reason under the sentence.
    SettingsFixture(
        name: "settings-save-failed", picture: PictureSettings(aspect: "16:9"),
        failure: .notWritten("The operation couldn’t be completed. No space left on device")),
]

@MainActor
struct SettingsSnapshotTests {
    static func render(
        _ picture: PictureSettings, failure: PictureSettings.SaveFailure? = nil
    ) -> Bitmap? {
        var state = settingsState(picture)
        state.pictureFailure = failure
        return Snapshot.render(
            SettingsSheet(state: state, send: { _ in }).environment(\.pictureDisplay, testDisplay),
            size: SettingsSheet.size)
    }

    @Test(arguments: settingsFixtures)
    func theSheetLooksAsRecorded(_ fixture: SettingsFixture) throws {
        let image = try #require(Self.render(fixture.picture, failure: fixture.failure))
        try SnapshotTests.expectAsRecorded(image, name: fixture.name)
    }

    /// Two aspects side by side differ by more than a snapshot allows, so a preview drawn at the
    /// wrong shape fails.
    @Test(.disabled(if: Snapshot.recording))
    func anotherAspectDoesNotPass() throws {
        let image = try #require(Self.render(PictureSettings(aspect: "16:10", scale: 3)))
        let other = try #require(Bitmap.read(SnapshotTests.file("settings-16x9")))
        let differing = try #require(
            image.differingPixels(from: other, tolerance: Snapshot.channelTolerance))
        #expect(differing > Snapshot.allowedPixels)
    }
}
