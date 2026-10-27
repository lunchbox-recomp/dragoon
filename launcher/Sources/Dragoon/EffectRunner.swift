import AppKit
import DragoonCore
import Foundation
import UniformTypeIdentifiers

/// Carries out the flow's effects and sends each result back as an event.
@MainActor
final class EffectRunner {
    var send: (Flow.Event) -> Void = { _ in }

    private let places: Places
    private let fs: any FileSystem = SystemFileSystem()
    private let processes: any ProcessRunner = SystemProcessRunner()
    private let builds = BuildRunner()
    private let games = GameLauncher()

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

    /// Starts the game and hides the window while it runs. The window comes back once the
    /// launch's one result has been sent.
    private func play(disc: String, launch: Int) {
        let session = games.play(game: places.game, disc: disc, data: places.data)
        NSApplication.shared.hide(nil)
        Task {
            for await result in session {
                switch result {
                case .exited(let ending, let panic):
                    send(.gameExited(launch: launch, exit: ending, panic: panic))
                case .couldNotStart(let failure):
                    send(.gameCouldNotStart(launch: launch, reason: Strings.gameStart(failure)))
                }
            }
            NSApplication.shared.unhide(nil)
            NSApplication.shared.activate()
        }
    }

    private func startBuild(_ request: BuildRequest) {
        let stream = builds.run(request)
        Task {
            do {
                for try await event in stream { send(.build(event)) }
                send(.buildEnded(nil))
            } catch let failure as BuildFailure {
                send(.buildEnded(failure))
            } catch {
                send(.buildEnded(.couldNotStart(error.localizedDescription)))
            }
        }
    }
}
