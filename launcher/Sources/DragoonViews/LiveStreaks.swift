import AppKit
import SwiftUI

/// The hero's streaks in the window, as one Core Animation layer each that the window server
/// moves at up to 30 frames a second. Each frame then costs the launcher nothing.
struct LiveStreaks: NSViewRepresentable {
    /// The banner's first hue, its second and white, as `Streak.colorIndex` picks them.
    let colors: [Color]
    let paused: Bool
    let still: Bool
    /// How many times their own speed the streaks run.
    var rate: Double = 1

    func makeNSView(context: Context) -> StreakLayerView {
        StreakLayerView()
    }

    func updateNSView(_ view: StreakLayerView, context: Context) {
        view.show(
            colors: colors.map { NSColor($0).cgColor }, paused: paused, still: still, rate: rate)
    }
}

final class StreakLayerView: NSView {
    /// The layer the streaks hang from, whose clock `show` stops, starts and runs at a rate.
    let field = CALayer()
    private var colors: [CGColor] = []
    private var still = false
    private var builtSize = CGSize.zero

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.addSublayer(field)
        // Fades the streaks out toward the Play bar. On macOS a layer's unit space starts at
        // the bottom.
        let mask = CAGradientLayer()
        mask.colors = [NSColor.clear.cgColor, NSColor.black.cgColor]
        mask.locations = [
            NSNumber(value: 1 - StreakField.fadeEnd), NSNumber(value: 1 - StreakField.fadeStart),
        ]
        mask.startPoint = CGPoint(x: 0.5, y: 0)
        mask.endPoint = CGPoint(x: 0.5, y: 1)
        layer?.mask = mask
    }

    required init?(coder: NSCoder) {
        nil
    }

    func show(colors: [CGColor], paused: Bool, still: Bool, rate: Double = 1) {
        if colors != self.colors || still != self.still {
            self.colors = colors
            self.still = still
            rebuild()
        }
        field.run(at: paused ? 0 : Float(rate))
    }

    override func layout() {
        super.layout()
        if bounds.size != builtSize { rebuild() }
    }

    /// One gradient layer a streak, laid out as `StreakField` lays them in a `Canvas`. The
    /// view's y runs up, so the field turns the other way and its lanes count from the top.
    private func rebuild() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }
        builtSize = bounds.size
        layer?.mask?.frame = bounds
        field.sublayers = nil
        guard colors.count == 3, bounds.width > 0, bounds.height > 0 else { return }
        let shape = StreakField(size: bounds.size)
        field.bounds = CGRect(x: 0, y: 0, width: shape.width, height: shape.height)
        field.position = CGPoint(x: bounds.midX, y: bounds.midY)
        field.setAffineTransform(CGAffineTransform(rotationAngle: -StreakField.angle.radians))
        for index in 0..<StreakField.count {
            let streak = Streak(index: index)
            let line = CAGradientLayer()
            let color = colors[streak.colorIndex]
            line.colors = [
                color.copy(alpha: 0) ?? color, color.copy(alpha: streak.opacity) ?? color,
            ]
            line.startPoint = CGPoint(x: 0, y: 0.5)
            line.endPoint = CGPoint(x: 1, y: 0.5)
            line.bounds = CGRect(x: 0, y: 0, width: streak.length, height: streak.width)
            line.cornerRadius = streak.width / 2
            // The layer hangs from its head.
            line.anchorPoint = CGPoint(x: 1, y: 0.5)
            line.position = CGPoint(
                x: shape.head(streak, time: 0), y: shape.height * (1 - streak.lane))
            if !still {
                let run = CABasicAnimation(keyPath: "position.x")
                run.fromValue = 0
                run.toValue = shape.travel(streak)
                run.duration = shape.travel(streak) / streak.speed
                run.timeOffset = streak.phase * run.duration
                run.repeatCount = .infinity
                run.preferredFrameRateRange = CAFrameRateRange(
                    minimum: 10, maximum: 30, preferred: 30)
                line.add(run, forKey: "run")
            }
            field.addSublayer(line)
        }
    }
}
