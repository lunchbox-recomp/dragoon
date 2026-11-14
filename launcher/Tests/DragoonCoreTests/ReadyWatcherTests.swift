@testable import DragoonCore
import Foundation
import Testing

/// Writes `text` at `path` as the engine does: through `path.tmp`, which then replaces it.
private func engineWrite(_ text: String, to path: String) throws {
    try Data(text.utf8).write(to: URL(fileURLWithPath: path + ".tmp"))
    guard rename(path + ".tmp", path) == 0 else { throw POSIXError(.EIO) }
}

/// What the watch gave, in order, until it ended or `seconds` passed.
private func given(
    by stream: AsyncStream<ReadyMarks>, within seconds: Double = 2,
    meanwhile: @escaping @Sendable () async throws -> Void = {}
) async throws -> (marks: [ReadyMarks], ended: Bool) {
    try await withThrowingTaskGroup(of: (marks: [ReadyMarks], ended: Bool)?.self) { group in
        group.addTask {
            var all: [ReadyMarks] = []
            for await marks in stream { all.append(marks) }
            return (all, !Task.isCancelled)
        }
        group.addTask {
            do {
                try await meanwhile()
                try await Task.sleep(for: .seconds(seconds))
            } catch is CancellationError {
                // The watch ended first.
            }
            return nil
        }
        // The first to finish: the watch ending, or the time running out, which cancels it.
        var result: (marks: [ReadyMarks], ended: Bool)?
        for try await finished in group {
            if let finished {
                result = finished
                group.cancelAll()
            } else if result == nil {
                group.cancelAll()
            }
        }
        return result ?? ([], false)
    }
}

/// `ReadyWatcher` on a scratch folder whose path has spaces, as the data folder's does.
@Suite(.timeLimit(.minutes(1))) struct ReadyWatcherTests {
    @Test func linesTheEngineWritesComeInOrderAndTheWatchEndsWithBoth() async throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        let stream = ReadyWatcher.watch(path)
        let (marks, ended) = try await given(by: stream) {
            try await Task.sleep(for: .milliseconds(100))
            try engineWrite("window 412\n", to: path)
            try await Task.sleep(for: .milliseconds(100))
            try engineWrite("window 412\nframe 1093\n", to: path)
        }
        #expect(marks == [ReadyMarks(window: 412), ReadyMarks(window: 412, frame: 1093)])
        #expect(ended)
    }

    /// Lines written before the watch began are read as it begins.
    @Test func aFileThatIsThereAlreadyIsReadAtOnce() async throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        try engineWrite("window 5\nframe 9\n", to: path)
        let (marks, ended) = try await given(by: ReadyWatcher.watch(path))
        #expect(marks == [ReadyMarks(window: 5, frame: 9)])
        #expect(ended)
    }

    /// An engine from before the ready file writes nothing, so the watch gives nothing, whatever
    /// else changes in the folder, until it's stopped.
    @Test func aFileThatNeverAppearsGivesNothing() async throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        let (marks, ended) = try await given(by: ReadyWatcher.watch(path), within: 0.5) {
            try Data("{}".utf8).write(to: URL(fileURLWithPath: scratch.path + "/game.pid"))
            try FileManager.default.removeItem(atPath: scratch.path + "/game.pid")
        }
        #expect(marks.isEmpty)
        #expect(!ended)
    }

    /// The same marks again, or a change elsewhere in the folder, give nothing new.
    @Test func marksThatHaveNotChangedAreNotGivenAgain() async throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        let (marks, ended) = try await given(by: ReadyWatcher.watch(path), within: 0.6) {
            try engineWrite("window 3\n", to: path)
            try await Task.sleep(for: .milliseconds(100))
            try engineWrite("window 3\n", to: path)
            try Data("x".utf8).write(to: URL(fileURLWithPath: scratch.path + "/settings.txt"))
            try await Task.sleep(for: .milliseconds(100))
            // A line still being written counts once it's whole.
            try engineWrite("window 3\nframe 4", to: path)
        }
        #expect(marks == [ReadyMarks(window: 3)])
        #expect(!ended)
    }

    /// The launcher removes the file once the game has ended, which changes nothing.
    @Test func theFileGoingAwayGivesNothing() async throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let path = scratch.path + "/ready.txt"
        let (marks, _) = try await given(by: ReadyWatcher.watch(path), within: 0.5) {
            try engineWrite("window 3\n", to: path)
            try await Task.sleep(for: .milliseconds(100))
            try FileManager.default.removeItem(atPath: path)
        }
        #expect(marks == [ReadyMarks(window: 3)])
    }

    @Test func aFolderThatIsNotThereEndsTheWatchAtOnce() async throws {
        let scratch = try ScratchDirectory("ready")
        defer { scratch.remove() }
        let (marks, ended) = try await given(by: ReadyWatcher.watch(scratch.path + "/gone/ready.txt"))
        #expect(marks.isEmpty)
        #expect(ended)
    }
}
