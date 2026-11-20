@testable import DragoonCore
import Foundation
import Testing

/// Play to the game's window and first frame, from the launcher's clock at Play, the game's
/// start time and the ready file's milliseconds since that start.
@Suite struct LaunchTimesTests {
    @Test func theFilesTimesCountFromTheGamesStart() {
        let times = LaunchTimes(
            play: 1_800_000_000_000_000, gameStart: 1_800_000_000_046_500,
            marks: ReadyMarks(window: 412, frame: 1093))
        #expect(times.toWindow == 458.5)
        #expect(times.toFrame == 1139.5)
    }

    @Test func aLineNotInYetHasNoTime() {
        let times = LaunchTimes(play: 5_000, gameStart: 7_000, marks: ReadyMarks(window: 10))
        #expect(times.toWindow == 12)
        #expect(times.toFrame == nil)
        #expect(LaunchTimes(play: 5_000, gameStart: 7_000, marks: ReadyMarks()).toWindow == nil)
    }

    @Test func theLogLineSaysBoth() {
        let times = LaunchTimes(
            play: 0, gameStart: 50_000, marks: ReadyMarks(window: 412, frame: 1093))
        #expect(times.summary == "Play to the game's window 462 ms, to its first frame 1143 ms")
        #expect(LaunchTimes(play: 0, gameStart: 0, marks: ReadyMarks(window: 7)).summary
            == "Play to the game's window 7 ms, to its first frame unknown")
    }

    @Test func aDateIsMicrosecondsSince1970() {
        #expect(LaunchTimes.microseconds(Date(timeIntervalSince1970: 1.25)) == 1_250_000)
    }
}

/// Play to the game's window on a fake game, a shell script that writes the ready file as the
/// engine does, its window line after 300 ms and its frame line 400 ms after that. The flow runs
/// as the app runs it, with the bookmark and the disc check answered at once, and the launch,
/// the watch and the flow's hide are the app's own code. Each run prints its times and none is
/// held to a bar here, since a loaded runner can take many times as long; status.md's hand-off
/// rows are what these lines printed.
///
/// The fake also links its window line's file as `window.txt`, since the launcher removes the
/// ready file when the game ends. A loaded runner can hand the test its watch's window marks only
/// after that, so the line's time is read from the link once the game is over.
@Suite(.timeLimit(.minutes(1))) struct LaunchTimingTests {
    static let fakeGame = """
        sleep 0.3
        printf 'window 300\\n' > "$GCN_READY_FILE.tmp"
        mv "$GCN_READY_FILE.tmp" "$GCN_READY_FILE"
        ln "$GCN_READY_FILE" window.txt
        sleep 0.4
        printf 'window 300\\nframe 700\\n' > "$GCN_READY_FILE.tmp"
        mv "$GCN_READY_FILE.tmp" "$GCN_READY_FILE"
        sleep 0.2
        """

    struct Run {
        /// Play to the game's process starting, by the launcher's clock and the game's start.
        var toStart: Double
        /// From the window line going in, by the file's time, to the flow's hide.
        var toSee: Double
        /// From the game's start to its window line going in, by the file's time. The fake says
        /// 300 ms, and its shell's own start comes on top.
        var toWrite: Double
        var times: LaunchTimes
        /// Play to the flow's hide, by the launcher's clock alone.
        var toHide: Double
    }

    func launch() async throws -> Run {
        let fixture = try GameFixture()
        try fixture.installScript(Self.fakeGame)
        var run = launched()
        let play = LaunchTimes.microseconds(Date())
        run.send(.playPressed)
        run.send(.bookmarkResolved(.found(fixture.disc)))
        let effects = run.send(.discChecked(path: fixture.disc, check: .ok))
        guard case .play(let disc, let launch)? = effects.first else {
            Issue.record("no play effect in \(effects)")
            throw CancellationError()
        }
        var pid: pid_t = 0
        let session = fixture.play(disc: disc) { pid = $0 }
        let gameStart = try #require(LiveProcess.startTime(of: pid))
        var hidden: UInt64?
        var last = ReadyMarks()
        for await marks in ReadyWatcher.watch(fixture.readyFile) {
            if run.send(.gameReady(launch: launch, marks: marks)) == [.hideWindow(timedOut: false)] {
                hidden = LaunchTimes.microseconds(Date())
            }
            last = marks
        }
        _ = await results(of: session)
        let hiddenAt = try #require(hidden)
        let writtenAt = try #require(GamePanic.lastWritten(at: fixture.data + "/window.txt"))
        return Run(
            toStart: (Double(gameStart) - Double(play)) / 1000,
            toSee: (Double(hiddenAt) - Double(writtenAt) / 1000) / 1000,
            toWrite: (Double(writtenAt) / 1000 - Double(gameStart)) / 1000,
            times: LaunchTimes(play: play, gameStart: gameStart, marks: last),
            toHide: (Double(hiddenAt) - Double(play)) / 1000)
    }

    @Test func playToTheGamesWindowOnAFakeGame() async throws {
        var runs: [Run] = []
        for _ in 0..<5 { runs.append(try await launch()) }
        for run in runs {
            print(String(
                format: "launch timing: start %.1f ms, line written %.1f ms after the start, seen %.1f ms after that, %@, hidden %.1f ms after Play",
                run.toStart, run.toWrite, run.toSee, run.times.summary, run.toHide))
        }
    }
}
