import QuartzCore

extension CALayer {
    /// Stops the layer's clock where it is, or starts it again from there, so every animation
    /// under it holds while nobody can see it.
    func hold(_ paused: Bool) {
        if paused, speed != 0 {
            let now = convertTime(CACurrentMediaTime(), from: nil)
            speed = 0
            timeOffset = now
        } else if !paused, speed == 0 {
            let stoppedAt = timeOffset
            speed = 1
            timeOffset = 0
            beginTime = 0
            beginTime = convertTime(CACurrentMediaTime(), from: nil) - stoppedAt
        }
    }
}
