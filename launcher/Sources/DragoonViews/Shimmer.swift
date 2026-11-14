import AppKit
import SwiftUI

/// A band of light sweeping across a segment whose step prints no progress, so the bar shows
/// the step is running without moving its fill. Under Reduce Motion the segment's light fades
/// up and down in place instead. `paused` holds it where it is.
///
/// The window runs it with Core Animation, so a frame costs the launcher nothing, as the hero's
/// streaks do. A fixed clock draws the band where it is at that moment.
struct Shimmer: View {
    /// Seconds for the band to cross once, or for the fade to go up and down.
    static let period = 1.6
    /// The band's width as a share of the segment's.
    static let band = 0.7

    let paused: Bool
    let fades: Bool
    @Environment(\.animationClock) private var clock

    var body: some View {
        Group {
            switch clock {
            case .live:
                LiveShimmer(paused: paused, fades: fades)
            case .fixed(let date):
                GeometryReader { geometry in
                    still(at: date.timeIntervalSinceReferenceDate, width: geometry.size.width)
                }
            }
        }
        .allowsHitTesting(false)
    }

    @ViewBuilder
    private func still(at time: Double, width: CGFloat) -> some View {
        let phase = (time / Self.period).truncatingRemainder(dividingBy: 1)
        if fades {
            Color.white.opacity(0.08 + 0.22 * (1 - abs(phase * 2 - 1)))
        } else {
            let band = width * Self.band
            LinearGradient(
                colors: [.white.opacity(0), .white.opacity(0.45), .white.opacity(0)],
                startPoint: .leading, endPoint: .trailing
            )
            .frame(width: band)
            .offset(x: -band + (width + band) * phase)
        }
    }
}

private struct LiveShimmer: NSViewRepresentable {
    let paused: Bool
    let fades: Bool

    func makeNSView(context: Context) -> ShimmerLayerView {
        ShimmerLayerView()
    }

    func updateNSView(_ view: ShimmerLayerView, context: Context) {
        view.show(paused: paused, fades: fades)
    }
}

final class ShimmerLayerView: NSView {
    private let light = CAGradientLayer()
    private var fades = false
    private var builtSize = CGSize.zero

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.masksToBounds = true
        layer?.addSublayer(light)
    }

    required init?(coder: NSCoder) {
        nil
    }

    func show(paused: Bool, fades: Bool) {
        if fades != self.fades {
            self.fades = fades
            rebuild()
        }
        light.hold(paused)
    }

    override func layout() {
        super.layout()
        if bounds.size != builtSize { rebuild() }
    }

    private func rebuild() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }
        builtSize = bounds.size
        light.removeAllAnimations()
        guard bounds.width > 0 else { return }
        let animation: CABasicAnimation
        if fades {
            light.colors = [NSColor.white.cgColor, NSColor.white.cgColor]
            light.frame = bounds
            animation = CABasicAnimation(keyPath: "opacity")
            animation.fromValue = 0.08
            animation.toValue = 0.3
            animation.autoreverses = true
            animation.duration = Shimmer.period / 2
        } else {
            let band = bounds.width * Shimmer.band
            light.colors = [
                NSColor.white.withAlphaComponent(0).cgColor,
                NSColor.white.withAlphaComponent(0.45).cgColor,
                NSColor.white.withAlphaComponent(0).cgColor,
            ]
            light.startPoint = CGPoint(x: 0, y: 0.5)
            light.endPoint = CGPoint(x: 1, y: 0.5)
            light.bounds = CGRect(x: 0, y: 0, width: band, height: bounds.height)
            light.position = CGPoint(x: -band / 2, y: bounds.midY)
            animation = CABasicAnimation(keyPath: "position.x")
            animation.fromValue = -band / 2
            animation.toValue = bounds.width + band / 2
            animation.duration = Shimmer.period
        }
        animation.repeatCount = .infinity
        animation.preferredFrameRateRange = CAFrameRateRange(minimum: 10, maximum: 30, preferred: 30)
        light.add(animation, forKey: "shimmer")
    }
}
