import Foundation

/// The recipe's steps as the build bar's segments, each as wide as the seconds it took on the
/// Mac the build was measured on, the first build on an M4 Max in `tools/README.md:684`. That
/// build took 95.2 s and timed every step but the swap, so the swap is the 0.2 s left over.
/// Package and swap together are a sliver at the end.
public enum BuildSegment: String, CaseIterable, Comparable, Sendable {
    case recompile, compile, warmup, package, swap

    public var referenceSeconds: TimeInterval {
        switch self {
        case .recompile: return 4.2
        case .compile: return 18.0
        case .warmup: return 72.7
        case .package: return 0.1
        case .swap: return 0.2
        }
    }

    /// Whether the recipe prints progress events for the step: one per file compile starts
    /// and one per warm-up run done.
    public var counts: Bool { self == .compile || self == .warmup }

    public static let referenceTotal = allCases.reduce(0) { $0 + $1.referenceSeconds }

    /// Where the segment starts along the bar, from 0 to 1.
    public var start: Double {
        Self.allCases.prefix { $0 != self }.reduce(0) { $0 + $1.referenceSeconds }
            / Self.referenceTotal
    }

    public var width: Double { referenceSeconds / Self.referenceTotal }

    private var order: Int { Self.allCases.firstIndex(of: self) ?? 0 }

    public static func < (left: BuildSegment, right: BuildSegment) -> Bool {
        left.order < right.order
    }
}

/// When a progress event came and the count it carried.
public struct BuildSample: Equatable, Sendable {
    public var time: Date
    public var done: Int

    public init(time: Date, done: Int) {
        self.time = time
        self.done = done
    }
}

/// A step the build has passed, and how long it took on this Mac. `complete` is false for a
/// step that counts its work and didn't count all of it, such as a warm-up whose cache was
/// current already.
public struct FinishedStep: Equatable, Sendable {
    public var segment: BuildSegment
    public var seconds: TimeInterval
    public var complete: Bool

    public init(segment: BuildSegment, seconds: TimeInterval, complete: Bool) {
        self.segment = segment
        self.seconds = seconds
        self.complete = complete
    }
}

/// The bar's sums. The bar moves only on the recipe's events, so nothing here reads a clock.
public enum BuildMeter {
    /// The most samples the rate is taken over, as DuckStation's loading screen keeps.
    public static let sampleLimit = 30
    /// Samples a step needs before it gives a time left.
    public static let samplesForEstimate = 3

    /// The bar's fill at a step and its count: the segments before it and the share of its own
    /// that's done. Nil for a step the bar doesn't know.
    public static func fraction(step: String, done: Int, total: Int) -> Double? {
        guard let segment = BuildSegment(rawValue: step) else { return nil }
        let share = total > 0 ? Double(min(max(done, 0), total)) / Double(total) : 0
        return segment.start + segment.width * share
    }

    /// Work a second across the samples, from the first to the last, as DuckStation's
    /// `GetLoadingScreenTimeEstimate` sums them. Nil without time or work between them.
    public static func rate(_ samples: [BuildSample]) -> Double? {
        guard let first = samples.first, let last = samples.last else { return nil }
        let seconds = last.time.timeIntervalSince(first.time)
        let work = last.done - first.done
        guard seconds > 0, work > 0 else { return nil }
        return Double(work) / seconds
    }

    /// How much slower than the measured Mac this one is, from the steps that did all their
    /// work. 1 when none has.
    public static func speedRatio(_ finished: [FinishedStep]) -> Double {
        let counted = finished.filter(\.complete)
        let measured = counted.reduce(0) { $0 + $1.segment.referenceSeconds }
        guard measured > 0 else { return 1 }
        return counted.reduce(0) { $0 + $1.seconds } / measured
    }

    /// Seconds left in the build: this step's work at its rate, and every later step's
    /// measured time scaled by `speedRatio`. Nil for a step that counts nothing, and before
    /// the step has `samplesForEstimate` samples.
    public static func remaining(
        segment: BuildSegment, done: Int, total: Int, samples: [BuildSample],
        finished: [FinishedStep]
    ) -> TimeInterval? {
        guard segment.counts, samples.count >= samplesForEstimate, let rate = rate(samples)
        else { return nil }
        let here = Double(max(total - done, 0)) / rate
        let later = BuildSegment.allCases.filter { $0 > segment }
            .reduce(0) { $0 + $1.referenceSeconds }
        return here + later * speedRatio(finished)
    }
}
