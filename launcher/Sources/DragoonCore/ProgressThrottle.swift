import Foundation

/// Holds the recipe's progress events to one every `interval` seconds, so the build page
/// redraws at most that often however fast make prints. A held event keeps the moment it
/// came, and a newer one replaces it. Steps, `done` and errors go at once, after any progress
/// held back.
public struct ProgressThrottle: Sendable {
    /// DuckStation redraws its progress at most this often (`gpu_hw.cpp:1145`).
    public static let interval: TimeInterval = 0.1

    public struct Timed: Equatable, Sendable {
        public var event: BuildEvent
        public var time: Date

        public init(event: BuildEvent, time: Date) {
            self.event = event
            self.time = time
        }
    }

    private var lastSent: Date?
    private var held: Timed?

    public init() {}

    /// What to send now for `event`, which came at `time`.
    public mutating func offer(_ event: BuildEvent, at time: Date) -> [Timed] {
        let timed = Timed(event: event, time: time)
        if case .progress = event, let lastSent,
            time.timeIntervalSince(lastSent) < Self.interval
        {
            held = timed
            return []
        }
        defer {
            held = nil
            lastSent = time
        }
        guard case .progress = event else { return [held, timed].compactMap { $0 } }
        return [timed]
    }

    /// When the held event may go, or nil when none is held.
    public var due: Date? {
        guard held != nil else { return nil }
        return lastSent?.addingTimeInterval(Self.interval)
    }

    /// The held event, once it's due at `time`.
    public mutating func flush(at time: Date) -> Timed? {
        guard let held, let due, time >= due else { return nil }
        self.held = nil
        lastSent = time
        return held
    }
}
