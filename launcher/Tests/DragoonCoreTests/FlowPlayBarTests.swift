import DragoonCore
import Foundation
import Testing

private let panic = GamePanic("Invalid read at 0x00000004")

/// Library's own layout: no step list, the Play bar's state and the game problem's panic.txt.
@Suite struct FlowPlayBarTests {
    @Test func libraryShowsNoStepList() {
        var run = launched()
        #expect(run.screen == .library)
        #expect(run.state.step == nil)
        // A rebuild is setup again, so its steps show.
        run.send(.rebuildPressed)
        #expect(run.state.step == .build)
    }

    @Test func playGoesFromReadyThroughTheDiscCheckToPlaying() {
        var run = launched()
        #expect(run.state.playStatus == .ready)
        run.send(.playPressed)
        #expect(run.state.playStatus == .checkingDisc)
        run.send(.bookmarkResolved(.found(flowDisc)))
        #expect(run.state.playStatus == .checkingDisc)
        run.send(.discChecked(path: flowDisc, check: .ok))
        #expect(run.state.playStatus == .playing)
        run.send(.gameExited(launch: 1, exit: .status(0), panic: nil))
        #expect(run.state.playStatus == .ready)
    }

    @Test func aGameAnEarlierLauncherStartedIsPlaying() {
        var run = launched(earlierGame: 4242)
        #expect(run.state.playStatus == .playing)
        run.send(.earlierGameEnded)
        #expect(run.state.playStatus == .ready)
    }

    /// The disc panel from Change Disc isn't Play's business.
    @Test func changingTheDiscLeavesPlayReady() {
        var run = launched()
        run.send(.changeDiscPressed)
        #expect(run.state.playStatus == .ready)
        #expect(!run.state.libraryIsIdle)
    }

    @Test func thePanicShowsOnlyWhenAskedAndHidesAgain() {
        var run = launched()
        _ = run.send(playToStarting)
        run.send(.gameExited(launch: 1, exit: .signal(11), panic: panic))
        #expect(!run.state.panicShown)
        #expect(run.send(.showPanicPressed) == [])
        #expect(run.state.panicShown)
        run.send(.showPanicPressed)
        #expect(!run.state.panicShown)
    }

    @Test func aNewGameOrANewProblemStartsWithThePanicHidden() {
        var run = launched()
        _ = run.send(playToStarting)
        run.send(.gameExited(launch: 1, exit: .signal(11), panic: panic))
        run.send(.showPanicPressed)
        run.send(.playPressed)
        #expect(!run.state.panicShown)

        _ = run.send([.bookmarkResolved(.found(flowDisc)), .discChecked(path: flowDisc, check: .ok)])
        run.send(.gameExited(launch: 2, exit: .signal(6), panic: panic))
        #expect(!run.state.panicShown)
    }

    @Test(arguments: [
        nil, GameProblem.exited(.status(3), panic: nil), .couldNotStart(reason: "no game"),
    ])
    func thereIsNoPanicToShowWithoutOne(_ problem: GameProblem?) {
        var run = launched()
        _ = run.send(playToStarting)
        switch problem {
        case .exited(let ending, let panic)?:
            run.send(.gameExited(launch: 1, exit: ending, panic: panic))
        case .couldNotStart(let reason)?:
            run.send(.gameCouldNotStart(launch: 1, reason: reason))
        case nil:
            run.send(.gameExited(launch: 1, exit: .status(0), panic: nil))
        }
        run.send(.showPanicPressed)
        #expect(!run.state.panicShown)
    }
}
