import DragoonCore
import Foundation
import Testing

/// `count` pixels of one color, as RGBA bytes.
private func pixels(_ count: Int, _ red: UInt8, _ green: UInt8, _ blue: UInt8, alpha: UInt8 = 255)
    -> [UInt8]
{
    (0..<count).flatMap { _ in [red, green, blue, alpha] }
}

/// A hue in degrees as the fraction of a turn the palette gives.
private func turn(_ degrees: Double) -> Double { degrees / 360 }

/// How far apart two hues are round the circle, so 0 and a hair under 1 are close.
private func apart(_ one: Double, _ other: Double) -> Double {
    let gap = abs(one - other).truncatingRemainder(dividingBy: 1)
    return min(gap, 1 - gap)
}

private func expectHues(_ palette: BannerPalette, _ primary: Double, _ secondary: Double,
                        sourceLocation: SourceLocation = #_sourceLocation) {
    #expect(apart(palette.primary, primary) < 1e-9, "primary \(palette.primary * 360)°",
            sourceLocation: sourceLocation)
    #expect(apart(palette.secondary, secondary) < 1e-9, "secondary \(palette.secondary * 360)°",
            sourceLocation: sourceLocation)
}

/// The hero's two hues from the banner's opaque, colored pixels.
@Suite struct BannerPaletteTests {
    @Test func noBannerGivesTheFixedPalette() {
        #expect(BannerPalette(banner: nil) == .fallback)
    }

    @Test func theCommonestHueComesFirstAndTheNextSecond() {
        let palette = BannerPalette(rgba: pixels(60, 0, 255, 0) + pixels(100, 0, 0, 255))
        expectHues(palette, turn(240), turn(120))
    }

    @Test func aBannerOfOneHueGetsASecondSixtyDegreesOn() {
        expectHues(BannerPalette(rgba: pixels(10, 255, 0, 0)), 0, turn(60))
        // Past a full turn it wraps.
        expectHues(BannerPalette(rgba: pixels(10, 255, 0, 255)), turn(300), 0)
    }

    @Test func onlyOpaquePixelsCount() {
        let palette = BannerPalette(
            rgba: pixels(500, 255, 0, 0, alpha: 254) + pixels(500, 0, 255, 0, alpha: 0)
                + pixels(3, 0, 0, 255))
        expectHues(palette, turn(240), turn(300))
    }

    @Test func grayHasNoHueAndDoesNotCount() {
        let grays = pixels(300, 255, 255, 255) + pixels(300, 0, 0, 0) + pixels(300, 128, 120, 110)
        expectHues(BannerPalette(rgba: grays + pixels(2, 255, 255, 0)), turn(60), turn(120))
        #expect(BannerPalette(rgba: grays) == .fallback)
        #expect(BannerPalette(rgba: []) == .fallback)
    }

    /// A pixel needs its channels `minimumChroma` apart to have a hue.
    @Test func thePixelAtTheChromaFloorCountsAndTheOneBelowDoesNot() {
        let floor = UInt8(BannerPalette.minimumChroma)
        expectHues(BannerPalette(rgba: pixels(1, 100 + floor, 100, 100)), 0, turn(60))
        #expect(BannerPalette(rgba: pixels(1, 99 + floor, 100, 100)) == .fallback)
    }

    @Test func aHueIsTheMeanOfItsBucket() {
        // 0° and 20° share the 0° to 30° bucket.
        let palette = BannerPalette(rgba: pixels(50, 255, 0, 0) + pixels(50, 255, 85, 0))
        expectHues(palette, turn(10), turn(70))
    }

    /// 30° starts the second bucket, so it pools with 50° and not with 0°.
    @Test func aBucketStartsAtItsOwnEdge() {
        let palette = BannerPalette(
            rgba: pixels(10, 204, 102, 0) + pixels(10, 204, 170, 0) + pixels(15, 255, 0, 0))
        expectHues(palette, turn(40), turn(100))
    }

    /// Two buckets side by side are one color's edges, so the second skips them, round the
    /// wrap too.
    @Test func theSecondHueSkipsTheBucketsBesideTheFirst() {
        let orange = pixels(80, 255, 175, 0)  // 41°
        let rose = pixels(80, 255, 0, 43)  // 350°
        let green = pixels(40, 0, 255, 0)
        expectHues(BannerPalette(rgba: pixels(100, 255, 0, 0) + orange + rose + green), 0, turn(120))
    }

    @Test func aTieGoesToTheLowerHue() {
        expectHues(BannerPalette(rgba: pixels(10, 0, 0, 255) + pixels(10, 0, 255, 0)),
                   turn(120), turn(240))
    }

    @Test func aBannerGivesThePaletteOfItsPixels() throws {
        // Opaque RGB555 blue in every pixel.
        let banner = try #require(DiscBanner(
            bytes: makeBNR(pixels: Array(repeating: 0x801F, count: 96 * 32)), discID: "GKYE01"))
        expectHues(BannerPalette(banner: banner), turn(240), turn(300))
    }
}
