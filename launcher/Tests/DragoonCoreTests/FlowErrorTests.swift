import DragoonCore
import Foundation
import Testing

/// One test for each row of the error table in the research's section 7.
@Suite struct FlowErrorTests {
    /// Tools missing or the install cancelled: the install button again, and what the tools are
    /// for.
    @Test func missingToolsOfferTheInstallAgainUntilTheyArrive() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        run.send(.toolsDetected(.missing))
        #expect(run.screen == .tools(.missing))
        #expect(run.send(.installToolsPressed) == [.installTools])
        // The player cancels Apple's installer, so the next check finds nothing either.
        #expect(run.send(.toolsCheckDue) == [.detectTools])
        #expect(run.send(.toolsDetected(.missing)) == [.scheduleToolsCheck(after: 5)])
        #expect(run.screen == .tools(.missing))
        #expect(run.send(.installToolsPressed) == [.installTools])
    }

    /// No SDK links: the tools are older than the SDKs, and the step opens Software Update.
    @Test func noSDKThatLinksOpensSoftwareUpdateAndChecksAgainWhenAsked() {
        let tried = ["/Library/Developer/CommandLineTools/SDKs/MacOSX27.0.sdk"]
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        #expect(run.send(.toolsDetected(.noLinkableSDK(tried: tried))) == [])
        #expect(run.screen == .tools(.noLinkableSDK(tried: tried)))
        #expect(run.send(.installToolsPressed) == [])
        #expect(run.send(.toolsCheckDue) == [])
        #expect(run.send(.openSoftwareUpdatePressed) == [.openSoftwareUpdate])
        #expect(run.send(.checkToolsPressed) == [.detectTools])
        #expect(run.screen == .tools(.checking))
    }

    @Test func aProbeThatCantBeWrittenSaysWhereAndChecksAgainWhenAsked() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        run.send(.toolsDetected(.cantWriteProbe(path: "/x/probe.cpp", error: "disk full")))
        #expect(run.screen == .tools(.cantWriteProbe(path: "/x/probe.cpp", error: "disk full")))
        #expect(run.send(.checkToolsPressed) == [.detectTools])
    }

    /// Another game, region or revision: what the disc has against what Dragoon needs.
    @Test func anotherGameShowsItsDiscIDAgainstTheOneNeeded() {
        var run = launched()
        run.send(.changeDiscPressed)
        run.send(.discChosen(path: flowDisc, bookmark: Data("another".utf8)))
        #expect(run.send(.discChecked(path: flowDisc, check: .wrongGame(foundID: "GMSE01"))) == [])
        #expect(run.screen == .disc(.problem(.wrongGame(found: "GMSE01", needed: "GKYE01"))))
        #expect(run.state.step == .disc)
        // The disc it had is still the one it keeps.
        #expect(run.state.settings.disc == flowBookmark)
    }

    @Test func anotherRevisionShowsItsSHA1AgainstTheOneNeeded() {
        let found = String(repeating: "f", count: 40)
        var run = launched()
        run.send(.changeDiscPressed)
        run.send(.discChosen(path: flowDisc, bookmark: Data("another".utf8)))
        run.send(.discChecked(path: flowDisc, check: .wrongRevision(foundSHA1: found)))
        #expect(run.screen == .disc(.problem(.wrongRevision(
            found: found, needed: flowSource.disc.dolSHA1))))
        #expect(run.state.settings.disc == flowBookmark)
    }

    /// `.rvz`, `.gcz`, `.wia` or `.wbfs`: convert to ISO in Dolphin first.
    @Test(arguments: UnsupportedDiscFormat.allCases)
    func aCompressedImageAsksForAnISO(format: UnsupportedDiscFormat) {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        run.send(.toolsDetected(.ready(flowToolchain)))
        run.send(.discChosen(path: flowDisc, bookmark: flowBookmark))
        run.send(.discChecked(path: flowDisc, check: .needsConversion(format: format)))
        #expect(run.screen == .disc(.problem(.needsConversion(format))))
        #expect(run.state.settings.disc == nil)
        #expect(run.send(.chooseDiscPressed) == [.openDiscPanel])
    }

    /// Disc moved or drive unplugged: find it again, or pick it again.
    @Test func aDiscThatMovedCanBeFoundAgain() {
        var run = launched()
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
        #expect(run.send(.bookmarkResolved(.missing)) == [])
        #expect(run.screen == .disc(.problem(.moved)))
        // The drive is plugged back in.
        #expect(run.send(.lookAgainPressed) == [.resolveBookmark(flowBookmark)])
        #expect(run.send(.bookmarkResolved(.found(flowDisc)))
            == [.checkDisc(path: flowDisc, expected: flowSource.disc)])
        #expect(run.send(.discChecked(path: flowDisc, check: .ok)) == [.play(disc: flowDisc)])
        #expect(run.screen == .library)
    }

    @Test func aDiscThatMovedCanBePickedAgainAndThePlayGoesOn() {
        let moved = "/Volumes/Games/Kirby Air Ride (USA).ciso"
        let bookmark = Data("a bookmark to where it is now".utf8)
        var run = launched()
        run.send(.playPressed)
        run.send(.bookmarkResolved(.missing))
        #expect(run.send(.chooseDiscPressed) == [.openDiscPanel])
        run.send(.discChosen(path: moved, bookmark: bookmark))
        #expect(run.send(.discChecked(path: moved, check: .ok)) == [
            .saveSettings(LauncherSettings(welcomeSeen: true, disc: bookmark)),
            .play(disc: moved),
        ])
    }

    /// Under about 2 GB free: how much is needed and where.
    @Test func tooLittleSpaceSaysHowMuchIsNeededAndWhere() {
        let space = FreeSpace(available: 1_500_000_000, volume: "Macintosh HD")
        var run = launched()
        run.send(.rebuildPressed)
        #expect(run.send(.spaceChecked(space)) == [])
        #expect(run.screen == .build(.lowSpace(space)))
        #expect(Flow.neededSpace == 2_000_000_000)
        // Check Again starts over from the space.
        #expect(run.send(.buildPressed) == [.checkSpace])
    }

    /// Configure, compile or warm-up failed: the step, the end of the log, Copy Log and Show Log.
    @Test func aStepThatFailedShowsTheEndOfItsLog() {
        let failure = BuildFailure.failed(step: "compile", message: "make exited 2", log: flowLog)
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        run.send(.build(.step("compile")))
        #expect(run.send(.buildEnded(failure)) == [.readLogTail(flowLog)])
        #expect(run.screen == .build(.failed(failure, lastLines: [])))
        #expect(run.state.step == .build)
        #expect(run.send(.logTailRead(path: flowLog, lines: ["clang: error", "make: *** [all]"])) == [])
        #expect(run.screen == .build(.failed(failure, lastLines: ["clang: error", "make: *** [all]"])))
        #expect(run.send(.copyLogPressed) == [.copyLog(flowLog)])
        #expect(run.send(.showLogPressed) == [.showLog(flowLog)])
        #expect(run.send(.buildPressed) == [.checkSpace])
    }

    @Test func aWarmUpThatFailedIsShownOnTheWarmUpStep() {
        let failure = BuildFailure.failed(step: "warmup", message: "the game exited 1", log: flowLog)
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        run.send(.build(.step("warmup")))
        run.send(.buildEnded(failure))
        #expect(run.state.step == .warmup)
        #expect(run.send(.copyLogPressed) == [.copyLog(flowLog)])
    }

    @Test func aRebuildThatFailedLeavesTheOldGameToPlay() {
        let old = InstalledGame(stamp: Commits(
            dragoon: String(repeating: "8", count: 40), gcnRecomp: sourceCommits.gcnRecomp))
        let failure = BuildFailure.failed(step: "recompile", message: "bad", log: flowLog)
        var run = launched(installed: old)
        for (event, _) in rebuildToRunning { run.send(event) }
        run.send(.buildEnded(failure))
        #expect(run.state.installed == old)
        #expect(run.state.canGoBackToLibrary)
        #expect(run.send(.backToLibraryPressed) == [.deleteOldBuilds])
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
    }

    @Test(arguments: [
        BuildFailure.alreadyRunning, .couldNotStart("no python3"),
    ])
    func aBuildThatNeverRanHasNoLogToShow(failure: BuildFailure) {
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        #expect(run.send(.buildEnded(failure)) == [])
        #expect(run.screen == .build(.failed(failure, lastLines: [])))
        #expect(run.send(.copyLogPressed) == [])
        #expect(run.send(.showLogPressed) == [])
    }

    @Test func aRecipeThatRefusedItsFilesShowsItsLog() {
        let failure = BuildFailure.refused(message: "the kit is from another commit", log: flowLog)
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        #expect(run.send(.buildEnded(failure)) == [.readLogTail(flowLog)])
        #expect(run.send(.showLogPressed) == [.showLog(flowLog)])
    }

    /// The game exited with an error: the exit code and `panic.txt` when the runtime wrote one.
    @Test func aGameThatExitedWithAnErrorShowsItsCodeAndPanic() {
        var run = launched()
        run.send(.gameStarted)
        #expect(run.state.gameRunning)
        #expect(!run.state.canPlayOrRebuild)
        #expect(run.send(.playPressed) == [])
        #expect(run.send(.rebuildPressed) == [])
        #expect(run.send(.gameExited(status: 134, panic: "unmapped read at 0x80001234"))
            == [.deleteOldBuilds])
        #expect(run.state.gameProblem == GameProblem(status: 134, panic: "unmapped read at 0x80001234"))
        // Playing again clears it, and so does a clean exit.
        run.send(.playPressed)
        #expect(run.state.gameProblem == nil)
        run.send(.gameExited(status: 2, panic: nil))
        #expect(run.state.gameProblem == GameProblem(status: 2, panic: nil))
        run.send(.gameExited(status: 0, panic: nil))
        #expect(run.state.gameProblem == nil)
    }

    /// Running from Downloads or a DMG: move Dragoon to Applications first.
    @Test(arguments: [
        ("/private/var/folders/x1/T/AppTranslocation/8E9C1A2B/d/Dragoon.app", false),
        ("/Volumes/Dragoon/Dragoon.app", true),
    ])
    func aLauncherRunFromDownloadsOrADiskImageAsksToBeMoved(appPath: String, readOnly: Bool) {
        var run = launched(appPath: appPath, onReadOnlyVolume: readOnly)
        guard case .mustMove = run.screen else {
            Issue.record("\(run.screen) isn't mustMove")
            return
        }
        #expect(run.effects == [])
        #expect(run.state.step == nil)
        for event: Flow.Event in [.playPressed, .rebuildPressed, .continuePressed, .showSavesPressed] {
            #expect(run.send(event) == [])
        }
        #expect(run.send(.quitPressed) == [.quit])
    }

    /// New launcher version: rebuild now or later, and the old game plays until the rebuild
    /// starts.
    @Test func aNewLauncherVersionOffersARebuildAndTheOldGamePlaysMeanwhile() {
        let old = InstalledGame(stamp: Commits(
            dragoon: String(repeating: "7", count: 40), gcnRecomp: sourceCommits.gcnRecomp))
        var run = launched(installed: old)
        #expect(run.screen == .library)
        #expect(run.state.offersRebuild)
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
        run.send(.bookmarkResolved(.found(flowDisc)))
        #expect(run.send(.discChecked(path: flowDisc, check: .ok)) == [.play(disc: flowDisc)])
        #expect(run.state.installed == old)
        #expect(run.send(.rebuildLaterPressed) == [])
        #expect(!run.state.offersRebuild)
        #expect(run.send(.rebuildPressed) == [.checkSpace])
    }
}
