import DragoonCore
import SwiftUI

/// The banner, or `placeholder` while there's none. When a banner arrives its pixels fly in
/// over `duration` seconds, and under Reduce Motion it fades in instead. A banner there from
/// the start just shows.
struct BannerReveal<Placeholder: View>: View {
    static var duration: Double { 0.9 }

    let banner: DiscBanner?
    let scale: CGFloat
    @ViewBuilder let placeholder: () -> Placeholder

    var body: some View {
        ReduceMotionReader { reduceMotion in
            KeyframeAnimator(initialValue: 1.0, trigger: banner != nil) { progress in
                if let banner {
                    if progress >= 1 {
                        BannerLogo(banner: banner, scale: scale)
                    } else if reduceMotion {
                        BannerLogo(banner: banner, scale: scale).opacity(progress)
                    } else {
                        BannerFlight(banner: banner, scale: scale, progress: progress)
                    }
                } else {
                    placeholder()
                }
            } keyframes: { _ in
                KeyframeTrack {
                    MoveKeyframe(0.0)
                    LinearKeyframe(1.0, duration: Self.duration)
                }
            }
        }
    }
}

/// The banner's pixels on their way in, `progress` from 0 to 1. Each starts somewhere down and
/// to the left along the hero's streaks, waits its turn and slows into place trailing a streak
/// of its own color.
struct BannerFlight: View {
    /// How far left of its place a pixel can start, in points.
    static let reach: CGFloat = 520
    /// The most of `progress` a pixel waits before it sets off.
    static let mostDelay = 0.45

    let banner: DiscBanner
    let scale: CGFloat
    let progress: Double

    var body: some View {
        let size = CGSize(
            width: CGFloat(DiscBanner.width) * scale, height: CGFloat(DiscBanner.height) * scale)
        let drop = Self.reach * 0.25
        Color.clear
            .frame(width: size.width, height: size.height)
            .overlay(alignment: .topLeading) {
                Canvas { context, _ in
                    context.translateBy(x: Self.reach, y: drop)
                    draw(in: &context)
                }
                .frame(width: size.width + Self.reach, height: size.height + drop * 2)
                .offset(x: -Self.reach, y: -drop)
                .allowsHitTesting(false)
            }
    }

    private func draw(in context: inout GraphicsContext) {
        let rgba = banner.rgba
        let side = scale
        for index in 0..<DiscBanner.width * DiscBanner.height {
            let alpha = Double(rgba[index * 4 + 3]) / 255
            guard alpha > 0 else { continue }
            let delay = Streak.unit(index, 11) * Self.mostDelay
            let local = min(max((progress - delay) / (1 - Self.mostDelay), 0), 1)
            guard local > 0 else { continue }
            let eased = 1 - pow(1 - local, 3)
            let distance = 80 + Streak.unit(index, 12) * (Double(Self.reach) - 80)
            let home = CGPoint(
                x: CGFloat(index % DiscBanner.width) * side,
                y: CGFloat(index / DiscBanner.width) * side)
            // Up and to the right, the streaks' way, with a little spread.
            let rise = 0.21 + (Streak.unit(index, 13) - 0.5) * 0.3
            let left = (1 - eased) * distance
            let at = CGPoint(x: home.x - left, y: home.y + left * rise)
            let color = Color(
                .sRGB, red: Double(rgba[index * 4]) / 255, green: Double(rgba[index * 4 + 1]) / 255,
                blue: Double(rgba[index * 4 + 2]) / 255, opacity: alpha * min(1, local * 4))
            if left > 1 {
                var trail = Path()
                trail.move(to: CGPoint(x: at.x - left * 0.35, y: at.y + left * 0.35 * rise))
                trail.addLine(to: CGPoint(x: at.x + side / 2, y: at.y + side / 2))
                context.stroke(trail, with: .color(color.opacity(0.35)), lineWidth: side * 0.6)
            }
            context.fill(Path(CGRect(x: at.x, y: at.y, width: side, height: side)), with: .color(color))
        }
    }
}
