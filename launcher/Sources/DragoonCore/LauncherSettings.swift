import Foundation

/// What the launcher remembers between launches, kept in `<data>/launcher.json`.
public struct LauncherSettings: Codable, Equatable, Sendable {
    public static let fileName = "launcher.json"

    /// Whether the player has gone past Welcome.
    public var welcomeSeen: Bool
    /// A bookmark to the player's disc image. The launcher keeps this rather than a copy.
    public var disc: Data?

    public init(welcomeSeen: Bool = false, disc: Data? = nil) {
        self.welcomeSeen = welcomeSeen
        self.disc = disc
    }

    private enum CodingKeys: String, CodingKey {
        case welcomeSeen, disc = "discBookmark"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        welcomeSeen = try container.decodeIfPresent(Bool.self, forKey: .welcomeSeen) ?? false
        disc = try container.decodeIfPresent(Data.self, forKey: .disc)
    }

    /// The settings in `dataDirectory`, or the defaults when there are none or they can't be
    /// read.
    public static func load(from dataDirectory: String, fs: any FileSystem) -> LauncherSettings {
        guard let data = try? fs.readData(at: dataDirectory + "/" + fileName),
            let settings = try? JSONDecoder().decode(LauncherSettings.self, from: data)
        else { return LauncherSettings() }
        return settings
    }

    /// Replaces the settings in `dataDirectory` whole, making the directory first.
    public func save(to dataDirectory: String, fs: any FileSystem) throws {
        try fs.writeData(encodeJSON(self), to: dataDirectory + "/" + Self.fileName)
    }
}
