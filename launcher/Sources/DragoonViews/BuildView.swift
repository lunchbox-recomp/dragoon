import DragoonCore
import SwiftUI

/// The Build and Warm-up steps: ready to build, getting ready, running, finished or stopped.
/// The disc's banner flies in here once the disc passes, and comes into color as the build
/// goes.
struct BuildView: View {
    let screen: BuildScreen
    let state: Flow.State
    let send: Send

    var body: some View {
        let colors = HeroColors(palette: BannerPalette(banner: state.banner))
        StepPage(title) {
            // In a stack of its own, so the reveal takes no room until there's a banner.
            VStack(alignment: .leading, spacing: 0) {
                BuildBanner(
                    banner: state.banner, saturation: saturation, colors: colors,
                    finished: isFinished
                )
                .padding(.bottom, state.banner == nil ? 0 : 20)
                switch screen {
                case .ready:
                    Text(Strings.buildReady)
                case .preparing:
                    ProgressRow(Strings.buildPreparing)
                case .lowSpace(let space):
                    Text(Strings.lowSpace(space, needed: Flow.neededSpace))
                case .running(let progress), .finished(let progress):
                    // One view for both, so the bar can become Play.
                    BuildMeterView(
                        progress: progress, finished: isFinished, colors: colors,
                        canPlay: state.canPlay, send: send)
                case .failed(let failure, let lastLines):
                    FailedBuild(failure: failure, lastLines: lastLines, colors: colors)
                }
            }
        } buttons: {
            if state.canGoBackToLibrary {
                Button(Strings.backToLibrary) { send(.backToLibraryPressed) }
            }
            switch screen {
            case .ready:
                Button(Strings.buildGame) { send(.buildPressed) }
                    .keyboardShortcut(.defaultAction)
            case .preparing:
                EmptyView()
            case .lowSpace:
                Button(Strings.checkAgain) { send(.buildPressed) }
                    .keyboardShortcut(.defaultAction)
            case .running(let progress):
                Button(progress.canceling ? Strings.canceling : Strings.cancel) {
                    send(.cancelBuildPressed)
                }
                .disabled(progress.canceling)
            case .finished:
                // Play is where the bar was.
                EmptyView()
            case .failed(let failure, _):
                if failure.log != nil {
                    Button(Strings.copyLog) { send(.copyLogPressed) }
                    Button(Strings.showLog) { send(.showLogPressed) }
                }
                Button(Strings.tryAgain) { send(.buildPressed) }
                    .keyboardShortcut(.defaultAction)
            }
        }
    }

    private var isFinished: Bool {
        if case .finished = screen { return true }
        return false
    }

    private var title: String {
        isFinished ? Strings.buildFinishedTitle : Strings.step(state.step ?? .build)
    }

    /// Gray while the build gets ready, coming into color with the bar, and in full color
    /// before a build and once it's done.
    private var saturation: Double {
        switch screen {
        case .ready, .lowSpace, .finished: return 1
        case .preparing: return 0
        case .running(let progress): return progress.fraction
        case .failed(let failure, _): return FailedBuild.stoppedAt(failure)?.start ?? 0
        }
    }
}

/// The bar stopped at the step that failed, what happened, the end of its log and where the
/// whole log is.
private struct FailedBuild: View {
    let failure: BuildFailure
    let lastLines: [String]
    let colors: HeroColors

    /// The bar's segment for the step the build stopped at, or nil when it stopped at none.
    static func stoppedAt(_ failure: BuildFailure) -> BuildSegment? {
        failure.step.flatMap(BuildSegment.init(rawValue:))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let stopped = Self.stoppedAt(failure) {
                SegmentedBar(fraction: stopped.start, colors: colors, stopped: stopped)
                    .padding(.bottom, 8)
            }
            Text(Strings.buildFailure(failure)).textSelection(.enabled)
            if let log = failure.log {
                Text(Strings.logPlace(log))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
            if !lastLines.isEmpty {
                Text(Strings.logEnd).font(.headline)
                ScrollView {
                    Text(lastLines.joined(separator: "\n"))
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 220)
            }
        }
    }
}
