import Foundation

/// Where a running build is, from the recipe's events and the moments they came. The bar's
/// fill moves only on an event and never goes back, and it's full only once `done` comes.
public struct BuildProgress: Equatable, Sendable {
    /// The recipe's name for its warm-up step.
    public static let warmupStep = BuildSegment.warmup.rawValue
    /// The recipe's warm-up and the steps it runs after it.
    public static let stepsFromWarmup: Set<String> = [warmupStep, "package", "swap"]

    /// The recipe's step, or nil before its first event.
    public private(set) var step: String?
    /// The step's count, 0 of 0 until its first progress event.
    public private(set) var done = 0
    public private(set) var total = 0
    /// Cancel was pressed and the build hasn't stopped yet.
    public var canceling = false
    /// When the first event came.
    public private(set) var started: Date?
    /// When `done` came.
    public private(set) var ended: Date?
    /// When the step's first event came.
    public private(set) var stepStarted: Date?
    /// The step's counts as they came, the newest `BuildMeter.sampleLimit` of them since its
    /// total last changed or its count last fell.
    public private(set) var samples: [BuildSample] = []
    /// The steps passed, in order.
    public private(set) var finishedSteps: [FinishedStep] = []
    /// The bar's fill, from 0 to 1.
    public private(set) var fraction = 0.0
    /// Whether the warm-up will play its passes, as the recipe's plan says. Without a plan it
    /// counts as playing them.
    public private(set) var warmupPlays = true

    public init(canceling: Bool = false) {
        self.canceling = canceling
    }

    /// The step's segment, or nil before the first step and for a step the bar doesn't know.
    public var segment: BuildSegment? { step.flatMap(BuildSegment.init(rawValue:)) }

    public var isDone: Bool { ended != nil }

    /// The segments the plan says won't run, which the bar and the time left leave out.
    public var skipped: Set<BuildSegment> { warmupPlays ? [] : [.warmup] }

    /// Seconds from the first event to `now`, or to `done`.
    public func elapsed(at now: Date) -> TimeInterval {
        guard let started else { return 0 }
        return max((ended ?? now).timeIntervalSince(started), 0)
    }

    /// Seconds left as of the last event, or nil while `BuildMeter.remaining` has none.
    public var remaining: TimeInterval? {
        guard !isDone, let segment else { return nil }
        return BuildMeter.remaining(
            segment: segment, done: done, total: total, samples: samples,
            finished: finishedSteps, skipped: skipped)
    }

    public mutating func note(_ event: BuildEvent, at time: Date) {
        switch event {
        case .plan(let warmup):
            warmupPlays = warmup
        case .step(let name):
            begin(name, at: time)
        case .progress(let name, let newDone, let newTotal):
            if name != step { begin(name, at: time) }
            count(newDone, of: newTotal, at: time)
        case .done:
            if started == nil { started = time }
            finishStep(at: time)
            ended = time
            fraction = 1
            return
        case .error:
            return
        }
        if let step,
            let fill = BuildMeter.fraction(step: step, done: done, total: total, skipped: skipped)
        {
            fraction = max(fraction, fill)
        }
    }

    private mutating func begin(_ name: String, at time: Date) {
        if started == nil { started = time }
        finishStep(at: time)
        step = name
        stepStarted = time
        done = 0
        total = 0
        samples = []
    }

    /// A new total or a count that fell starts the samples again, as DuckStation's
    /// `UpdateLoadingScreenProgress` does, and a count that didn't change adds none.
    private mutating func count(_ count: Int, of newTotal: Int, at time: Date) {
        let sample = BuildSample(time: time, done: count)
        if newTotal != total || count < done {
            samples = [sample]
        } else if count != done {
            samples.append(sample)
            if samples.count > BuildMeter.sampleLimit { samples.removeFirst() }
        }
        done = count
        total = newTotal
    }

    private mutating func finishStep(at time: Date) {
        guard let segment, let stepStarted else { return }
        let complete = !segment.counts || (total > 0 && done >= total)
        finishedSteps.append(FinishedStep(
            segment: segment, seconds: time.timeIntervalSince(stepStarted), complete: complete))
        self.stepStarted = nil
    }
}
