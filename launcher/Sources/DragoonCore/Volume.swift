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
    /// A volume that won't say counts as having none free.
    public static func freeSpace(at path: String) -> FreeSpace {
        var url = URL(fileURLWithPath: path)
        while !FileManager.default.fileExists(atPath: url.path), url.path != "/" {
            url.deleteLastPathComponent()
        }
        let values = try? url.resourceValues(forKeys: [
            .volumeAvailableCapacityForImportantUsageKey, .volumeLocalizedNameKey,
        ])
        return FreeSpace(
            available: values?.volumeAvailableCapacityForImportantUsage ?? 0,
            volume: values?.volumeLocalizedName ?? url.path)
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
