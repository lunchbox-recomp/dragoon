import DragoonCore
import Foundation
import Testing

/// The recipe's events held to one redraw every 0.1 s.
@Suite struct ProgressThrottleTests {
    static func compile(_ done: Int) -> BuildEvent {
        .progress(step: "compile", done: done, total: 135)
    }

    static func timed(_ event: BuildEvent, _ seconds: Double) -> ProgressThrottle.Timed {
        ProgressThrottle.Timed(event: event, time: at(seconds))
    }

    @Test func theFirstProgressGoesAtOnce() {
        var throttle = ProgressThrottle()
        #expect(throttle.offer(Self.compile(1), at: at(1)) == [Self.timed(Self.compile(1), 1)])
        #expect(throttle.due == nil)
    }

    @Test func progressWithinATenthOfASecondWaitsAndOnlyTheNewestIsKept() {
        var throttle = ProgressThrottle()
        _ = throttle.offer(Self.compile(1), at: at(1))
        #expect(throttle.offer(Self.compile(2), at: at(1.02)) == [])
        #expect(throttle.offer(Self.compile(3), at: at(1.05)) == [])
        #expect(throttle.due == at(1).addingTimeInterval(ProgressThrottle.interval))
        #expect(throttle.flush(at: at(1.08)) == nil)
        #expect(throttle.flush(at: at(1.11)) == Self.timed(Self.compile(3), 1.05))
        #expect(throttle.due == nil)
        #expect(throttle.flush(at: at(2)) == nil)
    }

    @Test func progressMoreThanATenthOfASecondLaterGoesAtOnce() {
        var throttle = ProgressThrottle()
        _ = throttle.offer(Self.compile(1), at: at(1))
        #expect(throttle.offer(Self.compile(2), at: at(1.11)) == [Self.timed(Self.compile(2), 1.11)])
    }

    @Test func aStepGoesAtOnceAfterTheProgressHeldBack() {
        var throttle = ProgressThrottle()
        _ = throttle.offer(Self.compile(1), at: at(1))
        _ = throttle.offer(Self.compile(135), at: at(1.01))
        #expect(throttle.offer(.step("warmup"), at: at(1.02)) == [
            Self.timed(Self.compile(135), 1.01), Self.timed(.step("warmup"), 1.02),
        ])
        #expect(throttle.due == nil)
    }

    @Test(arguments: [
        BuildEvent.done(game: "/x/game/current/Dragoon.app"),
        .error(step: "compile", message: "make failed", log: "/x.log"),
    ])
    func doneAndErrorGoAtOnce(_ event: BuildEvent) {
        var throttle = ProgressThrottle()
        _ = throttle.offer(.step("swap"), at: at(1))
        #expect(throttle.offer(event, at: at(1.01)) == [Self.timed(event, 1.01)])
    }

    @Test(arguments: [
        BuildEvent.done(game: "/x/game/current/Dragoon.app"),
        .error(step: "compile", message: "make failed", log: "/x.log"),
    ])
    func doneAndErrorGoAfterTheProgressHeldBack(_ event: BuildEvent) {
        var throttle = ProgressThrottle()
        _ = throttle.offer(Self.compile(1), at: at(1))
        _ = throttle.offer(Self.compile(2), at: at(1.01))
        #expect(throttle.offer(event, at: at(1.02)) == [
            Self.timed(Self.compile(2), 1.01), Self.timed(event, 1.02),
        ])
        #expect(throttle.due == nil)
    }
}
