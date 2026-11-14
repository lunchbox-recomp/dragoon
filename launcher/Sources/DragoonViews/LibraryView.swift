import DragoonCore
import SwiftUI

/// Where every later launch opens: the hero in the banner's colors with the banner over it,
/// then Play. Rebuild, Change Disc, Show Saves and Settings are in the "..." menu. Play grows
/// into the launch card, which covers the rest until the window is back after the game.
/// Settings opens a sheet over it.
struct LibraryView: View {
    let state: Flow.State
    let send: Send
    @Environment(\.windowIsActive) private var windowIsActive
    @Namespace private var launchSpace

    var body: some View {
        let colors = HeroColors(palette: BannerPalette(banner: state.banner))
        ReduceMotionReader { reduceMotion in
            ZStack {
                HeroBackdrop(colors: colors)
                HeroStreaks(
                    colors: colors,
                    // The card has streaks of its own.
                    paused: Motion.heroPaused(
                        windowIsActive: windowIsActive,
                        gameRunning: state.gameRunning || state.handOff != nil,
                        reduceMotion: reduceMotion),
                    still: reduceMotion
                )
                // The lower part darkens so the bar reads over any banner's colors.
                LinearGradient(
                    colors: [.clear, colors.ground.opacity(0.9)], startPoint: .center,
                    endPoint: .bottom)
                content(colors, launchSpace: reduceMotion ? nil : launchSpace)
                if let handOff = state.handOff {
                    card(handOff, colors: colors, reduceMotion: reduceMotion)
                }
            }
            .animation(
                reduceMotion ? .easeInOut(duration: 0.2) : .spring(duration: 0.45, bounce: 0.15),
                value: state.handOff == nil)
            .ignoresSafeArea()
        }
        .sheet(isPresented: Binding(
            get: { state.picture != nil },
            set: { if !$0 { send(.settingsDonePressed) } })
        ) {
            SettingsSheet(state: state, send: send)
        }
    }

    @ViewBuilder
    private func card(_ handOff: Flow.HandOff, colors: HeroColors, reduceMotion: Bool) -> some View {
        let card = LaunchCard(handOff: handOff, banner: state.banner, colors: colors)
            .transition(.opacity)
            .zIndex(1)
        if reduceMotion {
            card
        } else {
            card.matchedGeometryEffect(id: LaunchCard.geometryID, in: launchSpace)
        }
    }

    /// Play and the boxes above it always fit. The panic the player opened comes before the
    /// logo, so the logo shows only in what's left once the panic's scroller has its full
    /// height, and is left out when it doesn't fit there.
    private func content(_ colors: HeroColors, launchSpace: Namespace.ID?) -> some View {
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
            PlayBar(state: state, send: send, colors: colors, launchSpace: launchSpace)
        }
        .padding(.horizontal, 40)
        .padding(.top, 40)
        .padding(.bottom, 32)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
    }
}
