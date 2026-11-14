import Foundation

/// The four keys of `<data>/settings.txt` the engine saves: the picture's aspect, fullscreen and
/// scale, and the disc speed. The game's working directory is `<data>`, so this is the file it
/// reads as it starts and its Display page saves (gcn-recomp `runtime/settings.h`). The launcher
/// shows the picture keys and writes the disc speed back as it read it, as the engine does.
public struct PictureSettings: Equatable, Sendable {
    /// "W:H", two whole numbers from 1 to 9999, or "window" for the window's own shape.
    public var aspect: String
    public var fullscreen: Bool
    /// The internal resolution, this many times 640x480. The renderer draws at most
    /// `maxScale`.
    public var scale: Int
    /// `disc fast`, or `disc console` when false.
    public var fastDisc: Bool

    /// The aspects the launcher offers, in the order the game's Display page shows them.
    public static let aspects = ["4:3", "16:9", "16:10", "21:9", "window"]
    /// The largest scale the renderer draws at (`gx::kMaxInternalScale`), and the largest the
    /// Display page offers.
    public static let maxScale = 8
    /// The largest scale the file takes, nine digits, which the engine reads without overflow.
    static let largestScale = 999_999_999
    /// The largest side of an aspect the file takes, four digits, as `--aspect` takes it.
    static let largestAspectSide = 9999

    public init(aspect: String = "4:3", fullscreen: Bool = false, scale: Int = 2, fastDisc: Bool = true) {
        self.aspect = aspect
        self.fullscreen = fullscreen
        self.scale = scale
        self.fastDisc = fastDisc
    }

    /// The settings in a file's bytes over the defaults, as `settings_load` reads them. A line
    /// whose value the engine refuses leaves the key as it was.
    public init(parsing data: Data) {
        self.init()
        for (key, value) in SettingsText.entries(in: data) {
            let text = String(decoding: value, as: UTF8.self)
            switch String(decoding: key, as: UTF8.self) {
            case "aspect":
                if Self.ratio(of: text) != nil { aspect = text }
            case "fullscreen":
                if text == "0" || text == "1" { fullscreen = text == "1" }
            case "scale":
                if let n = Self.positive(text, max: Self.largestScale) { scale = n }
            case "disc":
                if text == "fast" || text == "console" { fastDisc = text == "fast" }
            default:
                break
            }
        }
    }

    /// Width over height for an aspect the file takes, 0 for "window", or nil for one it
    /// refuses (`settings_parse_aspect`).
    public static func ratio(of aspect: String) -> Double? {
        guard let sides = sides(of: aspect) else { return aspect == "window" ? 0 : nil }
        return Double(sides.w) / Double(sides.h)
    }

    /// The two whole numbers of a "W:H" aspect, or nil for "window" and anything the file
    /// refuses.
    public static func sides(of aspect: String) -> (w: Int, h: Int)? {
        guard let colon = aspect.firstIndex(of: ":"),
            let w = positive(String(aspect[..<colon]), max: largestAspectSide),
            let h = positive(String(aspect[aspect.index(after: colon)...]), max: largestAspectSide)
        else { return nil }
        return (w, h)
    }

    /// A whole number from 1 to `max` in ASCII digits alone, and no more of them than `max` has.
    private static func positive(_ text: String, max: Int) -> Int? {
        let digits = Array(text.utf8)
        guard !digits.isEmpty, digits.count <= String(max).count,
            digits.allSatisfy({ $0 >= UInt8(ascii: "0") && $0 <= UInt8(ascii: "9") }),
            let n = Int(text), n >= 1, n <= max
        else { return nil }
        return n
    }

    /// The settings in `<dataDirectory>/settings.txt`, or the defaults when it's missing or can't
    /// be read.
    public static func load(from dataDirectory: String, fs: any FileSystem) -> PictureSettings {
        guard let data = try? fs.readData(at: path(in: dataDirectory)) else { return PictureSettings() }
        return PictureSettings(parsing: data)
    }

    static func path(in dataDirectory: String) -> String {
        dataDirectory + "/" + SettingsText.fileName
    }

    /// Why a save wrote nothing.
    public enum SaveFailure: Error, Equatable, Sendable {
        /// A value the engine's load would skip, which `settings_save` refuses too.
        case refused
        /// The file is there and can't be read, so its other lines would be lost.
        case unreadable(String)
        /// The new file couldn't be written or renamed over the old one, which is as it was.
        case notWritten(String)
    }

    /// Sets the four keys in `<dataDirectory>/settings.txt`, keeping every other line, through
    /// `settings.txt.tmp` renamed over the file, as `settings_save` does. A save that fails
    /// leaves the old file whole and removes the `.tmp`.
    public func save(to dataDirectory: String, fs: any FileSystem) throws(SaveFailure) {
        guard Self.ratio(of: aspect) != nil, Self.positive(String(scale), max: Self.largestScale) != nil
        else { throw .refused }
        let path = Self.path(in: dataDirectory)
        let old: Data
        do {
            old = try fs.readData(at: path)
        } catch {
            // A file that isn't there is an empty one. One that is and can't be read isn't.
            guard !fs.fileExists(at: path) else { throw .unreadable(error.localizedDescription) }
            old = Data()
        }
        let new = SettingsText.setting(values, in: old)
        let temporary = path + ".tmp"
        do {
            try fs.writeData(new, to: temporary)
            try fs.renameItem(at: temporary, over: path)
        } catch {
            try? fs.removeItem(at: temporary)
            throw .notWritten(error.localizedDescription)
        }
    }

    /// The keys `settings_save` owns, in its order.
    var values: [(key: String, value: String)] {
        [
            ("aspect", aspect), ("fullscreen", fullscreen ? "1" : "0"), ("scale", String(scale)),
            ("disc", fastDisc ? "fast" : "console"),
        ]
    }
}
