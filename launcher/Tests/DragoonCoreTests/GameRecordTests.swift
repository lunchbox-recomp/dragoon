@testable import DragoonCore
import Foundation
import Testing

/// `<data>/game.pid` with real processes. The game is a link to /bin/sleep, so its process runs
/// the installed game's executable once links are resolved, and its one argument is how many
/// seconds it sleeps.
@Suite(.timeLimit(.minutes(1))) struct GameRecordTests {
    /// A launcher opened while a game from an earlier launcher runs finds that game in the record
    /// and keeps Library's buttons off. They come back on once the game exits.
    @Test func aLauncherOpenedWhileTheGameRunsWaitsForItToExit() async throws {
        let fixture = try GameFixture()
        try fixture.installSleep()
        let session = fixture.play(disc: "1")
        let watching = ContinuousClock.now
        let pid = try #require(fixture.runningGame())
        var run = launched(earlierGame: pid)
        #expect(run.effects == [.watchEarlierGame(pid: pid)])
        #expect(!run.state.libraryIsIdle)
        await LiveProcess.waitForEnd(of: pid)
        // The game sleeps for a second, which a wait that returned at once wouldn't have taken.
        #expect(ContinuousClock.now - watching > .milliseconds(500))
        #expect(run.send(.earlierGameEnded) == [.deleteOldBuilds])
        #expect(run.state.libraryIsIdle)
        #expect(await results(of: session) == [.exited(.status(0), panic: nil)])
        #expect(!FileManager.default.fileExists(atPath: fixture.record))
    }

    /// The ways a record can fail to name the game that runs now.
    enum Stale: String, CaseIterable {
        case garbled, pidGone, otherStartTime, otherExecutable
    }

    @Test(arguments: Stale.allCases)
    func aStaleRecordIsRemovedAndIgnored(_ stale: Stale) async throws {
        let fixture = try GameFixture()
        try fixture.installSleep()
        let session = fixture.play(disc: "20")
        let record = try JSONDecoder().decode(
            GameRecord.self, from: Data(contentsOf: URL(fileURLWithPath: fixture.record)))
        #expect(fixture.runningGame() == record.pid)
        switch stale {
        case .garbled:
            try fixture.write(fixture.record, "not a record\n")
        case .pidGone:
            try write(GameRecord(pid: try exitedPid(), started: record.started), to: fixture)
        case .otherStartTime:
            try write(GameRecord(pid: record.pid, started: record.started + 1), to: fixture)
        case .otherExecutable:
            let started = try #require(LiveProcess.startTime(of: getpid()))
            try write(GameRecord(pid: getpid(), started: started), to: fixture)
        }
        #expect(fixture.runningGame() == nil)
        #expect(!FileManager.default.fileExists(atPath: fixture.record))
        kill(record.pid, SIGKILL)
        #expect(await results(of: session) == [.exited(.signal(SIGKILL), panic: nil)])
    }

    /// A game that ends between the record's check and the watch is still seen to end.
    @Test func aProcessThatsGoneAlreadyIsntWaitedFor() async throws {
        await LiveProcess.waitForEnd(of: try exitedPid())
    }

    private func write(_ record: GameRecord, to fixture: GameFixture) throws {
        try encodeJSON(record).write(to: URL(fileURLWithPath: fixture.record))
    }

    /// The pid of a process that has exited and been collected.
    private func exitedPid() throws -> pid_t {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/true")
        try process.run()
        process.waitUntilExit()
        return process.processIdentifier
    }
}
