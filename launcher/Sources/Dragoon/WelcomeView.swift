import DragoonCore
import SwiftUI

/// What happens and how long it takes, with the legal line.
struct WelcomeView: View {
    let send: Send

    var body: some View {
        StepPage(Strings.welcomeTitle) {
            Text(Strings.welcome)
            Text(Strings.welcomeTime)
            Text(Strings.legal)
                .font(.footnote)
                .foregroundStyle(.secondary)
        } buttons: {
            Button(Strings.continueButton) { send(.continuePressed) }
                .keyboardShortcut(.defaultAction)
        }
    }
}
