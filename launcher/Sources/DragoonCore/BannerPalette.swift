import Foundation

/// The two hues Library's hero is drawn in, taken from the disc's banner so the window wears the
/// game's colors. Each is a fraction of a turn, from 0 up to 1, with red at 0.
///
/// Every opaque pixel with a hue goes into one of 12 buckets 30° wide, by its hue. The fullest
/// bucket gives the first hue and the next fullest the second, each as the mean hue of the
/// pixels in it. The two buckets beside the first are its own edges, the way a pink spills
/// into red, so the second never comes from them. Ties go to the lower hue.
public struct BannerPalette: Equatable, Sendable {
    public static let buckets = 12
    /// How far apart a pixel's highest and lowest channels have to be, out of 255, for it to
    /// have a hue. White, black and the grays between have none.
    public static let minimumChroma = 48
    /// With no banner, or none with a hue: teal and magenta.
    public static let fallback = BannerPalette(primary: 0.53, secondary: 0.86)
    /// How far the second hue sits from the first when only one bucket has pixels.
    static let loneHueStep = 1.0 / 6

    public var primary: Double
    public var secondary: Double

    public init(primary: Double, secondary: Double) {
        self.primary = primary
        self.secondary = secondary
    }

    public init(banner: DiscBanner?) {
        self = banner.map { BannerPalette(rgba: $0.rgba) } ?? .fallback
    }

    /// The palette of straight-alpha RGBA pixels, four bytes each.
    public init(rgba: [UInt8]) {
        var counts = [Int](repeating: 0, count: Self.buckets)
        var sums = [Double](repeating: 0, count: Self.buckets)
        for at in stride(from: 0, to: rgba.count - 3, by: 4) where rgba[at + 3] == 255 {
            guard let hue = Self.hue(rgba[at], rgba[at + 1], rgba[at + 2]) else { continue }
            let bucket = min(Int(hue * Double(Self.buckets)), Self.buckets - 1)
            counts[bucket] += 1
            sums[bucket] += hue
        }
        // Fullest first, and the lower hue first among equals.
        let ranked = counts.indices.filter { counts[$0] > 0 }
            .sorted { counts[$0] != counts[$1] ? counts[$0] > counts[$1] : $0 < $1 }
        guard let first = ranked.first else {
            self = .fallback
            return
        }
        let primary = sums[first] / Double(counts[first])
        let beside = [(first + 1) % Self.buckets, (first + Self.buckets - 1) % Self.buckets]
        guard let second = ranked.dropFirst().first(where: { !beside.contains($0) }) else {
            self.init(
                primary: primary,
                secondary: (primary + Self.loneHueStep).truncatingRemainder(dividingBy: 1))
            return
        }
        self.init(primary: primary, secondary: sums[second] / Double(counts[second]))
    }

    /// A color's hue as a fraction of a turn, or nil when it's too gray to have one.
    static func hue(_ red: UInt8, _ green: UInt8, _ blue: UInt8) -> Double? {
        let high = max(red, green, blue), low = min(red, green, blue)
        let chroma = Double(high - low)
        guard Int(high - low) >= minimumChroma else { return nil }
        let r = Double(red), g = Double(green), b = Double(blue)
        var sixths: Double
        if high == red {
            sixths = (g - b) / chroma
            if sixths < 0 { sixths += 6 }
        } else if high == green {
            sixths = (b - r) / chroma + 2
        } else {
            sixths = (r - g) / chroma + 4
        }
        return sixths / 6
    }
}
