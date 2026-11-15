import DragoonCore
import Foundation
import Testing

/// `BuildProgress` from the recipe's events and the moments they came.
@Suite struct BuildProgressTests {
    /// The progress after each of `events`, the seconds each came at.
    static func replay(_ events: [(Double, BuildEvent)]) -> BuildProgress {
        var progress = BuildProgress()
        for (seconds, event) in events { progress.note(event, at: at(seconds)) }
        return progress
    }

    @Test func nothingHasHappenedBeforeTheFirstEvent() {
        let progress = BuildProgress()
        #expect(progress.step == nil)
        #expect(progress.fraction == 0)
        #expect(progress.remaining == nil)
        #expect(progress.elapsed(at: at(50)) == 0)
        #expect(!progress.isDone)
    }

    @Test func aStepStartsItsSegmentAndTheClock() {
        let progress = Self.replay([(0, .step("recompile")), (4, .step("compile"))])
        #expect(progress.step == "compile")
        #expect(progress.segment == .compile)
        #expect(progress.fraction == BuildSegment.compile.start)
        #expect(progress.elapsed(at: at(10)) == 10)
        #expect(progress.finishedSteps
            == [FinishedStep(segment: .recompile, seconds: 4, complete: true)])
    }

    @Test func progressFillsTheStepsSegmentByItsCount() {
        let progress = Self.replay([
            (0, .step("compile")), (1, .progress(step: "compile", done: 41, total: 135)),
        ])
        #expect(progress.done == 41)
        #expect(progress.total == 135)
        #expect(progress.fraction == BuildMeter.fraction(step: "compile", done: 41, total: 135))
    }

    @Test func aStalledStepDoesNotMoveTheBar() {
        let progress = Self.replay([
            (0, .step("warmup")), (2, .progress(step: "warmup", done: 1, total: 8)),
        ])
        let later = Self.replay([
            (0, .step("warmup")), (2, .progress(step: "warmup", done: 1, total: 8)),
            (40, .progress(step: "warmup", done: 1, total: 8)),
        ])
        #expect(later.fraction == progress.fraction)
        #expect(later.samples == progress.samples)
    }

    @Test func theBarNeverGoesBack() {
        let progress = Self.replay([
            (0, .step("warmup")), (2, .progress(step: "warmup", done: 5, total: 8)),
            (3, .progress(step: "warmup", done: 2, total: 8)), (4, .step("compile")),
        ])
        #expect(progress.fraction
            == BuildMeter.fraction(step: "warmup", done: 5, total: 8))
    }

    @Test func aStepTheBarDoesNotKnowHoldsIt() {
        let progress = Self.replay([
            (0, .step("compile")), (1, .progress(step: "compile", done: 10, total: 20)),
            (2, .step("sign")),
        ])
        #expect(progress.step == "sign")
        #expect(progress.segment == nil)
        #expect(progress.fraction == BuildMeter.fraction(step: "compile", done: 10, total: 20))
    }

    @Test func onlyDoneFillsTheBar() {
        let swapping = Self.replay([(0, .step("package")), (1, .step("swap"))])
        #expect(swapping.fraction < 1)
        var done = swapping
        done.note(.done(game: "/x/game/current/Dragoon.app"), at: at(2))
        #expect(done.fraction == 1)
        #expect(done.isDone)
        #expect(done.remaining == nil)
    }

    @Test func theClockStopsWhenTheBuildIsDone() {
        let progress = Self.replay([
            (0, .step("recompile")), (96, .done(game: "/x/game/current/Dragoon.app")),
        ])
        #expect(progress.elapsed(at: at(500)) == 96)
    }

    @Test func anErrorChangesNothing() {
        let before = Self.replay([(0, .step("compile"))])
        var after = before
        after.note(.error(step: "compile", message: "make failed", log: "/x.log"), at: at(3))
        #expect(after == before)
    }

    @Test func eachCountIsASampleAndARepeatIsNot() {
        let progress = Self.replay([
            (0, .step("compile")), (1, .progress(step: "compile", done: 1, total: 135)),
            (2, .progress(step: "compile", done: 1, total: 135)),
            (3, .progress(step: "compile", done: 2, total: 135)),
        ])
        #expect(progress.samples
            == [BuildSample(time: at(1), done: 1), BuildSample(time: at(3), done: 2)])
    }

    @Test func aNewTotalOrACountThatFallsStartsTheSamplesAgain() {
        let newTotal = Self.replay([
            (0, .step("compile")), (1, .progress(step: "compile", done: 1, total: 135)),
            (2, .progress(step: "compile", done: 2, total: 136)),
        ])
        #expect(newTotal.samples == [BuildSample(time: at(2), done: 2)])
        let fell = Self.replay([
            (0, .step("compile")), (1, .progress(step: "compile", done: 5, total: 135)),
            (2, .progress(step: "compile", done: 3, total: 135)),
        ])
        #expect(fell.samples == [BuildSample(time: at(2), done: 3)])
    }

    @Test func aNewStepStartsTheSamplesAgain() {
        let progress = Self.replay([
            (0, .step("compile")), (1, .progress(step: "compile", done: 135, total: 135)),
            (2, .step("warmup")),
        ])
        #expect(progress.samples == [])
        #expect(progress.done == 0)
        #expect(progress.total == 0)
    }

    @Test func atMostThirtySamplesAreKept() {
        var events: [(Double, BuildEvent)] = [(0, .step("compile"))]
        events += (1...40).map { (Double($0), .progress(step: "compile", done: $0, total: 135)) }
        let progress = Self.replay(events)
        #expect(progress.samples.count == BuildMeter.sampleLimit)
        #expect(progress.samples.first == BuildSample(time: at(11), done: 11))
    }

    @Test func aProgressEventForAnotherStepStartsThatStep() {
        let progress = Self.replay([
            (0, .step("recompile")), (3, .progress(step: "compile", done: 1, total: 135)),
        ])
        #expect(progress.step == "compile")
        #expect(progress.finishedSteps
            == [FinishedStep(segment: .recompile, seconds: 3, complete: true)])
    }

    @Test func aCountingStepLeftShortIsNotComplete() {
        // The warm-up's stamp was current, so it ran no passes.
        let progress = Self.replay([
            (0, .step("compile")), (1, .progress(step: "compile", done: 135, total: 135)),
            (9, .step("warmup")), (9.5, .step("package")),
        ])
        #expect(progress.finishedSteps == [
            FinishedStep(segment: .compile, seconds: 9, complete: true),
            FinishedStep(segment: .warmup, seconds: 0.5, complete: false),
        ])
    }

    @Test func theTimeLeftComesAfterThreeRunsAndUsesThisMacsRatio() throws {
        var events: [(Double, BuildEvent)] = [
            (0, .step("recompile")), (8.4, .step("compile")),
            (8.5, .progress(step: "compile", done: 135, total: 135)), (44.4, .step("warmup")),
            (60, .progress(step: "warmup", done: 1, total: 8)),
            (62, .progress(step: "warmup", done: 2, total: 8)),
        ]
        #expect(Self.replay(events).remaining == nil)
        events.append((64, .progress(step: "warmup", done: 3, total: 8)))
        let left = try #require(Self.replay(events).remaining)
        // A run every 2 s leaves 10 s, and package and swap take twice their 0.3 s here.
        #expect(abs(left - (10 + 0.6)) < 1e-9)
    }

    /// The compile, 5 files a second, as the time left counts it with and without the warm-up.
    static func compiling(plan: [(Double, BuildEvent)]) -> BuildProgress {
        replay(plan + [(0, .step("recompile")), (4.2, .step("compile"))]
            + (1...3).map { (4.2 + Double($0) * 0.2, .progress(step: "compile", done: $0, total: 135)) })
    }

    @Test func aPlanWithoutTheWarmUpLeavesItOutOfTheTimeLeft() throws {
        let skipping = Self.compiling(plan: [(0, .plan(warmup: false))])
        #expect(!skipping.warmupPlays)
        let left = try #require(skipping.remaining)
        // 132 files at 5 a second, then package and swap at this Mac's ratio of 1.
        #expect(abs(left - (132.0 / 5 + 0.1 + 0.2)) < 1e-9)
    }

    @Test(arguments: [[(0.0, BuildEvent.plan(warmup: true))], []])
    func aPlanWithTheWarmUpOrNoneCountsIt(plan: [(Double, BuildEvent)]) throws {
        let playing = Self.compiling(plan: plan)
        #expect(playing.warmupPlays)
        let left = try #require(playing.remaining)
        #expect(abs(left - (132.0 / 5 + 72.7 + 0.1 + 0.2)) < 1e-9)
    }

    /// The compile at `done` of 135 files, 5 a second, after `plan`.
    static func compiled(_ done: Int, plan: [(Double, BuildEvent)]) -> BuildProgress {
        replay(plan + [(0, .step("recompile")), (4.2, .step("compile"))]
            + (1...done).map { (4.2 + Double($0) * 0.2, .progress(step: "compile", done: $0, total: 135)) })
    }

    @Test func aPlanWithoutTheWarmUpLeavesItOutOfTheBar() {
        // A rebuild whose stamp is current: 22.5 s of measured steps run, not 95.2 s.
        let skipping = Self.compiled(100, plan: [(0, .plan(warmup: false))])
        #expect(skipping.skipped == [.warmup])
        #expect(abs(skipping.fraction - (4.2 + 18.0 * 100 / 135) / 22.5) < 1e-9)
        let compiled = Self.compiled(135, plan: [(0, .plan(warmup: false))])
        #expect(abs(compiled.fraction - 22.2 / 22.5) < 1e-9)
        let playing = Self.compiled(100, plan: [(0, .plan(warmup: true))])
        #expect(playing.skipped == [])
        #expect(abs(playing.fraction - (4.2 + 18.0 * 100 / 135) / 95.2) < 1e-9)
    }

    /// The recipe prints one plan, before any step (`launcher_build.py`'s `build_game`), so a
    /// plan after a step is only an event out of order, and one is all this tests.
    @Test func aLatePlanWithoutTheWarmUpMovesTheBarForward() {
        var progress = Self.compiled(100, plan: [])
        let before = progress.fraction
        progress.note(.plan(warmup: false), at: at(30))
        #expect(progress.fraction > before)
        #expect(abs(progress.fraction - (4.2 + 18.0 * 100 / 135) / 22.5) < 1e-9)
    }

    @Test func aPlanMovesNeitherTheBarNorTheClock() {
        let progress = Self.replay([(3, .plan(warmup: false))])
        #expect(progress.step == nil)
        #expect(progress.started == nil)
        #expect(progress.fraction == 0)
    }

    /// A build as the recipe prints it, 135 files and 8 warm-up runs that finish in clumps.
    static let wholeBuild: [(Double, BuildEvent)] = {
        var events: [(Double, BuildEvent)] = [(0, .step("recompile")), (4.3, .step("compile"))]
        events += (1...135).map { (4.3 + Double($0) * 0.12, .progress(step: "compile", done: $0, total: 135)) }
        events.append((23, .step("warmup")))
        let runs: [Double] = [61, 61.2, 61.3, 62, 62.4, 80, 83, 95]
        events += runs.enumerated().map { ($0.element, .progress(step: "warmup", done: $0.offset + 1, total: 8)) }
        events += [(95.6, .step("package")), (96.2, .step("swap")),
                   (96.5, .done(game: "/x/game/current/Dragoon.app"))]
        return events
    }()

    /// A warm-up event with `runs` of 8 ended and `frames` of 139,760 played.
    static func warming(_ runs: Int, frames: Int) -> BuildEvent {
        .progress(
            step: "warmup", done: runs, total: 8, frames: FrameCount(done: frames, total: 139_760))
    }

    @Test func framesFillTheWarmUpsSegmentAndTheCountStaysItsRuns() {
        let progress = Self.replay([(0, .step("warmup")), (30, Self.warming(0, frames: 69_880))])
        #expect(progress.done == 0)
        #expect(progress.total == 8)
        #expect(progress.frames == FrameCount(done: 69_880, total: 139_760))
        #expect(progress.fraction
            == BuildMeter.fraction(step: "warmup", done: 69_880, total: 139_760))
        #expect(progress.fraction > BuildSegment.warmup.start)
    }

    @Test func withoutFramesTheRunsFillIt() {
        let progress = Self.replay([
            (0, .step("warmup")), (30, .progress(step: "warmup", done: 2, total: 8)),
        ])
        #expect(progress.frames == nil)
        #expect(progress.fraction == BuildMeter.fraction(step: "warmup", done: 2, total: 8))
        #expect(progress.samples == [BuildSample(time: at(30), done: 2)])
    }

    @Test func eachFrameCountIsASampleAndTheFirstStartsThemAgain() {
        let progress = Self.replay([
            (0, .step("warmup")), (1, .progress(step: "warmup", done: 1, total: 8)),
            (2, Self.warming(1, frames: 1_900)), (3, Self.warming(1, frames: 1_900)),
            (4, Self.warming(2, frames: 3_800)),
        ])
        #expect(progress.samples
            == [BuildSample(time: at(2), done: 1_900), BuildSample(time: at(4), done: 3_800)])
    }

    @Test func aRunWithoutFramesAfterThemKeepsTheFramesAndTheFill() {
        let before = Self.replay([(0, .step("warmup")), (2, Self.warming(0, frames: 50_000))])
        var after = before
        after.note(.progress(step: "warmup", done: 1, total: 8), at: at(3))
        #expect(after.frames == before.frames)
        #expect(after.fraction == before.fraction)
        #expect(after.samples == before.samples)
        #expect(after.done == 1)
    }

    @Test func aNewStepDropsTheFrames() {
        let progress = Self.replay([
            (0, .step("warmup")), (2, Self.warming(8, frames: 139_760)), (3, .step("package")),
        ])
        #expect(progress.frames == nil)
        #expect(progress.finishedSteps.last
            == FinishedStep(segment: .warmup, seconds: 3, complete: true))
    }

    @Test func theTimeLeftComesFromTheFramesRate() throws {
        var events: [(Double, BuildEvent)] = [
            (0, .step("recompile")), (4.2, .step("compile")),
            (4.3, .progress(step: "compile", done: 135, total: 135)), (22.2, .step("warmup")),
            (30, Self.warming(0, frames: 15_200)), (31, Self.warming(0, frames: 17_100)),
        ]
        #expect(Self.replay(events).remaining == nil)
        events.append((32, Self.warming(0, frames: 19_000)))
        let left = try #require(Self.replay(events).remaining)
        // 1,900 frames a second leave 120,760, and package and swap take their 0.3 s, since
        // this Mac matched the measured one's 22.2 s.
        #expect(abs(left - (120_760.0 / 1_900 + 0.3)) < 1e-9)
    }

    /// The whole build with the warm-up's frames every 0.25 s, 1,900 a second until the runs
    /// end in clumps from 61 s.
    static let wholeBuildWithFrames: [(Double, BuildEvent)] = {
        var events = Array(Self.wholeBuild.prefix { $0.0 < 23 })
        events.append((23, .step("warmup")))
        let runs: [Double] = [61, 61.2, 61.3, 62, 62.4, 80, 83, 95]
        for tick in 1...288 {
            let seconds = 23 + Double(tick) * 0.25
            let played = min(Int(Double(tick) * 0.25 * 1_900), 139_760)
            events.append((seconds, Self.warming(runs.filter { $0 <= seconds }.count, frames: played)))
        }
        events.append((95, Self.warming(8, frames: 139_760)))
        events += [(95.6, .step("package")), (96.2, .step("swap")),
                   (96.5, .done(game: "/x/game/current/Dragoon.app"))]
        return events
    }()

    @Test(arguments: [BuildProgressTests.wholeBuild, BuildProgressTests.wholeBuildWithFrames])
    func overAWholeBuildTheBarNeverFallsAndFillsOnlyOnDone(build: [(Double, BuildEvent)]) {
        var progress = BuildProgress()
        var last = 0.0
        for (seconds, event) in build {
            progress.note(event, at: at(seconds))
            #expect(progress.fraction >= last)
            if case .done = event {
                #expect(progress.fraction == 1)
            } else {
                #expect(progress.fraction < 1)
            }
            last = progress.fraction
        }
    }
}
