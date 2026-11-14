import DragoonCore
import Foundation
import SwiftUI
import Testing

@testable import DragoonViews

/// The build page's words for counts and times, and how its bar splits the fill.
struct BuildPageTests {
    @Test(arguments: [
        ("compile", 41, 135, "41 of 135 files"),
        ("warmup", 3, 8, "3 of 8 runs done"),
        ("sign", 1, 2, "1 of 2"),
    ])
    func countsHaveTheirUnits(step: String, done: Int, total: Int, text: String) {
        #expect(Strings.count(step: step, done: done, total: total) == text)
    }

    @Test(arguments: [
        (0.0, "0:00"), (5.9, "0:05"), (72, "1:12"), (600, "10:00"), (3725, "1:02:05"),
        (-3, "0:00"),
    ])
    func theClockIsMinutesAndSeconds(seconds: Double, text: String) {
        #expect(Strings.clock(seconds) == text)
    }

    @Test(arguments: [
        (0.4, "About 5 s left"), (21, "About 25 s left"), (55, "About 55 s left"),
        (56, "About 1 min left"), (96, "About 2 min left"), (150, "About 3 min left"),
    ])
    func theTimeLeftIsRoughAndRoundedUpUnderAMinute(seconds: Double, text: String) {
        #expect(Strings.timeLeft(seconds) == text)
    }

    @Test func theTimeLeftShowsOnlyOnceThereIsOne() {
        #expect(Strings.buildTime(elapsed: 14, left: nil) == "0:14")
        #expect(Strings.buildTime(elapsed: 14, left: 96) == "0:14  ·  About 2 min left")
    }

    static func samples(_ seconds: [Double]) -> [BuildSample] {
        seconds.enumerated().map {
            BuildSample(time: Date(timeIntervalSinceReferenceDate: $0.element), done: $0.offset + 1)
        }
    }

    /// The warm-up's runs roll their count, and the compile's files, several a second, don't.
    @Test(arguments: [
        ([], true), ([4.0], true), ([1.0, 2.0], true), ([1.0, 1.5], true), ([1.0, 1.4], false),
        ([1.0, 1.1, 5.0], true), ([1.0, 1.125, 1.25], false),
    ])
    func onlyACountThatChangesAtMostTwiceASecondRolls(seconds: [Double], rolls: Bool) {
        #expect(BuildMeterView.rollsCount(Self.samples(seconds)) == rolls)
    }

    @Test func theDrawnSegmentsCoverTheBarInOrder() {
        let parts = SegmentedBar.parts
        #expect(parts.map(\.segments) == [[.recompile], [.compile], [.warmup], [.package, .swap]])
        #expect(parts[0].start == 0)
        for (part, next) in zip(parts, parts.dropFirst()) {
            #expect(abs(part.start + part.width - next.start) < 1e-9)
        }
        let last = parts[parts.count - 1]
        #expect(abs(last.start + last.width - 1) < 1e-9)
    }

    /// A window that isn't key but can be seen, as when the player clicks another app, keeps
    /// its clock and stops its shimmer. One that can't be seen stops both.
    @Test(arguments: [
        (true, true, false, false), (false, true, true, false), (false, false, true, true),
    ])
    func theClockStopsOnlyWhenTheWindowCantBeSeen(
        active: Bool, visible: Bool, shimmerPaused: Bool, clockPaused: Bool
    ) {
        let paused = Motion.buildPaused(windowIsActive: active, windowIsVisible: visible)
        #expect(paused.shimmer == shimmerPaused)
        #expect(paused.clock == clockPaused)
    }

    static let barWidth = 400

    /// The bar alone, empty, at the build page's moment and one pixel a point.
    @MainActor
    static func bar(shimmering: BuildSegment?, fades: Bool) -> Bitmap? {
        let renderer = ImageRenderer(
            content: SegmentedBar(
                fraction: 0, colors: HeroColors(palette: BannerPalette(banner: nil)),
                shimmering: shimmering, reduceMotion: fades)
                .frame(width: CGFloat(barWidth))
                .background(Color(white: 0.12))
                .environment(\.animationClock, .fixed(Snapshot.buildMoment)))
        return renderer.cgImage.flatMap(Bitmap.init)
    }

    /// How many pixels differ between `one` and `other`, left of `x` and from `x` on.
    static func differing(_ one: Bitmap, _ other: Bitmap, splitAt x: Int) -> (left: Int, right: Int) {
        var counts = (left: 0, right: 0)
        for row in 0..<one.height {
            for column in 0..<one.width {
                let pixel = (row * one.width + column) * 4
                let off = (0..<3).contains {
                    abs(Int(one.bytes[pixel + $0]) - Int(other.bytes[pixel + $0]))
                        > Snapshot.channelTolerance
                }
                if off && column < x { counts.left += 1 } else if off { counts.right += 1 }
            }
        }
        return counts
    }

    @MainActor
    @Test func theBuildPageDrawsHalfAShimmerOn() {
        // As `Shimmer` takes its phase from a fixed clock.
        let phase = (Snapshot.buildMoment.timeIntervalSinceReferenceDate / Shimmer.period)
            .truncatingRemainder(dividingBy: 1)
        #expect(abs(phase - 0.5) < 1e-6)
    }

    /// The whole page's snapshot can't see a shimmer in a segment this small, so the bar is
    /// drawn on its own: the band, or under Reduce Motion the fade, lights the running step's
    /// segment and nothing else.
    @MainActor
    @Test(arguments: [false, true])
    func theShimmerLightsOnlyTheRunningStepsSegment(fades: Bool) throws {
        let still = try #require(Self.bar(shimmering: nil, fades: fades))
        let lit = try #require(Self.bar(shimmering: .recompile, fades: fades))
        #expect(still.width == Self.barWidth && lit.width == Self.barWidth)
        let usable = Double(Self.barWidth) - Double(SegmentedBar.gap) * 3
        let end = Int((usable * BuildSegment.recompile.width).rounded(.up))
        let segmentPixels = end * Int(SegmentedBar.height)
        let counts = Self.differing(still, lit, splitAt: end)
        #expect(counts.left > segmentPixels / 3, "\(counts.left) of \(segmentPixels) lit")
        #expect(counts.right == 0)
    }

    @Test(arguments: [(0.0, 0.0), (0.25, 0.0), (0.5, 0.5), (0.75, 1.0), (1.0, 1.0)])
    func eachSegmentFillsOnlyItsOwnShare(fraction: Double, fill: Double) {
        #expect(SegmentedBar.fill(fraction, start: 0.25, width: 0.5) == fill)
    }
}
