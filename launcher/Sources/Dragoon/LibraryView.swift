import DragoonCore
import SwiftUI

/// Where every later launch opens: Play, Rebuild, Show Saves and Change Disc.
struct LibraryView: View {
    let state: Flow.State
    let send: Send

    var body: some View {
        StepPage(Strings.libraryTitle) {
            Text(state.gameRunning ? Strings.gameRunning : Strings.libraryReady)
            if state.offersRebuild {
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(Strings.rebuildOffer)
                        HStack {
                            Spacer()
                            Button(Strings.later) { send(.rebuildLaterPressed) }
                            Button(Strings.rebuildNow) { send(.rebuildPressed) }
                                .disabled(!state.canPlayOrRebuild)
                        }
                    }
                    .padding(4)
                }
            }
            if let problem = state.gameProblem {
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(Strings.gameFailed(problem))
                        if let panic = problem.panic {
                            Text(Strings.panicHeading).font(.headline)
                            ScrollView {
                                Text(panic)
                                    .font(.caption.monospaced())
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .frame(maxHeight: 160)
                        }
                    }
                    .padding(4)
                }
            }
        } buttons: {
            Button(Strings.showSaves) { send(.showSavesPressed) }
            Button(Strings.changeDisc) { send(.changeDiscPressed) }
                .disabled(state.isBusy)
            Button(Strings.rebuild) { send(.rebuildPressed) }
                .disabled(!state.canPlayOrRebuild)
            Button(Strings.play) { send(.playPressed) }
                .keyboardShortcut(.defaultAction)
                .disabled(!state.canPlayOrRebuild)
        }
    }
}
