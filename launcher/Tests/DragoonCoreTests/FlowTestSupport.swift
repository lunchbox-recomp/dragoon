import DragoonCore
import Foundation

let flowHome = "/Users/Test Player"
let flowApp = flowHome + "/Applications/Dragoon.app"
let flowDisc = flowHome + "/Games/Kirby Air Ride (USA).gcm"
let flowBookmark = Data("a bookmark to the disc".utf8)
let flowLog = flowHome + "/Library/Logs/Dragoon/build-2027-01-15T08-00-00.000Z.log"

/// The commits the app's source holds, which a game built by this launcher is stamped with.
let sourceCommits = Commits(
    dragoon: String(repeating: "1", count: 40), gcnRecomp: String(repeating: "2", count: 40))
let flowSource = SourceInfo(
    commits: sourceCommits,
    disc: ExpectedDisc(id: "GKYE01", dolSHA1: String(repeating: "3", count: 40)))

let flowToolchain = Toolchain(
    developerDirectory: "/Library/Developer/CommandLineTools",
    clang: "/Library/Developer/CommandLineTools/usr/bin/clang",
    clangxx: "/Library/Developer/CommandLineTools/usr/bin/clang++",
    make: "/Library/Developer/CommandLineTools/usr/bin/make",
    python3: "/Library/Developer/CommandLineTools/usr/bin/python3",
    sdk: "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
    clangVersion: "Apple clang version 21.0.0 (clang-2100.1.1.101)")

let enoughSpace = FreeSpace(available: 50_000_000_000, volume: "Macintosh HD")

/// Drives `Flow.reduce` one event at a time, keeping the state and the last effects.
struct FlowRun {
    private(set) var state = Flow.State()
    private(set) var effects: [Flow.Effect] = []

    var screen: Flow.Screen { state.screen }

    /// The build's progress while it runs or once it has finished, or nil on any other screen.
    var progress: BuildProgress? {
        switch screen {
        case .build(.running(let progress)), .build(.finished(let progress)): return progress
        default: return nil
        }
    }

    @discardableResult
    mutating func send(_ event: Flow.Event) -> [Flow.Effect] {
        (state, effects) = Flow.reduce(state, event)
        return effects
    }

    /// Sends each event in turn, and returns the effects of each.
    mutating func send(_ events: [Flow.Event]) -> [[Flow.Effect]] {
        events.map { send($0) }
    }
}

/// When the Flow tests' build events come, for tests where the moment doesn't matter.
let flowBuildTime = Date(timeIntervalSinceReferenceDate: 0)

extension Flow.Event {
    /// A recipe event that came at `flowBuildTime`.
    static func build(_ event: BuildEvent) -> Flow.Event {
        .build(event, at: flowBuildTime)
    }
}

/// A banner made up for the tests, as the cache would hold one.
let flowBanner = DiscBanner(bytes: makeBNR(pixels: distinctPixels), discID: "GKYE01")!

/// A launch with what's given. By default the player has built a game from this source, seen
/// Welcome, has a bookmark to their disc and has its banner in the cache.
func launched(
    settings: LauncherSettings = LauncherSettings(welcomeSeen: true, disc: flowBookmark),
    installed: InstalledGame? = InstalledGame(stamp: sourceCommits),
    appPath: String = flowApp, onReadOnlyVolume: Bool = false,
    source: SourceInfo? = flowSource, earlierGame: Int32? = nil,
    banner: DiscBanner? = flowBanner
) -> FlowRun {
    var run = FlowRun()
    run.send(.launched(Flow.Launch(
        appPath: appPath, onReadOnlyVolume: onReadOnlyVolume, settings: settings, source: source,
        installed: installed, earlierGame: earlierGame, banner: banner)))
    return run
}

/// The events that take Play from Library to the game starting, for a disc that's where the
/// bookmark says. The last one gives `play`.
let playToStarting: [Flow.Event] = [
    .playPressed, .bookmarkResolved(.found(flowDisc)), .discChecked(path: flowDisc, check: .ok),
]

/// What a disc that passes gives once Play has checked it: the game's start and its hand-off
/// timer, for the launch with this number.
func starting(_ launch: Int) -> [Flow.Effect] {
    [
        .play(disc: flowDisc, launch: launch),
        .scheduleHandOffTimeout(launch: launch, after: Flow.handOffTimeout),
    ]
}

/// The events that take a rebuild from Library to a running build, each with the effects it
/// gives, for a disc that's where the bookmark says.
let rebuildToRunning: [(Flow.Event, [Flow.Effect])] = [
    (.rebuildPressed, [.checkSpace]),
    (.spaceChecked(enoughSpace), [.resolveBookmark(flowBookmark)]),
    (.bookmarkResolved(.found(flowDisc)), [.checkDisc(path: flowDisc, expected: flowSource.disc)]),
    (.discChecked(path: flowDisc, check: .ok), [.detectTools]),
    (.toolsDetected(.ready(flowToolchain)), [.startBuild(toolchain: flowToolchain, disc: flowDisc)]),
]
