import DragoonCore
import DragoonViews
import Foundation
import Testing

/// A state the window can show at `size`, named for its snapshot file, drawn as Reduce Motion
/// would when `reduceMotion` is set, with its animations at `moment`.
struct ScreenFixture: CustomTestStringConvertible, Sendable {
    let name: String
    let state: Flow.State
    var reduceMotion = false
    var size = LauncherView.defaultSize
    var moment = Snapshot.moment

    var testDescription: String { name }
}

private let home = "/Users/Test Player"
private let commits = Commits(
    dragoon: String(repeating: "1", count: 40), gcnRecomp: String(repeating: "2", count: 40))
private let source = SourceInfo(
    commits: commits, disc: ExpectedDisc(id: "GKYE01", dolSHA1: String(repeating: "3", count: 40)))
private let log = home + "/Library/Logs/Dragoon/build-2027-01-15T08-00-00.000Z.log"

/// A state on `screen`. `installed` is set when a game has been built, so steps offer Back to
/// Library.
private func state(
    _ screen: Flow.Screen, installed: InstalledGame? = nil, waiting: Flow.Waiting? = nil,
    change: (inout Flow.State) -> Void = { _ in }
) -> Flow.State {
    var state = Flow.State()
    state.screen = screen
    state.source = source
    state.installed = installed
    state.waiting = waiting
    change(&state)
    return state
}

/// One fixture for each case of `Flow.Screen` and of `ToolsScreen`, `DiscScreen` and
/// `BuildScreen`, with one move reason and one disc problem, and Library with each of the boxes
/// it can show.
let screenFixtures: [ScreenFixture] = [
    ScreenFixture(name: "starting", state: Flow.State()),
    ScreenFixture(name: "must-move", state: state(.mustMove(.refusedCharacter(":")))),
    ScreenFixture(name: "damaged", state: state(.damaged)),
    ScreenFixture(name: "welcome", state: state(.welcome)),
    ScreenFixture(name: "tools-checking", state: state(.tools(.checking), waiting: .tools(disc: nil))),
    ScreenFixture(name: "tools-missing", state: state(.tools(.missing))),
    ScreenFixture(
        name: "tools-no-linkable-sdk",
        state: state(.tools(.noLinkableSDK(tried: [
            "/Library/Developer/CommandLineTools/SDKs/MacOSX27.0.sdk",
            "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
        ])))),
    ScreenFixture(
        name: "tools-cant-write-probe",
        state: state(.tools(.cantWriteProbe(
            path: home + "/Library/Caches/Dragoon", error: "You don't have permission.")))),
    ScreenFixture(name: "disc-choose", state: state(.disc(.choose))),
    ScreenFixture(
        name: "disc-checking",
        state: state(.disc(.checking), waiting: .disc(path: home + "/Games/Disc.gcm", bookmark: nil))),
    ScreenFixture(
        name: "disc-missing",
        state: state(.disc(.problem(.missing)), installed: InstalledGame(stamp: commits))),
    // The disc has just passed, so its banner is there.
    ScreenFixture(
        name: "build-ready", state: state(.build(.ready)) { $0.banner = TestBanner.banner }),
    ScreenFixture(name: "build-preparing", state: state(.build(.preparing), waiting: .space)),
    ScreenFixture(
        name: "build-low-space",
        state: state(.build(.lowSpace(FreeSpace(available: 1_200_000_000, volume: "Macintosh HD"))))),
    // The build page draws at `Snapshot.buildMoment`, where the shimmer shows.
    ScreenFixture(name: "build-start", state: building(startingBuild), moment: Snapshot.buildMoment),
    ScreenFixture(
        name: "build-start-reduce-motion", state: building(startingBuild), reduceMotion: true,
        moment: Snapshot.buildMoment),
    ScreenFixture(name: "build-compile", state: building(compiling), moment: Snapshot.buildMoment),
    // Three segments, the warm-up left out as the plan says, the compile's three-quarters full.
    ScreenFixture(
        name: "build-compile-skip-warmup", state: building(compilingWithoutWarmup),
        moment: Snapshot.buildMoment),
    ScreenFixture(name: "build-warmup", state: building(warmingUp), moment: Snapshot.buildMoment),
    ScreenFixture(
        name: "build-done",
        state: state(.build(.finished(builtGame)), installed: InstalledGame(stamp: commits)) {
            $0.banner = TestBanner.banner
        },
        moment: Snapshot.buildMoment),
    // With the banner, in as much color as the bar had before the failed step: nearly gray here.
    ScreenFixture(
        name: "build-failed",
        state: state(.build(.failed(
            .failed(step: "compile", message: "make exited with status 2.", log: log),
            skipped: [],
            lastLines: ["clang: error: linker command failed with exit code 1", "make: *** [dragoon] Error 1"]))) {
            $0.banner = TestBanner.banner
        }),
    // The compile failed at 100 of 135 files after a plan without the warm-up: the bar the
    // running page drew, three segments, stopped where the compile's starts.
    ScreenFixture(
        name: "build-failed-skip-warmup",
        state: state(.build(.failed(
            .failed(step: "compile", message: "make exited with status 2.", log: log),
            skipped: compilingWithoutWarmup.skipped,
            lastLines: ["gen/func_80012345.c:41:3: error: use of undeclared identifier 'r3'", "make: *** [gen/func_80012345.o] Error 1"]))) {
            $0.banner = TestBanner.banner
        }),
    // The warm-up failed after a plan that left it out, as when the disc's drive goes away: the
    // failed step is drawn, so four segments with the warm-up's outlined, and the fill stops
    // where it starts.
    ScreenFixture(
        name: "build-failed-warmup-skip-plan",
        state: state(.build(.failed(
            .failed(step: "warmup", message: "warm_shaders.py exited 2", log: log),
            skipped: [.warmup],
            lastLines: ["/Volumes/Games/Disc.gcm: no such disc image"]))) {
            $0.banner = TestBanner.banner
        }),
    ScreenFixture(name: "library", state: library()),
    ScreenFixture(name: "library-reduce-motion", state: library(), reduceMotion: true),
    ScreenFixture(name: "library-no-banner", state: library { $0.banner = nil }),
    ScreenFixture(name: "library-playing", state: library { $0.gameRunning = true }),
    ScreenFixture(
        name: "library-rebuild-offer",
        state: library { $0.installed = InstalledGame(stamp: nil) }),
    ScreenFixture(name: "library-game-problem", state: library { $0.gameProblem = crash }),
    ScreenFixture(
        name: "library-panic",
        state: library {
            $0.gameProblem = crash
            $0.panicShown = true
        }),
    // Library's fullest: the rebuild offer and a long panic shown, at the window's opening size,
    // at the smallest it goes, and at 558 points tall, where the logo once took the panic's room.
    ScreenFixture(name: "library-fullest", state: fullest),
    ScreenFixture(name: "library-fullest-smallest", state: fullest, size: LauncherView.minimumSize),
    ScreenFixture(
        name: "library-fullest-558", state: fullest,
        size: CGSize(width: LauncherView.defaultSize.width, height: 558)),
    // Play's launch card in each phase: idle as the window comes back after the game, charge
    // while the disc is checked and launch once the game has started.
    ScreenFixture(name: "launch-card-idle", state: library { $0.handOff = .returning }),
    ScreenFixture(name: "launch-card-charge", state: charging()),
    ScreenFixture(name: "launch-card-launch", state: launching()),
    ScreenFixture(name: "launch-card-reduce-motion", state: launching(), reduceMotion: true),
]

/// A first build running, with the test banner.
private func building(_ progress: BuildProgress) -> Flow.State {
    state(.build(.running(progress)), waiting: .build) { $0.banner = TestBanner.banner }
}

/// A build's progress after `events`, each the given seconds before the build page's moment.
private func progress(_ events: [(Double, BuildEvent)]) -> BuildProgress {
    var progress = BuildProgress()
    for (ago, event) in events {
        progress.note(event, at: Snapshot.buildMoment.addingTimeInterval(-ago))
    }
    return progress
}

private func compileFiles(_ count: Int, from start: Double, every gap: Double) -> [(Double, BuildEvent)] {
    (1...count).map { (start - Double($0 - 1) * gap, .progress(step: "compile", done: $0, total: 135)) }
}

/// Recompile 3 seconds in, which prints no progress.
private let startingBuild = progress([(3, .step("recompile"))])

/// 41 of 135 files 14 seconds in, five a second.
private let compiling = progress(
    [(14, .step("recompile")), (9.6, .step("compile"))] + compileFiles(41, from: 9.5, every: 0.2))

/// 100 of 135 files after a plan without the warm-up, as a rebuild whose shader cache is current
/// prints it.
private let compilingWithoutWarmup = progress(
    [(25.6, .plan(warmup: false)), (25.6, .step("recompile")), (21.4, .step("compile"))]
        + compileFiles(100, from: 21.3, every: 0.2))

/// 3 of 8 warm-up runs done a minute in.
private let warmingUp = progress(
    [(60, .step("recompile")), (55.6, .step("compile"))] + compileFiles(135, from: 55.5, every: 0.1)
        + [(37, .step("warmup")), (10, .progress(step: "warmup", done: 1, total: 8)),
           (6, .progress(step: "warmup", done: 2, total: 8)),
           (2, .progress(step: "warmup", done: 3, total: 8))])

/// A whole build that took 1:36.
private let builtGame = progress([
    (96, .step("recompile")), (91.6, .step("compile")),
    (73, .progress(step: "compile", done: 135, total: 135)), (73, .step("warmup")),
    (1, .progress(step: "warmup", done: 8, total: 8)), (1, .step("package")),
    (0.4, .step("swap")), (0, .done(game: home + "/Library/Application Support/Dragoon/game/current/Dragoon.app")),
])

/// Library with Play pressed and the bookmark being resolved.
private func charging() -> Flow.State {
    library {
        $0.handOff = .charging
        $0.intent = .play
        $0.waiting = .bookmark
    }
}

/// Library with the game started and no window line yet.
private func launching() -> Flow.State {
    library {
        $0.handOff = .launched
        $0.gameRunning = true
        $0.launchNumber = 1
    }
}

private let crash = GameProblem.exited(
    .signal(11), panic: GamePanic("Invalid read at 0x00000004\npc 0x80012345\nlr 0x80012300"))

private let fullest = library {
    $0.installed = InstalledGame(stamp: nil)
    let frames = (0..<40).map { "frame \($0): 0x8001\(String(format: "%04X", 0x2300 + $0 * 0x24))" }
    $0.gameProblem = .exited(.signal(11), panic: GamePanic(frames.joined(separator: "\n")))
    $0.panicShown = true
}

/// Library with a game built from this source and the test banner.
private func library(change: (inout Flow.State) -> Void = { _ in }) -> Flow.State {
    state(.library, installed: InstalledGame(stamp: commits)) {
        $0.banner = TestBanner.banner
        change(&$0)
    }
}
