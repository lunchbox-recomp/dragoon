import Foundation

/// The launcher's window as a pure state machine. The app sends each thing the player does and
/// each result as an `Event`, and carries out the `Effect`s that come back, so every path runs in
/// a test without a window.
///
/// The first run goes Welcome, Tools, Disc, Build and Warm-up, then Library, and every later
/// launch with a game built opens on Library. Before each build the flow checks the space, then
/// the disc behind its bookmark, then the tools. Before each launch it checks the disc.
public enum Flow {
    /// The free space a build needs, which `volumeAvailableCapacityForImportantUsage` is held to.
    public static let neededSpace: Int64 = 2_000_000_000
    /// Seconds between tools checks while the tools are missing.
    public static let toolsCheckInterval: TimeInterval = 5

    public static func reduce(_ state: State, _ event: Event) -> (State, [Effect]) {
        var next = state
        let effects = next.apply(event)
        return (next, effects)
    }
}

extension Flow.State {
    fileprivate typealias Effect = Flow.Effect

    fileprivate mutating func apply(_ event: Flow.Event) -> [Effect] {
        switch screen {
        case .starting:
            guard case .launched(let launch) = event else { return [] }
            return launched(launch)
        case .mustMove, .damaged:
            return event == .quitPressed ? [.quit] : []
        default:
            break
        }
        switch event {
        case .launched: return []
        case .quitPressed: return [.quit]
        case .continuePressed:
            guard screen == .welcome else { return [] }
            settings.welcomeSeen = true
            return [.saveSettings(settings)] + checkTools()

        case .installToolsPressed:
            return screen == .tools(.missing) ? [.installTools] : []
        case .openSoftwareUpdatePressed:
            guard case .tools(.noLinkableSDK) = screen else { return [] }
            return [.openSoftwareUpdate]
        case .checkToolsPressed:
            guard case .tools = screen, waiting == nil else { return [] }
            return checkTools()
        case .toolsCheckDue:
            guard screen == .tools(.missing), waiting == nil else { return [] }
            waiting = .tools(disc: nil)
            return [.detectTools]
        case .toolsDetected(let status):
            guard case .tools(let disc) = waiting else { return [] }
            return toolsDetected(status, disc: disc)

        case .chooseDiscPressed:
            guard case .disc = screen, waiting == nil else { return [] }
            return [.openDiscPanel]
        case .changeDiscPressed:
            guard screen == .library, waiting == nil else { return [] }
            return [.openDiscPanel]
        case .discChosen(let path, let bookmark):
            guard choosesDisc, let source else { return [] }
            screen = .disc(.checking)
            waiting = .disc(path: path, bookmark: bookmark)
            return [.checkDisc(path: path, expected: source.disc)]
        case .discChoiceFailed(let reason):
            guard choosesDisc else { return [] }
            screen = .disc(.problem(.unreadable(reason: reason)))
            return []
        case .lookAgainPressed:
            guard screen == .disc(.problem(.moved)), waiting == nil else { return [] }
            return resolveDisc()
        case .bookmarkResolved(let resolution):
            guard waiting == .bookmark, let source else { return [] }
            waiting = nil
            guard case .found(let path) = resolution else {
                screen = .disc(.problem(.moved))
                return []
            }
            waiting = .disc(path: path, bookmark: nil)
            return [.checkDisc(path: path, expected: source.disc)]
        case .discChecked(let path, let check):
            guard case .disc(path, let bookmark) = waiting, let source else { return [] }
            waiting = nil
            if let problem = DiscProblem(check, expected: source.disc) {
                screen = .disc(.problem(problem))
                return []
            }
            var effects: [Effect] = []
            if let bookmark {
                settings.disc = bookmark
                effects.append(.saveSettings(settings))
            }
            return effects + discReady(path)

        case .buildPressed:
            guard waiting == nil else { return [] }
            switch screen {
            case .build(.ready), .build(.lowSpace), .build(.failed): return begin(.build)
            default: return []
            }
        case .rebuildPressed:
            guard canPlayOrRebuild else { return [] }
            return begin(.build)
        case .spaceChecked(let space):
            guard waiting == .space else { return [] }
            waiting = nil
            guard space.available >= Flow.neededSpace else {
                screen = .build(.lowSpace(space))
                return []
            }
            return resolveDisc()
        case .build(let buildEvent):
            guard waiting == .build, case .build(.running(var progress)) = screen else { return [] }
            switch buildEvent {
            case .step(let step): progress = BuildProgress(step: step, canceling: progress.canceling)
            case .progress(let step, let done, let total):
                progress = BuildProgress(
                    step: step, done: done, total: total, canceling: progress.canceling)
            case .done, .error: return []
            }
            screen = .build(.running(progress))
            return []
        case .cancelBuildPressed:
            guard waiting == .build, case .build(.running(var progress)) = screen,
                !progress.canceling
            else { return [] }
            progress.canceling = true
            screen = .build(.running(progress))
            return [.cancelBuild]
        case .buildEnded(let failure):
            guard waiting == .build else { return [] }
            return buildEnded(failure)
        case .logTailRead(let path, let lines):
            guard case .build(.failed(let failure, _)) = screen, failure.log == path else {
                return []
            }
            screen = .build(.failed(failure, lastLines: lines))
            return []
        case .copyLogPressed:
            guard case .build(.failed(let failure, _)) = screen, let log = failure.log else {
                return []
            }
            return [.copyLog(log)]
        case .showLogPressed:
            guard case .build(.failed(let failure, _)) = screen, let log = failure.log else {
                return []
            }
            return [.showLog(log)]

        case .playPressed:
            guard canPlayOrRebuild else { return [] }
            gameProblem = nil
            return begin(.play)
        case .rebuildLaterPressed:
            if screen == .library { rebuildDeclined = true }
            return []
        case .showSavesPressed:
            return screen == .library ? [.showSaves] : []
        case .backToLibraryPressed:
            return canGoBackToLibrary ? showLibrary() : []
        case .gameStarted:
            gameRunning = true
            return []
        case .gameExited(let status, let panic):
            gameRunning = false
            gameProblem = status == 0 ? nil : GameProblem(status: status, panic: panic)
            return deleteOldBuildsIfIdle()
        }
    }

    // MARK: - Launch and Library

    private mutating func launched(_ launch: Flow.Launch) -> [Effect] {
        settings = launch.settings
        source = launch.source
        installed = launch.installed
        if let reason = MoveReason(appPath: launch.appPath, onReadOnlyVolume: launch.onReadOnlyVolume) {
            screen = .mustMove(reason)
            return []
        }
        guard source != nil else {
            screen = .damaged
            return []
        }
        if installed != nil { return showLibrary() }
        if !settings.welcomeSeen {
            screen = .welcome
            return []
        }
        return checkTools()
    }

    /// Library, giving up whatever the flow was on its way to.
    private mutating func showLibrary() -> [Effect] {
        screen = .library
        intent = nil
        waiting = nil
        return deleteOldBuildsIfIdle()
    }

    private func deleteOldBuildsIfIdle() -> [Effect] {
        installed != nil && !gameRunning && waiting != .build ? [.deleteOldBuilds] : []
    }

    // MARK: - Tools

    private mutating func checkTools() -> [Effect] {
        screen = .tools(.checking)
        waiting = .tools(disc: nil)
        return [.detectTools]
    }

    private mutating func toolsDetected(_ status: ToolchainStatus, disc: String?) -> [Effect] {
        waiting = nil
        switch status {
        case .cancelled:
            // It says nothing about the tools, so look again.
            waiting = .tools(disc: disc)
            return [.detectTools]
        case .ready(let toolchain):
            if let disc, intent == .build {
                screen = .build(.running(BuildProgress()))
                waiting = .build
                return [.startBuild(toolchain: toolchain, disc: disc)]
            }
            if let intent { return begin(intent) }
            screen = .disc(.choose)
            return []
        case .missing:
            screen = .tools(.missing)
            return [.scheduleToolsCheck(after: Flow.toolsCheckInterval)]
        case .noLinkableSDK(let tried):
            screen = .tools(.noLinkableSDK(tried: tried))
            return []
        case .cantWriteProbe(let path, let error):
            screen = .tools(.cantWriteProbe(path: path, error: error))
            return []
        }
    }

    // MARK: - Disc

    /// Whether a disc the player chose in the panel is taken now.
    private var choosesDisc: Bool {
        guard waiting == nil else { return false }
        if case .disc = screen { return true }
        return screen == .library
    }

    /// Resolves the bookmark, or asks for a disc when there is none.
    private mutating func resolveDisc() -> [Effect] {
        guard let bookmark = settings.disc else {
            screen = .disc(.choose)
            return []
        }
        waiting = .bookmark
        return [.resolveBookmark(bookmark)]
    }

    /// The disc at `path` passed its check, so go on to what the player asked for.
    private mutating func discReady(_ path: String) -> [Effect] {
        switch intent {
        case .play:
            intent = nil
            screen = .library
            return [.play(disc: path)]
        case .build:
            screen = .build(.preparing)
            waiting = .tools(disc: path)
            return [.detectTools]
        case nil:
            if installed != nil { return showLibrary() }
            screen = .build(.ready)
            return []
        }
    }

    // MARK: - Build

    private mutating func begin(_ intent: Flow.Intent) -> [Effect] {
        self.intent = intent
        switch intent {
        case .play:
            return resolveDisc()
        case .build:
            screen = .build(.preparing)
            waiting = .space
            return [.checkSpace]
        }
    }

    private mutating func buildEnded(_ failure: BuildFailure?) -> [Effect] {
        waiting = nil
        intent = nil
        switch failure {
        case nil:
            installed = InstalledGame(stamp: source?.commits)
            return showLibrary()
        case .cancelled?:
            // A rebuild that was canceled leaves the old game current.
            if installed != nil { return showLibrary() }
            screen = .build(.ready)
            return []
        case let failure?:
            screen = .build(.failed(failure, lastLines: []))
            return failure.log.map { [.readLogTail($0)] } ?? []
        }
    }
}
