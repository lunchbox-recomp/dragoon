import DragoonCore
import SwiftUI

/// Play, what it's doing and the "..." menu with everything else Library does.
struct PlayBar: View {
    let state: Flow.State
    let send: Send
    let colors: HeroColors

    var body: some View {
        HStack(spacing: 20) {
            Button {
                send(.playPressed)
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "play.fill")
                    Text(state.playStatus == .playing ? Strings.playing : Strings.play)
                }
            }
            .buttonStyle(PlayButtonStyle(colors: colors))
            .keyboardShortcut(.defaultAction)
            .disabled(!state.libraryIsIdle)
            Text(Strings.playStatus(state.playStatus))
                .font(.title3)
                .foregroundStyle(.white.opacity(0.78))
            Spacer(minLength: 0)
            MoreMenu(state: state, send: send)
        }
    }
}

/// A 64 pt capsule in the banner's first hue.
struct PlayButtonStyle: ButtonStyle {
    let colors: HeroColors

    func makeBody(configuration: Configuration) -> some View {
        PlayCapsule(configuration: configuration, colors: colors)
    }
}

private struct PlayCapsule: View {
    let configuration: ButtonStyleConfiguration
    let colors: HeroColors
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        let increased = contrast == .increased
        configuration.label
            .font(.system(size: 24, weight: .bold, design: .rounded))
            .foregroundStyle(colors.buttonInk)
            .padding(.horizontal, 44)
            .frame(height: HeroColors.buttonHeight)
            .background(
                Capsule().fill(LinearGradient(
                    colors: [colors.buttonTop, colors.buttonBottom], startPoint: .top,
                    endPoint: .bottom)))
            .overlay(
                Capsule().strokeBorder(
                    .white.opacity(increased ? 0.9 : 0.3), lineWidth: increased ? 2 : 1))
            .contentShape(Capsule())
            .shadow(color: colors.buttonTop.opacity(isEnabled ? 0.5 : 0), radius: 20, y: 6)
            .saturation(isEnabled ? 1 : 0.25)
            .opacity(isEnabled ? 1 : 0.55)
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// Rebuild, Change Disc and Show Saves behind a round "..." button.
struct MoreMenu: View {
    let state: Flow.State
    let send: Send

    var body: some View {
        Menu {
            Button(Strings.rebuild) { send(.rebuildPressed) }
                .disabled(!state.libraryIsIdle)
            Button(Strings.changeDisc) { send(.changeDiscPressed) }
                .disabled(!state.libraryIsIdle)
            Divider()
            Button(Strings.showSaves) { send(.showSavesPressed) }
        } label: {
            Image(systemName: "ellipsis")
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 48, height: 48)
                .background(Circle().fill(.white.opacity(0.14)))
                .overlay(Circle().strokeBorder(.white.opacity(0.25)))
                .contentShape(Circle())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .accessibilityLabel(Strings.more)
    }
}
