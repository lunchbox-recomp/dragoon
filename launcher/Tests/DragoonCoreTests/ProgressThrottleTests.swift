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

/// `ThrottledSend` on a clock the test sets and a sleep that moves it on at once.
@MainActor
final class ThrottleRig {
    var now = at(0)
    private(set) var waits: [TimeInterval] = []
    private(set) var sent: [ProgressThrottle.Timed] = []
    private lazy var throttled = ThrottledSend(
        now: { [unowned self] in now },
        sleep: { [unowned self] seconds in
            waits.append(seconds)
            now = now.addingTimeInterval(seconds)
        },
        send: { [unowned self] in sent.append($0) })

    func offer(_ event: BuildEvent, at seconds: Double) {
        now = at(seconds)
        throttled.offer(event, at: now)
    }

    /// Lets the main actor run what the throttle queued on it, until `done` or 100 turns.
    func settle(until done: () -> Bool = { false }) async {
        for _ in 0..<100 where !done() { await Task.yield() }
    }
}

@MainActor
@Suite struct ThrottledSendTests {
    static let compile = ProgressThrottleTests.compile
    static let timed = ProgressThrottleTests.timed

    @Test func aHeldProgressGoesOnceItIsDueWithTheMomentItCame() async {
        let rig = ThrottleRig()
        rig.offer(Self.compile(1), at: 1)
        rig.offer(Self.compile(2), at: 1.02)
        rig.offer(Self.compile(3), at: 1.05)
        #expect(rig.sent == [Self.timed(Self.compile(1), 1)])
        await rig.settle { rig.sent.count == 2 }
        #expect(rig.sent == [Self.timed(Self.compile(1), 1), Self.timed(Self.compile(3), 1.05)])
        // It slept from the second event to a tenth of a second after the first, once.
        #expect(rig.waits.count == 1)
        #expect(abs((rig.waits.first ?? 0) - 0.08) < 1e-9)
    }

    @Test func aProgressHeldAfterAFlushGetsAFlushOfItsOwn() async {
        let rig = ThrottleRig()
        rig.offer(Self.compile(1), at: 1)
        rig.offer(Self.compile(2), at: 1.02)
        await rig.settle { rig.sent.count == 2 }
        // The flush went at 1.1, so 1.15 is held until 1.2.
        rig.offer(Self.compile(3), at: 1.15)
        await rig.settle { rig.sent.count == 3 }
        #expect(rig.sent.map(\.event) == [Self.compile(1), Self.compile(2), Self.compile(3)])
        #expect(rig.waits.count == 2)
        #expect(abs((rig.waits.last ?? 0) - 0.05) < 1e-9)
    }

    @Test func doneSendsTheHeldProgressAndTheFlushThenSendsNothing() async {
        let rig = ThrottleRig()
        let done = BuildEvent.done(game: "/x/game/current/Dragoon.app")
        rig.offer(Self.compile(1), at: 1)
        rig.offer(Self.compile(2), at: 1.02)
        rig.offer(done, at: 1.03)
        let expected = [
            Self.timed(Self.compile(1), 1), Self.timed(Self.compile(2), 1.02), Self.timed(done, 1.03),
        ]
        #expect(rig.sent == expected)
        await rig.settle()
        #expect(rig.waits.count == 1)
        #expect(rig.sent == expected)
    }
}
