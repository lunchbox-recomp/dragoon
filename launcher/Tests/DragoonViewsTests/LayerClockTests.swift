import QuartzCore
import Testing

@testable import DragoonViews

/// `hold`, which the build bar's shimmer stops and starts its clock with. The streaks run at a
/// rate through `run(at:)`, which `LiveStreaksTests` checks.
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
}
