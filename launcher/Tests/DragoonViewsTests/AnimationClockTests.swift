import Foundation
import SwiftUI
import Testing

@testable import DragoonViews

/// A bar whose width follows the second of the time it's given, so two moments draw apart.
private struct SecondsBar: View {
    var body: some View {
        ClockedTimeline { date in
            let second = Calendar(identifier: .gregorian).component(.second, from: date)
            Rectangle().frame(width: CGFloat(second * 10), height: 20)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

@MainActor
struct AnimationClockTests {
    @Test func aFixedClockDrawsTheSameFrameEveryTime() throws {
        let bar = SecondsBar().environment(\.animationClock, .fixed(Snapshot.moment + 7))
        let first = try #require(Snapshot.render(bar))
        let second = try #require(Snapshot.render(bar))
        #expect(first == second)
    }

    /// `Snapshot.render` fixes the clock at `Snapshot.moment`, and a view inside can name another.
    @Test func aFixedClockDrawsTheMomentItNames() throws {
        let fixed = try #require(Snapshot.render(SecondsBar()))
        let later = try #require(Snapshot.render(
            SecondsBar().environment(\.animationClock, .fixed(Snapshot.moment + 30))))
        #expect(fixed != later)
    }
}
