import DragoonCore
import Foundation
import Testing

private let shown = ReadyMarks(window: 412)
private let both = ReadyMarks(window: 412, frame: 1093)

/// Library after Play with the disc where the bookmark says, so the game has started.
private func started() -> FlowRun {
    var run = launched()
    _ = run.send(playToStarting)
    return run
}

/// Play's launch card and the hand-off to the game's window: the card goes up on Play, the
/// launcher hides on the ready file's window line or after `Flow.handOffTimeout`, and comes back
/// when the game ends.
@Suite struct FlowHandOffTests {
    @Test func libraryHasNoCardBeforePlay() {
        #expect(launched().state.handOff == nil)
    }

    @Test func playPutsTheCardUpAndItChargesWhileTheDiscIsChecked() {
        var run = launched()
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
        #expect(run.state.handOff == .charging)
        #expect(run.send(.bookmarkResolved(.found(flowDisc)))
            == [.checkDisc(path: flowDisc, expected: flowSource.disc)])
        #expect(run.state.handOff == .charging)
    }

    @Test func aDiscThatPassesStartsTheGameAndTheTimeout() {
        var run = launched()
        let effects = run.send(playToStarting)
        #expect(effects.last == [
            .play(disc: flowDisc, launch: 1),
            .scheduleHandOffTimeout(launch: 1, after: Flow.handOffTimeout),
        ])
        #expect(run.state.handOff == .launched)
        #expect(Flow.handOffTimeout == 5)
    }

    @Test func theWindowLineHidesTheLauncher() {
        var run = started()
        #expect(run.send(.gameReady(launch: 1, marks: shown)) == [.hideWindow(timedOut: false)])
        #expect(run.state.handOff == .hidden)
    }

    /// Both lines in one read, as an engine with no splash writes them.
    @Test func bothLinesAtOnceHideItToo() {
        var run = started()
        #expect(run.send(.gameReady(launch: 1, marks: both)) == [.hideWindow(timedOut: false)])
    }

    @Test func marksWithNoWindowLineLeaveTheCardUp() {
        var run = started()
        #expect(run.send(.gameReady(launch: 1, marks: ReadyMarks())) == [])
        #expect(run.send(.gameReady(launch: 1, marks: ReadyMarks(frame: 30))) == [])
        #expect(run.state.handOff == .launched)
    }

    /// An engine from before the ready file never writes it, so the launcher hides anyway once
    /// the time is up, and says so.
    @Test func theTimeoutHidesTheLauncherAndSaysItTimedOut() {
        var run = started()
        #expect(run.send(.handOffTimedOut(launch: 1)) == [.hideWindow(timedOut: true)])
        #expect(run.state.handOff == .hidden)
    }

    @Test func onceHiddenNeitherLaterLinesNorTheTimeoutDoAnything() {
        var run = started()
        run.send(.gameReady(launch: 1, marks: shown))
        #expect(run.send(.gameReady(launch: 1, marks: both)) == [])
        #expect(run.send(.handOffTimedOut(launch: 1)) == [])
        #expect(run.state.handOff == .hidden)

        var late = started()
        late.send(.handOffTimedOut(launch: 1))
        #expect(late.send(.gameReady(launch: 1, marks: both)) == [])
    }

    @Test func theGameEndingBringsTheWindowBackWithTheCardThenTheCardGoes() {
        var run = started()
        run.send(.gameReady(launch: 1, marks: both))
        #expect(run.send(.gameExited(launch: 1, exit: .status(0), panic: nil))
            == [.showWindow, .deleteOldBuilds])
        #expect(run.state.handOff == .returning)
        #expect(run.state.playStatus == .ready)
        #expect(run.send(.windowShown) == [])
        #expect(run.state.handOff == nil)
    }

    @Test func aGameThatEndsBeforeItsWindowOrTheTimeoutComesBack() {
        var run = started()
        #expect(run.send(.gameExited(launch: 1, exit: .signal(11), panic: nil))
            == [.showWindow, .deleteOldBuilds])
        #expect(run.state.handOff == .returning)
        // Its timer runs out after it has ended.
        #expect(run.send(.handOffTimedOut(launch: 1)) == [])
        #expect(run.state.handOff == .returning)
    }

    @Test func aGameThatCouldNotStartTakesTheCardDown() {
        var run = started()
        #expect(run.send(.gameCouldNotStart(launch: 1, reason: "no game")) == [.showWindow, .deleteOldBuilds])
        #expect(run.state.handOff == .returning)
        run.send(.windowShown)
        #expect(run.state.handOff == nil)
        #expect(run.state.gameProblem == .couldNotStart(reason: "no game"))
    }

    /// A line or a timer from another launch, an earlier one or none, changes nothing.
    @Test(arguments: [0, 2])
    func anotherLaunchsLinesAndTimerAreIgnored(_ launch: Int) {
        var run = started()
        #expect(run.send(.gameReady(launch: launch, marks: both)) == [])
        #expect(run.send(.handOffTimedOut(launch: launch)) == [])
        #expect(run.state.handOff == .launched)
    }

    /// The second launch's card waits for its own line, not the first launch's late timer.
    @Test func aSecondLaunchWaitsForItsOwnLine() {
        var run = started()
        run.send(.gameExited(launch: 1, exit: .status(0), panic: nil))
        run.send(.windowShown)
        _ = run.send(playToStarting)
        #expect(run.state.handOff == .launched)
        #expect(run.send(.handOffTimedOut(launch: 1)) == [])
        #expect(run.send(.gameReady(launch: 1, marks: both)) == [])
        #expect(run.send(.gameReady(launch: 2, marks: shown)) == [.hideWindow(timedOut: false)])
    }

    @Test func windowShownChangesNothingUnlessTheCardIsComingBack() {
        var run = launched()
        #expect(run.send(.windowShown) == [])
        _ = run.send(playToStarting)
        #expect(run.send(.windowShown) == [])
        #expect(run.state.handOff == .launched)
        run.send(.gameReady(launch: 1, marks: shown))
        #expect(run.send(.windowShown) == [])
        #expect(run.state.handOff == .hidden)
    }

    /// The disc isn't there or isn't the right one, so the card comes down and the window stays.
    @Test(arguments: [
        [Flow.Event.playPressed, .bookmarkResolved(.stale)],
        [.playPressed, .bookmarkResolved(.missing)],
        [.playPressed, .bookmarkResolved(.found(flowDisc)),
         .discChecked(path: flowDisc, check: .wrongGame(foundID: "GALE01"))],
    ])
    func aDiscProblemTakesTheCardDownWithNoHide(_ events: [Flow.Event]) {
        var run = launched()
        let effects = run.send(events).joined()
        #expect(run.state.handOff == nil)
        #expect(!effects.contains(.hideWindow(timedOut: false)))
        #expect(!effects.contains(.hideWindow(timedOut: true)))
    }

    @Test func playWithNoBookmarkAsksForTheDiscWithNoCard() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true, disc: nil))
        #expect(run.send(.playPressed) == [])
        #expect(run.screen == .disc(.choose))
        #expect(run.state.handOff == nil)
    }

    /// Neither window shows for any time: the launcher hides only on the window line or the
    /// timeout, whatever else happens first.
    @Test func theLauncherNeverHidesWithoutTheWindowLineOrTheTimeout() {
        var run = launched()
        var effects = run.send(playToStarting).joined().map { $0 }
        effects += run.send(.gameReady(launch: 1, marks: ReadyMarks(frame: 3)))
        effects += run.send(.showSavesPressed)
        effects += run.send(.playPressed)
        #expect(!effects.contains { if case .hideWindow = $0 { true } else { false } })
        #expect(run.send(.handOffTimedOut(launch: 1)) == [.hideWindow(timedOut: true)])
    }

    /// Play again while the card is coming back puts it up again, and the fade's end leaves it.
    @Test func playWhileTheCardComesBackPutsItUpAgain() {
        var run = started()
        run.send(.gameExited(launch: 1, exit: .status(0), panic: nil))
        run.send(.playPressed)
        #expect(run.state.handOff == .charging)
        run.send(.windowShown)
        #expect(run.state.handOff == .charging)
    }

    @Test func aGameAnEarlierLauncherStartedHasNoCard() {
        var run = launched(earlierGame: 4242)
        #expect(run.state.handOff == nil)
        #expect(run.send(.earlierGameEnded) == [.deleteOldBuilds])
        #expect(run.state.handOff == nil)
    }
}
