import DragoonCore
import SwiftUI

/// The one-time "Picture: 4:3 or 16:9" card under Play on the first game's Ready to Play page:
/// the Settings sheet's preview at 4:3 and at 16:9 side by side, each a button that saves its
/// aspect, and Keep 4:3, which saves nothing. The other aspects are in the sheet.
struct PictureCardView: View {
    /// The previews' height in points, which fits the card under Play at the window's smallest.
    static let previewHeight: CGFloat = 80

    let card: Flow.PictureCard
    /// Whether a pick does anything now, `Flow.State.pictureCardIsIdle`.
    let idle: Bool
    let colors: HeroColors
    let send: Send
    @Environment(\.pictureDisplay) private var display

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            HStack(alignment: .top, spacing: 10) {
                ForEach(Flow.PictureCard.aspects, id: \.self) { aspect in
                    tile(aspect)
                }
            }
            .fixedSize()
            VStack(alignment: .leading, spacing: 4) {
                Text(Strings.pictureCardTitle).font(.headline)
                if let failure = card.failure {
                    Label(Strings.pictureFailure(failure), systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(ProblemCard.alert)
                        .fixedSize(horizontal: false, vertical: true)
                    if let reason = failure.reason {
                        Text(reason)
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.6))
                            .lineLimit(2)
                            .textSelection(.enabled)
                    }
                } else {
                    Text(Strings.pictureCardNote)
                        .font(.callout)
                        .foregroundStyle(.white.opacity(0.78))
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 4)
                Button(Strings.pictureCardKeep) { send(.pictureCardSkipped) }
                    .disabled(!idle)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        // As tall as the previews or the text, whichever is taller, and no taller.
        .fixedSize(horizontal: false, vertical: true)
        .padding(12)
        .background(LibraryPanel(tint: colors.glow))
    }

    /// The preview at `aspect` with its label under it, as one button.
    private func tile(_ aspect: String) -> some View {
        var picture = card.picture
        picture.aspect = aspect
        return Button {
            send(.pictureCardPicked(aspect))
        } label: {
            VStack(spacing: 4) {
                PicturePreview(picture, display: display, colors: colors, frameHeight: Self.previewHeight)
                Text(Strings.aspectLabel(aspect)).font(.system(size: 14, weight: .semibold))
            }
        }
        .buttonStyle(TileStyle())
        .disabled(!idle)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Strings.pictureCardUse(aspect))
        .accessibilityAddTraits(.isButton)
    }
}

/// A preview and its label in a rounded frame, drawn in shapes so a snapshot shows it.
private struct TileStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        Tile(configuration: configuration)
    }
}

private struct Tile: View {
    let configuration: ButtonStyleConfiguration
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        let increased = contrast == .increased
        let shape = RoundedRectangle(cornerRadius: 8, style: .continuous)
        configuration.label
            .foregroundStyle(.white)
            .padding(6)
            .background(shape.fill(.white.opacity(configuration.isPressed ? 0.2 : 0.08)))
            .overlay(shape.strokeBorder(.white.opacity(increased ? 0.8 : 0.3), lineWidth: increased ? 2 : 1))
            .contentShape(shape)
            .opacity(isEnabled ? 1 : 0.5)
    }
}
