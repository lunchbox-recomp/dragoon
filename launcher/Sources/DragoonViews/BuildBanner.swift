import DragoonCore
import SwiftUI

/// The disc's banner on the build page, gray when the build starts and in full color when it's
/// done, over a glow of its second hue that pulses once as the build finishes. Under Reduce
/// Motion the glow only fades up.
struct BuildBanner: View {
    /// The glow's pulse, in seconds.
    static let pulseLength = 1.4

    let banner: DiscBanner?
    /// From 0, gray, to 1, the banner's own colors.
    let saturation: Double
    let colors: HeroColors
    let finished: Bool

    var body: some View {
        ReduceMotionReader { reduceMotion in
            // As `.saturation(saturation)`, which leaves a banner in full color at 0. It fades
            // to gray and out of it, and otherwise steps with the bar: easing each step kept
            // SwiftUI drawing all through the compile, at 2.6% of a core.
            BannerReveal(banner: banner, scale: 3) { EmptyView() }
                .grayscale(1 - saturation)
                .animation(.easeInOut(duration: 0.4), value: saturation == 0)
                .background {
                    if banner != nil {
                        glow(trigger: reduceMotion ? false : finished)
                            .animation(.easeInOut(duration: 0.6), value: finished)
                    }
                }
        }
    }

    private func glow(trigger: Bool) -> some View {
        KeyframeAnimator(initialValue: 0.0, trigger: trigger) { pulse in
            Ellipse()
                .fill(RadialGradient(
                    colors: [colors.glow.opacity(glowStrength + 0.4 * pulse), .clear],
                    center: .center, startRadius: 0, endRadius: 190))
                .frame(width: 380, height: 160)
                .scaleEffect(1 + 0.2 * pulse)
                .allowsHitTesting(false)
        } keyframes: { _ in
            KeyframeTrack {
                CubicKeyframe(1.0, duration: Self.pulseLength * 0.25)
                CubicKeyframe(0.3, duration: Self.pulseLength * 0.25)
                CubicKeyframe(0.8, duration: Self.pulseLength * 0.2)
                CubicKeyframe(0.0, duration: Self.pulseLength * 0.3)
            }
        }
    }

    /// The glow is strongest once the build is done.
    private var glowStrength: Double { finished ? 0.5 : 0.2 }
}
