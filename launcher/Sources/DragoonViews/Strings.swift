import DragoonCore
import Foundation

/// Every string the window shows the player, in one place so they can be read together.
public enum Strings {
    public static let appName = "Dragoon"
    static let quit = "Quit"
    static let backToLibrary = "Back to Library"
    static let checkAgain = "Check Again"

    static func step(_ step: Flow.Step) -> String {
        switch step {
        case .welcome: return "Welcome"
        case .tools: return "Tools"
        case .disc: return "Disc"
        case .build: return "Build"
        case .warmup: return "Warm-up"
        case .library: return "Library"
        }
    }

    // MARK: - Moving and damage

    static let moveTitle = "Move Dragoon to Applications"

    static func move(_ reason: MoveReason) -> String {
        switch reason {
        case .translocated:
            return "macOS is running this copy of Dragoon from a temporary read-only place, as it does for an app opened where it was downloaded. Move Dragoon to Applications and open it from there."
        case .readOnlyVolume:
            return "Dragoon is on a read-only volume, such as a disk image. Move Dragoon to Applications and open it from there."
        case .refusedCharacter(let character):
            return "The path to Dragoon has a \(MoveReason.finderName(of: character)) in a folder's name, and the build can't use a path with that character. Move Dragoon to Applications and open it from there."
        }
    }

    static let damagedTitle = "Dragoon Is Missing Files"
    static let damaged = "This copy of Dragoon can't read the source it builds the game from. Install Dragoon again."

    // MARK: - Welcome

    static let welcomeTitle = "Welcome to Dragoon"
    static let welcome = "Dragoon builds Kirby Air Ride for this Mac from your own disc image. It checks for Apple's developer tools and for your disc, then it builds the game and warms up its shaders."
    static let legal = "Dragoon isn't affiliated with or endorsed by Nintendo or HAL Laboratory. Kirby Air Ride is a Nintendo trademark. A build contains the game's code, so please don't share it."
    static let continueButton = "Continue"

    // MARK: - Tools

    static let toolsTitle = "Developer Tools"
    static let toolsChecking = "Looking for Apple's developer tools…"
    static let toolsMissing = "Dragoon needs Apple's Command Line Tools to build the game. They hold the compiler and the other tools the build runs."
    static let toolsInstaller = "Install Tools opens Apple's installer. The tools take about 1.8 GB once they're installed. This step looks for the tools again every \(Int(Flow.toolsCheckInterval)) seconds."
    static let installTools = "Install Tools"
    static let noLinkableSDK = "The Command Line Tools on this Mac are older than its SDKs, so the build can't link. Update the tools in Software Update, then check again."
    static let sdksTried = "SDKs tried"
    static let openSoftwareUpdate = "Open Software Update"

    static func cantWriteProbe(path: String, error: String) -> String {
        "Dragoon couldn't write a test file at \(path) to check the tools. \(error)"
    }

    // MARK: - Disc

    static let discTitle = "Your Disc"
    static let discChoose = "Choose your Kirby Air Ride (USA) disc image. Dragoon reads .iso, .gcm and .ciso files. It remembers where the file is and doesn't copy it."
    static let discChecking = "Checking the disc…"
    static let chooseDisc = "Choose Disc…"
    static let lookAgain = "Look Again"

    static func disc(_ problem: DiscProblem) -> String {
        switch problem {
        case .wrongGame(let found, let needed):
            return "This disc's ID is \(found), and Dragoon needs \(needed)."
        case .wrongRevision(let found, let needed):
            return "This is another revision of the game. Its main.dol has SHA-1 \(found), and Dragoon needs \(needed)."
        case .needsConversion(let format):
            return "This is \(article(format)) \(format.rawValue) image. Convert it to ISO in Dolphin first, then choose the ISO."
        case .unreadable(let reason):
            return "Dragoon couldn't read this disc image. \(reason)"
        case .moved:
            return "Dragoon's record of where your disc image is has gone out of date, as it does when the file is moved or renamed. Choose the disc again."
        case .missing:
            return "Dragoon can't find your disc image where it was. If its drive is unplugged, plug it in and look again, or choose the disc again."
        }
    }

    /// The article for an image kind as it's said aloud, so "an RVZ" and "a GCZ".
    private static func article(_ format: UnsupportedDiscFormat) -> String {
        switch format {
        case .rvz: return "an"
        case .gcz, .wia, .wbfs: return "a"
        }
    }

    // MARK: - Build

    static let buildReady = "Dragoon is ready to build the game. A build needs \(bytes(Flow.neededSpace)) free."
    static let buildGame = "Build Game"
    static let buildPreparing = "Checking the space, the disc and the tools…"
    static let buildStarting = "Starting the build…"
    static let cancel = "Cancel"
    static let canceling = "Canceling…"
    static let tryAgain = "Try Again"
    static let copyLog = "Copy Log"
    static let showLog = "Show Log"
    static let logEnd = "The end of the log"

    static func lowSpace(_ space: FreeSpace, needed: Int64) -> String {
        "A build needs \(bytes(needed)) free on \(space.volume), and it has \(bytes(space.available))."
    }

    /// What a running build is doing, by the recipe's name for its step.
    static func running(_ step: String) -> String {
        switch step {
        case "recompile": return "Recompiling the game's code…"
        case "compile": return "Compiling…"
        case BuildProgress.warmupStep: return "Warming up the shaders…"
        case "package": return "Packaging the game…"
        case "swap": return "Installing the game…"
        default: return "Building…"
        }
    }

    /// A step's count with its unit. Compile counts each file as make starts it. The warm-up
    /// gives the share of its frames played once it has `frames`, and each run as it ends
    /// from a game that prints none.
    static func count(step: String, done: Int, total: Int, frames: FrameCount? = nil) -> String {
        switch step {
        case "compile": return "\(done) of \(total) files"
        case BuildProgress.warmupStep:
            if let frames, frames.total > 0 {
                return percent(Double(min(frames.done, frames.total)) / Double(frames.total))
                    + " warmed up"
            }
            return "\(done) of \(total) runs done"
        default: return "\(done) of \(total)"
        }
    }

    /// The time a build has taken, and the time left once there's an estimate.
    static func buildTime(elapsed: TimeInterval, left: TimeInterval?) -> String {
        guard let left else { return clock(elapsed) }
        return clock(elapsed) + "  ·  " + timeLeft(left)
    }

    /// Minutes and seconds, as 1:05, and hours too past an hour, as 1:02:05.
    static func clock(_ seconds: TimeInterval) -> String {
        let whole = Int(max(seconds, 0))
        let (hours, minutes, rest) = (whole / 3600, whole / 60 % 60, whole % 60)
        let tail = String(format: "%02d", rest)
        return hours > 0
            ? "\(hours):" + String(format: "%02d", minutes) + ":" + tail : "\(minutes):" + tail
    }

    /// Under a minute in steps of 5 seconds, rounded up, and in whole minutes past that.
    static func timeLeft(_ seconds: TimeInterval) -> String {
        if seconds <= 55 { return "About \(max(Int((seconds / 5).rounded(.up)) * 5, 5)) s left" }
        return "About \(Int((seconds / 60).rounded())) min left"
    }

    static let buildFinishedTitle = "Ready to Play"
    static let buildFinished = "The game is built."

    static func buildTook(_ seconds: TimeInterval) -> String {
        "The build took \(clock(seconds))."
    }

    /// The bar's name and value for VoiceOver.
    static let buildMeter = "Build progress"

    static func percent(_ fraction: Double) -> String {
        "\(Int((fraction * 100).rounded(.down)))%"
    }

    static func buildFailure(_ failure: BuildFailure) -> String {
        switch failure {
        case .failed(let step?, let message, _):
            return "The build stopped at its \(step) step. \(message)"
        case .failed(nil, let message, _):
            return "The build stopped. \(message)"
        case .refused(let message, _):
            return "The build couldn't start with what it was given. \(message)"
        case .alreadyRunning:
            return "Another build is already running."
        case .couldNotStart(let reason):
            return "The build couldn't start. \(reason)"
        case .cancelled:
            return "The build was canceled."
        }
    }

    static func logPlace(_ log: String) -> String {
        "The log is at \(log)."
    }

    // MARK: - Library

    static let libraryTitle = "Kirby Air Ride"
    static let libraryReady = "The game is built and ready to play."
    static let gameRunning = "The game is running."
    static let play = "Play"
    static let playing = "Playing"
    /// The "..." menu's name for VoiceOver.
    static let more = "More"
    static let rebuild = "Rebuild"
    static let showSaves = "Show Saves"
    static let changeDisc = "Change Disc…"
    static func rebuildOffer(_ offer: RebuildOffer) -> String {
        switch offer {
        case .otherVersion:
            return "This copy of Dragoon builds a different version of the game than the one you have. You can rebuild now or later, and the game you have plays until a rebuild starts."
        case .unknownVersion:
            return "Dragoon can't tell which version of the game you have. You can rebuild now or later, and the game you have plays until a rebuild starts."
        }
    }
    static let rebuildNow = "Rebuild Now"
    static let later = "Later"
    /// The line beside Play.
    static func playStatus(_ status: PlayStatus) -> String {
        switch status {
        case .ready: return libraryReady
        case .checkingDisc: return discChecking
        case .playing: return gameRunning
        }
    }

    /// The line under the logo on Play's launch card, or nil for none.
    static func launchCard(_ handOff: Flow.HandOff) -> String? {
        switch handOff {
        case .charging: return discChecking
        case .launched: return "Starting the game…"
        case .hidden: return gameRunning
        case .returning: return nil
        }
    }

    static let showPanic = "Show panic.txt"
    static let hidePanic = "Hide panic.txt"
    static let panicHeading = "The game wrote this in panic.txt"
    static let panicCut = "panic.txt is longer than this, so only its first \(GamePanic.limit / 1024) KB are shown."

    static func gameFailed(_ problem: GameProblem) -> String {
        switch problem {
        case .exited(.status(let status), _): return "The game quit with exit code \(status)."
        case .exited(.signal(let number), _):
            // A number macOS has no name for is shown alone.
            let name = GameExit.signal(number).signalName.map { " (\($0))" } ?? ""
            return "The game was stopped by signal \(number)\(name)."
        case .couldNotStart(let reason): return "The game couldn't start. \(reason)"
        }
    }

    /// Why the game couldn't start, after "The game couldn't start."
    public static func gameStart(_ failure: GameStartFailure) -> String {
        switch failure {
        case .missing(let path): return "There's no game at \(path)."
        case .failed(let reason): return reason
        }
    }

    // MARK: - Settings

    static let settings = "Settings…"
    static let settingsTitle = "Settings"
    // The headings and labels are the game's Display page's own (overlay_display.cpp).
    static let aspectHeading = "Aspect ratio"
    static let fullscreen = "Fullscreen"
    static let scaleHeading = "Scale"
    static func aspectLabel(_ aspect: String) -> String {
        aspect == "window" ? "Fill window" : aspect
    }
    static func scaleLabel(_ scale: Int) -> String { "\(scale)x" }
    /// What the aspect does to the picture, under the preview.
    static func aspectNote(_ aspect: String) -> String {
        switch aspect {
        case "4:3": return "4:3 is the console's own shape."
        case "window": return "The picture takes the window's shape as it's resized. The window opens at 4:3."
        case _ where PictureSettings.aspects.contains(aspect):
            // The HUD at 16:9 is measured (docs/dev/status.md's HUD row), and 16:10 and 21:9 are
            // checked by tests/src/test_hud_anchors.cpp's offered aspects. Top Ride's 38 HUD
            // draws measured stretched. A menu over a world view, such as the pause menu,
            // stretches because the menu cameras are centered only in a frame with no world view,
            // which test_hud_anchors.cpp checks, though no dump has shown one (widescreen.md).
            return "The world widens to \(aspect). The race HUD keeps its 4:3 size at the picture's edges and middle, the menus stay 4:3 in the middle, and the pause menu and Top Ride's HUD stretch."
        default:
            // A hand-edited aspect the sheet has no button for, such as 5:4.
            return "settings.txt sets \(aspect), which isn't one of these."
        }
    }
    /// Where the game's picture goes, its window or the screen, as the preview draws it.
    static func windowNote(_ layout: PicturePreview.Layout) -> String {
        let source = layout.source, fit = layout.fit
        switch layout.shows {
        case .window:
            return "The game's window opens at \(source.width) x \(source.height) points."
        case .unknownScreen:
            return "The game fills the screen."
        case .screen:
            if fit.width == source.width && fit.height == source.height {
                return "The game fills the \(source.width) x \(source.height) point screen."
            }
            return "The game fills the screen, with the picture \(fit.width) x \(fit.height) points in it."
        }
    }
    static func scaleNote(_ scale: Int) -> String {
        let size = PictureGeometry.internalSize(scale: scale)
        return "Each frame is drawn at \(size.width) x \(size.height), then stretched to the picture's shape."
    }
    /// The preview's name for VoiceOver.
    static func previewLabel(_ size: WholeSize) -> String {
        "The game's picture at \(size.width) x \(size.height) points"
    }
    static let settingsWhen = "The game reads these as it starts, and its Display page saves them too."
    static let done = "Done"
    /// Why the last change wasn't saved. The system's reason, when there is one, shows under it.
    static func pictureFailure(_ failure: PictureSettings.SaveFailure) -> String {
        switch failure {
        case .refused: return "The game doesn't read these settings, so settings.txt wasn't changed."
        case .unreadable: return "settings.txt is there and can't be read, so it wasn't changed."
        case .notWritten: return "The change couldn't be saved, and settings.txt is as it was."
        }
    }

    // MARK: - Picture card

    static let pictureCardTitle = "Picture: 4:3 or 16:9"
    // The first sentence is the sheet's 4:3 note. The next two are its 16:9 note without where
    // the HUD's boxes sit and the menus' 4:3 middle, which the previews draw, and with what
    // stretches as the sheet says it.
    static let pictureCardNote = "4:3 is the console's own shape. At 16:9 the world widens and the race HUD keeps its 4:3 size. The pause menu and Top Ride's HUD stretch. Settings in Library's … menu has 16:10, 21:9 and Fill window."
    static let pictureCardKeep = "Keep 4:3"
    /// A preview's button for VoiceOver.
    static func pictureCardUse(_ aspect: String) -> String { "Use \(aspect)" }

    // MARK: - Sizes

    static func bytes(_ count: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: count, countStyle: .file)
    }
}
