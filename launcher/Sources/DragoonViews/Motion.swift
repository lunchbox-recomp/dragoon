import SwiftUI

private struct WindowIsActiveKey: EnvironmentKey {
    static let defaultValue = true
}

private struct ReducesMotionKey: EnvironmentKey {
    static let defaultValue: Bool? = nil
}

extension EnvironmentValues {
    /// Whether the window is key and on screen. The app sets it, and the hero stops while it's
    /// false.
    public var windowIsActive: Bool {
        get { self[WindowIsActiveKey.self] }
        set { self[WindowIsActiveKey.self] = newValue }
    }

    /// Reduce Motion as the window draws it, or nil to follow the system's setting. A snapshot
    /// sets it to draw a screen as a player with Reduce Motion on sees it.
    public var reducesMotion: Bool? {
        get { self[ReducesMotionKey.self] }
        set { self[ReducesMotionKey.self] = newValue }
    }
}

enum Motion {
    /// The hero's streaks stop when nobody can see them, while the game has the screen and under
    /// Reduce Motion, so Library costs nothing then.
    static func heroPaused(windowIsActive: Bool, gameRunning: Bool, reduceMotion: Bool) -> Bool {
        !windowIsActive || gameRunning || reduceMotion
    }
}

/// Reduce Motion as `reducesMotion` sets it, or as the system does.
struct ReduceMotionReader<Content: View>: View {
    @ViewBuilder let content: (Bool) -> Content
    @Environment(\.reducesMotion) private var override
    @Environment(\.accessibilityReduceMotion) private var system

    var body: some View {
        content(override ?? system)
    }
}
