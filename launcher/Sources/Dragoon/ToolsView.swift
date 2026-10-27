import DragoonCore
import SwiftUI

/// The tools check, with the install button while the tools are missing.
struct ToolsView: View {
    let screen: ToolsScreen
    let state: Flow.State
    let send: Send

    var body: some View {
        StepPage(Strings.toolsTitle) {
            switch screen {
            case .checking:
                ProgressRow(Strings.toolsChecking)
            case .missing:
                Text(Strings.toolsMissing)
                Text(Strings.toolsInstaller).foregroundStyle(.secondary)
            case .noLinkableSDK(let tried):
                Text(Strings.noLinkableSDK)
                Text(Strings.sdksTried).font(.headline)
                ForEach(tried, id: \.self) { sdk in
                    Text(sdk).font(.caption.monospaced()).textSelection(.enabled)
                }
            case .cantWriteProbe(let path, let error):
                Text(Strings.cantWriteProbe(path: path, error: error)).textSelection(.enabled)
            }
        } buttons: {
            if state.canGoBackToLibrary {
                Button(Strings.backToLibrary) { send(.backToLibraryPressed) }
            }
            switch screen {
            case .checking:
                EmptyView()
            case .missing:
                Button(Strings.installTools) { send(.installToolsPressed) }
                    .keyboardShortcut(.defaultAction)
            case .noLinkableSDK:
                Button(Strings.checkAgain) { send(.checkToolsPressed) }
                    .disabled(state.isBusy)
                Button(Strings.openSoftwareUpdate) { send(.openSoftwareUpdatePressed) }
                    .keyboardShortcut(.defaultAction)
            case .cantWriteProbe:
                Button(Strings.checkAgain) { send(.checkToolsPressed) }
                    .keyboardShortcut(.defaultAction)
                    .disabled(state.isBusy)
            }
        }
    }
}
