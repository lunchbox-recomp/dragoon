import Foundation

/// The disc's `opening.bnr` kept as the file it is in `<data>/disc/opening.bnr`, so Library has
/// the banner with the disc's drive unplugged. Only a disc that passed its check is read into
/// it, and the flow sees to that.
public enum BannerCache {
    public static func path(data: String) -> String {
        data + "/disc/opening.bnr"
    }

    /// The cached banner, decoded for the disc `discID` names, or nil when there's none or it
    /// isn't a banner.
    public static func load(data: String, discID: String, fs: any FileSystem) -> DiscBanner? {
        guard let bytes = try? fs.readData(at: path(data: data)) else { return nil }
        return DiscBanner(bytes: bytes, discID: discID)
    }

    /// Reads the banner of the disc image at `disc` and keeps its bytes in the cache. A banner
    /// that can't be kept is still given back, since the cache only saves reading it again.
    public static func readAndKeep(disc: String, data: String, fs: any FileSystem) -> DiscBanner? {
        guard let banner = DiscBanner.read(at: disc, fs: fs) else { return nil }
        try? fs.writeData(banner.bytes, to: path(data: data))
        return banner
    }
}
