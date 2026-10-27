import DragoonCore
import Foundation

/// A scratch directory with spaces in its name that holds what a build needs. That is a bundle
/// whose recipe is a shell script a test writes, a python3 that records how it was called and
/// then runs that script with sh after the -B and -s, and directories for the logs, data and cache.
final class RecipeFixture: @unchecked Sendable {
    let root: String

    var bundle: String { root + "/Dragoon.app" }
    var recipe: String { bundle + "/Contents/Resources/source/tools/launcher_build.py" }
    var python3: String { root + "/tools/python3" }
    var logs: String { root + "/Library/Logs/Dragoon" }
    var data: String { root + "/Library/Application Support/Dragoon" }
    var cache: String { root + "/Library/Caches/Dragoon" }
    var disc: String { root + "/Kirby Air Ride (USA).gcm" }
    /// Where the stand-in python3 writes its arguments, one per line, and its environment.
    var argumentsFile: String { root + "/python arguments.txt" }
    var environmentFile: String { root + "/python environment.txt" }
    /// Where scripts write their own pid, the pid of a helper they start, and a note.
    var pidFile: String { root + "/recipe pid.txt" }
    var helperFile: String { root + "/helper pid.txt" }
    var noteFile: String { root + "/note.txt" }

    /// The clock the tests run on, so the log's name is known. It's 2027-01-15 08:00:00 UTC.
    static let clock = Date(timeIntervalSince1970: 1_800_000_000)
    static let logName = "build-2027-01-15T08-00-00.000Z.log"
    var logPath: String { logs + "/" + Self.logName }

    var toolchain: Toolchain {
        Toolchain(
            developerDirectory: "/Library/Developer/CommandLineTools",
            clang: "/Library/Developer/CommandLineTools/usr/bin/clang",
            clangxx: "/Library/Developer/CommandLineTools/usr/bin/clang++",
            make: "/Library/Developer/CommandLineTools/usr/bin/make", python3: python3,
            sdk: "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
            clangVersion: "Apple clang version 17.0.0")
    }

    init() throws {
        let made = FileManager.default.temporaryDirectory
            .appendingPathComponent("Dragoon build tests \(UUID().uuidString)")
        try FileManager.default.createDirectory(at: made, withIntermediateDirectories: true)
        root = SystemFileSystem().resolvingSymlinks(at: made.path)
        try executable(
            python3,
            """
            #!/bin/sh
            printf '%s\\n' "$@" > \(shellWord(argumentsFile))
            /usr/bin/env > \(shellWord(environmentFile))
            shift 2
            exec /bin/sh "$@"
            """)
    }

    deinit { try? FileManager.default.removeItem(atPath: root) }

    /// Installs `body` as the recipe. It runs with the arguments the launcher gave, and `$log` is
    /// the one after `--log`.
    func install(_ body: String) throws {
        try executable(
            recipe,
            """
            log=
            for argument in "$@"; do
              if [ "$previous" = "--log" ]; then log="$argument"; fi
              previous="$argument"
            done
            \(body)
            """)
    }

    /// Installs `source`, which is Python, as the recipe, for a test that runs a real python3.
    func installPython(_ source: String) throws {
        try executable(recipe, source)
    }

    /// A request that runs the recipe under the python3 in `/usr/bin`, with the developer
    /// directory that `xcode-select -p` names, as it runs on a Mac with the tools installed.
    func requestWithRealPython() async throws -> BuildRequest {
        var real = toolchain
        real.python3 = "/usr/bin/python3"
        real.developerDirectory = try await SystemProcessRunner().run("/usr/bin/xcode-select", ["-p"])
            .stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        return BuildRequest(
            toolchain: real, bundle: bundle, disc: disc, data: data, cache: cache)
    }

    func request(noWarmup: Bool = false, keepBuild: Bool = false) -> BuildRequest {
        BuildRequest(
            toolchain: toolchain, bundle: bundle, disc: disc, data: data, cache: cache,
            noWarmup: noWarmup, keepBuild: keepBuild)
    }

    func runner(killGrace: TimeInterval? = nil, now: Date = RecipeFixture.clock) -> BuildRunner {
        BuildRunner(logDirectory: logs, killGrace: killGrace, now: { now })
    }

    /// The names of the files in the log directory.
    var logNames: [String] {
        (try? FileManager.default.contentsOfDirectory(atPath: logs))?.sorted() ?? []
    }

    func log() -> String {
        (try? String(contentsOfFile: logPath, encoding: .utf8)) ?? ""
    }

    private func executable(_ path: String, _ text: String) throws {
        try FileManager.default.createDirectory(
            atPath: (path as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
        try Data((text + "\n").utf8).write(to: URL(fileURLWithPath: path))
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path)
    }
}

/// Everything a build's stream gave.
struct Finished {
    var events: [BuildEvent] = []
    var failure: BuildFailure?
}

func collect(_ stream: AsyncThrowingStream<BuildEvent, Error>) async -> Finished {
    var finished = Finished()
    do {
        for try await event in stream { finished.events.append(event) }
    } catch {
        finished.failure = error as? BuildFailure
    }
    return finished
}
