import QuartzCore

extension CALayer {
    /// Stops the layer's clock where it is, or starts it again from there, so every animation
    /// under it holds while nobody can see it.
    func hold(_ paused: Bool) {
        run(at: paused ? 0 : 1)
    }

    /// Runs the layer's clock at `rate` from where it is now, so its animations speed up, slow
    /// down or stop without a jump. A layer's time is `(parent - beginTime) * speed +
    /// timeOffset`, so starting the count again from now at now's time keeps it where it is.
    func run(at rate: Float) {
        guard rate != speed else { return }
        let now = CACurrentMediaTime()
        let at = convertTime(now, from: nil)
        beginTime = superlayer?.convertTime(now, from: nil) ?? now
        timeOffset = at
        speed = rate
    }
}
