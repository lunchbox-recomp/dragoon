import QuartzCore
import Testing

@testable import DragoonViews

/// `hold`, which the build bar's shimmer stops and starts its clock with, and `run(at:)` under a
/// parent with a clock of its own. The streaks' rates are in `LiveStreaksTests`.
struct LayerClockTests {
    @Test func holdStopsTheClockAndStartsItAgainAtItsOwnSpeed() {
        let parent = CALayer()
        let layer = CALayer()
        parent.addSublayer(layer)
        layer.hold(true)
        #expect(layer.speed == 0)
        layer.hold(false)
        #expect(layer.speed == 1)
    }

    /// Starting again carries on from where the clock stopped, here 7.25 seconds on its own
    /// clock.
    @Test func aHeldLayerCarriesOnFromWhereItStopped() {
        let parent = CALayer()
        let layer = CALayer()
        parent.addSublayer(layer)
        layer.hold(true)
        layer.timeOffset = 7.25
        let before = CACurrentMediaTime()
        layer.hold(false)
        let local = layer.convertTime(CACurrentMediaTime(), from: nil)
        #expect(local >= 7.25 - 1e-6)
        #expect(local <= 7.25 + (CACurrentMediaTime() - before) + 1e-6)
    }

    /// The count starts again from the parent's time, not the media clock's. Under a parent
    /// that runs at speed 2 from a `beginTime` of 100 the two differ by far more than the
    /// microseconds the change takes, so the layer's time carries on from where it was.
    @Test func aChangedRateCarriesOnUnderAParentWithItsOwnClock() {
        let parent = CALayer()
        parent.speed = 2
        parent.beginTime = 100
        let layer = CALayer()
        parent.addSublayer(layer)
        let start = CACurrentMediaTime()
        let before = layer.convertTime(CACurrentMediaTime(), from: nil)
        layer.run(at: 0.5)
        let after = layer.convertTime(CACurrentMediaTime(), from: nil)
        // The layer's time runs at twice the media clock's pace before the change and at its pace
        // after, so it moves by at most twice the time taken.
        #expect(after >= before - 1e-6)
        #expect(after <= before + 2 * (CACurrentMediaTime() - start) + 1e-6)
        #expect(layer.speed == 0.5)
    }
}
