import SwiftUI

/// Library's backdrop: the banner's first hue fading down to near-black, with a glow of its
/// second hue where the logo sits.
struct HeroBackdrop: View {
    let colors: HeroColors

    var body: some View {
        ZStack {
            LinearGradient(colors: [colors.sky, colors.ground], startPoint: .top, endPoint: .bottom)
            RadialGradient(
                colors: [colors.glow.opacity(0.32), .clear], center: UnitPoint(x: 0.22, y: 0.62),
                startRadius: 0, endRadius: 420)
        }
    }
}

/// Speed streaks drifting up and to the right. Nearer streaks are thicker, brighter and
/// faster. `paused` holds them where they are and `still` draws them at rest, as Reduce Motion
/// wants.
///
/// The window moves them with Core Animation, which runs in the window server. Redrawing a
/// SwiftUI `Canvas` at 30 frames a second cost the launcher 4 to 7% of a core on Library,
/// almost all of it AppKit's layout and display pass for each frame. A fixed clock, as the
/// snapshots use, draws the same streaks in a `Canvas` at that moment.
struct HeroStreaks: View {
    let colors: HeroColors
    let paused: Bool
    let still: Bool
    @Environment(\.animationClock) private var clock

    var body: some View {
        Group {
            switch clock {
            case .live:
                LiveStreaks(
                    colors: [colors.streakPrimary, colors.streakSecondary, .white],
                    paused: paused, still: still)
            case .fixed(let date):
                Canvas { context, size in
                    StreakField(size: size).draw(
                        in: &context, colors: colors,
                        time: still ? 0 : date.timeIntervalSinceReferenceDate)
                }
            }
        }
        .allowsHitTesting(false)
    }
}

/// Where the streaks run: a level field around the window's center, turned by `angle`, so it
/// covers the window once turned.
struct StreakField {
    static let count = 56
    /// The streaks rise 12° from level.
    static let angle = Angle.degrees(-12)
    /// A streak is at full strength above this fraction of the window's height and gone below
    /// `fadeEnd`, so the Play bar sits on calm ground.
    static let fadeStart = 0.4
    static let fadeEnd = 0.85

    let size: CGSize

    var width: Double { Double(size.width + size.height * 0.5) }
    var height: Double { Double(size.height * 1.3) }

    /// How far a streak runs before it starts again, from its tail at 0 to its head past the
    /// far edge.
    func travel(_ streak: Streak) -> Double { width + streak.length }

    /// Where the head is along the field at `time` seconds.
    func head(_ streak: Streak, time: Double) -> Double {
        let travel = travel(streak)
        return (time * streak.speed + streak.phase * travel).truncatingRemainder(dividingBy: travel)
    }

    /// How strong a streak is at a height in the window, from 0 to 1.
    static func fade(atWindowFraction y: Double) -> Double {
        1 - min(max((y - fadeStart) / (fadeEnd - fadeStart), 0), 1)
    }

    /// Every streak at `time`, faded by where its head is in the window.
    func draw(in context: inout GraphicsContext, colors: HeroColors, time: Double) {
        let palette = [colors.streakPrimary, colors.streakSecondary, Color.white]
        context.translateBy(x: size.width / 2, y: size.height / 2)
        context.rotate(by: Self.angle)
        context.translateBy(x: -width / 2, y: -height / 2)
        let sine = sin(Self.angle.radians), cosine = cos(Self.angle.radians)
        for index in 0..<Self.count {
            let streak = Streak(index: index)
            let head = head(streak, time: time)
            let y = streak.lane * height
            // The head's height in the window, once turned.
            let windowY = Double(size.height) / 2 + sine * (head - width / 2)
                + cosine * (y - height / 2)
            let fade = Self.fade(atWindowFraction: windowY / Double(size.height))
            guard fade > 0 else { continue }
            let color = palette[streak.colorIndex]
            let tail = CGPoint(x: head - streak.length, y: y)
            var path = Path()
            path.move(to: tail)
            path.addLine(to: CGPoint(x: head, y: y))
            context.stroke(
                path,
                with: .linearGradient(
                    Gradient(colors: [color.opacity(0), color.opacity(streak.opacity * fade)]),
                    startPoint: tail, endPoint: CGPoint(x: head, y: y)),
                style: StrokeStyle(lineWidth: streak.width, lineCap: .round))
        }
    }
}

/// One streak's fixed traits, drawn from its index so every launch looks the same.
struct Streak {
    /// From 0 at the top of the field to 1 at the bottom.
    let lane: Double
    /// From 0, far, to 1, near.
    let depth: Double
    /// Where along its run the streak starts, as a fraction.
    let phase: Double
    /// Picks the streak's color.
    let tint: Double

    init(index: Int) {
        lane = Self.unit(index, 0)
        depth = Self.unit(index, 1)
        phase = Self.unit(index, 2)
        tint = Self.unit(index, 3)
    }

    /// Points a second.
    var speed: Double { 26 + depth * 120 }
    var length: Double { 90 + depth * 260 }
    var width: Double { 1 + depth * 3 }
    var opacity: Double { 0.2 + depth * 0.6 }
    /// The banner's first hue, its second, or white.
    var colorIndex: Int { tint < 0.45 ? 0 : tint < 0.85 ? 1 : 2 }

    /// A number from 0 up to 1 that `index` and `salt` always give, from SplitMix64's mixer.
    static func unit(_ index: Int, _ salt: UInt64) -> Double {
        var bits = UInt64(truncatingIfNeeded: index) &* 0x9E37_79B9_7F4A_7C15
            &+ salt &* 0xD1B5_4A32_D192_ED03
        bits = (bits ^ (bits >> 30)) &* 0xBF58_476D_1CE4_E5B9
        bits = (bits ^ (bits >> 27)) &* 0x94D0_49BB_1331_11EB
        bits ^= bits >> 31
        return Double(bits >> 11) / Double(UInt64(1) << 53)
    }
}
