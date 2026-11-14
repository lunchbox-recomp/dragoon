import Foundation

/// A size in whole points or pixels.
public struct WholeSize: Equatable, Hashable, Sendable {
    public var width: Int
    public var height: Int

    public init(_ width: Int, _ height: Int) {
        self.width = width
        self.height = height
    }
}

/// Where a picture goes in a larger area, in whole points or pixels.
public struct WholeRect: Equatable, Sendable {
    public var x, y, width, height: Int

    public init(x: Int, y: Int, width: Int, height: Int) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }
}

/// The sizes the game's picture comes out at for a `PictureSettings`, with the engine's own
/// arithmetic: gcn-recomp `runtime/gx/aspect.h` and where `runtime/main.cpp` opens the window.
public enum PictureGeometry {
    /// The height `main.cpp` opens the window at, in points, before the display's usable area
    /// cuts it down.
    public static let openingHeight = 960
    /// The title bar `main.cpp` allows for above the window where SDL can't say the frame's size
    /// before the window shows, as on macOS.
    public static let titleBar = 40
    /// The picture the scale multiplies, as `runtime/settings.h` gives it.
    public static let basePicture = WholeSize(640, 480)

    /// The shape the window opens at: the aspect's own, or 4:3 for "window", which then
    /// follows the window as it's resized.
    public static func openingShape(_ aspect: String) -> WholeSize {
        guard let sides = PictureSettings.sides(of: aspect) else { return WholeSize(4, 3) }
        return WholeSize(sides.w, sides.h)
    }

    /// The window the game opens for `aspect`, in points. `usable` is the display's usable area,
    /// as `SDL_GetDisplayUsableBounds` gives it, or nil for no limit.
    public static func window(aspect: String, usable: WholeSize?) -> WholeSize {
        let shape = openingShape(aspect)
        guard let usable, usable.width > 0, usable.height > 0 else {
            return windowSize(height: openingHeight, shape: shape, maxWidth: 0, maxHeight: 0)
        }
        // aspect_window_rect with a 40 point title bar and no other frame.
        return windowSize(
            height: openingHeight, shape: shape, maxWidth: max(1, usable.width),
            maxHeight: max(1, usable.height - titleBar))
    }

    /// `gx::aspect_window_width`: the width of a window `height` high at `shape`, rounded up.
    public static func width(height: Int, shape: WholeSize) -> Int {
        Int((Int64(height) * Int64(shape.width) + Int64(shape.height) - 1) / Int64(shape.height))
    }

    /// `gx::aspect_window_size`: `height` high at `shape`, or the largest window of that shape in
    /// `maxWidth` by `maxHeight`, with a height a whole number of the shape's steps. A limit of 0
    /// or less is none.
    public static func windowSize(height: Int, shape: WholeSize, maxWidth: Int, maxHeight: Int) -> WholeSize {
        let maxW = maxWidth <= 0 ? Int64(Int32.max) : Int64(maxWidth)
        let maxH = maxHeight <= 0 ? Int64(Int32.max) : Int64(maxHeight)
        let widestFit = maxW * Int64(shape.height) / Int64(shape.width)
        var tall = min(Int64(height), maxH, widestFit)
        let step = Int64(shape.height / gcd(shape.width, shape.height))
        if tall < Int64(height) && tall >= step { tall -= tall % step }
        tall = max(1, tall)
        return WholeSize(min(width(height: Int(tall), shape: shape), Int(maxW)), Int(tall))
    }

    /// `gx::fit_aspect`: a picture of width over height `ratio` as large as fits in `area`,
    /// centred, rounded down to whole pixels. The ratio goes through a 32-bit float, as the
    /// engine's does.
    public static func fit(_ area: WholeSize, ratio: Float) -> WholeRect {
        let a = Double(ratio)
        var w = area.width
        var h = Int((Double(area.width) / a + 1e-3).rounded(.down))
        if h > area.height {
            h = area.height
            w = Int((Double(area.height) * a + 1e-3).rounded(.down))
        }
        return WholeRect(x: (area.width - w) / 2, y: (area.height - h) / 2, width: w, height: h)
    }

    /// Where the picture goes on a fullscreen display: fit to the aspect, or the whole display
    /// for "window", whose picture takes the display's shape.
    public static func fullscreen(aspect: String, display: WholeSize) -> WholeRect {
        guard let sides = PictureSettings.sides(of: aspect) else {
            return WholeRect(x: 0, y: 0, width: display.width, height: display.height)
        }
        return fit(display, ratio: Float(sides.w) / Float(sides.h))
    }

    /// The picture the renderer draws at `scale`, which it holds to 1 through
    /// `PictureSettings.maxScale`.
    public static func internalSize(scale: Int) -> WholeSize {
        let n = min(max(scale, 1), PictureSettings.maxScale)
        return WholeSize(basePicture.width * n, basePicture.height * n)
    }

    private static func gcd(_ a: Int, _ b: Int) -> Int {
        b == 0 ? a : gcd(b, a % b)
    }
}
