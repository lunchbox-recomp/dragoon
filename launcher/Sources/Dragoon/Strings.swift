import DragoonCore
import Foundation

/// Every string the window shows the player, in one place so they can be read together.
enum Strings {
    static let appName = "Dragoon"
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
            return "The path to Dragoon has a \(finderName(character)) in a folder's name, and the build can't use a path with that character. Move Dragoon to Applications and open it from there."
        }
    }

    /// Finder shows a `:` in a folder's name as `/`.
    private static func finderName(_ character: Character) -> String {
        character == ":" ? "/" : String(character)
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
            return "This is a \(format.rawValue) image. Convert it to ISO in Dolphin first, then choose the ISO."
        case .unreadable(let reason):
            return "Dragoon couldn't read this disc image. \(reason)"
        case .moved:
            return "Dragoon can't find your disc image where it was. If its drive is unplugged, plug it in and look again, or choose the disc again."
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

    static func progress(done: Int, total: Int, step: String) -> String {
        step == BuildProgress.warmupStep ? "Pass \(done) of \(total)" : "\(done) of \(total)"
    }

    static func buildFailure(_ failure: BuildFailure) -> String {
        switch failure {
        case .failed(let step?, let message, _):
            return "The build stopped at its \(step) step. \(message)"
        case .failed(nil, let message, _):
            return "The build stopped. \(message)"
        case .refused(let message, _):
            return "The build couldn't use the files that came with this copy of Dragoon. \(message)"
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
    static let rebuild = "Rebuild"
    static let showSaves = "Show Saves"
    static let changeDisc = "Change Disc…"
    static let rebuildOffer = "This copy of Dragoon builds a different version of the game than the one you have. You can rebuild now or later, and the game you have plays until a rebuild starts."
    static let rebuildNow = "Rebuild Now"
    static let later = "Later"
    static let panicHeading = "The game wrote this in panic.txt"

    static func gameFailed(_ problem: GameProblem) -> String {
        "The game quit with exit code \(problem.status)."
    }

    // MARK: - Sizes

    static func bytes(_ count: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: count, countStyle: .file)
    }
}
