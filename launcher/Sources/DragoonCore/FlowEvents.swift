import Foundation

extension Flow {
    /// What the app knows as it starts, before any window shows.
    public struct Launch: Equatable, Sendable {
        /// The app bundle's path.
        public var appPath: String
        public var onReadOnlyVolume: Bool
        public var settings: LauncherSettings
        /// The app's source snapshot, or nil when its `source-info.json` can't be used.
        public var source: SourceInfo?
        public var installed: InstalledGame?

        public init(
            appPath: String, onReadOnlyVolume: Bool, settings: LauncherSettings,
            source: SourceInfo?, installed: InstalledGame?
        ) {
            self.appPath = appPath
            self.onReadOnlyVolume = onReadOnlyVolume
            self.settings = settings
            self.source = source
            self.installed = installed
        }
    }

    /// Something the player did, or the result of an effect.
    public enum Event: Equatable, Sendable {
        case launched(Launch)

        // The player
        case continuePressed
        case installToolsPressed
        case openSoftwareUpdatePressed
        case checkToolsPressed
        case chooseDiscPressed
        case lookAgainPressed
        case buildPressed
        case cancelBuildPressed
        case copyLogPressed
        case showLogPressed
        case playPressed
        case rebuildPressed
        case rebuildLaterPressed
        case showSavesPressed
        case changeDiscPressed
        case backToLibraryPressed
        case quitPressed

        // Results
        case toolsDetected(ToolchainStatus)
        /// `scheduleToolsCheck`'s time is up.
        case toolsCheckDue
        /// The player chose a disc image in the file panel, and the app made a bookmark to it.
        case discChosen(path: String, bookmark: Data)
        /// The player chose a disc image the app couldn't make a bookmark to.
        case discChoiceFailed(reason: String)
        /// The player closed the file panel without choosing.
        case discPanelCanceled
        case bookmarkResolved(BookmarkResolution)
        case discChecked(path: String, check: DiscCheck)
        case spaceChecked(FreeSpace)
        case build(BuildEvent)
        /// The build's stream ended, with nil when the new game is current.
        case buildEnded(BuildFailure?)
        case logTailRead(path: String, lines: [String])
        /// The game that the `play` with this launch number started has ended. `panic` is the
        /// text of the `panic.txt` the runtime wrote, after an ending that isn't a clean exit.
        case gameExited(launch: Int, exit: GameExit, panic: String?)
        /// The `play` with this launch number couldn't start the game, and `reason` says why.
        case gameCouldNotStart(launch: Int, reason: String)
    }

    /// What the app does for the flow. Each result comes back as an event.
    public enum Effect: Equatable, Sendable {
        case saveSettings(LauncherSettings)
        /// `Toolchain.detect`, which gives `toolsDetected`.
        case detectTools
        /// Gives `toolsCheckDue` after `after` seconds.
        case scheduleToolsCheck(after: TimeInterval)
        /// Runs `xcode-select --install`, which opens Apple's installer.
        case installTools
        case openSoftwareUpdate
        /// A file panel for `.iso`, `.gcm` and `.ciso`, which gives `discChosen`,
        /// `discChoiceFailed` or `discPanelCanceled`.
        case openDiscPanel
        /// Gives `bookmarkResolved`.
        case resolveBookmark(Data)
        /// `checkDisc`, which gives `discChecked`.
        case checkDisc(path: String, expected: ExpectedDisc)
        /// The free space where the game is built, which gives `spaceChecked`.
        case checkSpace
        /// `BuildRunner.run`, whose events come back as `build` and whose end comes back as
        /// `buildEnded`.
        case startBuild(toolchain: Toolchain, disc: String)
        case cancelBuild
        /// Gives `logTailRead`.
        case readLogTail(String)
        case copyLog(String)
        case showLog(String)
        /// Starts the current game with the disc at `disc`. Its one result is `gameExited` once
        /// the game ends, or `gameCouldNotStart`, and either echoes `launch`.
        case play(disc: String, launch: Int)
        case showSaves
        /// `OldBuilds.delete`, sent only while no game and no build is running.
        case deleteOldBuilds
        case quit
    }
}
