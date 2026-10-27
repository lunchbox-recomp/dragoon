import DragoonCore
import Foundation
import Testing

private let oldCommits = Commits(
    dragoon: String(repeating: "7", count: 40), gcnRecomp: String(repeating: "6", count: 40))

/// Library, rebuilds, the disc's bookmark, old builds and results that come late.
@Suite struct FlowLibraryTests {
    /// A stamp that can't be read gets its own offer, since which version it is isn't known.
    @Test(arguments: [
        (Commits(dragoon: oldCommits.dragoon, gcnRecomp: sourceCommits.gcnRecomp), .otherVersion),
        (Commits(dragoon: sourceCommits.dragoon, gcnRecomp: oldCommits.gcnRecomp), .otherVersion),
        (nil, .unknownVersion),
        (sourceCommits, nil),
    ] as [(Commits?, RebuildOffer?)])
    func aRebuildIsOfferedWhenTheStampNamesOtherCommits(stamp: Commits?, offer: RebuildOffer?) {
        let run = launched(installed: InstalledGame(stamp: stamp))
        #expect(run.screen == .library)
        #expect(run.state.rebuildOffer == offer)
    }

    @Test func aCancelledRebuildGoesBackToLibraryWithTheOldGame() {
        let old = InstalledGame(stamp: oldCommits)
        var run = launched(installed: old)
        #expect(run.state.rebuildOffer == .otherVersion)
        for (event, effects) in rebuildToRunning {
            #expect(run.send(event) == effects)
        }
        run.send(.build(.step("compile")))
        run.send(.build(.progress(step: "compile", done: 40, total: 135)))
        #expect(run.send(.cancelBuildPressed) == [.cancelBuild])
        #expect(run.send(.buildEnded(.cancelled)) == [.deleteOldBuilds])
        #expect(run.screen == .library)
        #expect(run.state.installed == old)
        #expect(run.state.rebuildOffer == .otherVersion)
        #expect(run.state.waiting == nil)
        #expect(run.state.intent == nil)
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
    }

    /// The recipe can start another step between Cancel's signal and its exit.
    @Test func aStepAfterCancelKeepsTheBuildCanceling() {
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        run.send(.build(.step("compile")))
        #expect(run.send(.cancelBuildPressed) == [.cancelBuild])
        run.send(.build(.step("warmup")))
        #expect(run.screen == .build(.running(BuildProgress(step: "warmup", canceling: true))))
        #expect(run.send(.cancelBuildPressed) == [])
        run.send(.build(.progress(step: "warmup", done: 1, total: 8)))
        #expect(run.screen == .build(.running(BuildProgress(
            step: "warmup", done: 1, total: 8, canceling: true))))
    }

    @Test func aLogTailForAnotherLogIsIgnored() {
        let failure = BuildFailure.failed(step: "compile", message: "make exited 2", log: flowLog)
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        run.send(.buildEnded(failure))
        #expect(run.send(.logTailRead(path: flowLog + ".old", lines: ["another build"])) == [])
        #expect(run.screen == .build(.failed(failure, lastLines: [])))
    }

    /// Play checks the disc from Library, and Library's buttons wait for it.
    @Test func libraryWaitsWhilePlayChecksTheDisc() {
        var run = launched()
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
        #expect(run.screen == .library)
        #expect(!run.state.libraryIsIdle)
        for event: Flow.Event in [.playPressed, .rebuildPressed, .changeDiscPressed] {
            #expect(run.send(event) == [], "\(event)")
        }
        #expect(run.state.waiting == .bookmark)
    }

    @Test func aRebuildThatFinishesStampsTheGameWithTheSourcesCommits() {
        var run = launched(installed: InstalledGame(stamp: oldCommits))
        for (event, _) in rebuildToRunning { run.send(event) }
        #expect(run.send(.buildEnded(nil)) == [.deleteOldBuilds])
        #expect(run.state.installed == InstalledGame(stamp: sourceCommits))
        #expect(run.state.rebuildOffer == nil)
    }

    @Test func aStaleBookmarkGoesBackToTheDiscStep() {
        var run = launched()
        run.send(.rebuildPressed)
        run.send(.spaceChecked(enoughSpace))
        #expect(run.send(.bookmarkResolved(.stale)) == [])
        #expect(run.screen == .disc(.problem(.moved)))
        #expect(run.state.step == .disc)
        // The same bookmark would be stale again, so only a new choice gets past it.
        #expect(run.send(.lookAgainPressed) == [])
        // The game stays, and Library is one press away.
        #expect(run.state.installed == InstalledGame(stamp: sourceCommits))
        #expect(run.state.canGoBackToLibrary)
        // Picking it again carries the rebuild on.
        let bookmark = Data("a fresh bookmark".utf8)
        run.send(.chooseDiscPressed)
        run.send(.discChosen(path: flowDisc, bookmark: bookmark))
        #expect(run.send(.discChecked(path: flowDisc, check: .ok)) == [
            .saveSettings(LauncherSettings(welcomeSeen: true, disc: bookmark)), .detectTools,
        ])
        #expect(run.send(.toolsDetected(.ready(flowToolchain)))
            == [.startBuild(toolchain: flowToolchain, disc: flowDisc)])
    }

    @Test func noBookmarkAtAllAsksForTheDisc() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true))
        #expect(run.send(.playPressed) == [])
        #expect(run.screen == .disc(.choose))
    }

    @Test(arguments: [Int64(2_000_000_000), 50_000_000_000])
    func twoGBFreeIsEnoughToBuild(available: Int64) {
        var run = launched()
        run.send(.rebuildPressed)
        let space = FreeSpace(available: available, volume: "Macintosh HD")
        #expect(run.send(.spaceChecked(space)) == [.resolveBookmark(flowBookmark)])
        #expect(run.screen == .build(.preparing))
    }

    @Test(arguments: [Int64(1_999_999_999), 0])
    func lessThanTwoGBFreeStopsBeforeTheBuild(available: Int64) {
        var run = launched()
        run.send(.rebuildPressed)
        let space = FreeSpace(available: available, volume: "Macintosh HD")
        #expect(run.send(.spaceChecked(space)) == [])
        #expect(run.screen == .build(.lowSpace(space)))
    }

    @Test func missingToolsDuringARebuildCarryItOnOnceTheyArrive() {
        var run = launched()
        _ = run.send([
            .rebuildPressed, .spaceChecked(enoughSpace), .bookmarkResolved(.found(flowDisc)),
            .discChecked(path: flowDisc, check: .ok),
        ])
        #expect(run.send(.toolsDetected(.missing)) == [.scheduleToolsCheck(after: 5)])
        #expect(run.screen == .tools(.missing))
        #expect(run.send(.toolsCheckDue) == [.detectTools])
        // The tools took a while, so the rebuild starts over from the space.
        #expect(run.send(.toolsDetected(.ready(flowToolchain))) == [.checkSpace])
        #expect(run.screen == .build(.preparing))
    }

    @Test func backToLibraryGivesUpTheRebuildAndItsLateResults() {
        var run = launched()
        _ = run.send([
            .rebuildPressed, .spaceChecked(enoughSpace), .bookmarkResolved(.found(flowDisc)),
            .discChecked(path: flowDisc, check: .ok), .toolsDetected(.missing),
        ])
        #expect(run.state.canGoBackToLibrary)
        #expect(run.send(.backToLibraryPressed) == [.deleteOldBuilds])
        #expect(run.screen == .library)
        #expect(run.state.intent == nil)
        #expect(run.send(.toolsCheckDue) == [])
        #expect(run.send(.toolsDetected(.ready(flowToolchain))) == [])
        #expect(run.screen == .library)
    }

    @Test func aRunningBuildCantGoBackToLibrary() {
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        #expect(!run.state.canGoBackToLibrary)
        #expect(run.send(.backToLibraryPressed) == [])
        #expect(run.send(.playPressed) == [])
        #expect(run.send(.changeDiscPressed) == [])
    }

    @Test func changingTheDiscKeepsTheNewBookmarkAndGoesBackToLibrary() {
        let other = "/Volumes/Backup/Kirby Air Ride (USA).iso"
        let bookmark = Data("a bookmark to the backup".utf8)
        var run = launched()
        #expect(run.send(.changeDiscPressed) == [.openDiscPanel])
        #expect(run.screen == .library)
        #expect(run.send(.discChosen(path: other, bookmark: bookmark))
            == [.checkDisc(path: other, expected: flowSource.disc)])
        #expect(run.send(.discChecked(path: other, check: .ok)) == [
            .saveSettings(LauncherSettings(welcomeSeen: true, disc: bookmark)), .deleteOldBuilds,
        ])
        #expect(run.screen == .library)
    }

    /// With Change Disc's panel open, Library's other buttons wait, so the disc picked in the
    /// panel is the one kept.
    @Test func whileTheDiscPanelIsOpenLibraryWaitsForIt() {
        let other = "/Volumes/Backup/Kirby Air Ride (USA).iso"
        let bookmark = Data("a bookmark to the backup".utf8)
        var run = launched()
        #expect(run.send(.changeDiscPressed) == [.openDiscPanel])
        #expect(!run.state.libraryIsIdle)
        for event: Flow.Event in [.playPressed, .rebuildPressed, .changeDiscPressed] {
            #expect(run.send(event) == [], "\(event)")
        }
        #expect(run.send(.discChosen(path: other, bookmark: bookmark))
            == [.checkDisc(path: other, expected: flowSource.disc)])
        // A cancel that comes after the choice changes nothing.
        run.send(.discPanelCanceled)
        #expect(run.state.waiting == .disc(path: other, bookmark: bookmark))
        #expect(run.send(.discChecked(path: other, check: .ok)) == [
            .saveSettings(LauncherSettings(welcomeSeen: true, disc: bookmark)), .deleteOldBuilds,
        ])
        #expect(run.send(.playPressed) == [.resolveBookmark(bookmark)])
    }

    @Test func aDiscStepWithThePanelOpenCantGoBackToLibrary() {
        var run = launched()
        run.send(.playPressed)
        run.send(.bookmarkResolved(.missing))
        #expect(run.state.canGoBackToLibrary)
        run.send(.chooseDiscPressed)
        #expect(!run.state.canGoBackToLibrary)
        #expect(run.send(.backToLibraryPressed) == [])
        #expect(run.send(.lookAgainPressed) == [])
        run.send(.discPanelCanceled)
        #expect(run.send(.backToLibraryPressed) == [.deleteOldBuilds])
    }

    @Test func resultsTheFlowIsntWaitingForChangeNothing() {
        var run = launched()
        let before = run.state
        let late: [Flow.Event] = [
            .spaceChecked(enoughSpace), .bookmarkResolved(.found(flowDisc)),
            .discChecked(path: flowDisc, check: .ok), .toolsDetected(.ready(flowToolchain)),
            .build(.step("compile")), .buildEnded(nil), .logTailRead(path: flowLog, lines: ["x"]),
            .toolsCheckDue, .cancelBuildPressed, .copyLogPressed, .lookAgainPressed,
            .discChosen(path: flowDisc, bookmark: flowBookmark), .discChoiceFailed(reason: "x"),
            .discPanelCanceled,
        ]
        for event in late {
            #expect(run.send(event) == [], "\(event)")
        }
        #expect(run.state == before)
    }

    @Test func aDiscCheckOfAnotherPathIsIgnored() {
        var run = launched()
        run.send(.playPressed)
        run.send(.bookmarkResolved(.found(flowDisc)))
        #expect(run.send(.discChecked(path: "/elsewhere.iso", check: .ok)) == [])
        #expect(run.send(.discChecked(path: flowDisc, check: .ok)) == [.play(disc: flowDisc)])
    }

    @Test func showSavesIsAnEffect() {
        var run = launched()
        #expect(run.send(.showSavesPressed) == [.showSaves])
    }

    @Test func oldBuildsWaitUntilTheGameHasExited() {
        var run = launched()
        #expect(!run.send(playToStarting).joined().contains(.deleteOldBuilds))
        #expect(run.send(.gameExited(status: 0, panic: nil)) == [.deleteOldBuilds])
    }

    /// Nothing the player can press leaves Library while the game runs, so the state is set by
    /// hand here. Even then, old builds wait for the game.
    @Test func oldBuildsAreKeptWhileTheGameRunsWhateverTheFlowDoes() {
        var run = launched()
        run.send(.changeDiscPressed)
        run.send(.discChosen(path: flowDisc, bookmark: flowBookmark))
        var state = run.state
        state.gameRunning = true
        let (next, effects) = Flow.reduce(state, .discChecked(path: flowDisc, check: .ok))
        #expect(next.screen == .library)
        #expect(!effects.contains(.deleteOldBuilds))
        #expect(Flow.reduce(next, .gameExited(status: 0, panic: nil)).1 == [.deleteOldBuilds])
    }

    @Test func oldBuildsWaitUntilTheBuildHasEnded() {
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        #expect(run.send(.gameExited(status: 0, panic: nil)) == [])
        #expect(run.send(.buildEnded(nil)) == [.deleteOldBuilds])
    }

    @Test func noGameMeansNoOldBuildsToDelete() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        #expect(run.send(.gameExited(status: 0, panic: nil)) == [])
    }
}
