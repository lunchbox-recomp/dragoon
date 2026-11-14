import DragoonCore
import SwiftUI

/// Where the launch card is in its motion: at rest as it opens, charging while the disc is
/// checked, and launched once the game has started.
enum LaunchPhase: CaseIterable {
    case idle, charge, launch

    /// The phase the card holds for a step of the hand-off.
    init(_ handOff: Flow.HandOff) {
        switch handOff {
        case .charging: self = .charge
        case .launched, .hidden: self = .launch
        case .returning: self = .idle
        }
    }
}

/// How the card looks in a phase. The logo goes from 1.0 to 1.08 and the streaks from their own
/// speed to six times it.
struct LaunchLook: Equatable {
    var logoScale: CGFloat
    var streakRate: Double
    /// How strong the glow behind the logo is, from 0 to 1.
    var glow: Double

    init(_ phase: LaunchPhase) {
        switch phase {
        case .idle: (logoScale, streakRate, glow) = (1.0, 1, 0.3)
        case .charge: (logoScale, streakRate, glow) = (1.03, 2.5, 0.55)
        case .launch: (logoScale, streakRate, glow) = (1.08, 6, 0.85)
        }
    }
}

/// Play's launch card, which fills the window from Play until the game's window is up, and
/// again as the window comes back after the game. It grows out of the Play button
/// (`matchedGeometryEffect` in `LibraryView`).
///
/// While the disc is checked a `phaseAnimator` runs idle to charge and back. A phase animator
/// ends each run on its first phase, so it can't hold launch, and the launch step is a spring on
/// the hand-off instead. Under Reduce Motion the card only fades: the logo keeps its size and
/// the streaks stay at rest. A fixed clock, as the snapshots use, draws each step's phase.
struct LaunchCard: View {
    static let geometryID = "play"

    let handOff: Flow.HandOff
    let banner: DiscBanner?
    let colors: HeroColors
    @Environment(\.animationClock) private var clock
    @Environment(\.windowIsActive) private var windowIsActive

    var body: some View {
        ReduceMotionReader { reduceMotion in
            let rest = LaunchPhase(handOff)
            ZStack {
                HeroBackdrop(colors: colors)
                HeroStreaks(
                    colors: colors, paused: !windowIsActive || reduceMotion, still: reduceMotion,
                    rate: LaunchLook(rest).streakRate)
                VStack(spacing: 36) {
                    logo(rest: rest, reduceMotion: reduceMotion)
                    // On the way back there's no line, but its height stays, so the logo stays
                    // where it was.
                    let line = Strings.launchCard(handOff)
                    Text(line ?? " ")
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.85))
                        .opacity(line == nil ? 0 : 1)
                        .accessibilityHidden(line == nil)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
    }

    @ViewBuilder
    private func logo(rest: LaunchPhase, reduceMotion: Bool) -> some View {
        let face = LaunchFace(banner: banner, colors: colors)
        if reduceMotion {
            face.modifier(LaunchLookEffect(look: LaunchLook(rest), colors: colors, scales: false))
        } else if case .fixed = clock {
            face.modifier(LaunchLookEffect(look: LaunchLook(rest), colors: colors, scales: true))
        } else {
            face
                .phaseAnimator([LaunchPhase.idle, .charge], trigger: handOff) { content, phase in
                    content.modifier(LaunchLookEffect(
                        look: LaunchLook(handOff == .charging ? phase : rest), colors: colors,
                        scales: true))
                } animation: { _ in
                    .easeInOut(duration: 0.3)
                }
                .animation(.spring(duration: 0.35, bounce: 0.35), value: handOff)
        }
    }
}

/// The banner at 4x, or the wordmark with no banner, as Library shows them.
private struct LaunchFace: View {
    let banner: DiscBanner?
    let colors: HeroColors

    var body: some View {
        if let banner {
            BannerLogo(banner: banner, scale: 4)
        } else {
            Wordmark(colors: colors)
        }
    }
}

/// A look on the logo: its size, and the glow behind it.
private struct LaunchLookEffect: ViewModifier {
    static let glowRadius: CGFloat = 380

    let look: LaunchLook
    let colors: HeroColors
    /// Whether the logo grows, which Reduce Motion leaves out.
    let scales: Bool

    func body(content: Content) -> some View {
        content
            .scaleEffect(scales ? look.logoScale : 1)
            .background {
                // Square and past twice the radius, so the glow is gone before any edge.
                RadialGradient(
                    colors: [colors.glow.opacity(look.glow), .clear], center: .center,
                    startRadius: 0, endRadius: Self.glowRadius)
                    .frame(width: Self.glowRadius * 2 + 2, height: Self.glowRadius * 2 + 2)
                    .allowsHitTesting(false)
            }
    }
}
