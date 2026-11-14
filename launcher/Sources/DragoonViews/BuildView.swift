import DragoonCore
import SwiftUI

/// The Build and Warm-up steps: ready to build, getting ready, running, or stopped.
struct BuildView: View {
    let screen: BuildScreen
    let state: Flow.State
    let send: Send

    var body: some View {
        StepPage(Strings.step(state.step ?? .build)) {
            switch screen {
            case .ready:
                Text(Strings.buildReady)
            case .preparing:
                ProgressRow(Strings.buildPreparing)
            case .lowSpace(let space):
                Text(Strings.lowSpace(space, needed: Flow.neededSpace))
            case .running(let progress):
                RunningBuild(progress: progress)
            case .failed(let failure, let lastLines):
                FailedBuild(failure: failure, lastLines: lastLines)
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
}

/// The recipe's step and how far through it the build is.
private struct RunningBuild: View {
    let progress: BuildProgress

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(progress.step.map(Strings.running) ?? Strings.buildStarting)
            if let step = progress.step, progress.total > 0 {
                ProgressView(value: Double(progress.done), total: Double(progress.total))
                Text(Strings.progress(done: progress.done, total: progress.total, step: step))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ProgressView().progressViewStyle(.linear)
            }
        }
    }
}

/// The step that failed, the end of its log and where the whole log is.
private struct FailedBuild: View {
    let failure: BuildFailure
    let lastLines: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
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
