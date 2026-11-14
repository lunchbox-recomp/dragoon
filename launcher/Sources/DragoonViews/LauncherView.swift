import DragoonCore
import SwiftUI

/// The window: during setup the steps on the left and the current one on the right, and Library
/// on its own. A launcher that has to move, or can't read its source, shows only that.
public struct LauncherView: View {
    let state: Flow.State
    let send: Send

    public init(state: Flow.State, send: @escaping Send) {
        self.state = state
        self.send = send
    }

    /// The window is dark whatever the system's appearance.
    public var body: some View {
        Group {
            if let step = state.step {
                HStack(spacing: 0) {
                    StepList(current: step)
                    Divider()
                    page
                }
            } else {
                page
            }
        }
        .environment(\.colorScheme, .dark)
        .preferredColorScheme(.dark)
    }

    @ViewBuilder
    private var page: some View {
        switch state.screen {
        case .starting:
            Color.clear
        case .mustMove(let reason):
            MoveView(title: Strings.moveTitle, message: Strings.move(reason), send: send)
        case .damaged:
            MoveView(title: Strings.damagedTitle, message: Strings.damaged, send: send)
        case .welcome:
            WelcomeView(send: send)
        case .tools(let screen):
            ToolsView(screen: screen, state: state, send: send)
        case .disc(let screen):
            DiscView(screen: screen, state: state, send: send)
        case .build(let screen):
            BuildView(screen: screen, state: state, send: send)
        case .library:
            LibraryView(state: state, send: send)
        }
    }
}
