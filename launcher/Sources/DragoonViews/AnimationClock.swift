import SwiftUI

/// Where an animated view gets its time. In the window it moves as it does live. A snapshot
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
