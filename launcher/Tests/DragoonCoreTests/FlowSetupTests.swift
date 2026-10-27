import DragoonCore
import Foundation
import Testing

/// The first run, from Welcome to Library, and where later launches open.
@Suite struct FlowSetupTests {
    @Test func theFirstLaunchOpensOnWelcomeAndDoesNothingElse() {
        let run = launched(settings: LauncherSettings(), installed: nil)
        #expect(run.screen == .welcome)
        #expect(run.state.step == .welcome)
        #expect(run.effects == [])
    }

    @Test func continuingFromWelcomeRemembersItAndChecksTheTools() {
        var run = launched(settings: LauncherSettings(), installed: nil)
        let effects = run.send(.continuePressed)
        #expect(effects == [.saveSettings(LauncherSettings(welcomeSeen: true)), .detectTools])
        #expect(run.screen == .tools(.checking))
        #expect(run.state.step == .tools)
    }

    @Test func aLaterLaunchWithNoGameSkipsWelcomeAndChecksTheTools() {
        let run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        #expect(run.screen == .tools(.checking))
        #expect(run.effects == [.detectTools])
    }

    @Test(arguments: [
        (true, InstalledGame(stamp: sourceCommits)),
        (false, InstalledGame(stamp: sourceCommits)),
        (true, InstalledGame(stamp: nil)),
        (true, InstalledGame(stamp: Commits(
            dragoon: String(repeating: "9", count: 40), gcnRecomp: sourceCommits.gcnRecomp))),
    ])
    func everyLaterLaunchWithAGameOpensOnLibrary(welcomeSeen: Bool, installed: InstalledGame) {
        let run = launched(settings: LauncherSettings(welcomeSeen: welcomeSeen), installed: installed)
        #expect(run.screen == .library)
        #expect(run.state.step == .library)
        #expect(run.effects == [.deleteOldBuilds])
        #expect(run.state.installed == installed)
    }

    @Test func theFirstRunGoesThroughEveryStepToLibrary() {
        var run = launched(settings: LauncherSettings(), installed: nil)
        #expect(run.state.step == .welcome)
        run.send(.continuePressed)
        #expect(run.state.step == .tools)

        #expect(run.send(.toolsDetected(.ready(flowToolchain))) == [])
        #expect(run.screen == .disc(.choose))
        #expect(run.state.step == .disc)

        #expect(run.send(.chooseDiscPressed) == [.openDiscPanel])
        #expect(run.send(.discChosen(path: flowDisc, bookmark: flowBookmark))
            == [.checkDisc(path: flowDisc, expected: flowSource.disc)])
        #expect(run.screen == .disc(.checking))
        #expect(run.send(.discChecked(path: flowDisc, check: .ok))
            == [.saveSettings(LauncherSettings(welcomeSeen: true, disc: flowBookmark))])
        #expect(run.screen == .build(.ready))
        #expect(run.state.step == .build)

        // Before the build starts, the space, the disc behind the bookmark and the tools again.
        #expect(run.send(.buildPressed) == [.checkSpace])
        #expect(run.screen == .build(.preparing))
        #expect(run.send(.spaceChecked(enoughSpace)) == [.resolveBookmark(flowBookmark)])
        #expect(run.send(.bookmarkResolved(.found(flowDisc)))
            == [.checkDisc(path: flowDisc, expected: flowSource.disc)])
        #expect(run.send(.discChecked(path: flowDisc, check: .ok)) == [.detectTools])
        #expect(run.send(.toolsDetected(.ready(flowToolchain)))
            == [.startBuild(toolchain: flowToolchain, disc: flowDisc)])
        #expect(run.screen == .build(.running(BuildProgress())))

        run.send(.build(.step("recompile")))
        run.send(.build(.step("compile")))
        run.send(.build(.progress(step: "compile", done: 12, total: 135)))
        #expect(run.screen == .build(.running(BuildProgress(step: "compile", done: 12, total: 135))))
        #expect(run.state.step == .build)
        run.send(.build(.step("warmup")))
        run.send(.build(.progress(step: "warmup", done: 3, total: 8)))
        #expect(run.state.step == .warmup)
        run.send(.build(.step("package")))
        run.send(.build(.step("swap")))
        #expect(run.state.step == .warmup)
        #expect(run.send(.build(.done(game: "/x/game/current/Dragoon.app"))) == [])

        #expect(run.send(.buildEnded(nil)) == [.deleteOldBuilds])
        #expect(run.screen == .library)
        #expect(run.state.step == .library)
        #expect(run.state.installed == InstalledGame(stamp: sourceCommits))
        #expect(run.state.rebuildOffer == nil)
    }

    /// The list's current step only moves down, so the package and swap steps after the warm-up
    /// stay on Warm-up.
    @Test func theStepListNeverGoesBackOnTheFirstRun() {
        var run = launched(settings: LauncherSettings(), installed: nil)
        var steps = [run.state.step]
        let events: [Flow.Event] = [
            .continuePressed, .toolsDetected(.ready(flowToolchain)), .chooseDiscPressed,
            .discChosen(path: flowDisc, bookmark: flowBookmark),
            .discChecked(path: flowDisc, check: .ok), .buildPressed, .spaceChecked(enoughSpace),
            .bookmarkResolved(.found(flowDisc)), .discChecked(path: flowDisc, check: .ok),
            .toolsDetected(.ready(flowToolchain)), .build(.step("recompile")),
            .build(.step("compile")), .build(.step("warmup")), .build(.step("package")),
            .build(.step("swap")), .buildEnded(nil),
        ]
        for event in events {
            run.send(event)
            steps.append(run.state.step)
        }
        let listed = steps.compactMap { $0 }
        #expect(listed.count == steps.count)
        #expect(listed == listed.sorted())
        #expect(Set(listed) == Set(Flow.Step.allCases))
    }

    @Test(arguments: ["package", "swap"])
    func aBuildThatFailedAfterItsWarmUpStaysOnWarmUp(step: String) {
        let failure = BuildFailure.failed(step: step, message: "bad", log: flowLog)
        var run = launched()
        for (event, _) in rebuildToRunning { run.send(event) }
        run.send(.build(.step(step)))
        #expect(run.state.step == .warmup)
        run.send(.buildEnded(failure))
        #expect(run.state.step == .warmup)
    }

    @Test func theStepsAreInTheOrderTheWindowListsThem() {
        #expect(Flow.Step.allCases == [.welcome, .tools, .disc, .build, .warmup, .library])
        #expect(Flow.Step.tools < .disc)
    }

    @Test func missingToolsAreLookedForAgainEveryFiveSeconds() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        #expect(Flow.toolsCheckInterval == 5)
        #expect(run.send(.toolsDetected(.missing)) == [.scheduleToolsCheck(after: 5)])
        #expect(run.send(.toolsCheckDue) == [.detectTools])
        // The step stays as it was while it looks, and a second tick waits for the answer.
        #expect(run.screen == .tools(.missing))
        #expect(run.send(.toolsCheckDue) == [])
        #expect(run.send(.toolsDetected(.missing)) == [.scheduleToolsCheck(after: 5)])
        #expect(run.send(.toolsCheckDue) == [.detectTools])
        #expect(run.send(.toolsDetected(.ready(flowToolchain))) == [])
        #expect(run.screen == .disc(.choose))
        #expect(run.send(.toolsCheckDue) == [])
    }

    @Test func aToolsCheckThatWasCancelledLooksAgain() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        #expect(run.send(.toolsDetected(.cancelled)) == [.detectTools])
        #expect(run.screen == .tools(.checking))
        #expect(run.send(.toolsDetected(.ready(flowToolchain))) == [])
        #expect(run.screen == .disc(.choose))
    }

    @Test func aCancelledFirstBuildGoesBackToBuild() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        run.send(.toolsDetected(.ready(flowToolchain)))
        run.send(.chooseDiscPressed)
        run.send(.discChosen(path: flowDisc, bookmark: flowBookmark))
        run.send(.discChecked(path: flowDisc, check: .ok))
        _ = run.send([
            .buildPressed, .spaceChecked(enoughSpace), .bookmarkResolved(.found(flowDisc)),
            .discChecked(path: flowDisc, check: .ok), .toolsDetected(.ready(flowToolchain)),
        ])
        #expect(run.send(.cancelBuildPressed) == [.cancelBuild])
        #expect(run.screen == .build(.running(BuildProgress(canceling: true))))
        #expect(run.send(.cancelBuildPressed) == [])
        #expect(run.send(.buildEnded(.cancelled)) == [])
        #expect(run.screen == .build(.ready))
        #expect(run.state.installed == nil)
    }

    @Test func aDiscChosenWithoutABookmarkShowsWhy() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        run.send(.toolsDetected(.ready(flowToolchain)))
        run.send(.chooseDiscPressed)
        #expect(run.send(.discChoiceFailed(reason: "no such file")) == [])
        #expect(run.screen == .disc(.problem(.unreadable(reason: "no such file"))))
        #expect(run.state.waiting == nil)
        #expect(run.send(.chooseDiscPressed) == [.openDiscPanel])
    }

    /// The panel doesn't stop the window, so the flow waits on it as on any other result.
    @Test func whileTheDiscPanelIsOpenTheStepWaitsForIt() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil)
        run.send(.toolsDetected(.ready(flowToolchain)))
        #expect(run.send(.chooseDiscPressed) == [.openDiscPanel])
        #expect(run.state.waiting == .panel)
        #expect(run.state.isBusy)
        #expect(run.send(.chooseDiscPressed) == [])
        // The player cancels it, and Choose Disc opens it again.
        #expect(run.send(.discPanelCanceled) == [])
        #expect(run.screen == .disc(.choose))
        #expect(run.state.waiting == nil)
        #expect(run.send(.chooseDiscPressed) == [.openDiscPanel])
        #expect(run.send(.discChosen(path: flowDisc, bookmark: flowBookmark))
            == [.checkDisc(path: flowDisc, expected: flowSource.disc)])
    }

    @Test func aSourceThatCantBeReadStopsAtLaunch() {
        var run = launched(source: nil)
        #expect(run.screen == .damaged)
        #expect(run.state.step == nil)
        #expect(run.effects == [])
        #expect(run.send(.playPressed) == [])
        #expect(run.send(.quitPressed) == [.quit])
    }

    @Test func eventsBeforeTheLaunchAndASecondLaunchChangeNothing() {
        var run = FlowRun()
        #expect(run.send(.continuePressed) == [])
        #expect(run.screen == .starting)
        run = launched()
        let before = run.state
        #expect(run.send(.launched(Flow.Launch(
            appPath: flowApp, onReadOnlyVolume: false, settings: LauncherSettings(),
            source: flowSource, installed: nil))) == [])
        #expect(run.state == before)
    }
}
