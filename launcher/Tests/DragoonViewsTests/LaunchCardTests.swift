import DragoonCore
import SwiftUI
import Testing

@testable import DragoonViews

/// Play's launch card: the phase each step of the hand-off holds, how each phase looks, and
/// what it says.
@MainActor
struct LaunchCardTests {
    @Test func eachStepHoldsItsPhase() {
        #expect(LaunchPhase(.charging) == .charge)
        #expect(LaunchPhase(.launched) == .launch)
        #expect(LaunchPhase(.hidden) == .launch)
        #expect(LaunchPhase(.returning) == .idle)
    }

    /// The logo goes from 1.0 to 1.08, and the streaks and the glow build with each phase.
    @Test func eachPhaseBuildsOnTheOneBefore() {
        let looks = LaunchPhase.allCases.map(LaunchLook.init)
        #expect(looks.first?.logoScale == 1.0)
        #expect(looks.last?.logoScale == 1.08)
        #expect(looks.first?.streakRate == 1)
        for (before, after) in zip(looks, looks.dropFirst()) {
            #expect(before.logoScale < after.logoScale)
            #expect(before.streakRate < after.streakRate)
            #expect(before.glow < after.glow)
        }
    }

    @Test func theCardSaysWhatTheLaunchIsDoing() {
        #expect(Strings.launchCard(.charging) == Strings.discChecking)
        #expect(Strings.launchCard(.launched) == "Starting the game…")
        #expect(Strings.launchCard(.hidden) == Strings.gameRunning)
        #expect(Strings.launchCard(.returning) == nil)
    }

    /// The card at rest and launched, and launched with Reduce Motion, where the logo keeps its
    /// size and the streaks stay at rest, all draw differently.
    @Test func thePhasesAndReduceMotionDrawDifferently() throws {
        func render(_ name: String) throws -> Bitmap {
            let fixture = try #require(screenFixtures.first { $0.name == name })
            return try #require(SnapshotTests.render(fixture))
        }
        let idle = try render("launch-card-idle")
        let launch = try render("launch-card-launch")
        let still = try render("launch-card-reduce-motion")
        for (one, other) in [(idle, launch), (launch, still), (idle, still)] {
            let differing = try #require(
                one.differingPixels(from: other, tolerance: Snapshot.channelTolerance))
            #expect(differing > Snapshot.allowedPixels)
        }
    }
}
