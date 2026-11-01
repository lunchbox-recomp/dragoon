import DragoonCore
import Foundation
import Testing

/// Each of these runs a shell script as the game under `Process`, in a scratch directory whose
/// name has spaces. The scripts are in the tests that use them. A launch that never gives its
/// result fails its test when the limit is up, rather than stopping the run.
@Suite(.timeLimit(.minutes(1))) struct GameLauncherTests {
    @Test func theGameRunsInTheDataDirectoryWithTheDiscAsItsOneArgument() async throws {
        let fixture = try GameFixture()
        try fixture.install("exit 0")
        #expect(await results(of: fixture.play()) == [.exited(.status(0), panic: nil)])
        #expect(fixture.lines(fixture.argumentsFile) == [fixture.disc])
        #expect(fixture.lines(fixture.directoryFile) == [fixture.data])
    }

    /// The game gets every variable but the launcher's bundle identifier, so nothing in its
    /// environment ties it to the launcher's bundle.
    @Test func theGameGetsTheLaunchersEnvironmentWithoutItsBundleIdentifier() async throws {
        let fixture = try GameFixture()
        try fixture.install(
            """
            printf '%s\\n' "${DRAGOON_TEST_VALUE-unset}" > \(shellWord(fixture.noteFile))
            printf '%s\\n' "${__CFBundleIdentifier-unset}" >> \(shellWord(fixture.noteFile))
            """)
        let environment = [
            "DRAGOON_TEST_VALUE": "passed on",
            "__CFBundleIdentifier": "io.github.lunchbox-recomp.dragoon",
        ]
        #expect(
            await results(of: fixture.play(environment: environment))
                == [.exited(.status(0), panic: nil)])
        #expect(fixture.lines(fixture.noteFile) == ["passed on", "unset"])
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
                == [.exited(.status(3), panic: GamePanic("guest panic: unmapped read at 0x80001234\n"))])
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
            await results(of: fixture.play())
                == [.exited(.signal(SIGTERM), panic: GamePanic("guest panic: stopped\n"))])
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
        #expect(await results(of: fixture.play()) == [.exited(.status(1), panic: GamePanic("this run\n"))])
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

    /// An earlier run's `panic.txt` that can't be moved, here because a file is where the logs
    /// folder goes, isn't shown after a later run that wrote none.
    @Test func aPanicLeftByAnEarlierRunThatCantBeMovedIsNeverShown() async throws {
        let fixture = try GameFixture()
        try fixture.write(fixture.logs, "not a folder\n")
        try fixture.write(fixture.panic, "an earlier run's panic\n")
        try fixture.install("exit 1")
        #expect(await results(of: fixture.play()) == [.exited(.status(1), panic: nil)])
        #expect(fixture.text(fixture.panic) == "an earlier run's panic\n")
    }

    /// A `panic.txt` the game writes over that leftover once the launch has begun is its own.
    @Test func aPanicWrittenOverALeftoverThatCantBeMovedIsShown() async throws {
        let fixture = try GameFixture()
        try fixture.write(fixture.logs, "not a folder\n")
        try fixture.write(fixture.panic, "an earlier run's panic\n")
        try fixture.install(
            """
            echo 'this run' > panic.txt
            exit 1
            """)
        #expect(
            await results(of: fixture.play()) == [.exited(.status(1), panic: GamePanic("this run\n"))])
    }

    /// A link at `panic.txt` isn't followed, so what it points to is never read or shown.
    @Test func aPanicThatsALinkIsntFollowed() async throws {
        let fixture = try GameFixture()
        let elsewhere = fixture.root + "/not a panic.txt"
        try fixture.write(elsewhere, "someone else's file\n")
        try fixture.install(
            """
            ln -s \(shellWord(elsewhere)) panic.txt
            exit 1
            """)
        #expect(await results(of: fixture.play()) == [.exited(.status(1), panic: nil)])
    }

    /// A FIFO at `panic.txt` that nothing writes to gives no panic, rather than a read that waits
    /// for a writer and holds back the launch's result. Foundation's `Data(contentsOf:)` already
    /// refused a FIFO on this Mac, so this guards the `O_NONBLOCK` open that replaced it.
    @Test func aPanicThatsAFIFOGivesNoPanicAndTheResultStillComes() async throws {
        let fixture = try GameFixture()
        try fixture.install(
            """
            mkfifo panic.txt
            exit 1
            """)
        #expect(await results(of: fixture.play()) == [.exited(.status(1), panic: nil)])
    }

    /// Only the first `GamePanic.limit` bytes are read, and the panic says when there were more.
    @Test(arguments: [GamePanic.limit, GamePanic.limit + 1])
    func aPanicIsReadUpToTheLimitAndSaysWhenItWasCut(size: Int) async throws {
        let fixture = try GameFixture()
        let written = fixture.root + "/a long panic.txt"
        try fixture.write(written, String(repeating: "x", count: size))
        try fixture.install(
            """
            cp \(shellWord(written)) panic.txt
            exit 1
            """)
        let all = await results(of: fixture.play())
        guard all.count == 1, case .exited(.status(1), let panic?) = all[0] else {
            Issue.record("expected one exit 1 with a panic, got \(all.count) results")
            return
        }
        #expect(panic.text.utf8.count == GamePanic.limit)
        #expect(Set(panic.text) == ["x"])
        #expect(panic.cut == (size > GamePanic.limit))
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
        #expect(!FileManager.default.fileExists(atPath: fixture.record))
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

    /// A clock that ran ahead left ten game logs that sort after this launch's. This launch's own
    /// log stays all the same, since the game writes to it.
    @Test func theGamesOwnLogStaysWhenLogsFromAClockThatRanAheadSortAfterIt() async throws {
        let fixture = try GameFixture()
        let ahead = (0..<10).map { String(format: "game-2030-01-01T00-00-%02d.000Z.log", $0) }
        for name in ahead {
            try fixture.write(fixture.logs + "/" + name, "")
        }
        try fixture.install("echo 'this launch'")
        _ = await results(of: fixture.play())
        #expect(fixture.logNames == ([GameFixture.logName] + ahead.suffix(9)).sorted())
        #expect(fixture.lines(fixture.logPath) == ["this launch"])
    }

    /// A file where the logs folder should be means there's no log, and the game runs anyway.
    @Test func aLogThatCantBeOpenedLeavesTheGameToRunWithoutOne() async throws {
        let fixture = try GameFixture()
        try fixture.write(fixture.logs, "not a folder\n")
        try fixture.install("echo 'nowhere to go'")
        #expect(await results(of: fixture.play()) == [.exited(.status(0), panic: nil)])
        #expect(fixture.lines(fixture.argumentsFile) == [fixture.disc])
        #expect(fixture.text(fixture.logs) == "not a folder\n")
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
