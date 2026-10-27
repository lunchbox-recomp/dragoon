import DragoonCore
import SwiftUI

/// The window: the steps on the left and the current one on the right. A launcher that has to
/// move, or can't read its source, shows only that.
struct LauncherView: View {
    let model: LauncherModel

    var body: some View {
        let state = model.state
        Group {
            if let step = state.step {
                HStack(spacing: 0) {
                    StepList(current: step)
                    Divider()
                    page(state)
                }
            } else {
                page(state)
            }
        }
        .onAppear { model.launch() }
    }

    @ViewBuilder
    private func page(_ state: Flow.State) -> some View {
        let send: Send = { model.send($0) }
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
