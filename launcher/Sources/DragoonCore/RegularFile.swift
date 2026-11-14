import Foundation

/// Reads a small file the game writes. A link at the path isn't followed, and a FIFO is opened
/// without waiting for a writer and then left unread. A regular file then has `O_NONBLOCK`
/// cleared, as `SystemFileSystem`'s readers do, so its reads block as usual on any file system.
enum RegularFile {
    /// The first `limit` bytes of the regular file at `path`, and whether it holds more, or nil
    /// when no regular file is there.
    static func read(at path: String, limit: Int) -> (bytes: ArraySlice<UInt8>, cut: Bool)? {
        let descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
        guard descriptor >= 0 else { return nil }
        defer { close(descriptor) }
        var info = stat()
        guard fstat(descriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
            fcntl(descriptor, F_SETFL, 0) == 0
        else { return nil }
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
        return (bytes[..<min(filled, limit)], filled > limit)
    }
}
