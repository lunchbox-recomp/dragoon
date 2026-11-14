import DragoonCore
import SwiftUI
import Testing

@testable import DragoonViews

/// The hero's colors and motion, and the disc reveal partway through.
@MainActor
struct LibraryLookTests {
    @Test(arguments: [
        (true, false, false, false), (false, false, false, true), (true, true, false, true),
        (true, false, true, true),
    ])
    func theHeroStopsUnseenWhileTheGameRunsAndUnderReduceMotion(
        windowIsActive: Bool, gameRunning: Bool, reduceMotion: Bool, paused: Bool
    ) {
        #expect(Motion.heroPaused(
            windowIsActive: windowIsActive, gameRunning: gameRunning, reduceMotion: reduceMotion)
            == paused)
    }

    @Test func hueSaturationAndBrightnessGiveTheirRGB() {
        let cases: [(Double, (Double, Double, Double))] = [
            (0, (1, 0, 0)), (1.0 / 6, (1, 1, 0)), (1.0 / 3, (0, 1, 0)), (0.5, (0, 1, 1)),
            (2.0 / 3, (0, 0, 1)), (5.0 / 6, (1, 0, 1)), (1.0 / 12, (1, 0.5, 0)),
        ]
        for (hue, expected) in cases {
            let rgb = HeroColors.rgb(hue: hue, saturation: 1, brightness: 1)
            #expect(abs(rgb.0 - expected.0) < 1e-9 && abs(rgb.1 - expected.1) < 1e-9
                    && abs(rgb.2 - expected.2) < 1e-9, "hue \(hue) gave \(rgb)")
        }
        let gray = HeroColors.rgb(hue: 0.3, saturation: 0, brightness: 0.5)
        #expect(gray.0 == 0.5 && gray.1 == 0.5 && gray.2 == 0.5)
    }

    /// Play's text is white on a dark enough hue and near-black on a light one.
    @Test(arguments: [(0.92, true), (0.61, true), (1.0 / 6, false), (0.53, false), (1.0 / 3, false)])
    func playsInkReadsOnItsHue(hue: Double, white: Bool) {
        #expect(HeroColors.whiteReads(onHue: hue) == white)
    }

    /// The near-black ink is a gray of 0.08, whose luminance is 0.0072.
    @Test func theDarkInksLuminanceIsItsRealOne() {
        #expect(abs(HeroColors.linear(HeroColors.darkInk) - 0.0072) < 0.00005)
        #expect(abs(HeroColors.contrast(1, 0) - 21) < 1e-9)
    }

    /// On every whole degree of hue, Play's ink is the one with more contrast where it's worst
    /// behind the label, worked out here from the button's brightness at the label's top and
    /// bottom rows, and it meets the bar.
    @Test func playsInkMeetsItsBarOnEveryHue() {
        let ink = HeroColors.linear(0.08)
        var worst = Double.infinity
        for degree in 0..<360 {
            let hue = Double(degree) / 360
            func luminance(_ brightness: Double) -> Double {
                HeroColors.luminance(
                    hue: hue, saturation: HeroColors.buttonSaturation, brightness: brightness)
            }
            // The button runs from 0.86 at its top to 0.70 at its bottom, 64 points down, and
            // the label covers rows 21 to 45.
            let top = luminance(0.86 - 0.16 * 21 / 64), bottom = luminance(0.86 - 0.16 * 45 / 64)
            let white = 1.05 / (top + 0.05)
            let dark = (bottom + 0.05) / (ink + 0.05)
            #expect(HeroColors.whiteReads(onHue: hue) == (white >= dark), "at \(degree)°")
            worst = min(worst, max(white, dark))
        }
        #expect(worst >= HeroColors.minimumContrast)
        #expect(HeroColors.minimumContrast == 3)
        // The README's figure, and under 4.5:1 somewhere, so the bar is large text's.
        #expect(worst >= 4.0)
        #expect(worst < 4.5)
    }

    @Test func aStreakIsTheSameEveryLaunch() {
        #expect(Streak.unit(7, 3) == Streak.unit(7, 3))
        #expect(Streak.unit(7, 3) != Streak.unit(8, 3))
        let units = (0..<1000).map { Streak.unit($0, 1) }
        #expect(units.allSatisfy { (0..<1).contains($0) })
        // Spread over the range, not bunched.
        #expect(units.filter { $0 < 0.5 }.count > 400 && units.filter { $0 < 0.5 }.count < 600)
    }

    @Test func aStreakFadesOutTowardThePlayBar() {
        #expect(StreakField.fade(atWindowFraction: 0) == 1)
        #expect(StreakField.fade(atWindowFraction: StreakField.fadeStart) == 1)
        #expect(abs(StreakField.fade(atWindowFraction: 0.625) - 0.5) < 1e-9)
        #expect(StreakField.fade(atWindowFraction: StreakField.fadeEnd) == 0)
        #expect(StreakField.fade(atWindowFraction: 1) == 0)
    }

    /// A head runs from 0 to its travel and starts again, so the Canvas and the layers agree.
    @Test func aStreakComesRoundAgain() {
        let field = StreakField(size: CGSize(width: 960, height: 600))
        let streak = Streak(index: 5)
        let lap = field.travel(streak) / streak.speed
        for time in [0, 1.5, 40, 1_000_000] {
            let head = field.head(streak, time: time)
            #expect((0..<field.travel(streak)).contains(head))
            #expect(abs(field.head(streak, time: time + lap) - head) < 1e-6)
        }
        #expect(abs(field.head(streak, time: 0) - streak.phase * field.travel(streak)) < 1e-9)
    }

    @Test func panicScrollsOnlyWhenItWouldNotFit() {
        let line = String(repeating: "x", count: 100)
        #expect(ProblemCard.fitsWithoutScrolling(Array(repeating: line, count: 8).joined(separator: "\n")))
        #expect(!ProblemCard.fitsWithoutScrolling(Array(repeating: "x", count: 9).joined(separator: "\n")))
        #expect(!ProblemCard.fitsWithoutScrolling(line + "x"))
    }

    /// The banner's pixels partway in, over the hero's backdrop.
    @Test func theRevealPartwayLooksAsRecorded() throws {
        let colors = HeroColors(palette: BannerPalette(banner: TestBanner.banner))
        let view = ZStack {
            HeroBackdrop(colors: colors)
            BannerFlight(banner: TestBanner.banner, scale: 4, progress: 0.55)
                .offset(x: 120)
        }
        try SnapshotTests.expectAsRecorded(
            try #require(Snapshot.render(view)), name: "disc-reveal-partway")
    }

    @Test func theRevealDrawsNothingAtItsStart() throws {
        let empty = try #require(Snapshot.render(Color.clear))
        let start = try #require(Snapshot.render(
            BannerFlight(banner: TestBanner.banner, scale: 4, progress: 0)))
        #expect(start == empty)
    }
}
