import DragoonCore
import Foundation
import Testing

/// A state the window can show, named for its snapshot file.
struct ScreenFixture: CustomTestStringConvertible, Sendable {
    let name: String
    let state: Flow.State

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

/// One fixture for each case of `Flow.Screen` and of the screens it carries, and Library with
/// each of the boxes it can show.
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
    ScreenFixture(name: "build-ready", state: state(.build(.ready))),
    ScreenFixture(name: "build-preparing", state: state(.build(.preparing), waiting: .space)),
    ScreenFixture(
        name: "build-low-space",
        state: state(.build(.lowSpace(FreeSpace(available: 1_200_000_000, volume: "Macintosh HD"))))),
    ScreenFixture(
        name: "build-running",
        state: state(.build(.running(BuildProgress(step: "compile", done: 41, total: 135))),
                     waiting: .build)),
    ScreenFixture(
        name: "build-failed",
        state: state(.build(.failed(
            .failed(step: "compile", message: "make exited with status 2.", log: log),
            lastLines: ["clang: error: linker command failed with exit code 1", "make: *** [dragoon] Error 1"])))),
    ScreenFixture(name: "library", state: state(.library, installed: InstalledGame(stamp: commits))),
    ScreenFixture(
        name: "library-rebuild-offer",
        state: state(.library, installed: InstalledGame(stamp: nil))),
    ScreenFixture(
        name: "library-game-problem",
        state: state(.library, installed: InstalledGame(stamp: commits)) {
            $0.gameProblem = .exited(
                .signal(11), panic: GamePanic("Invalid read at 0x00000004\npc 0x80012345"))
        }),
]
