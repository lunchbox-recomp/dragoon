import DragoonCore
import SwiftUI

/// The build's bar: one segment a step, each as wide as the step's measured time, filled in the
/// banner's first hue up to `fraction`. Package and swap share the sliver at the end. Drawn in
/// shapes, since `ImageRenderer` can't draw a `ProgressView`.
struct SegmentedBar: View {
    static let height: CGFloat = 12
    static let gap: CGFloat = 3

    /// Where each drawn segment starts along the bar and how wide it is, from 0 to 1.
    static let parts: [(segments: [BuildSegment], start: Double, width: Double)] = [
        ([.recompile], BuildSegment.recompile.start, BuildSegment.recompile.width),
        ([.compile], BuildSegment.compile.start, BuildSegment.compile.width),
        ([.warmup], BuildSegment.warmup.start, BuildSegment.warmup.width),
        ([.package, .swap], BuildSegment.package.start,
         BuildSegment.package.width + BuildSegment.swap.width),
    ]

    let fraction: Double
    let colors: HeroColors
    /// The step whose segment shimmers, as one that prints no progress does while it runs.
    var shimmering: BuildSegment?
    var shimmerPaused = false
    var reduceMotion = false
    /// The step the build stopped at, whose segment is outlined in red.
    var stopped: BuildSegment?

    var body: some View {
        GeometryReader { geometry in
            let usable = geometry.size.width - Self.gap * CGFloat(Self.parts.count - 1)
            HStack(spacing: Self.gap) {
                ForEach(Self.parts.indices, id: \.self) { index in
                    let part = Self.parts[index]
                    segment(part.segments, fill: Self.fill(fraction, start: part.start, width: part.width))
                        .frame(width: max(usable * part.width, 2))
                }
            }
        }
        .frame(height: Self.height)
        .accessibilityElement()
        .accessibilityLabel(Strings.buildMeter)
        .accessibilityValue(Strings.percent(fraction))
    }

    /// How much of a drawn segment the bar's fill covers, from 0 to 1.
    static func fill(_ fraction: Double, start: Double, width: Double) -> Double {
        min(max((fraction - start) / width, 0), 1)
    }

    private func segment(_ segments: [BuildSegment], fill: Double) -> some View {
        let shape = RoundedRectangle(cornerRadius: 3, style: .continuous)
        return ZStack(alignment: .leading) {
            shape.fill(.white.opacity(0.12))
            GeometryReader { geometry in
                shape
                    .fill(LinearGradient(
                        colors: [colors.buttonTop, colors.buttonBottom], startPoint: .top,
                        endPoint: .bottom))
                    .frame(width: geometry.size.width * fill)
            }
            if let shimmering, segments.contains(shimmering) {
                Shimmer(paused: shimmerPaused, fades: reduceMotion)
            }
            if let stopped, segments.contains(stopped) {
                shape.strokeBorder(Color(red: 1, green: 0.36, blue: 0.33), lineWidth: 2)
            }
        }
        .clipShape(shape)
    }
}
