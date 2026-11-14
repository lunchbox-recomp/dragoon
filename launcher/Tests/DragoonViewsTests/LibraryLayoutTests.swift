import AppKit
import SwiftUI
import Testing

@testable import DragoonViews

/// How Library shares the window's height, measured on the views AppKit lays out. A snapshot
/// can't show it, since `ImageRenderer` draws a `ScrollView` as nothing.
@MainActor
struct LibraryLayoutTests {
    /// The heights of the scrollers `fixture` has in a window `size` big.
    static func scrollerHeights(_ fixture: ScreenFixture, size: CGSize) -> [CGFloat] {
        let host = NSHostingView(rootView: LauncherView(state: fixture.state, send: { _ in }))
        host.frame = NSRect(origin: .zero, size: size)
        host.layoutSubtreeIfNeeded()
        return scrollViews(in: host).map(\.frame.height)
    }

    static func scrollViews(in view: NSView) -> [NSScrollView] {
        (view as? NSScrollView).map { [$0] } ?? view.subviews.flatMap { scrollViews(in: $0) }
    }

    /// The panic the player opened outranks the logo: at every height from the window's
    /// smallest to 700 points, its scroller has its full 150 points, and the logo shows only
    /// in what's left.
    @Test func thePanicsScrollerKeepsItsFullHeightAtEveryWindowHeight() throws {
        let fixture = try #require(screenFixtures.first { $0.name == "library-fullest" })
        let full = ProblemCard.scrollerHeights.upperBound
        for height in Int(LauncherView.minimumSize.height)...700 {
            let size = CGSize(width: LauncherView.defaultSize.width, height: CGFloat(height))
            #expect(Self.scrollerHeights(fixture, size: size) == [full], "at \(height) points tall")
        }
    }
}
