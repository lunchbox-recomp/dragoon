import DragoonCore
import SwiftUI
import Testing

@testable import DragoonViews

/// Which look the banner's reveal takes, with Reduce Motion on and off.
@MainActor
struct BannerRevealTests {
    @Test func theRevealFliesInFadesUnderReduceMotionAndEndsInPlace() {
        typealias Look = BannerRevealFrame.Look
        #expect(Look.at(0.5, reduceMotion: false) == .flight(progress: 0.5))
        #expect(Look.at(0.5, reduceMotion: true) == .fade(opacity: 0.5))
        #expect(Look.at(0, reduceMotion: true) == .fade(opacity: 0))
        #expect(Look.at(1, reduceMotion: false) == .logo)
        #expect(Look.at(1, reduceMotion: true) == .logo)
    }

    /// Halfway through under Reduce Motion, the banner is in place at half strength, over the
    /// hero's backdrop.
    @Test func theRevealHalfwayUnderReduceMotionLooksAsRecorded() throws {
        let colors = HeroColors(palette: BannerPalette(banner: TestBanner.banner))
        let view = ZStack {
            HeroBackdrop(colors: colors)
            BannerRevealFrame(banner: TestBanner.banner, scale: 4, progress: 0.5)
        }
        .environment(\.reducesMotion, true)
        try SnapshotTests.expectAsRecorded(
            try #require(Snapshot.render(view)), name: "disc-reveal-reduce-motion")
    }
}
