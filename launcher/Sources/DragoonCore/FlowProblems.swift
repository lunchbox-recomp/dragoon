import Foundation

/// Why the launcher asks to be moved to Applications before it does anything else.
public enum MoveReason: Equatable, Sendable {
    /// macOS runs it from an `/AppTranslocation/` copy, as it does for an app opened where it
    /// was downloaded.
    case translocated
    /// It's on a read-only volume, such as a disk image.
    case readOnlyVolume
    /// Its path holds a character the kit's Makefile refuses. Finder shows a `:` in a folder's
    /// name as `/`.
    case refusedCharacter(Character)

    /// What the kit's Makefile refuses in a path.
    public static let refusedCharacters: [Character] = ["$", "\"", "`", ":", ";"]

    /// Why the app at `appPath` has to move, or nil when it can stay.
    public init?(appPath: String, onReadOnlyVolume: Bool) {
        if appPath.contains("/AppTranslocation/") {
            self = .translocated
        } else if onReadOnlyVolume {
            self = .readOnlyVolume
        } else if let refused = appPath.first(where: Self.refusedCharacters.contains) {
            self = .refusedCharacter(refused)
        } else {
            return nil
        }
    }
}

/// Why the disc step can't go on.
public enum DiscProblem: Equatable, Sendable {
    /// Another game or region. Both are disc IDs.
    case wrongGame(found: String, needed: String)
    /// Another revision of the game. Both are main.dol SHA-1s.
    case wrongRevision(found: String, needed: String)
    case needsConversion(UnsupportedDiscFormat)
    case unreadable(reason: String)
    /// The bookmark is stale, or the file or its drive is gone.
    case moved

    /// The problem `check` found, or nil when the disc is the one `expected` names.
    public init?(_ check: DiscCheck, expected: ExpectedDisc) {
        switch check {
        case .ok: return nil
        case .wrongGame(let found): self = .wrongGame(found: found, needed: expected.id)
        case .wrongRevision(let found):
            self = .wrongRevision(found: found, needed: expected.dolSHA1)
        case .needsConversion(let format): self = .needsConversion(format)
        case .unreadable(let reason): self = .unreadable(reason: reason)
        }
    }
}

/// How a game run ended badly.
public enum GameProblem: Equatable, Sendable {
    /// The game exited with `status`. `panic` is what the runtime wrote to `panic.txt`, when it
    /// wrote one.
    case exited(status: Int32, panic: String?)
    case couldNotStart(reason: String)
}

extension BuildFailure {
    /// The recipe's step that failed, when it said.
    public var step: String? {
        if case .failed(let step, _, _) = self { return step }
        return nil
    }

    /// The build's log, when this failure has one.
    public var log: String? {
        switch self {
        case .failed(_, _, let log), .refused(_, let log): return log
        case .alreadyRunning, .cancelled, .couldNotStart: return nil
        }
    }
}
