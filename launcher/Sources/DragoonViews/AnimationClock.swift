import SwiftUI

/// Where an animated view gets its time. The window runs on the display's frames. A snapshot
/// test fixes one moment, so every render of a view draws the same frame.
public enum AnimationClock: Sendable {
    case live
    case fixed(Date)
}

private struct AnimationClockKey: EnvironmentKey {
    static let defaultValue = AnimationClock.live
}

extension EnvironmentValues {
    public var animationClock: AnimationClock {
        get { self[AnimationClockKey.self] }
        set { self[AnimationClockKey.self] = newValue }
    }
}

/// What a view that animates draws in: a `TimelineView` on the display's frames, at most one
/// every `minimumInterval` seconds and none while `paused`, or the one moment a fixed clock
/// names.
struct ClockedTimeline<Content: View>: View {
    var minimumInterval: Double = 1.0 / 30
    var paused = false
    @ViewBuilder let content: (Date) -> Content
    @Environment(\.animationClock) private var clock

    var body: some View {
        switch clock {
        case .live:
            TimelineView(.animation(minimumInterval: minimumInterval, paused: paused)) { context in
                content(context.date)
            }
        case .fixed(let date):
            content(date)
        }
    }
}
