import Foundation

/// How much room the volume holding a path has.
public struct FreeSpace: Equatable, Sendable {
    /// Bytes free for important use, which counts what macOS can purge.
    public var available: Int64
    /// The volume's name, as Finder shows it.
    public var volume: String

    public init(available: Int64, volume: String) {
        self.available = available
        self.volume = volume
    }
}

/// What the launcher asks about volumes.
public enum Volume {
    /// The free space on the volume holding `path`, or the nearest folder above it that exists.
    /// macOS works out the space for important use with what it could purge, and at times
    /// answers that with nothing or 0. The bytes statfs(2) calls free are free whatever it says,
    /// so the larger of the two counts. A volume that won't say either counts as having none free.
    public static func freeSpace(at path: String) -> FreeSpace {
        var url = URL(fileURLWithPath: path)
        while !FileManager.default.fileExists(atPath: url.path), url.path != "/" {
            url.deleteLastPathComponent()
        }
        let values = try? url.resourceValues(forKeys: [
            .volumeAvailableCapacityForImportantUsageKey, .volumeLocalizedNameKey,
        ])
        return FreeSpace(
            available: usable(
                important: values?.volumeAvailableCapacityForImportantUsage, free: free(url.path)),
            volume: values?.volumeLocalizedName ?? url.path)
    }

    /// The space a build can count on, from macOS's figure for important use and the volume's
    /// free bytes, either of which can be missing.
    static func usable(important: Int64?, free: Int64?) -> Int64 {
        max(important ?? 0, free ?? 0)
    }

    /// The bytes statfs(2) says are free to a process that isn't root on the volume holding
    /// `path`, or nil when it can't say.
    static func free(_ path: String) -> Int64? {
        var info = statfs()
        guard statfs(path, &info) == 0 else { return nil }
        return Int64(info.f_bavail) * Int64(info.f_bsize)
    }

    /// Whether the volume holding `path` is mounted read-only, as a disk image is. This asks
    /// statfs(2) for the mount's flags, since `volumeIsReadOnly` calls the sealed system volume
    /// writable.
    public static func isReadOnly(_ path: String) -> Bool {
        var info = statfs()
        guard statfs(path, &info) == 0 else { return false }
        return info.f_flags & UInt32(MNT_RDONLY) != 0
    }
}
