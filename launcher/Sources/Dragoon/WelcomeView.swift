import DragoonCore
import SwiftUI

/// What happens, with the legal line.
struct WelcomeView: View {
    let send: Send

    var body: some View {
        StepPage(Strings.welcomeTitle) {
            Text(Strings.welcome)
            Text(Strings.legal)
                .font(.footnote)
                .foregroundStyle(.secondary)
        } buttons: {
            Button(Strings.continueButton) { send(.continuePressed) }
                .keyboardShortcut(.defaultAction)
        }
    }
}
