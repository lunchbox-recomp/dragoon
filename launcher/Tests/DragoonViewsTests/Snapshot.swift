import DragoonViews
import Foundation
import SwiftUI

/// Renders a view with `ImageRenderer` for comparison with a committed PNG in `Snapshots/`.
/// `RECORD=1` in the environment writes the PNG instead.
enum Snapshot {
    /// The window's default size, in points.
    static let size = CGSize(width: 960, height: 600)
    static let scale: CGFloat = 2
    /// How far a color channel may be off, out of 255, before the pixel counts as different.
    /// Text drawn by another macOS can shift its edges a little.
    static let channelTolerance = 16
    /// How many pixels may differ, as a fraction of the image.
    static let pixelTolerance = 0.002

    static func allowedPixels(_ image: Bitmap) -> Int {
        Int(Double(image.width * image.height) * pixelTolerance)
    }

    static let directory = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().appendingPathComponent("Snapshots")

    /// The moment every animated view draws, 2027-01-15 08:00 UTC.
    static let moment = Date(timeIntervalSince1970: 1_800_000_000)

    static var recording: Bool { ProcessInfo.processInfo.environment["RECORD"] == "1" }

    /// The view at the window's size, scale 2 and light appearance, on the window's gray, with
    /// its animations stopped at `moment`.
    @MainActor
    static func render(_ view: some View) -> Bitmap? {
        let renderer = ImageRenderer(
            content: view
                .frame(width: size.width, height: size.height)
                .background(Color(white: 0.93))
                .environment(\.colorScheme, .light)
                .environment(\.animationClock, .fixed(moment)))
        renderer.scale = scale
        return renderer.cgImage.flatMap(Bitmap.init)
    }
}
