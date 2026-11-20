import Foundation

/// The launcher's window as a pure state machine. The app sends each thing the player does and
/// each result as an `Event`, and carries out the `Effect`s that come back, so every path runs in
/// a test without a window.
///
/// The first run goes Welcome, Tools, Disc, Build and Warm-up, then Library, and every later
/// launch with a game built opens on Library. Before each build the flow checks the space, then
/// the disc behind its bookmark, then the tools. Before each launch it checks the disc.
public enum Flow {
    /// The free space a build needs, which `Volume.freeSpace` is held to.
    public static let neededSpace: Int64 = 2_000_000_000
    /// Seconds between tools checks while the tools are missing.
    public static let toolsCheckInterval: TimeInterval = 5
    /// Seconds after the game starts that the launcher hides with no window line, as it does for
    /// an engine from before the ready file. The engine writes that line at its window's first
    /// frame. At 5 s the wait cut off a fake game's line, which went in over 5 s after its start
    /// under a loaded test runner. How long a slow disc or a first run's shader compiles hold the
    /// line back hasn't been measured. 20 s still ends the wait on an engine that writes no file.
    public static let handOffTimeout: TimeInterval = 20

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
            waiting = .panel
            return [.openDiscPanel]
        case .changeDiscPressed:
            guard libraryIsIdle else { return [] }
            waiting = .panel
            return [.openDiscPanel]
        case .discChosen(let path, let bookmark):
            guard waiting == .panel, let source else { return [] }
            screen = .disc(.checking)
            waiting = .disc(path: path, bookmark: bookmark)
            return [.checkDisc(path: path, expected: source.disc)]
        case .discChoiceFailed(let reason):
            guard waiting == .panel else { return [] }
            waiting = nil
            screen = .disc(.problem(.unreadable(reason: reason)))
            return []
        case .discPanelCanceled:
            guard waiting == .panel else { return [] }
            waiting = nil
            return []
        case .lookAgainPressed:
            guard screen == .disc(.problem(.missing)), waiting == nil else { return [] }
            return resolveDisc()
        case .bookmarkResolved(let resolution):
            guard waiting == .bookmark, let source else { return [] }
            waiting = nil
            switch resolution {
            case .found(let path):
                waiting = .disc(path: path, bookmark: nil)
                return [.checkDisc(path: path, expected: source.disc)]
            case .stale:
                screen = .disc(.problem(.moved))
            case .missing:
                screen = .disc(.problem(.missing))
            }
            handOff = nil
            return []
        case .discChecked(let path, let check):
            guard case .disc(path, let bookmark) = waiting, let source else { return [] }
            waiting = nil
            if let problem = DiscProblem(check, expected: source.disc) {
                screen = .disc(.problem(problem))
                handOff = nil
                return []
            }
            var effects: [Effect] = []
            if let bookmark {
                settings.disc = bookmark
                effects.append(.saveSettings(settings))
            }
            // The banner is read once, and only from a disc that passed.
            let readBanner = banner == nil ? [Effect.readBanner(path)] : []
            return effects + discReady(path) + readBanner
        case .bannerRead(let read):
            if let read { banner = read }
            return []

        case .buildPressed:
            guard waiting == nil else { return [] }
            switch screen {
            case .build(.ready), .build(.lowSpace), .build(.failed): return begin(.build)
            default: return []
            }
        case .rebuildPressed:
            guard libraryIsIdle else { return [] }
            return begin(.build)
        case .spaceChecked(let space):
            guard waiting == .space else { return [] }
            waiting = nil
            guard space.available >= Flow.neededSpace else {
                screen = .build(.lowSpace(space))
                return []
            }
            return resolveDisc()
        case .build(let buildEvent, let time):
            guard waiting == .build, case .build(.running(var progress)) = screen else { return [] }
            progress.note(buildEvent, at: time)
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
            guard case .build(.failed(let failure, let skipped, _)) = screen, failure.log == path
            else { return [] }
            screen = .build(.failed(failure, skipped: skipped, lastLines: lines))
            return []
        case .copyLogPressed:
            guard case .build(.failed(let failure, _, _)) = screen, let log = failure.log else {
                return []
            }
            return [.copyLog(log)]
        case .showLogPressed:
            guard case .build(.failed(let failure, _, _)) = screen, let log = failure.log else {
                return []
            }
            return [.showLog(log)]

        case .playPressed:
            guard canPlay else { return [] }
            // Play on the Ready to Play page passes the Picture card by.
            pictureCard = nil
            gameProblem = nil
            panicShown = false
            handOff = .charging
            return begin(.play)
        case .rebuildLaterPressed:
            if screen == .library { rebuildDeclined = true }
            return []
        case .showSavesPressed:
            return screen == .library ? [.showSaves] : []
        case .showPanicPressed:
            guard screen == .library, case .exited(_, panic: _?)? = gameProblem else { return [] }
            panicShown.toggle()
            return []
        case .backToLibraryPressed:
            return canGoBackToLibrary ? showLibrary() : []
        case .gameExited(let launch, let ending, let panic):
            guard launch == launchNumber else { return [] }
            return gameStopped(ending == .status(0) ? nil : .exited(ending, panic: panic))
        case .gameCouldNotStart(let launch, let reason):
            guard launch == launchNumber else { return [] }
            return gameStopped(.couldNotStart(reason: reason))
        case .earlierGameEnded:
            // The earlier launcher's game holds launch 0's place, since Play stays off until it
            // ends.
            guard gameRunning, launchNumber == 0 else { return [] }
            return gameStopped(nil)
        case .gameReady(let launch, let marks):
            guard launch == launchNumber, handOff == .launched, marks.window != nil else {
                return []
            }
            handOff = .hidden
            return [.hideWindow(timedOut: false)]
        case .handOffTimedOut(let launch):
            guard launch == launchNumber, handOff == .launched else { return [] }
            handOff = .hidden
            return [.hideWindow(timedOut: true)]
        case .windowShown:
            if handOff == .returning { handOff = nil }
            return []

        case .settingsPressed:
            guard libraryIsIdle, picture == nil else { return [] }
            waiting = .picture
            return [.readPicture]
        case .pictureRead(let read):
            guard waiting == .picture else { return [] }
            waiting = nil
            picture = read
            savedPicture = read
            pictureFailure = nil
            return []
        case .pictureChosen(let chosen):
            // The game reads the file as it starts and its Display page saves it, so the
            // launcher writes it only while no game runs.
            guard let picture, libraryIsIdle, chosen != picture else { return [] }
            self.picture = chosen
            pictureFailure = nil
            return [.savePicture(chosen)]
        case .pictureSaved(let tried, let failure):
            if waiting == .pictureCard { return pictureCardSaved(tried, failure) }
            guard picture != nil else { return [] }
            if failure == nil {
                savedPicture = tried
            } else if picture == tried, let savedPicture {
                // The file is as it was, so the sheet shows what it holds, and picking the
                // same again saves again. A later pick on its way keeps its own result.
                picture = savedPicture
            }
            pictureFailure = failure
            return []
        case .settingsDonePressed:
            picture = nil
            savedPicture = nil
            pictureFailure = nil
            return []

        case .pictureCardRead(let read, let aspectLine):
            guard waiting == .pictureCard else { return [] }
            waiting = nil
            // An aspect the player or the game already set stays as it is, and the card never
            // shows while a game runs, which reads the file.
            guard !aspectLine, !gameRunning, case .build(.finished) = screen else { return [] }
            pictureCard = Flow.PictureCard(picture: read)
            settings.pictureCardShown = true
            return [.saveSettings(settings)]
        case .pictureCardPicked(let aspect):
            guard pictureCardIsIdle, var card = pictureCard, Flow.PictureCard.aspects.contains(aspect)
            else { return [] }
            card.picture.aspect = aspect
            card.failure = nil
            pictureCard = card
            waiting = .pictureCard
            return [.savePicture(card.picture)]
        case .pictureCardSkipped:
            guard pictureCardIsIdle else { return [] }
            pictureCard = nil
            return []
        }
    }

    /// The Picture card's pick was saved, so the card goes, or it wasn't, so it stays and says
    /// why.
    private mutating func pictureCardSaved(
        _ tried: PictureSettings, _ failure: PictureSettings.SaveFailure?
    ) -> [Effect] {
        waiting = nil
        guard var card = pictureCard, card.picture == tried else { return [] }
        if failure == nil {
            pictureCard = nil
        } else {
            card.failure = failure
            pictureCard = card
        }
        return []
    }

    // MARK: - Launch and Library

    private mutating func launched(_ launch: Flow.Launch) -> [Effect] {
        settings = launch.settings
        source = launch.source
        installed = launch.installed
        banner = launch.banner
        if let reason = MoveReason(appPath: launch.appPath, onReadOnlyVolume: launch.onReadOnlyVolume) {
            screen = .mustMove(reason)
            return []
        }
        guard source != nil else {
            screen = .damaged
            return []
        }
        // A game an earlier launcher started counts as running until it ends.
        gameRunning = launch.earlierGame != nil
        let watch = launch.earlierGame.map { [Effect.watchEarlierGame(pid: $0)] } ?? []
        return watch + firstScreen()
    }

    /// Library when there's a game, and otherwise Welcome until it's been seen, then Tools.
    private mutating func firstScreen() -> [Effect] {
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
        pictureCard = nil
        return deleteOldBuildsIfIdle()
    }

    private func deleteOldBuildsIfIdle() -> [Effect] {
        installed != nil && !gameRunning && waiting != .build ? [.deleteOldBuilds] : []
    }

    private mutating func gameStopped(_ problem: GameProblem?) -> [Effect] {
        gameRunning = false
        gameProblem = problem
        panicShown = false
        // The window comes back with the card up, and the card goes once it's in.
        var effects: [Effect] = []
        if handOff == .launched || handOff == .hidden {
            handOff = .returning
            effects.append(.showWindow)
        }
        return effects + deleteOldBuildsIfIdle()
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

    /// Resolves the bookmark, or asks for a disc when there is none.
    private mutating func resolveDisc() -> [Effect] {
        guard let bookmark = settings.disc else {
            screen = .disc(.choose)
            handOff = nil
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
            gameRunning = true
            launchNumber += 1
            handOff = .launched
            return [
                .play(disc: path, launch: launchNumber),
                .scheduleHandOffTimeout(launch: launchNumber, after: Flow.handOffTimeout),
            ]
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
        var progress = BuildProgress()
        if case .build(.running(let last)) = screen { progress = last }
        switch failure {
        case nil:
            let firstGame = installed == nil
            installed = InstalledGame(stamp: source?.commits)
            // The bar becomes Play, so the build ends on its own page.
            screen = .build(.finished(progress))
            let effects = deleteOldBuildsIfIdle()
            // The first game's page offers the Picture card once, after a look at settings.txt.
            guard firstGame, !settings.pictureCardShown, !gameRunning else { return effects }
            waiting = .pictureCard
            return effects + [.readPictureCard]
        case .cancelled?:
            // A rebuild that was canceled leaves the old game current.
            if installed != nil { return showLibrary() }
            screen = .build(.ready)
            return []
        case let failure?:
            // The bar keeps the plan it was drawn with.
            screen = .build(.failed(failure, skipped: progress.skipped, lastLines: []))
            return failure.log.map { [.readLogTail($0)] } ?? []
        }
    }
}
