import AppKit
import DragoonCore
import Foundation
import SwiftUI
import Testing

@testable import DragoonViews

/// Library with the Settings sheet open on `picture`, in the test banner's colors.
func settingsState(_ picture: PictureSettings) -> Flow.State {
    var state = Flow.State()
    state.screen = .library
    state.installed = InstalledGame(stamp: nil)
    state.banner = TestBanner.banner
    state.picture = picture
    return state
}

/// A 1920x1080 display whose menu bar takes 30 points, as the sheet's tests draw on.
let testDisplay = PictureDisplay(frame: WholeSize(1920, 1080), usable: WholeSize(1920, 1050))

@MainActor
struct SettingsSheetTests {
    /// How long Settings may take from the press to the sheet drawn.
    static let openingBudget = Duration.milliseconds(100)

    /// From Settings to a drawn sheet: the press, reading a real settings.txt, its result and the
    /// sheet laid out and drawn by AppKit, each the way the app does it. The sheet's slide in,
    /// which AppKit animates, isn't counted.
    @Test func theSheetIsDrawnWithin100msOfSettings() throws {
        let scratch = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon settings tests \(UUID().uuidString)/Application Support")
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: scratch.deletingLastPathComponent()) }
        try Data("# Picture\naspect 16:9\nfullscreen 0\nscale 3\n".utf8)
            .write(to: scratch.appendingPathComponent("settings.txt"))
        var library = settingsState(PictureSettings())
        library.picture = nil

        let clock = ContinuousClock()
        let start = clock.now
        let (pressed, effects) = Flow.reduce(library, .settingsPressed)
        #expect(effects == [.readPicture])
        let read = PictureSettings.load(from: scratch.path, fs: SystemFileSystem())
        let (open, _) = Flow.reduce(pressed, .pictureRead(read))
        let host = NSHostingView(
            rootView: SettingsSheet(state: open, send: { _ in }).environment(\.pictureDisplay, testDisplay))
        host.frame = NSRect(origin: .zero, size: SettingsSheet.size)
        host.layoutSubtreeIfNeeded()
        let bitmap = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        let took = clock.now - start

        #expect(open.picture == PictureSettings(aspect: "16:9", fullscreen: false, scale: 3))
        print("Settings to a drawn sheet: \(took.formatted(.units(allowed: [.milliseconds], fractionalPart: .show(length: 1))))")
        #expect(took < Self.openingBudget)
    }
}
