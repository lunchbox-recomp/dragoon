import Foundation

/// Watches the game's ready file with a `DispatchSource` on the folder it's in. The engine writes
/// the file through `.tmp` and renames that over it, so the file itself is replaced at each line
/// and the folder is what changes (gcn-recomp `runtime/ready_file.h`). Nothing runs between
/// changes, so a watch that waits on an engine that never writes the file costs nothing.
public enum ReadyWatcher {
    /// The file's marks as they change. The first read is as the watch begins, so lines written
    /// before then aren't missed. The stream ends once both lines are in, at once when the folder
    /// can't be watched, and when the task reading it is canceled.
    public static func watch(_ path: String) -> AsyncStream<ReadyMarks> {
        let (stream, continuation) = AsyncStream<ReadyMarks>.makeStream()
        let folder = (path as NSString).deletingLastPathComponent
        let descriptor = open(folder, O_EVTONLY | O_CLOEXEC)
        guard descriptor >= 0 else {
            continuation.finish()
            return stream
        }
        let queue = DispatchQueue(label: "Dragoon ready file")
        let source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: descriptor, eventMask: .write, queue: queue)
        let seen = SeenMarks()
        let check = { @Sendable in
            // No file yet, or one just removed, says nothing new.
            guard let marks = ReadyFile.read(at: path), marks != seen.last else { return }
            seen.last = marks
            continuation.yield(marks)
            if marks.isComplete { source.cancel() }
        }
        source.setEventHandler(handler: check)
        source.setCancelHandler {
            close(descriptor)
            continuation.finish()
        }
        continuation.onTermination = { _ in source.cancel() }
        source.activate()
        queue.async(execute: check)
        return stream
    }
}

/// The marks a watch last gave, touched only on its queue.
private final class SeenMarks: @unchecked Sendable {
    var last = ReadyMarks()
}
