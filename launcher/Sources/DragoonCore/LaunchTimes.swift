import Foundation

/// How long the player waited after Play, for the game's window and for its first frame. The
/// launcher's clock gives Play, the kernel gives the game's start, and the ready file's lines
/// count from that start.
public struct LaunchTimes: Equatable, Sendable {
    /// Milliseconds from Play to the first frame the game's window showed, or nil before that
    /// line.
    public var toWindow: Double?
    /// Milliseconds from Play to the game's own first frame, or nil before that line.
    public var toFrame: Double?

    /// `play` and `gameStart` are in microseconds since 1970, as `microseconds` and
    /// `LiveProcess.startTime` give them.
    public init(play: UInt64, gameStart: UInt64, marks: ReadyMarks) {
        let started = (Double(gameStart) - Double(play)) / 1000
        toWindow = marks.window.map { started + Double($0) }
        toFrame = marks.frame.map { started + Double($0) }
    }

    /// The times as one line for the log.
    public var summary: String {
        func ms(_ value: Double?) -> String {
            value.map { String(format: "%.0f ms", $0) } ?? "unknown"
        }
        return "Play to the game's window \(ms(toWindow)), to its first frame \(ms(toFrame))"
    }

    /// `date` in microseconds since 1970.
    public static func microseconds(_ date: Date) -> UInt64 {
        UInt64((date.timeIntervalSince1970 * 1_000_000).rounded())
    }
}
