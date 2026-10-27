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
    }

    public struct State: Equatable, Sendable {
        public var screen: Screen = .starting
        public var settings = LauncherSettings()
        public var source: SourceInfo?
        public var installed: InstalledGame?
        public var intent: Intent?
        public var waiting: Waiting?
        /// The game is starting or running, from the `play` effect until `gameExited` or
        /// `gameCouldNotStart`.
        public var gameRunning = false
        /// How the last game run ended, when it ended badly.
        public var gameProblem: GameProblem?
        /// The player chose Later on the rebuild offer.
        public var rebuildDeclined = false

        public init() {}

        /// Whether a result is on its way, so the window's buttons wait for it.
        public var isBusy: Bool { waiting != nil }

        /// Whether Library's Play, Rebuild and Change Disc do anything now, which needs no result
        /// on its way and no game running.
        public var libraryIsIdle: Bool { screen == .library && waiting == nil && !gameRunning }

        /// Whether a step can go back to Library, which needs a game, no build running and no
        /// disc panel open.
        public var canGoBackToLibrary: Bool {
            installed != nil && screen != .library && waiting != .build && waiting != .panel
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
            case .build(.running(let progress)) where progress.step == BuildProgress.warmupStep:
                return .warmup
            case .build(.failed(let failure, _)) where failure.step == BuildProgress.warmupStep:
                return .warmup
            case .build: return .build
            case .library: return .library
            }
        }
    }
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
    /// `lastLines` is the end of the log, once it has been read.
    case failed(BuildFailure, lastLines: [String])
}

/// Where a running build is, from the recipe's events.
public struct BuildProgress: Equatable, Sendable {
    /// The recipe's name for its warm-up step.
    public static let warmupStep = "warmup"

    /// The recipe's step, or nil before its first event.
    public var step: String?
    public var done = 0
    public var total = 0
    /// Cancel was pressed and the build hasn't stopped yet.
    public var canceling = false

    public init(step: String? = nil, done: Int = 0, total: Int = 0, canceling: Bool = false) {
        self.step = step
        self.done = done
        self.total = total
        self.canceling = canceling
    }
}
