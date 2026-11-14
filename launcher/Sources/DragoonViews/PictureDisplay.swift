import DragoonCore
import SwiftUI

/// The display the game opens on, in points: its whole frame, which a fullscreen game covers,
/// and the part a window may take, which leaves out the menu bar and the Dock.
public struct PictureDisplay: Equatable, Sendable {
    public var frame: WholeSize
    public var usable: WholeSize

    public init(frame: WholeSize, usable: WholeSize) {
        self.frame = frame
        self.usable = usable
    }
}

private struct PictureDisplayKey: EnvironmentKey {
    static let defaultValue: PictureDisplay? = nil
}

extension EnvironmentValues {
    /// The display the game opens on, which the app sets, or nil when it isn't known. The
    /// Settings sheet sizes its preview by it.
    public var pictureDisplay: PictureDisplay? {
        get { self[PictureDisplayKey.self] }
        set { self[PictureDisplayKey.self] = newValue }
    }
}
