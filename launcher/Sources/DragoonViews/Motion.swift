import AppKit
import SwiftUI

private struct WindowIsActiveKey: EnvironmentKey {
    static let defaultValue = true
}

private struct WindowIsVisibleKey: EnvironmentKey {
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

    /// Whether any of the window is on screen, key or not: it isn't covered, minimized or hidden.
    /// The app sets it, and the build page's clock stops while it's false.
    public var windowIsVisible: Bool {
        get { self[WindowIsVisibleKey.self] }
        set { self[WindowIsVisibleKey.self] = newValue }
    }

    /// Reduce Motion as the window draws it, or nil to follow the system's setting. A snapshot
    /// sets it to draw a screen as a player with Reduce Motion on sees it.
    public var reducesMotion: Bool? {
        get { self[ReducesMotionKey.self] }
        set { self[ReducesMotionKey.self] = newValue }
    }
}

public enum Motion {
    /// The hero's streaks stop when nobody can see them, while the game has the screen and under
    /// Reduce Motion, so Library costs nothing then.
    static func heroPaused(windowIsActive: Bool, gameRunning: Bool, reduceMotion: Bool) -> Bool {
        !windowIsActive || gameRunning || reduceMotion
    }

    /// Whether a window counts as active for `windowIsActive`: it's key and on screen.
    public static func windowIsActive(isKey: Bool, occlusion: NSWindow.OcclusionState) -> Bool {
        isKey && occlusion.contains(.visible)
    }

    /// What stops on the build page. The shimmer stops once the window isn't key, as the hero's
    /// streaks do. The clock stops only once none of the window can be seen, so a player who
    /// clicks another app and watches the build sees it go on.
    static func buildPaused(windowIsActive: Bool, windowIsVisible: Bool)
        -> (shimmer: Bool, clock: Bool)
    {
        (shimmer: !windowIsActive, clock: !windowIsVisible)
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
