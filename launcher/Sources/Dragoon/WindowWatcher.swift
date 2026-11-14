import AppKit
import SwiftUI

/// Tells `isActive` whether the window it sits in is key and on screen, so the hero can stop
/// when it isn't. It also lets the window be dragged by its background, since its title bar is
/// hidden.
struct WindowWatcher: NSViewRepresentable {
    @Binding var isActive: Bool

    func makeNSView(context: Context) -> WatchingView {
        let view = WatchingView()
        view.report = { active in
            // Not during SwiftUI's update of this view.
            DispatchQueue.main.async { isActive = active }
        }
        return view
    }

    func updateNSView(_ view: WatchingView, context: Context) {}
}

final class WatchingView: NSView {
    var report: (Bool) -> Void = { _ in }
    private var observers: [NSObjectProtocol] = []

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        observers.forEach(NotificationCenter.default.removeObserver)
        observers = []
        guard let window else { return }
        window.isMovableByWindowBackground = true
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
        report(window.isKeyWindow && window.occlusionState.contains(.visible))
    }
}
