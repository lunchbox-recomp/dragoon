import DragoonCore
import SwiftUI

/// Library's Settings sheet: the game's aspect, fullscreen and scale, with a preview of each.
/// Every change is a `pictureChosen`, which the flow saves to `settings.txt` while Library is
/// idle. The choices are drawn in shapes, with the game's Display page's labels in its order,
/// so a snapshot shows them.
public struct SettingsSheet: View {
    /// The sheet's size in points, which fits in the window at its smallest.
    nonisolated public static let size = CGSize(width: 640, height: 500)

    let state: Flow.State
    let send: Send
    @Environment(\.pictureDisplay) private var display

    public init(state: Flow.State, send: @escaping Send) {
        self.state = state
        self.send = send
    }

    public var body: some View {
        let picture = state.picture ?? PictureSettings()
        let colors = HeroColors(palette: BannerPalette(banner: state.banner))
        VStack(alignment: .leading, spacing: 12) {
            Text(Strings.settingsTitle).font(.title2.weight(.semibold))
            PicturePreview(picture, display: display, colors: colors)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(LibraryPanel(tint: colors.glow))
            // Two lines whatever the aspect says, so the choices stay put as it changes.
            note(Strings.aspectNote(picture.aspect))
                .lineLimit(2, reservesSpace: true)
            choices(picture, colors: colors)
                .disabled(!state.libraryIsIdle)
            Spacer(minLength: 0)
            HStack(alignment: .center, spacing: 12) {
                footer
                Spacer(minLength: 8)
                Button(Strings.done) { send(.settingsDonePressed) }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(width: Self.size.width, height: Self.size.height, alignment: .topLeading)
        .background(colors.ground)
        .environment(\.colorScheme, .dark)
    }

    /// The aspect, fullscreen and scale, each with its heading at the left and what it does
    /// under it.
    private func choices(_ picture: PictureSettings, colors: HeroColors) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            row(Strings.aspectHeading) {
                HStack(spacing: 8) {
                    ForEach(PictureSettings.aspects, id: \.self) { aspect in
                        choice(Strings.aspectLabel(aspect), selected: picture.aspect == aspect, colors: colors) {
                            var next = picture
                            next.aspect = aspect
                            send(.pictureChosen(next))
                        }
                    }
                }
            }
            row(nil) {
                VStack(alignment: .leading, spacing: 6) {
                    Toggle(Strings.fullscreen, isOn: Binding(
                        get: { picture.fullscreen },
                        set: { on in
                            var next = picture
                            next.fullscreen = on
                            send(.pictureChosen(next))
                        }))
                    .toggleStyle(CheckStyle(colors: colors))
                    note(Strings.windowNote(PicturePreview.layout(picture, display: display)))
                }
                .padding(.bottom, 8)
            }
            row(Strings.scaleHeading) {
                HStack(alignment: .center, spacing: 6) {
                    ForEach(1...PictureSettings.maxScale, id: \.self) { scale in
                        choice(
                            Strings.scaleLabel(scale),
                            selected: min(picture.scale, PictureSettings.maxScale) == scale, colors: colors
                        ) {
                            var next = picture
                            next.scale = scale
                            send(.pictureChosen(next))
                        }
                    }
                    Spacer(minLength: 8)
                    ScaleSteps(scale: picture.scale, colors: colors)
                }
            }
            row(nil) {
                note(Strings.scaleNote(picture.scale))
            }
        }
    }

    /// A heading in a column of its own width, then `content` in the rest.
    private func row(_ heading: String?, @ViewBuilder content: () -> some View) -> some View {
        HStack(alignment: .center, spacing: 16) {
            Text(heading ?? "")
                .font(.headline)
                .frame(width: 100, alignment: .leading)
            content()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// Why the last change wasn't saved, or when the game reads the file.
    @ViewBuilder
    private var footer: some View {
        if let failure = state.pictureFailure {
            VStack(alignment: .leading, spacing: 4) {
                Label(Strings.pictureFailure(failure), systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .foregroundStyle(ProblemCard.alert)
                if let reason = failure.reason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.6))
                        .textSelection(.enabled)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
        } else {
            Text(Strings.settingsWhen)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.6))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func note(_ text: String) -> some View {
        Text(text)
            .font(.callout)
            .foregroundStyle(.white.opacity(0.78))
            .fixedSize(horizontal: false, vertical: true)
    }

    private func choice(
        _ label: String, selected: Bool, colors: HeroColors, action: @escaping () -> Void
    ) -> some View {
        Button(label, action: action)
            .buttonStyle(ChoiceStyle(selected: selected, colors: colors))
            .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// One of a row of choices, filled in the banner's first hue when it's the one chosen.
private struct ChoiceStyle: ButtonStyle {
    let selected: Bool
    let colors: HeroColors

    func makeBody(configuration: Configuration) -> some View {
        ChoiceCapsule(configuration: configuration, selected: selected, colors: colors)
    }
}

private struct ChoiceCapsule: View {
    let configuration: ButtonStyleConfiguration
    let selected: Bool
    let colors: HeroColors
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        let increased = contrast == .increased
        let shape = RoundedRectangle(cornerRadius: 8, style: .continuous)
        configuration.label
            .font(.system(size: 14, weight: selected ? .bold : .regular))
            .lineLimit(1)
            .fixedSize()
            .foregroundStyle(selected ? colors.buttonInk : .white)
            .padding(.horizontal, 11)
            .frame(minWidth: 38, minHeight: 30)
            .background(shape.fill(selected ? colors.buttonTop : .white.opacity(0.1)))
            .overlay(
                shape.strokeBorder(
                    .white.opacity(selected || increased ? 0.8 : 0.25), lineWidth: increased ? 2 : 1))
            .contentShape(shape)
            .opacity(isEnabled ? (configuration.isPressed ? 0.75 : 1) : 0.5)
    }
}

/// A checkbox drawn in shapes.
private struct CheckStyle: ToggleStyle {
    let colors: HeroColors

    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            HStack(spacing: 8) {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(configuration.isOn ? colors.buttonTop : .white.opacity(0.1))
                    RoundedRectangle(cornerRadius: 4)
                        .strokeBorder(.white.opacity(0.6))
                    if configuration.isOn {
                        Path { tick in
                            tick.move(to: CGPoint(x: 4.5, y: 9.5))
                            tick.addLine(to: CGPoint(x: 7.5, y: 12.5))
                            tick.addLine(to: CGPoint(x: 13.5, y: 5.5))
                        }
                        .stroke(colors.buttonInk, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                    }
                }
                .frame(width: 18, height: 18)
                configuration.label
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(configuration.isOn ? .isSelected : [])
    }
}
