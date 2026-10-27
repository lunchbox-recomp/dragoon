import DragoonCore
import SwiftUI

/// Choosing the disc image, and what was wrong with one that didn't pass.
struct DiscView: View {
    let screen: DiscScreen
    let state: Flow.State
    let send: Send

    var body: some View {
        StepPage(Strings.discTitle) {
            switch screen {
            case .choose:
                Text(Strings.discChoose)
            case .checking:
                ProgressRow(Strings.discChecking)
            case .problem(let problem):
                Text(Strings.disc(problem)).textSelection(.enabled)
            }
        } buttons: {
            if state.canGoBackToLibrary {
                Button(Strings.backToLibrary) { send(.backToLibraryPressed) }
            }
            if screen == .problem(.missing) {
                Button(Strings.lookAgain) { send(.lookAgainPressed) }
                    .disabled(state.isBusy)
            }
            if screen != .checking {
                Button(Strings.chooseDisc) { send(.chooseDiscPressed) }
                    .keyboardShortcut(.defaultAction)
                    .disabled(state.isBusy)
            }
        }
    }
}
