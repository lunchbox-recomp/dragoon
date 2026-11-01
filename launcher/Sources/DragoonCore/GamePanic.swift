import Foundation

/// What the runtime wrote to `panic.txt` before the game stopped.
public struct GamePanic: Equatable, Sendable {
    /// The most of `panic.txt` that's read. The runtime's report of 16 frames and the heaps is a
    /// few KB.
    public static let limit = 64 * 1024

    /// The file's text, or the text of its first `limit` bytes when it's longer.
    public var text: String
    /// Whether the file is longer than `limit` bytes, so `text` is only its start.
    public var cut: Bool

    public init(_ text: String, cut: Bool = false) {
        self.text = text
        self.cut = cut
    }

    /// The `panic.txt` at `path`, or nil when no regular file is there. A link isn't followed,
    /// and a FIFO is opened without waiting for a writer and then left unread.
    static func read(at path: String) -> GamePanic? {
        let descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        guard descriptor >= 0 else { return nil }
        defer { close(descriptor) }
        var info = stat()
        guard fstat(descriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG else { return nil }
        // One byte past the limit tells a longer file from one that's exactly that long.
        var bytes = [UInt8](repeating: 0, count: limit + 1)
        var filled = 0
        while filled < bytes.count {
            let got = bytes.withUnsafeMutableBytes { buffer in
                pread(descriptor, buffer.baseAddress! + filled, buffer.count - filled, off_t(filled))
            }
            if got < 0 && errno == EINTR { continue }
            if got <= 0 { break }
            filled += got
        }
        return GamePanic(
            String(decoding: bytes[..<min(filled, limit)], as: UTF8.self), cut: filled > limit)
    }
}
