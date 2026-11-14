import DragoonViews
import Foundation
import SwiftUI

/// Renders a view with `ImageRenderer` for comparison with a committed PNG in `Snapshots/`.
/// `RECORD=1` in the environment writes the PNG instead.
enum Snapshot {
    /// The size the window opens at, in points.
    static let size = LauncherView.defaultSize
    static let scale: CGFloat = 2
    /// How far a color channel may be off, out of 255, before the pixel counts as different.
    /// Text drawn by another macOS can shift its edges a little.
    static let channelTolerance = 16
    /// A recorded PNG keeps each channel to the nearest multiple of this, which moves it at
    /// most 4 of the 16 the comparison allows.
    static let recordStep = 8
    /// How many pixels may differ, of the 960x600. Every screen renders 0 on the Mac that
    /// recorded them, and Quit changed to Exit on the must-move screen is 223.
    static let allowedPixels = 100

    static let directory = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().appendingPathComponent("Snapshots")

    /// Where a render that fails is written: `launcher/.build/snapshot-failures`, which git
    /// ignores and `swift package clean` removes.
    static let failures = directory.deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().appendingPathComponent(".build/snapshot-failures")

    /// The moment every animated view draws, 2027-01-15 08:00 UTC.
    static let moment = Date(timeIntervalSince1970: 1_800_000_000)
    /// The moment the build page's fixtures draw, half a shimmer on from `moment`, which falls
    /// on a whole period. The band sits in the middle of its segment, and the Reduce Motion fade
    /// is at its brightest. `BuildPageTests` checks it's half of `Shimmer.period`.
    static let buildMoment = moment.addingTimeInterval(0.8)

    static var recording: Bool { ProcessInfo.processInfo.environment["RECORD"] == "1" }

    /// The view at `size`, the window's opening size unless another is given, in dark
    /// appearance on the window's gray, with its animations stopped at `time`, `moment` unless
    /// given. It renders at scale 2, then each 2x2 block of pixels becomes one, so text is drawn
    /// as on a Retina screen and the PNGs stay a quarter the size.
    @MainActor
    static func render(_ view: some View, size: CGSize = size, at time: Date = moment) -> Bitmap? {
        let renderer = ImageRenderer(
            content: view
                .frame(width: size.width, height: size.height)
                .background(Color(white: 0.12))
                .environment(\.colorScheme, .dark)
                .environment(\.animationClock, .fixed(time)))
        renderer.scale = scale
        return renderer.cgImage.flatMap(Bitmap.init)?.halved()
    }
}
