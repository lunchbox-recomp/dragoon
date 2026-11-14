import DragoonCore
import SwiftUI

/// The window: the steps on the left and the current one on the right. A launcher that has to
/// move, or can't read its source, shows only that.
public struct LauncherView: View {
    let state: Flow.State
    let send: Send

    public init(state: Flow.State, send: @escaping Send) {
        self.state = state
        self.send = send
    }

    public var body: some View {
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
