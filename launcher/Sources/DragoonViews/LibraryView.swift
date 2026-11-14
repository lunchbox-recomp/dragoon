import DragoonCore
import SwiftUI

/// Where every later launch opens: the hero in the banner's colors with the banner over it,
/// then Play. Rebuild, Change Disc and Show Saves are in the "..." menu.
struct LibraryView: View {
    let state: Flow.State
    let send: Send
    @Environment(\.windowIsActive) private var windowIsActive

    var body: some View {
        let colors = HeroColors(palette: BannerPalette(banner: state.banner))
        ReduceMotionReader { reduceMotion in
            ZStack {
                HeroBackdrop(colors: colors)
                HeroStreaks(
                    colors: colors,
                    paused: Motion.heroPaused(
                        windowIsActive: windowIsActive, gameRunning: state.gameRunning,
                        reduceMotion: reduceMotion),
                    still: reduceMotion
                )
                // The lower part darkens so the bar reads over any banner's colors.
                LinearGradient(
                    colors: [.clear, colors.ground.opacity(0.9)], startPoint: .center,
                    endPoint: .bottom)
                content(colors)
            }
            .ignoresSafeArea()
        }
    }

    /// Play and the boxes above it always fit. The panic the player opened comes before the
    /// logo, so the logo shows only in what's left once the panic's scroller has its full
    /// height, and is left out when it doesn't fit there.
    private func content(_ colors: HeroColors) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Spacer(minLength: 0).layoutPriority(-1)
            ViewThatFits(in: .vertical) {
                BannerReveal(banner: state.banner, scale: 4) {
                    Wordmark(colors: colors)
                }
                .padding(.bottom, 12)
                Color.clear.frame(height: 0)
            }
            .layoutPriority(1)
            if let offer = state.rebuildOffer {
                RebuildStrip(offer: offer, idle: state.libraryIsIdle, send: send, colors: colors)
            }
            if let problem = state.gameProblem {
                ProblemCard(problem: problem, panicShown: state.panicShown, send: send)
                    .layoutPriority(2)
            }
            PlayBar(state: state, send: send, colors: colors)
        }
        .padding(.horizontal, 40)
        .padding(.top, 40)
        .padding(.bottom, 32)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
    }
}
