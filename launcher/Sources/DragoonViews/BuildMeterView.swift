import DragoonCore
import SwiftUI

/// A running build's bar, what its step is doing, the time it has taken and the time left,
/// and, once it's done, the bar become Play. The bar moves only on the recipe's events. The
/// clock ticks once a second, and it and the shimmer stop as `Motion.buildPaused` says.
struct BuildMeterView: View {
    /// The bar and Play share this height, so the page doesn't move as one becomes the other.
    static let rowHeight: CGFloat = 64

    let progress: BuildProgress
    let finished: Bool
    let colors: HeroColors
    let canPlay: Bool
    let send: Send
    @Environment(\.windowIsActive) private var windowIsActive
    @Environment(\.windowIsVisible) private var windowIsVisible
    @Namespace private var morph

    private var paused: (shimmer: Bool, clock: Bool) {
        Motion.buildPaused(windowIsActive: windowIsActive, windowIsVisible: windowIsVisible)
    }

    var body: some View {
        ReduceMotionReader { reduceMotion in
            VStack(alignment: .leading, spacing: 4) {
                Text(headline).font(.title3.weight(.semibold))
                ZStack(alignment: .leading) {
                    if finished {
                        play
                            .matchedGeometryEffect(id: morphID(reduceMotion), in: morph)
                            .transition(.opacity)
                    } else {
                        SegmentedBar(
                            fraction: progress.fraction, colors: colors, skipped: progress.skipped,
                            shimmering: progress.segment.flatMap { $0.counts ? nil : $0 },
                            shimmerPaused: paused.shimmer, reduceMotion: reduceMotion
                        )
                        .matchedGeometryEffect(id: morphID(reduceMotion), in: morph)
                        .transition(.opacity)
                    }
                }
                .frame(height: Self.rowHeight, alignment: .leading)
                .animation(
                    reduceMotion ? .easeInOut(duration: 0.35) : .spring(duration: 0.6, bounce: 0.25),
                    value: finished)
                details(reduceMotion)
            }
        }
    }

    /// The shortest gap between counts that rolls the new one in.
    static let rollGap: TimeInterval = 0.5

    /// Whether the count's last change came at least `rollGap` after the one before, so it
    /// rolls. Rolling make's files, several a second, kept SwiftUI drawing all through the
    /// compile, at 7% of a core, so a fast count just changes. The warm-up's frames come about
    /// every 0.25 s, so its share just changes too.
    static func rollsCount(_ samples: [BuildSample]) -> Bool {
        guard samples.count >= 2 else { return true }
        let last = samples[samples.count - 1], before = samples[samples.count - 2]
        return last.time.timeIntervalSince(before.time) >= rollGap
    }

    /// One id for the bar and Play, so the bar morphs into Play, and another for each under
    /// Reduce Motion, so one fades into the other.
    private func morphID(_ reduceMotion: Bool) -> String {
        reduceMotion ? (finished ? "play" : "bar") : "bar"
    }

    private var headline: String {
        if finished { return Strings.buildFinished }
        return progress.step.map(Strings.running) ?? Strings.buildStarting
    }

    private var play: some View {
        Button {
            send(.playPressed)
        } label: {
            HStack(spacing: 12) {
                Image(systemName: "play.fill")
                Text(Strings.play)
            }
        }
        .buttonStyle(PlayButtonStyle(colors: colors))
        .keyboardShortcut(.defaultAction)
        .disabled(!canPlay)
    }

    private func details(_ reduceMotion: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            if finished {
                Text(Strings.buildTook(progress.elapsed(at: Date())))
            } else if let step = progress.step, progress.total > 0 {
                let count = Strings.count(
                    step: step, done: progress.done, total: progress.total,
                    frames: progress.frames)
                Text(count)
                    .contentTransition(
                        reduceMotion ? .opacity : .numericText(value: Double(progress.work.done)))
                    .animation(
                        Self.rollsCount(progress.samples) ? .snappy(duration: 0.25) : nil,
                        value: count)
            }
            Spacer(minLength: 0)
            if !finished {
                ElapsedClock(progress: progress, paused: paused.clock)
            }
        }
        .font(.body.monospacedDigit())
        .foregroundStyle(.secondary)
    }
}

/// The time the build has taken, and the time left once there's an estimate. Live, it ticks
/// on each whole second from the build's start, at most once a second.
private struct ElapsedClock: View {
    let progress: BuildProgress
    let paused: Bool
    @Environment(\.animationClock) private var clock

    var body: some View {
        switch clock {
        case .fixed(let date):
            line(at: date)
        case .live:
            if paused || progress.started == nil {
                line(at: Date())
            } else {
                TimelineView(.periodic(from: progress.started ?? Date(), by: 1)) { context in
                    line(at: context.date)
                }
            }
        }
    }

    private func line(at date: Date) -> some View {
        Text(Strings.buildTime(
            elapsed: progress.elapsed(at: date), left: progress.remaining))
    }
}
