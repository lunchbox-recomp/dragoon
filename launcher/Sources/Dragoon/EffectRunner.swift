import AppKit
import DragoonCore
import DragoonViews
import Foundation
import UniformTypeIdentifiers
import os

/// Carries out the flow's effects and sends each result back as an event.
@MainActor
final class EffectRunner {
    /// Seconds the window takes to fade out for the game and back in after it.
    static let fadeDuration = 0.25

    var send: (Flow.Event) -> Void = { _ in }
    /// The launcher's window, which fades for the game.
    weak var window: NSWindow?
    /// When Play was last pressed, for the log's launch times.
    var playPressedAt: Date?

    private let places: Places
    private let fs: any FileSystem = SystemFileSystem()
    private let processes: any ProcessRunner = SystemProcessRunner()
    private let builds = BuildRunner()
    private let games = GameLauncher()
    private let log = Logger(subsystem: "io.github.lunchbox-recomp.dragoon", category: "launch")
    /// Counts the window's fades, so the end of one that another has replaced does nothing.
    private var fades = 0

    init(places: Places) {
        self.places = places
    }

    func perform(_ effect: Flow.Effect) {
        let fs = fs
        let places = places
        switch effect {
        case .saveSettings(let settings):
            // Settings that can't be saved cost the player Welcome or the disc's place next time,
            // and nothing now.
            try? settings.save(to: places.data, fs: fs)
        case .detectTools:
            let processes = processes
            background { .toolsDetected(await Toolchain.detect(runner: processes, fs: fs)) }
        case .scheduleToolsCheck(let seconds):
            background {
                try? await Task.sleep(for: .seconds(seconds))
                return .toolsCheckDue
            }
        case .installTools:
            let processes = processes
            Task.detached {
                _ = try? await processes.run(
                    "/usr/bin/xcode-select", ["--install"], environment: nil, timeout: 60)
            }
        case .openSoftwareUpdate:
            if let url = URL(string: "x-apple.systempreferences:com.apple.Software-Update-Settings.extension") {
                NSWorkspace.shared.open(url)
            }
        case .openDiscPanel:
            openDiscPanel()
        case .resolveBookmark(let bookmark):
            background { .bookmarkResolved(Bookmark.resolve(bookmark, fs: fs)) }
        case .checkDisc(let path, let expected):
            background {
                .discChecked(path: path, check: checkDisc(
                    at: path, expectedID: expected.id, expectedDOLSHA1: expected.dolSHA1, fs: fs))
            }
        case .readBanner(let disc):
            background { .bannerRead(BannerCache.readAndKeep(disc: disc, data: places.data, fs: fs)) }
        case .checkSpace:
            background { .spaceChecked(Volume.freeSpace(at: places.data)) }
        case .startBuild(let toolchain, let disc):
            startBuild(BuildRequest(
                toolchain: toolchain, bundle: places.bundle, disc: disc, data: places.data))
        case .cancelBuild:
            builds.cancel()
        case .readLogTail(let log):
            background { .logTailRead(path: log, lines: LogTail.lastLines(of: log, fs: fs)) }
        case .copyLog(let log):
            let text = (try? fs.readData(at: log)).map { String(decoding: $0, as: UTF8.self) } ?? log
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
        case .showLog(let log):
            NSWorkspace.shared.open(URL(fileURLWithPath: log))
        case .play(let disc, let launch):
            play(disc: disc, launch: launch)
        case .scheduleHandOffTimeout(let launch, let seconds):
            background {
                try? await Task.sleep(for: .seconds(seconds))
                return .handOffTimedOut(launch: launch)
            }
        case .hideWindow(let timedOut):
            if timedOut {
                log.notice(
                    "The game's ready file had no window line after \(Flow.handOffTimeout, format: .fixed(precision: 0)) s, so the launcher hid anyway")
            }
            hideWindow()
        case .showWindow:
            showWindow()
        case .watchEarlierGame(let pid):
            background {
                await LiveProcess.waitForEnd(of: pid)
                return .earlierGameEnded
            }
        case .showSaves:
            let folder = fs.isDirectory(at: places.saves) ? places.saves : places.data
            NSWorkspace.shared.open(URL(fileURLWithPath: folder))
        case .deleteOldBuilds:
            Task.detached { OldBuilds.delete(dataDirectory: places.data, fs: fs) }
        case .quit:
            NSApplication.shared.terminate(nil)
        }
    }

    /// Runs `work` off the main actor and sends what it gives.
    private func background(_ work: @escaping @Sendable () async -> Flow.Event) {
        Task {
            let event = await Task.detached(operation: work).value
            send(event)
        }
    }

    private func openDiscPanel() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = ["iso", "gcm", "ciso"].compactMap {
            UTType(filenameExtension: $0)
        }
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.begin { [weak self] response in
            MainActor.assumeIsolated {
                guard response == .OK, let url = panel.url else {
                    // This is the only thing that ends the flow's wait on the file chooser when
                    // it closes without a file, and no test reaches it.
                    self?.send(.discPanelCanceled)
                    return
                }
                do {
                    let bookmark = try Bookmark.make(for: url.path)
                    self?.send(.discChosen(path: url.path, bookmark: bookmark))
                } catch {
                    self?.send(.discChoiceFailed(reason: error.localizedDescription))
                }
            }
        }
    }

    /// Starts the game and watches its ready file, whose marks come back as events until both
    /// lines are in or the game ends, and then its one result. The flow hides the window and
    /// brings it back. The launch times go in the log once the watch ends.
    private func play(disc: String, launch: Int) {
        var started: UInt64?
        let session = games.play(
            game: places.game, disc: disc, data: places.data, readyFile: places.readyFile
        ) { started = LiveProcess.startTime(of: $0) }
        // After the play, which removes an earlier run's file, and before any line goes in.
        let marks = ReadyWatcher.watch(places.readyFile)
        let gameStart = started
        let play = playPressedAt.map(LaunchTimes.microseconds)
        let watching = Task {
            var last = ReadyMarks()
            for await read in marks {
                last = read
                send(.gameReady(launch: launch, marks: read))
            }
            if let play, let gameStart, last.window != nil {
                let times = LaunchTimes(play: play, gameStart: gameStart, marks: last)
                log.notice("\(times.summary, privacy: .public)")
            }
        }
        Task {
            for await result in session {
                watching.cancel()
                switch result {
                case .exited(let ending, let panic):
                    send(.gameExited(launch: launch, exit: ending, panic: panic))
                case .couldNotStart(let failure):
                    send(.gameCouldNotStart(launch: launch, reason: Strings.gameStart(failure)))
                }
            }
        }
    }

    /// Fades the window out, then hides the app and leaves the window whole for the next time it
    /// shows, such as from the Dock.
    ///
    /// On macOS 26.6 AppKit doesn't move an inactive app's fade, and the fade's completion
    /// handler waits with it, so a timer of the fade's length ends it. The launcher is active
    /// after a click on Play, but `NSApplication.hide` does nothing for an app that isn't, so then
    /// the window stays clear and lets clicks through until the game ends. Ordering the window out
    /// instead would quit the app, as SwiftUI ends an app whose one `Window` goes.
    private func hideWindow() {
        let fade = nextFade()
        if let window { Self.fade(window, to: 0) }
        afterFade(fade) { runner in
            runner.window?.alphaValue = 0
            NSApplication.shared.hide(nil)
            if NSApplication.shared.isHidden {
                runner.window?.alphaValue = 1
            } else {
                runner.window?.ignoresMouseEvents = true
            }
        }
    }

    /// Shows the app and fades the window in from clear when it was hidden or left clear, makes
    /// the launcher active, then sends `windowShown`.
    private func showWindow() {
        let fade = nextFade()
        if let window, NSApplication.shared.isHidden || window.ignoresMouseEvents {
            window.alphaValue = 0
            window.ignoresMouseEvents = false
        }
        NSApplication.shared.unhide(nil)
        NSApplication.shared.activate()
        if let window { Self.fade(window, to: 1) }
        afterFade(fade) { runner in
            runner.window?.alphaValue = 1
            runner.send(.windowShown)
        }
    }

    private func nextFade() -> Int {
        fades += 1
        return fades
    }

    /// Runs `then` once the fade's time is up, unless another fade has begun since.
    private func afterFade(_ fade: Int, then: @escaping @MainActor (EffectRunner) -> Void) {
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(Self.fadeDuration))
            guard let self, self.fades == fade else { return }
            then(self)
        }
    }

    private static func fade(_ window: NSWindow, to alpha: CGFloat) {
        NSAnimationContext.runAnimationGroup { context in
            context.duration = fadeDuration
            window.animator().alphaValue = alpha
        }
    }

    /// Sends the build's events through a throttle of its own, so the page redraws at most every
    /// `ProgressThrottle.interval` seconds.
    private func startBuild(_ request: BuildRequest) {
        let stream = builds.run(request)
        let throttle = ThrottledSend { [weak self] in self?.send(.build($0.event, at: $0.time)) }
        Task {
            do {
                for try await event in stream { throttle.offer(event, at: Date()) }
                send(.buildEnded(nil))
            } catch let failure as BuildFailure {
                send(.buildEnded(failure))
            } catch {
                send(.buildEnded(.couldNotStart(error.localizedDescription)))
            }
        }
    }
}
