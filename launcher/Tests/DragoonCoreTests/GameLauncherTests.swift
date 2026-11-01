import DragoonCore
import Foundation
import Testing

/// Each of these runs a shell script as the game under `Process`, in a scratch directory whose
/// name has spaces. The scripts are in the tests that use them.
@Suite struct GameLauncherTests {
    @Test func theGameRunsInTheDataDirectoryWithTheDiscAsItsOneArgument() async throws {
        let fixture = try GameFixture()
        try fixture.install("exit 0")
        #expect(await results(of: fixture.play()) == [.exited(.status(0), panic: nil)])
        #expect(fixture.lines(fixture.argumentsFile) == [fixture.disc])
        #expect(fixture.lines(fixture.directoryFile) == [fixture.data])
    }

    @Test func whatTheGamePrintsGoesToItsLogInTheLogsFolder() async throws {
        let fixture = try GameFixture()
        try fixture.install(
            """
            echo 'on stdout'
            echo 'on stderr' >&2
            """)
        _ = await results(of: fixture.play())
        #expect(fixture.logNames == [GameFixture.logName])
        #expect(fixture.lines(fixture.logPath).sorted() == ["on stderr", "on stdout"])
    }

    @Test func aNonzeroExitHandsOverTheCodeAndThePanicAndMovesThePanicToTheLogs() async throws {
        let fixture = try GameFixture()
        try fixture.install(
            """
            echo 'guest panic: unmapped read at 0x80001234' > panic.txt
            exit 3
            """)
        #expect(
            await results(of: fixture.play())
                == [.exited(.status(3), panic: "guest panic: unmapped read at 0x80001234\n")])
        #expect(!FileManager.default.fileExists(atPath: fixture.panic))
        #expect(
            fixture.text(fixture.logs + "/panic-\(GameFixture.stamp).txt")
                == "guest panic: unmapped read at 0x80001234\n")
    }

    @Test func aGameStoppedByASignalHandsOverWhichOneAndItsPanic() async throws {
        let fixture = try GameFixture()
        try fixture.install(
            """
            echo 'guest panic: stopped' > panic.txt
            kill -TERM $$
            """)
        #expect(
            await results(of: fixture.play()) == [.exited(.signal(SIGTERM), panic: "guest panic: stopped\n")])
    }

    @Test func aCleanExitHandsOverNoPanic() async throws {
        let fixture = try GameFixture()
        try fixture.install(
            """
            echo 'written anyway' > panic.txt
            exit 0
            """)
        #expect(await results(of: fixture.play()) == [.exited(.status(0), panic: nil)])
    }

    @Test func aPanicWhoseNameIsTakenInTheLogsFolderLandsBesideItAndReplacesNothing() async throws {
        let fixture = try GameFixture()
        let taken = fixture.logs + "/panic-\(GameFixture.stamp).txt"
        try fixture.write(taken, "an older panic\n")
        try fixture.install(
            """
            echo 'this run' > panic.txt
            exit 1
            """)
        #expect(await results(of: fixture.play()) == [.exited(.status(1), panic: "this run\n")])
        #expect(fixture.text(taken) == "an older panic\n")
        #expect(fixture.text(fixture.logs + "/panic-\(GameFixture.stamp)-1.txt") == "this run\n")
        #expect(!FileManager.default.fileExists(atPath: fixture.panic))
    }

    @Test func aPanicLeftByAnEarlierRunMovesToTheLogsBeforeTheGameStartsAndIsNeverShown() async throws {
        let fixture = try GameFixture()
        try fixture.write(fixture.panic, "an earlier run's panic\n")
        try fixture.install(
            """
            if [ -e panic.txt ]; then echo 'panic.txt was there' > \(shellWord(fixture.noteFile)); fi
            exit 1
            """)
        #expect(await results(of: fixture.play()) == [.exited(.status(1), panic: nil)])
        #expect(fixture.text(fixture.noteFile) == nil)
        #expect(
            fixture.text(fixture.logs + "/panic-\(GameFixture.stamp).txt") == "an earlier run's panic\n")
    }

    @Test func aGameWhoseFileIsMissingCantStartAndWritesNoLog() async throws {
        let fixture = try GameFixture()
        #expect(
            await results(of: fixture.play()) == [.couldNotStart(.missing(path: fixture.executable))])
        #expect(fixture.logNames.isEmpty)
    }

    @Test func aGameThatCantBeSpawnedSaysWhy() async throws {
        let fixture = try GameFixture()
        try fixture.install("exit 0")
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o644], ofItemAtPath: fixture.executable)
        let all = await results(of: fixture.play())
        guard all.count == 1, case .couldNotStart(.failed(let reason)) = all[0] else {
            Issue.record("expected one couldNotStart(.failed), got \(all)")
            return
        }
        #expect(!reason.isEmpty)
        #expect(fixture.text(fixture.argumentsFile) == nil)
    }

    /// The game's ways of ending, for the test that each gives one result.
    enum Ending: String, CaseIterable {
        case exits, cantBeSpawned, diesAtOnce
    }

    @Test(arguments: Ending.allCases)
    func everyLaunchEndsInExactlyOneResult(_ ending: Ending) async throws {
        let fixture = try GameFixture()
        switch ending {
        case .exits:
            try fixture.installScript("exit 0")
        case .cantBeSpawned:
            try fixture.installScript("exit 0")
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o644], ofItemAtPath: fixture.executable)
        case .diesAtOnce:
            try fixture.installScript("kill -KILL $$")
        }
        let all = await results(of: fixture.play())
        #expect(all.count == 1, "\(all)")
        if ending == .diesAtOnce { #expect(all == [.exited(.signal(SIGKILL), panic: nil)]) }
    }

    @Test func onlyTheNewestTenGameLogsStayAndTheBuildLogsAreLeftAlone() async throws {
        let fixture = try GameFixture()
        let games = (0..<12).map { String(format: "game-2020-01-01T00-00-%02d.000Z.log", $0) }
        let builds = (0..<12).map { String(format: "build-2020-01-01T00-00-%02d.000Z.log", $0) }
        let others = ["game-notes.txt", "panic-2020-01-01T00-00-00.000Z.txt"]
        for name in games + builds + others {
            try fixture.write(fixture.logs + "/" + name, "")
        }
        try fixture.install("exit 0")
        _ = await results(of: fixture.play())
        #expect(
            fixture.logNames == (builds + games.suffix(9) + [GameFixture.logName] + others).sorted())
    }

    @Test func aSignalIsNamedAsMacOSSpellsIt() {
        #expect(GameExit.signal(SIGSEGV).signalName == "SIGSEGV")
        #expect(GameExit.signal(SIGABRT).signalName == "SIGABRT")
        #expect(GameExit.signal(SIGKILL).signalName == "SIGKILL")
        #expect(GameExit.signal(SIGUSR2).signalName == "SIGUSR2")
        #expect(GameExit.signal(0).signalName == nil)
        #expect(GameExit.signal(NSIG).signalName == nil)
        #expect(GameExit.status(SIGSEGV).signalName == nil)
    }
}
