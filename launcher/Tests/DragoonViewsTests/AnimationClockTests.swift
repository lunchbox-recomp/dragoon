import DragoonCore
import Foundation
import SwiftUI
import Testing

@testable import DragoonViews

/// Library's streaks, the view that reads the clock.
private func streaks(still: Bool = false) -> some View {
    HeroStreaks(colors: HeroColors(palette: .fallback), paused: false, still: still)
}

/// How many pixels of two renders differ as a snapshot counts them. SwiftUI dithers the
/// streaks' gradients, so two renders of one frame needn't be the same bytes.
@MainActor
private func differing(_ view: some View, _ other: some View) throws -> Int {
    let first = try #require(Snapshot.render(view))
    let second = try #require(Snapshot.render(other))
    return try #require(first.differingPixels(from: second, tolerance: Snapshot.channelTolerance))
}

@MainActor
struct AnimationClockTests {
    @Test func aFixedClockDrawsTheSameFrameEveryTime() throws {
        let view = streaks().environment(\.animationClock, .fixed(Snapshot.moment + 7))
        #expect(try differing(view, view) == 0)
    }

    /// `Snapshot.render` fixes the clock at `Snapshot.moment`, and a view inside can name another.
    @Test func aFixedClockDrawsTheMomentItNames() throws {
        let later = streaks().environment(\.animationClock, .fixed(Snapshot.moment + 0.5))
        #expect(try differing(streaks(), later) > Snapshot.allowedPixels)
    }

    /// At rest, as Reduce Motion wants, the moment makes no difference.
    @Test func stillStreaksDrawTheSameAtAnyMoment() throws {
        let later = streaks(still: true).environment(\.animationClock, .fixed(Snapshot.moment + 0.5))
        #expect(try differing(streaks(still: true), later) == 0)
    }
}
