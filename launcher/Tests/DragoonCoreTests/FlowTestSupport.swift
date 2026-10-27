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

/// A launch with what's given. By default the player has built a game from this source, seen
/// Welcome and has a bookmark to their disc.
func launched(
    settings: LauncherSettings = LauncherSettings(welcomeSeen: true, disc: flowBookmark),
    installed: InstalledGame? = InstalledGame(stamp: sourceCommits),
    appPath: String = flowApp, onReadOnlyVolume: Bool = false,
    source: SourceInfo? = flowSource
) -> FlowRun {
    var run = FlowRun()
    run.send(.launched(Flow.Launch(
        appPath: appPath, onReadOnlyVolume: onReadOnlyVolume, settings: settings, source: source,
        installed: installed)))
    return run
}

/// The events that take Play from Library to the game starting, for a disc that's where the
/// bookmark says. The last one gives `play`.
let playToStarting: [Flow.Event] = [
    .playPressed, .bookmarkResolved(.found(flowDisc)), .discChecked(path: flowDisc, check: .ok),
]

/// The events that take a rebuild from Library to a running build, each with the effects it
/// gives, for a disc that's where the bookmark says.
let rebuildToRunning: [(Flow.Event, [Flow.Effect])] = [
    (.rebuildPressed, [.checkSpace]),
    (.spaceChecked(enoughSpace), [.resolveBookmark(flowBookmark)]),
    (.bookmarkResolved(.found(flowDisc)), [.checkDisc(path: flowDisc, expected: flowSource.disc)]),
    (.discChecked(path: flowDisc, check: .ok), [.detectTools]),
    (.toolsDetected(.ready(flowToolchain)), [.startBuild(toolchain: flowToolchain, disc: flowDisc)]),
]
