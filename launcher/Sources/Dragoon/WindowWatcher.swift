import AppKit
import DragoonViews
import SwiftUI

/// Tells `isActive` whether the window it sits in is key and on screen, so the hero can stop
/// when it isn't, and `isVisible` whether any of it is on screen, key or not, and hands the
/// window to `found`. It also lets the window be dragged by its background, since its title bar
/// is hidden.
struct WindowWatcher: NSViewRepresentable {
    @Binding var isActive: Bool
    @Binding var isVisible: Bool
    let found: (NSWindow) -> Void

    func makeNSView(context: Context) -> WatchingView {
        let view = WatchingView()
        view.report = { active, visible in
            // Not during SwiftUI's update of this view.
            DispatchQueue.main.async {
                isActive = active
                isVisible = visible
            }
        }
        view.found = found
        return view
    }

    func updateNSView(_ view: WatchingView, context: Context) {}
}

final class WatchingView: NSView {
    var report: (_ active: Bool, _ visible: Bool) -> Void = { _, _ in }
    var found: (NSWindow) -> Void = { _ in }
    private var observers: [NSObjectProtocol] = []

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        observers.forEach(NotificationCenter.default.removeObserver)
        observers = []
        guard let window else { return }
        window.isMovableByWindowBackground = true
        found(window)
        let names: [Notification.Name] = [
            NSWindow.didBecomeKeyNotification, NSWindow.didResignKeyNotification,
            NSWindow.didChangeOcclusionStateNotification,
        ]
        observers = names.map { name in
            NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) {
                [weak self] _ in
                MainActor.assumeIsolated { self?.update() }
            }
        }
        update()
    }

    private func update() {
        guard let window else { return }
        report(
            Motion.windowIsActive(isKey: window.isKeyWindow, occlusion: window.occlusionState),
            window.occlusionState.contains(.visible))
    }
}
