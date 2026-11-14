import DragoonCore
import SwiftUI

/// The steps down the left of the window, with the ones before the current step ticked.
struct StepList: View {
    let current: Flow.Step

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Flow.Step.allCases, id: \.self) { step in
                HStack(spacing: 8) {
                    Image(systemName: symbol(for: step))
                        .foregroundStyle(step == current ? Color.accentColor : Color.secondary)
                    Text(Strings.step(step))
                        .fontWeight(step == current ? .semibold : .regular)
                        .foregroundStyle(step > current ? Color.secondary : Color.primary)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(width: 180, alignment: .topLeading)
        .frame(maxHeight: .infinity, alignment: .topLeading)
    }

    private func symbol(for step: Flow.Step) -> String {
        if step < current { return "checkmark.circle.fill" }
        return step == current ? "circle.inset.filled" : "circle"
    }
}
