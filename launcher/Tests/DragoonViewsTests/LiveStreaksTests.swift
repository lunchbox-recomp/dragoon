import AppKit
import Testing

@testable import DragoonViews

/// The layers the window moves the hero's streaks with, built with no window, and the rule
/// that says when the window can be seen.
@MainActor
struct LiveStreaksTests {
    static let colors = [NSColor.systemTeal, NSColor.systemPink, NSColor.white].map(\.cgColor)

    static func view(paused: Bool, still: Bool) -> StreakLayerView {
        let view = StreakLayerView(frame: NSRect(origin: .zero, size: LauncherView.defaultSize))
        view.show(colors: colors, paused: paused, still: still)
        return view
    }

    /// How many of the field's streaks have their run animation.
    static func running(_ view: StreakLayerView) -> Int {
        (view.field.sublayers ?? []).filter { $0.animation(forKey: "run") != nil }.count
    }

    /// Paused stops the field's clock, and still leaves the streaks with nothing to run.
    @Test(arguments: [
        (false, false, Float(1), 56), (true, false, Float(0), 56), (false, true, Float(1), 0),
        (true, true, Float(0), 0),
    ])
    func theFieldRunsOnlyWhenNeitherPausedNorStill(
        paused: Bool, still: Bool, speed: Float, running: Int
    ) {
        let view = Self.view(paused: paused, still: still)
        #expect(view.field.sublayers?.count == 56)
        #expect(view.field.speed == speed)
        #expect(Self.running(view) == running)
    }

    @Test func aPausedFieldRunsAgain() {
        let view = Self.view(paused: true, still: false)
        view.show(colors: Self.colors, paused: false, still: false)
        #expect(view.field.speed == 1)
        #expect(Self.running(view) == 56)
    }

    @Test(arguments: [(true, true, true), (false, true, false), (true, false, false), (false, false, false)])
    func aWindowIsActiveWhenKeyAndOnScreen(isKey: Bool, visible: Bool, active: Bool) {
        #expect(Motion.windowIsActive(isKey: isKey, occlusion: visible ? .visible : []) == active)
    }
}
