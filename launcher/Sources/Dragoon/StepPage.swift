import DragoonCore
import SwiftUI

/// How a view hands what the player did to the flow.
typealias Send = @MainActor (Flow.Event) -> Void

/// The right side of the window: a title, what the step says and its buttons at the bottom.
struct StepPage<Content: View, Buttons: View>: View {
    let title: String
    let content: Content
    let buttons: Buttons

    init(
        _ title: String, @ViewBuilder content: () -> Content,
        @ViewBuilder buttons: () -> Buttons
    ) {
        self.title = title
        self.content = content()
        self.buttons = buttons()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title).font(.title)
            content
            Spacer(minLength: 0)
            HStack {
                Spacer()
                buttons
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

/// A line of text beside a small spinner, for a step waiting on a result.
struct ProgressRow: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            Text(text)
        }
    }
}
