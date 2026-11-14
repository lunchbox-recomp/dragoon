import DragoonCore
import Foundation
import Testing

/// A moment `seconds` into a build, for samples and steps. It counts from the reference date,
/// so the sums the tests check aren't rounded to a large date's precision.
func at(_ seconds: Double) -> Date {
    Date(timeIntervalSinceReferenceDate: seconds)
}

/// The bar's segments, its fill and the time left, as pure sums.
@Suite struct BuildMeterTests {
    @Test func theSegmentsAreWeightedByTheMeasuredStepTimes() {
        #expect(BuildSegment.allCases.map(\.rawValue)
            == ["recompile", "compile", "warmup", "package", "swap"])
        #expect(BuildSegment.recompile.referenceSeconds == 4.2)
        #expect(BuildSegment.compile.referenceSeconds == 18.0)
        #expect(BuildSegment.warmup.referenceSeconds == 72.7)
        #expect(BuildSegment.package.referenceSeconds == 0.1)
        #expect(BuildSegment.swap.referenceSeconds == 0.2)
        // The measured build's whole time, so the swap is what the other steps left.
        #expect(abs(BuildSegment.referenceTotal - 95.2) < 1e-9)
        #expect(BuildSegment.recompile.start == 0)
        #expect(abs(BuildSegment.compile.start - 4.2 / 95.2) < 1e-9)
        #expect(abs(BuildSegment.warmup.start - 22.2 / 95.2) < 1e-9)
        #expect(abs(BuildSegment.warmup.width - 72.7 / 95.2) < 1e-9)
        // Package and swap are a sliver at the end.
        #expect(BuildSegment.package.width + BuildSegment.swap.width < 0.011)
        #expect(abs(BuildSegment.swap.start + BuildSegment.swap.width - 1) < 1e-9)
    }

    @Test func onlyCompileAndWarmupCountTheirWork() {
        #expect(BuildSegment.allCases.filter(\.counts) == [.compile, .warmup])
    }

    @Test func theFillIsTheSegmentsBeforePlusTheShareOfThisOneDone() throws {
        let compile = BuildSegment.compile
        #expect(BuildMeter.fraction(step: "recompile", done: 0, total: 0) == 0)
        #expect(BuildMeter.fraction(step: "compile", done: 0, total: 135) == compile.start)
        let half = try #require(BuildMeter.fraction(step: "compile", done: 135, total: 270))
        #expect(abs(half - (compile.start + compile.width / 2)) < 1e-9)
        let all = try #require(BuildMeter.fraction(step: "compile", done: 135, total: 135))
        #expect(abs(all - BuildSegment.warmup.start) < 1e-9)
        let runs = try #require(BuildMeter.fraction(step: "warmup", done: 3, total: 8))
        #expect(abs(runs - (BuildSegment.warmup.start + BuildSegment.warmup.width * 3 / 8)) < 1e-9)
    }

    @Test func aCountPastItsTotalFillsOnlyItsSegment() throws {
        let fill = try #require(BuildMeter.fraction(step: "warmup", done: 9, total: 8))
        #expect(abs(fill - BuildSegment.package.start) < 1e-9)
    }

    @Test func aStepThatCountsNothingStaysAtItsStart() {
        #expect(BuildMeter.fraction(step: "package", done: 0, total: 0) == BuildSegment.package.start)
        #expect(BuildMeter.fraction(step: "swap", done: 0, total: 0) == BuildSegment.swap.start)
        #expect(BuildSegment.swap.start < 1)
    }

    @Test func aStepTheBarDoesNotKnowHasNoFill() {
        #expect(BuildMeter.fraction(step: "kit", done: 1, total: 2) == nil)
    }

    @Test func theRateIsTheWorkOverTheTimeAcrossEverySample() {
        let samples = [
            BuildSample(time: at(10), done: 1), BuildSample(time: at(11), done: 3),
            BuildSample(time: at(14), done: 9),
        ]
        #expect(BuildMeter.rate(samples) == 2)
    }

    @Test(arguments: [
        [BuildSample(time: at(10), done: 1)],
        [BuildSample(time: at(10), done: 1), BuildSample(time: at(10), done: 4)],
        [BuildSample(time: at(10), done: 4), BuildSample(time: at(12), done: 4)],
    ])
    func noRateWithoutTimeAndWorkBetweenSamples(_ samples: [BuildSample]) {
        #expect(BuildMeter.rate(samples) == nil)
    }

    @Test func theSpeedRatioIsTheFinishedStepsOverTheirMeasuredTimes() {
        let finished = [
            FinishedStep(segment: .recompile, seconds: 8.4, complete: true),
            FinishedStep(segment: .compile, seconds: 36, complete: true),
        ]
        #expect(abs(BuildMeter.speedRatio(finished) - 2) < 1e-9)
    }

    @Test func aStepThatDidNotDoItsWorkIsLeftOutOfTheRatio() {
        // A warm-up whose stamp was current took no time and ran no passes.
        let finished = [
            FinishedStep(segment: .compile, seconds: 9, complete: true),
            FinishedStep(segment: .warmup, seconds: 0.2, complete: false),
        ]
        #expect(abs(BuildMeter.speedRatio(finished) - 0.5) < 1e-9)
    }

    @Test func withNothingFinishedTheRatioIsOne() {
        #expect(BuildMeter.speedRatio([]) == 1)
    }

    @Test func noTimeLeftBeforeThreeSamples() {
        let two = [BuildSample(time: at(5), done: 1), BuildSample(time: at(6), done: 2)]
        #expect(BuildMeter.remaining(
            segment: .compile, done: 2, total: 135, samples: two, finished: []) == nil)
    }

    @Test func theTimeLeftIsThisStepAtItsRatePlusTheRestScaledByThisMac() throws {
        let samples = [
            BuildSample(time: at(5), done: 10), BuildSample(time: at(6), done: 15),
            BuildSample(time: at(7), done: 20),
        ]
        // Recompile took twice its measured time, so the rest will too.
        let finished = [FinishedStep(segment: .recompile, seconds: 8.4, complete: true)]
        let left = try #require(BuildMeter.remaining(
            segment: .compile, done: 20, total: 135, samples: samples, finished: finished))
        let later = (72.7 + 0.1 + 0.2) * 2
        #expect(abs(left - (115.0 / 5 + later)) < 1e-9)
    }

    @Test func aSkippedStepIsLeftOutOfTheTimeLeft() throws {
        let samples = [
            BuildSample(time: at(5), done: 10), BuildSample(time: at(6), done: 15),
            BuildSample(time: at(7), done: 20),
        ]
        let left = try #require(BuildMeter.remaining(
            segment: .compile, done: 20, total: 135, samples: samples, finished: [],
            skipped: [.warmup]))
        #expect(abs(left - (115.0 / 5 + 0.1 + 0.2)) < 1e-9)
    }

    @Test func aStepThatCountsNothingHasNoTimeLeft() {
        let samples = (0..<3).map { BuildSample(time: at(Double($0)), done: $0 + 1) }
        #expect(BuildMeter.remaining(
            segment: .recompile, done: 3, total: 3, samples: samples, finished: []) == nil)
    }
}
