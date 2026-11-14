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
        // A run every 2 s leaves 10 s, and package and swap take twice their 1 s here.
        #expect(abs(left - (10 + 2)) < 1e-9)
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

    @Test func overAWholeBuildTheBarNeverFallsAndFillsOnlyOnDone() {
        var progress = BuildProgress()
        var last = 0.0
        for (seconds, event) in Self.wholeBuild {
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
