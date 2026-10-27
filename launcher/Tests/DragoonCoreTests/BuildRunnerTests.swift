import DragoonCore
import Foundation
import Testing

/// Each of these runs a shell script as the recipe under the real spawn, in a scratch directory
/// whose name has spaces. The scripts are in the tests that use them.
@Suite struct BuildRunnerTests {
    @Test func eventsArriveInOrderAndTheStreamEndsWhenTheGameIsCurrent() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            echo '{"event": "step", "step": "recompile"}'
            echo '{"event": "step", "step": "compile"}'
            echo '{"event": "progress", "step": "compile", "done": 12, "total": 135}'
            echo '{"event": "progress", "step": "compile", "done": 135, "total": 135}'
            echo '{"event": "step", "step": "swap"}'
            echo '{"event": "done", "game": "/data/game/current/Dragoon.app"}'
            """#)
        let finished = await collect(fixture.runner().run(fixture.request()))
        #expect(
            finished.events == [
                .step("recompile"), .step("compile"),
                .progress(step: "compile", done: 12, total: 135),
                .progress(step: "compile", done: 135, total: 135), .step("swap"),
                .done(game: "/data/game/current/Dragoon.app"),
            ])
        #expect(finished.failure == nil)
    }

    @Test func theRecipeRunsUnderPythonWithBAndSFirstAndEveryArgumentWhole() async throws {
        let fixture = try RecipeFixture()
        try fixture.install("")
        _ = await collect(fixture.runner().run(fixture.request()))
        let source = fixture.bundle + "/Contents/Resources/source"
        let tools = "/Library/Developer/CommandLineTools"
        #expect(
            try lines(of: fixture.argumentsFile) == [
                "-B", "-s", source + "/tools/launcher_build.py",
                "--source", source,
                "--kit", fixture.bundle + "/Contents/Resources/kit",
                "--disc", fixture.root + "/Kirby Air Ride (USA).gcm",
                "--data", fixture.root + "/Library/Application Support/Dragoon",
                "--cache", fixture.root + "/Library/Caches/Dragoon",
                "--make", tools + "/usr/bin/make",
                "--cc", tools + "/usr/bin/clang",
                "--cxx", tools + "/usr/bin/clang++",
                "--python", fixture.python3,
                "--sdk", tools + "/SDKs/MacOSX26.5.sdk",
                "--log", fixture.logs + "/build-2027-01-15T08-00-00.000Z.log",
            ])
    }

    @Test func aRealPythonStartedTheWayTheLauncherDoesLoadsNoUserSitePackages() async throws {
        let fixture = try RecipeFixture()
        try fixture.installPython(
            """
            import json, site, sys

            def step(text):
                print(json.dumps({"event": "step", "step": text}), flush=True)

            step("no_user_site=%d" % sys.flags.no_user_site)
            step("user_site_enabled=%s" % site.ENABLE_USER_SITE)
            step("user_site_on_path=%s" % (site.getusersitepackages() in sys.path))
            """)
        let finished = await collect(fixture.runner().run(try await fixture.requestWithRealPython()))
        #expect(
            finished.events == [
                .step("no_user_site=1"), .step("user_site_enabled=False"),
                .step("user_site_on_path=False"),
            ])
        #expect(finished.failure == nil)
    }

    @Test func theFlagsGoAfterTheLogOnlyWhenAsked() async throws {
        let fixture = try RecipeFixture()
        try fixture.install("")
        _ = await collect(fixture.runner().run(fixture.request(noWarmup: true, keepBuild: true)))
        #expect(try lines(of: fixture.argumentsFile).suffix(2) == ["--no-warmup", "--keep-build"])

        _ = await collect(fixture.runner().run(fixture.request(noWarmup: true)))
        #expect(try lines(of: fixture.argumentsFile).last == "--no-warmup")

        _ = await collect(fixture.runner().run(fixture.request()))
        #expect(try lines(of: fixture.argumentsFile).last == fixture.logPath)
    }

    @Test func theRecipeGetsAFixedEnvironmentAndNothingFromTheLaunchersOwn() async throws {
        let fixture = try RecipeFixture()
        try fixture.install("")
        _ = await collect(fixture.runner().run(fixture.request()))
        var environment: [String: String] = [:]
        for line in try lines(of: fixture.environmentFile) {
            let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
            if parts.count == 2 { environment[parts[0]] = parts[1] }
        }
        // The shell that prints these adds its own.
        for added in ["PWD", "OLDPWD", "SHLVL", "_"] { environment[added] = nil }
        #expect(
            Set(environment.keys) == [
                "PATH", "HOME", "TMPDIR", "LANG", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE",
                "DEVELOPER_DIR",
            ])
        #expect(environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin")
        #expect(environment["PYTHONDONTWRITEBYTECODE"] == "1")
        #expect(environment["PYTHONNOUSERSITE"] == "1")
        #expect(environment["DEVELOPER_DIR"] == "/Library/Developer/CommandLineTools")
    }

    @Test func linesThatAreNotEventsAreLoggedAndNeverTreatedAsErrors() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            echo 'make: warning: clock skew detected'
            echo '{"event": "step", "step": "compile"}'
            echo '{"event": "step"'
            echo '{"something": "else"}'
            echo '{"event": "unheard-of", "step": "x"}'
            echo '{"event": "warning", "step": "swap", "message": "no room", "log": "/l"}'
            echo '{"event": "progress", "step": "compile", "done": "many"}'
            echo ''
            echo 'plain text'
            echo 'a warning on stderr' >&2
            echo '{"event": "done", "game": "/g"}'
            printf 'a last line with no newline'
            """#)
        let finished = await collect(fixture.runner().run(fixture.request()))
        #expect(finished.events == [.step("compile"), .done(game: "/g")])
        #expect(finished.failure == nil)
        // Stdout and stderr are read at once, so the order between them isn't fixed.
        let expected = [
            "[stderr] a warning on stderr",
            "[stdout] a last line with no newline",
            "[stdout] make: warning: clock skew detected",
            "[stdout] plain text",
            "[stdout] {\"event\": \"progress\", \"step\": \"compile\", \"done\": \"many\"}",
            "[stdout] {\"event\": \"step\"",
            "[stdout] {\"event\": \"unheard-of\", \"step\": \"x\"}",
            "[stdout] {\"event\": \"warning\", \"step\": \"swap\", \"message\": \"no room\", \"log\": \"/l\"}",
            "[stdout] {\"something\": \"else\"}",
        ]
        #expect(try lines(of: fixture.logPath).sorted() == expected.sorted())
    }

    @Test func theRecipesOwnLogLinesAreKeptBesideTheLaunchers() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            mkdir -p "${log%/*}"
            echo '== recompile' >> "$log"
            echo 'stdout line'
            echo '== compile' >> "$log"
            """#)
        _ = await collect(fixture.runner().run(fixture.request()))
        // The recipe and the launcher write at once, so the order between them isn't fixed.
        #expect(
            try lines(of: fixture.logPath).sorted()
                == ["== compile", "== recompile", "[stdout] stdout line"])
    }

    // MARK: exit codes

    @Test func exitOneWithAnErrorEventGivesThatFailure() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            echo '{"event": "step", "step": "compile"}'
            echo '{"event": "error", "step": "compile", "message": "make exited 2", "log": "'"$log"'"}'
            exit 1
            """#)
        let finished = await collect(fixture.runner().run(fixture.request()))
        #expect(
            finished.events == [
                .step("compile"),
                .error(step: "compile", message: "make exited 2", log: fixture.logPath),
            ])
        #expect(
            finished.failure
                == .failed(step: "compile", message: "make exited 2", log: fixture.logPath))
    }

    @Test func exitOneWithNoErrorEventStillGivesAFailureThatNamesTheLog() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            echo '{"event": "step", "step": "compile"}'
            exit 1
            """#)
        let finished = await collect(fixture.runner().run(fixture.request()))
        let failure = try #require(finished.failure)
        #expect(
            failure
                == .failed(
                    step: nil, message: "the build stopped without saying why",
                    log: fixture.logPath))
        #expect(failure.message.contains(fixture.logPath))
        #expect(try lines(of: fixture.logPath) == ["[launcher] the build stopped without saying why"])
    }

    @Test func exitThreeMeansABuildIsAlreadyRunningAndWritesNoLog() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            echo '{"event": "error", "step": "lock", "message": "another build holds /c/build.lock", "log": "'"$log"'"}'
            exit 3
            """#)
        let finished = await collect(fixture.runner().run(fixture.request()))
        #expect(finished.failure == .alreadyRunning)
        #expect(finished.failure?.message == "a build is already running")
        // The recipe's own error event names a log that doesn't exist, so the stream leaves it out.
        #expect(finished.events.isEmpty)
        #expect(fixture.logNames.isEmpty)
    }

    @Test func exitTwoIsARefusalThatCarriesTheKitsReasonOrTheRecipesStderr() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            echo '{"event": "error", "step": "kit", "message": "the kit is from another commit", "log": "'"$log"'"}'
            echo "launcher_build.py: the kit is from another commit" >&2
            exit 2
            """#)
        var finished = await collect(fixture.runner().run(fixture.request()))
        #expect(
            finished.failure
                == .refused(message: "the kit is from another commit", log: fixture.logPath))
        #expect(finished.events.isEmpty)

        try fixture.install(
            #"""
            echo "launcher_build.py: --disc /x isn't a file" >&2
            exit 2
            """#)
        finished = await collect(fixture.runner().run(fixture.request()))
        #expect(
            finished.failure
                == .refused(message: "launcher_build.py: --disc /x isn't a file", log: fixture.logPath))
    }

    @Test func anyOtherExitOrASignalIsAFailureNamingTheLog() async throws {
        let fixture = try RecipeFixture()
        try fixture.install("exit 7")
        var finished = await collect(fixture.runner().run(fixture.request()))
        #expect(
            finished.failure
                == .failed(
                    step: nil, message: "the recipe ended with status 7", log: fixture.logPath))

        try fixture.install("kill -9 $$")
        finished = await collect(fixture.runner().run(fixture.request()))
        #expect(
            finished.failure
                == .failed(
                    step: nil, message: "the recipe was stopped by signal 9", log: fixture.logPath))
    }

    @Test func aPythonThatCantBeStartedIsAFailureNotACrash() async throws {
        let fixture = try RecipeFixture()
        var request = fixture.request()
        request.toolchain.python3 = fixture.root + "/no such python3"
        let finished = await collect(fixture.runner().run(request))
        guard case .couldNotStart = finished.failure else {
            Issue.record("expected couldNotStart, got \(String(describing: finished.failure))")
            return
        }
    }

    // MARK: cancelling

    @Test func aHangingRecipeIsCancelledAndLeavesNothingInItsGroup() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(hanging(fixture))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        #expect(try await iterator.next() == .step("compile"))
        let leader = try #require(Processes.pid(inFile: fixture.pidFile))
        pgid = leader
        let helper = try #require(Processes.pid(inFile: fixture.helperFile))
        #expect(Processes.groupExists(leader))
        #expect(getpgid(leader) == leader)

        let cancelled = ContinuousClock.now
        runner.cancel()
        await #expect(throws: BuildFailure.cancelled) {
            while try await iterator.next() != nil {}
        }
        // SIGTERM alone ends it, so the stream is over long before the 10 second grace is.
        #expect(ContinuousClock.now - cancelled < .seconds(5))
        #expect(await Processes.eventually { !Processes.groupExists(leader) })
        #expect(await Processes.eventually { !Processes.exists(helper) })
    }

    @Test func aSecondRunWhileOneIsRunningIsRefusedAndCancelStillStopsTheFirst() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            hanging(fixture, before: "echo started >> \(shellWord(fixture.noteFile))"))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var first = runner.run(fixture.request()).makeAsyncIterator()
        #expect(try await first.next() == .step("compile"))
        let leader = try #require(Processes.pid(inFile: fixture.pidFile))
        pgid = leader

        let second = await collect(runner.run(fixture.request()))
        #expect(second.failure == .alreadyRunning)
        #expect(second.events.isEmpty)
        #expect(try lines(of: fixture.noteFile) == ["started"])
        #expect(Processes.groupExists(leader))

        runner.cancel()
        await #expect(throws: BuildFailure.cancelled) {
            while try await first.next() != nil {}
        }
        #expect(await Processes.eventually { !Processes.groupExists(leader) })
    }

    @Test func aRunStartedAfterTheLastOneEndedIsAccepted() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            #"""
            echo '{"event": "done", "game": "/g"}'
            """#)
        let runner = fixture.runner()
        for _ in 0..<2 {
            let finished = await collect(runner.run(fixture.request()))
            #expect(finished.events == [.done(game: "/g")])
            #expect(finished.failure == nil)
        }
    }

    @Test func aCancelBeforeTheSwapLeavesTheOldGameCurrentAndEndsCancelled() async throws {
        let fixture = try RecipeFixture()
        try fixture.makeGame("old", current: "old")
        try fixture.install(hanging(fixture))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        #expect(try await iterator.next() == .step("compile"))
        pgid = Processes.pid(inFile: fixture.pidFile)
        runner.cancel()
        await #expect(throws: BuildFailure.cancelled) {
            while try await iterator.next() != nil {}
        }
        #expect(try fixture.currentGame() == "old")
        #expect(BuildFailure.cancelled.message == "the build was canceled")
    }

    @Test func aCancelAfterTheSwapEndsWithTheNewGameDoneAndTellsTheLog() async throws {
        let fixture = try RecipeFixture()
        try fixture.makeGame("old", current: "old")
        try fixture.install(hanging(fixture, before: #"""
                    mkdir -p "$data/game/new/Dragoon.app" && ln -sfn new "$data/game/current"
                    """#))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        #expect(try await iterator.next() == .step("compile"))
        pgid = Processes.pid(inFile: fixture.pidFile)
        runner.cancel()
        #expect(try await iterator.next() == .done(game: fixture.data + "/game/current/Dragoon.app"))
        #expect(try await iterator.next() == nil)
        #expect(try fixture.currentGame() == "new")
        #expect(fixture.log().contains("[launcher] the build was canceled after the new game became current"))
    }

    @Test func aCancelAfterTheSwapIsDoneTooWhenNoGameWasCurrentBefore() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(hanging(fixture, before: #"""
                    mkdir -p "$data/game/new/Dragoon.app" && ln -sfn new "$data/game/current"
                    """#))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        #expect(try await iterator.next() == .step("compile"))
        pgid = Processes.pid(inFile: fixture.pidFile)
        runner.cancel()
        #expect(try await iterator.next() == .done(game: fixture.data + "/game/current/Dragoon.app"))
        #expect(try await iterator.next() == nil)
    }

    @Test func aCancelAfterTheRecipeSaidDoneDoesNotSayItAgain() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(hanging(fixture, before: #"""
                    mkdir -p "$data/game/new/Dragoon.app" && ln -sfn new "$data/game/current"
                    echo '{"event": "done", "game": "'"$data"'/game/current/Dragoon.app"}'
                    """#))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        #expect(try await iterator.next() == .done(game: fixture.data + "/game/current/Dragoon.app"))
        #expect(try await iterator.next() == .step("compile"))
        pgid = Processes.pid(inFile: fixture.pidFile)
        runner.cancel()
        #expect(try await iterator.next() == nil)
    }

    @Test func cancelSendsSigtermFirstSoARecipeCanCleanUp() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            hanging(
                fixture,
                before: #"""
                    note=\#(shellWord(fixture.noteFile))
                    trap 'echo got term > "$note"; exit 143' TERM
                    """#))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        _ = try await iterator.next()
        pgid = Processes.pid(inFile: fixture.pidFile)
        runner.cancel()
        await #expect(throws: BuildFailure.cancelled) {
            while try await iterator.next() != nil {}
        }
        #expect(try lines(of: fixture.noteFile) == ["got term"])
    }

    @Test func aRecipeThatIgnoresSigtermIsKilledOnceTheGraceRunsOut() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(hanging(fixture, before: "trap '' TERM"))
        let runner = fixture.runner(killGrace: 1.5)
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        _ = try await iterator.next()
        pgid = Processes.pid(inFile: fixture.pidFile)
        let helper = try #require(Processes.pid(inFile: fixture.helperFile))
        let cancelled = ContinuousClock.now
        runner.cancel()

        // Well before the grace is over it's still there, since SIGTERM did nothing.
        try await Task.sleep(for: .milliseconds(300))
        #expect(Processes.groupExists(pgid!))

        let gone = await Processes.eventually(timeout: 8) { !Processes.groupExists(pgid!) }
        #expect(gone)
        // With no SIGKILL the stream would wait for good, so a failing run ends the group here.
        Processes.killGroup(pgid)
        #expect(ContinuousClock.now - cancelled >= .milliseconds(1400))
        #expect(await Processes.eventually { !Processes.exists(helper) })
        // It's gone, so the stream ends.
        await #expect(throws: BuildFailure.cancelled) {
            while try await iterator.next() != nil {}
        }
    }

    @Test func aSurvivorOfSigtermThatHoldsNoPipeStillGetsTheSigkillBeforeTheStreamEnds() async throws {
        let fixture = try RecipeFixture()
        // The recipe dies of the SIGTERM, and the helper it leaves ignores it and holds no pipe.
        try fixture.install(
            #"""
            echo $$ > \#(shellWord(fixture.pidFile))
            ( trap '' TERM; exec /bin/sleep 30 ) > /dev/null 2>&1 &
            echo $! > \#(shellWord(fixture.helperFile))
            echo '{"event": "step", "step": "compile"}'
            wait
            """#)
        let runner = fixture.runner(killGrace: 1.5)
        var leader: pid_t?
        defer { Processes.killGroup(leader) }

        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        _ = try await iterator.next()
        leader = Processes.pid(inFile: fixture.pidFile)
        let pgid = try #require(leader)
        let helper = try #require(Processes.pid(inFile: fixture.helperFile))
        let cancelled = ContinuousClock.now
        runner.cancel()
        await #expect(throws: BuildFailure.cancelled) {
            while try await iterator.next() != nil {}
        }
        // The stream waited for the SIGKILL, and the group is gone by the time it ends.
        #expect(ContinuousClock.now - cancelled >= .milliseconds(1400))
        #expect(await Processes.eventually(timeout: 2) { !Processes.groupExists(pgid) })
        #expect(await Processes.eventually(timeout: 2) { !Processes.exists(helper) })
    }

    @Test func droppingTheStreamCancelsTheBuild() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(hanging(fixture))
        let runner = fixture.runner()
        var pgid: pid_t?
        defer { Processes.killGroup(pgid) }

        for try await _ in runner.run(fixture.request()) {
            pgid = Processes.pid(inFile: fixture.pidFile)
            break
        }
        let group = try #require(pgid)
        #expect(await Processes.eventually { !Processes.groupExists(group) })
    }

    @Test func cancellingAtOnceNeverLeavesARecipeRunning() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(hanging(fixture))
        let runner = fixture.runner()
        let stream = runner.run(fixture.request())
        runner.cancel()
        let finished = await collect(stream)
        #expect(finished.failure == .cancelled)
        if let pgid = Processes.pid(inFile: fixture.pidFile) {
            #expect(await Processes.eventually { !Processes.groupExists(pgid) })
        }
    }

    @Test func aRecipeThatFinishesTheJobOnSigtermAndExitsZeroHasSucceeded() async throws {
        let fixture = try RecipeFixture()
        try fixture.install(
            hanging(
                fixture,
                before: #"""
                    trap 'echo "{\"event\": \"done\", \"game\": \"/g\"}"; exit 0' TERM
                    """#))
        let runner = fixture.runner()
        var iterator = runner.run(fixture.request()).makeAsyncIterator()
        _ = try await iterator.next()
        runner.cancel()
        #expect(try await iterator.next() == .done(game: "/g"))
        #expect(try await iterator.next() == nil)
    }

    // MARK: logs

    @Test func onlyTheNewestTenLogsStay() async throws {
        let fixture = try RecipeFixture()
        try FileManager.default.createDirectory(
            atPath: fixture.logs, withIntermediateDirectories: true)
        let old = (0..<12).map { String(format: "build-2020-01-01T00-00-%02d.000Z.log", $0) }
        for name in old + ["notes.txt", "build-notes.txt"] {
            FileManager.default.createFile(atPath: fixture.logs + "/" + name, contents: Data())
        }
        try fixture.install(#"echo 'written' >> "$log""#)
        _ = await collect(fixture.runner().run(fixture.request()))
        #expect(
            fixture.logNames
                == old.suffix(9) + [RecipeFixture.logName, "build-notes.txt", "notes.txt"])
    }

    @Test func aBuildThatWritesNoLogDoesNotCostAnOldOne() async throws {
        let fixture = try RecipeFixture()
        try fixture.install("exit 3")
        try FileManager.default.createDirectory(
            atPath: fixture.logs, withIntermediateDirectories: true)
        let old = (0..<10).map { String(format: "build-2020-01-01T00-00-%02d.000Z.log", $0) }
        for name in old {
            FileManager.default.createFile(atPath: fixture.logs + "/" + name, contents: Data())
        }
        _ = await collect(fixture.runner().run(fixture.request()))
        #expect(fixture.logNames == old)
    }

    @Test func aClockSetBackNeverPrunesThisBuildsOwnLog() async throws {
        let fixture = try RecipeFixture()
        try FileManager.default.createDirectory(
            atPath: fixture.logs, withIntermediateDirectories: true)
        let old = (0..<10).map { String(format: "build-2030-01-01T00-00-%02d.000Z.log", $0) }
        for name in old {
            FileManager.default.createFile(atPath: fixture.logs + "/" + name, contents: Data())
        }
        try fixture.install(#"echo 'written' >> "$log""#)
        _ = await collect(fixture.runner().run(fixture.request()))
        #expect(fixture.logNames == [RecipeFixture.logName] + old.suffix(9))
    }

    // MARK: helpers

    /// A recipe that runs `before`, writes its pid and the pid of a helper it starts, says it is on
    /// the compile step and then waits for the helper for good. `before` comes first so a trap in
    /// it is set before the helper starts, which inherits it.
    private func hanging(_ fixture: RecipeFixture, before: String = "") -> String {
        """
        \(before)
        echo $$ > \(shellWord(fixture.pidFile))
        /bin/sleep 30 &
        echo $! > \(shellWord(fixture.helperFile))
        echo '{"event": "step", "step": "compile"}'
        wait
        """
    }

    private func lines(of path: String) throws -> [String] {
        try String(contentsOfFile: path, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
    }
}
