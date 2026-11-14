import DragoonCore
import SwiftUI

/// The rebuild offer as a strip above Play.
struct RebuildStrip: View {
    let offer: RebuildOffer
    let idle: Bool
    let send: Send
    let colors: HeroColors

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.triangle.2.circlepath")
                .foregroundStyle(colors.glow)
            Text(Strings.rebuildOffer(offer))
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Button(Strings.later) { send(.rebuildLaterPressed) }
            Button(Strings.rebuildNow) { send(.rebuildPressed) }
                .disabled(!idle)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(LibraryPanel(tint: colors.glow))
    }
}

/// How the last game ended, with its `panic.txt` behind a button.
struct ProblemCard: View {
    static let alert = Color(red: 1, green: 0.45, blue: 0.38)
    /// A long panic's scroller is 150 points tall when the window has room and shrinks to 60
    /// when it hasn't.
    static let scrollerHeights: ClosedRange<CGFloat> = 60...150

    let problem: GameProblem
    let panicShown: Bool
    let send: Send

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(Self.alert)
                Text(Strings.gameFailed(problem))
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if case .exited(_, _?) = problem {
                    Button {
                        send(.showPanicPressed)
                    } label: {
                        Label(
                            panicShown ? Strings.hidePanic : Strings.showPanic,
                            systemImage: panicShown ? "chevron.up" : "chevron.down")
                    }
                }
            }
            if panicShown, case .exited(_, let panic?) = problem {
                Text(Strings.panicHeading).font(.headline)
                Group {
                    // A short panic.txt is plain text, which a snapshot can draw.
                    if Self.fitsWithoutScrolling(panic.text) {
                        panicText(panic)
                    } else {
                        ScrollView { panicText(panic) }
                            .frame(minHeight: Self.scrollerHeights.lowerBound,
                                   maxHeight: Self.scrollerHeights.upperBound)
                    }
                }
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous).fill(.black.opacity(0.35)))
                if panic.cut {
                    Text(Strings.panicCut).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
        .background(LibraryPanel(tint: Self.alert))
    }

    /// At most 8 lines of at most 100 characters fit in 150 points, the scroller's tallest.
    static func fitsWithoutScrolling(_ text: String) -> Bool {
        let lines = text.split(separator: "\n", omittingEmptySubsequences: false)
        return lines.count <= 8 && lines.allSatisfy { $0.count <= 100 }
    }

    private func panicText(_ panic: GamePanic) -> some View {
        Text(panic.text)
            .font(.caption.monospaced())
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// A rounded panel washed in `tint`, drawn in shapes so a snapshot shows it.
struct LibraryPanel: View {
    let tint: Color
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
        shape.fill(Color.black.opacity(0.45))
            .overlay(shape.fill(tint.opacity(0.14)))
            .overlay(shape.strokeBorder(tint.opacity(contrast == .increased ? 0.9 : 0.45)))
    }
}
