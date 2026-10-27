import DragoonCore
import SwiftUI

/// A launcher that can't build from where it is says why, and offers only Quit.
struct MoveView: View {
    let title: String
    let message: String
    let send: Send

    var body: some View {
        StepPage(title) {
            Text(message).textSelection(.enabled)
        } buttons: {
            Button(Strings.quit) { send(.quitPressed) }
                .keyboardShortcut(.defaultAction)
        }
    }
}
