import Foundation

extension Flow {
    /// The steps in the window's list, in order.
    public enum Step: Int, CaseIterable, Comparable, Sendable {
        case welcome, tools, disc, build, warmup, library

        public static func < (left: Step, right: Step) -> Bool { left.rawValue < right.rawValue }
    }

    /// What the right side of the window shows.
    public enum Screen: Equatable, Sendable {
        /// Before `launched`.
        case starting
        /// The launcher can't build from where it is, so it asks to be moved and does nothing
        /// else.
        case mustMove(MoveReason)
        /// The app's source snapshot can't be read, so nothing can be built.
        case damaged
        case welcome
        case tools(ToolsScreen)
        case disc(DiscScreen)
        case build(BuildScreen)
        case library
    }

    /// What the player asked for that takes several effects to get to.
    public enum Intent: Equatable, Sendable {
        /// Space, disc, tools, then the build.
        case build
        /// The disc, then the game.
        case play
    }

    /// The result the flow is waiting on. A result it isn't waiting on is ignored, so one that
    /// arrives after the player has moved on changes nothing.
    public enum Waiting: Equatable, Sendable {
        /// The disc panel is open. It doesn't stop the window, so the flow waits on it.
        case panel
        case space
        case bookmark
        /// A disc check of `path`. `bookmark` is set for a disc the player just chose, and is
        /// kept only when the check passes.
        case disc(path: String, bookmark: Data?)
        /// A tools check. `disc` is set when a build starts as soon as the tools are ready.
        case tools(disc: String?)
        case build
        /// `settings.txt` is being read for the Settings sheet.
        case picture
        /// `settings.txt` is being read for the Picture card, or the card's pick saved.
        case pictureCard
    }

    /// The one-time "Picture: 4:3 or 16:9" card on the Ready to Play page after the first build.
    public struct PictureCard: Equatable, Sendable {
        /// The aspects the card offers. The others are in the Settings sheet.
        public static let aspects = ["4:3", "16:9"]

        /// What settings.txt held as the card read it, which a pick saves with its aspect.
        public var picture: PictureSettings
        /// Why the last pick wasn't saved, until the next pick.
        public var failure: PictureSettings.SaveFailure?

        public init(picture: PictureSettings, failure: PictureSettings.SaveFailure? = nil) {
            self.picture = picture
            self.failure = failure
        }
    }

    /// Where Play's launch card is, from Play until the window is back after the game.
    public enum HandOff: Equatable, Sendable {
        /// Play was pressed, and the bookmark is resolved and the disc checked behind the card.
        case charging
        /// The game has started, and the launcher waits for its window line or the timeout.
        case launched
        /// The launcher's window is hidden while the game runs.
        case hidden
        /// The game has ended and the window is fading back in with the card up.
        case returning
    }

    public struct State: Equatable, Sendable {
        public var screen: Screen = .starting
        public var settings = LauncherSettings()
        public var source: SourceInfo?
        public var installed: InstalledGame?
        /// The disc's banner, from the cache at launch or read once a disc passes its check.
        public var banner: DiscBanner?
        public var intent: Intent?
        public var waiting: Waiting?
        /// The game is starting or running, from the `play` effect until `gameExited` or
        /// `gameCouldNotStart` for its launch. A game an earlier launcher started runs until
        /// `earlierGameEnded`.
        public var gameRunning = false
        /// The launch number of the last `play`, which is 0 before the first. A result that
        /// echoes any other number is ignored, so a late one can't end a game that's running.
        public var launchNumber = 0
        /// How the last game run ended, when it ended badly.
        public var gameProblem: GameProblem?
        /// The player chose Later on the rebuild offer.
        public var rebuildDeclined = false
        /// The player opened the game problem's `panic.txt`. Each new problem starts closed.
        public var panicShown = false
        /// Play's launch card, or nil when Library shows none.
        public var handOff: HandOff?
        /// What the Settings sheet shows while it's open, and nil while it's closed.
        public var picture: PictureSettings?
        /// What settings.txt holds as of the sheet's read or its last save, which the sheet goes
        /// back to when a change isn't saved. Nil while the sheet is closed.
        public var savedPicture: PictureSettings?
        /// Why the sheet's last change wasn't saved, until the next change or the sheet closes.
        public var pictureFailure: PictureSettings.SaveFailure?
        /// The Picture card the Ready to Play page shows, or nil when it shows none.
        public var pictureCard: PictureCard?

        public init() {}

        /// What Play is doing, for the label beside it.
        public var playStatus: PlayStatus {
            if gameRunning { return .playing }
            return intent == .play ? .checkingDisc : .ready
        }

        /// Whether a result is on its way, so the window's buttons wait for it.
        public var isBusy: Bool { waiting != nil }

        /// Whether Library's Play, Rebuild and Change Disc do anything now, which needs no result
        /// on its way and no game running.
        public var libraryIsIdle: Bool { screen == .library && waiting == nil && !gameRunning }

        /// Whether the Picture card's picks do anything now, which needs it up on the Ready to
        /// Play page, no result on its way and no game running, as `libraryIsIdle` does.
        public var pictureCardIsIdle: Bool {
            guard pictureCard != nil, case .build(.finished) = screen else { return false }
            return waiting == nil && !gameRunning
        }

        /// Whether Play does anything now: Library's, or the one a finished build's bar became.
        /// Library's waits while the Settings sheet is open, so the game never starts while the
        /// sheet can write `settings.txt`.
        public var canPlay: Bool {
            if case .build(.finished) = screen { return waiting == nil && !gameRunning }
            return libraryIsIdle && picture == nil
        }

        /// Whether a step can go back to Library, which needs a game, no build running, no disc
        /// panel open and no Picture card read or save on its way. Library's Play and Settings
        /// would otherwise come before the card's save is done, and the sheet would take its
        /// result.
        public var canGoBackToLibrary: Bool {
            installed != nil && screen != .library && waiting != .build && waiting != .panel
                && waiting != .pictureCard
        }

        /// Why Library offers a rebuild, or nil when it doesn't. The old game plays until a
        /// rebuild starts.
        public var rebuildOffer: RebuildOffer? {
            guard let installed, let source, !rebuildDeclined else { return nil }
            guard let stamp = installed.stamp else { return .unknownVersion }
            return stamp == source.commits ? nil : .otherVersion
        }

        /// The step the window's list marks as current, or nil when it shows no list.
        public var step: Step? {
            switch screen {
            case .starting, .mustMove, .damaged: return nil
            case .welcome: return .welcome
            case .tools: return .tools
            case .disc: return .disc
            case .build(.running(let progress)): return Self.listStep(forBuildStep: progress.step)
            case .build(.failed(let failure, _, _)): return Self.listStep(forBuildStep: failure.step)
            case .build(.finished): return .library
            case .build: return .build
            // Library has its own layout, and the list is for setup.
            case .library: return nil
            }
        }

        /// Warm-up for the recipe's warm-up and the steps after it, so the list never goes back
        /// to Build, and Build for the rest.
        private static func listStep(forBuildStep step: String?) -> Step {
            guard let step, BuildProgress.stepsFromWarmup.contains(step) else { return .build }
            return .warmup
        }
    }
}

/// What Library's Play is doing.
public enum PlayStatus: Equatable, Sendable {
    /// Waiting for the player. Play is on when `libraryIsIdle`.
    case ready
    /// Play was pressed, and the bookmark is being resolved or the disc checked.
    case checkingDisc
    /// The game is starting or running.
    case playing
}

/// Why Library offers a rebuild.
public enum RebuildOffer: Equatable, Sendable {
    /// The installed game's stamp names other commits than the app's source.
    case otherVersion
    /// The installed game's stamp can't be read, so which version it is isn't known.
    case unknownVersion
}

public enum ToolsScreen: Equatable, Sendable {
    case checking
    /// The install button, what the tools are for and their size once installed. The step looks
    /// again every `Flow.toolsCheckInterval` seconds.
    case missing
    /// The tools are older than the SDKs. `tried` lists each SDK.
    case noLinkableSDK(tried: [String])
    case cantWriteProbe(path: String, error: String)
}

public enum DiscScreen: Equatable, Sendable {
    case choose
    case checking
    case problem(DiscProblem)
}

public enum BuildScreen: Equatable, Sendable {
    /// The first build hasn't started.
    case ready
    /// Checking the space, the disc and the tools before the build starts.
    case preparing
    case lowSpace(FreeSpace)
    case running(BuildProgress)
    /// The new game is current. The bar has become Play.
    case finished(BuildProgress)
    /// `skipped` is what the running build's plan left out of the bar, and `lastLines` the end
    /// of the log, once it has been read.
    case failed(BuildFailure, skipped: Set<BuildSegment>, lastLines: [String])
}
