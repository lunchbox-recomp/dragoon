# Launcher

The macOS launcher for Dragoon, as a SwiftPM package meant to build with the Command Line Tools alone. `Dragoon` is the SwiftUI app and stays thin, and `DragoonCore` holds everything that can be tested. That includes the `ProcessRunner` and `FileSystem` protocols, which each have a real version in `Sources/DragoonCore/` and a fake in `Tests/DragoonCoreTests/`, and one set of tests runs against both file systems.

```
swift build --package-path launcher
launcher/tools/swift_test.py
```

Every argument after `swift_test.py` goes to `swift test`, `--help` included, so `launcher/tools/swift_test.py --filter FileSystemTests` runs one suite and the wrapper has no help of its own. Its tests are in `launcher/tools/test_swift_test.py`, and the other launcher tools live beside it.

## On this Mac

Measured on 2026-10-26 on macOS 26.6.2 with the Command Line Tools 26.6 (`CLTools_Executables` 26.6.0.0.1781586589) and Swift 6.3.3, with no Xcode.

| What was run | Result |
|---|---|
| `swift build --package-path launcher` | Builds on the default SDK, `MacOSX26.5.sdk`. No `SDKROOT` is needed |
| `swift test --package-path launcher` | Fails with `no such module 'Testing'` |
| `swift test` with only `-Xswiftc -F` | The tests compile, then the runner can't load `Testing.framework` |
| `launcher/tools/swift_test.py` | Adds the Testing paths and runs the tests, which pass |
| `Dragoon --check-tools` | Reports `MacOSX26.5.sdk` and the tools under `/Library/Developer/CommandLineTools/usr/bin/` |
| `Dragoon --check-disc` on the supported disc and on another game's | `ok`, and `wrongGame` with the other disc's ID. `extract_dol.py` agrees on both |

## The tools check

`Dragoon --check-tools` prints what `Toolchain.detect` found as JSON and exits without opening a window. The exit code is 0 for a `ready` status and 1 for any other.

It runs `xcode-select -p` first, because a developer tool shim under `/usr/bin` would open Apple's install prompt. Then `xcrun --find` names `clang`, `clang++`, `make` and `python3` by full path. Each of those queries gets 10 seconds, and one that runs out counts as having failed.

The SDK is the first that compiles and links a C++ file that includes `<cstdio>`, and each try gets 60 seconds. With Xcode selected it tries the one `xcrun --show-sdk-path` names first. Then it tries `SDKs/MacOSX.sdk`, then every other `MacOSX*.sdk` newest first, skipping an SDK whose major version is above the tools' own in that last step only.

The probe's source goes in `~/Library/Caches/Dragoon` and comes out again after the probe. If it can't be written the status is `cantWriteProbe`, which names the path and the error. No SDK is blamed.

A check whose task is canceled stops the command it's waiting on and gives `cancelled`, so a cancel never reads as missing tools or an SDK that doesn't link. Only a `ready` answer survives a cancel, so a check that had found its tools already keeps them.

The choice is kept in `toolchain.json` in `~/Library/Application Support/Dragoon`. It's used only while the developer directory and the tool paths match and the first line of `clang --version` hasn't changed. A different developer directory or tool path forces a probe too, and so does an SDK that's gone.

## The disc check

`Dragoon --check-disc PATH` checks a disc image against the `source-info.json` in the app's source snapshot and prints the result as JSON. `--source-info FILE` names another one when the binary isn't inside the app, and it can come before or after `--check-disc`. The exit code is 0 for `ok`, 1 for any other result and 2 for a bad argument or a source-info it can't use.

A matching disc is `ok`, and another game's is `wrongGame` with the disc ID it found. A different build of the right game is `wrongRevision` with the SHA-1 of the main.dol it found, and a format the build doesn't read is `needsConversion` with `RVZ`, `GCZ`, `WIA` or `WBFS`. A file that can't be opened, ends early or has a main.dol with no sections is `unreadable` with a reason.

It reads a disc the way `gcn-recomp/recomp/extract_dol.py` does. The disc ID is the first 6 bytes, and main.dol starts at the big-endian word at 0x420. Its length is the largest offset plus size among the 18 sections in its header that have a size, and the SHA-1 covers that many bytes.

A CISO is a 0x8000-byte header followed by the blocks its map marks with a 1. Any other block reads as zeros.

An `RVZ`, `GCZ`, `WIA` or `WBFS` image is named by its magic and has to be converted first. The magics come from Dolphin's `Source/Core/DiscIO/`.

The recipe's reader stops with a Python error when the file ends before the DOL offset or the DOL's section table, and it hashes what it gets when the file ends later in the DOL. The check says `unreadable` for all of these, and for a CISO read past the blocks its map covers.

The image is read through a file handle a piece at a time, with no read over 1 MiB. A 1.4 GB disc doesn't cost 1.4 GB of memory.

## Running the recipe

`BuildRunner.run(_:)` runs the build recipe with the tools the tools check found and gives its JSON lines back as `BuildEvent` values. The command is `<python3> -B -s <bundle>/Contents/Resources/source/tools/launcher_build.py` and then the recipe's options as a list, so a path with spaces stays one argument. `-B` keeps `__pycache__` out of the signed bundle, `-s` keeps the player's user site-packages off the path, and the kit comes from `Contents/Resources/kit`.

The recipe gets an environment of its own with a fixed `PATH`, `HOME`, `TMPDIR`, `LANG`, `PYTHONDONTWRITEBYTECODE`, `PYTHONNOUSERSITE` and `DEVELOPER_DIR`. Nothing from the player's shell or their user site-packages reaches its Python.

It starts as the leader of a new process group, so the recipe, make, clang and the warm-up's game stop together. `BuildRunner.cancel()` or dropping the stream sends that group SIGTERM, and SIGKILL 10 seconds later if anything is left. Every `SystemProcessRunner` call starts its process this way too, so canceling a task that waits on `Toolchain.detect` stops its command the same way.

A stdout line that isn't an event is logged and never counted as an error. Everything the recipe prints on stderr is logged too. Both go into `~/Library/Logs/Dragoon/build-<time>.log` beside what the recipe writes there, and the newest 10 logs stay.

The recipe's exit code decides how the stream ends.

| Exit | The stream |
|---|---|
| 0 | Ends normally, and the new game is current. A shader cache the recipe couldn't install after the swap is a `warning` line in the log, since that isn't a `BuildEvent` |
| 1 | A step failed before the swap, so the old game is still current. Yields the recipe's `error` event, then throws `failed` with its step and message, or with the log's path when there was none |
| 2 | Throws `refused`, with the kit's reason or the recipe's stderr, and yields no `error` event |
| 3 | Throws `alreadyRunning`, "a build is already running", with no `error` event |
| Anything else, or a signal | Throws `failed`, with the log's path |
| `run(_:)` while a build is running | Throws `alreadyRunning` and starts nothing, so `cancel()` still reaches the running build |
| `cancel()` before the swap | Throws `cancelled`, unless the recipe exits 0 anyway |
| `cancel()` after the swap | Ends with `done`, since `game/current` is the new game by then. The warmed shader cache may not have been installed |

## The window

The window has the steps on the left and the current step on the right. What it does is `Flow`, a pure state machine in `DragoonCore` whose `reduce` takes a state and an event and gives the next state and a list of effects. The app carries out each effect and sends its result back as an event, so the tests drive every path with no window, the tools check's 5 second timer included.

The first run walks the steps in order from Welcome down to Library, and every later launch with a built game opens on Library. While the tools are missing, the Tools step offers Apple's installer and looks for them again every 5 seconds. Before each build the launcher wants 2 GB free by `volumeAvailableCapacityForImportantUsage`, then resolves the disc's bookmark and checks the disc, then checks the tools.

Play resolves the bookmark and checks the disc too. A stale bookmark or a disc that's gone goes back to the Disc step, and the game stays where it was. Look Again tries the bookmark again only for a disc that's gone, such as one on an unplugged drive.

From the `play` effect until the game exits or can't start, Library counts the game as running and keeps Play, Rebuild and Change Disc off. In this version `play` doesn't start the game, so it reports at once that the game couldn't start.

A launcher whose path holds `/AppTranslocation/`, or that's on a read-only volume, asks to be moved to Applications and does nothing else. So does one whose path holds a character the kit's Makefile refuses, which is `$`, `"`, a backtick, `:` or `;`. Finder shows a `:` in a folder's name as `/`, so that's how the window names it.

Library offers a rebuild when `game/current/stamp.json` names other commits than the app's `source-info.json` or can't be read, and the old game plays until a rebuild starts. A rebuild that fails or is canceled leaves the old game current. Builds other than the current one are deleted while no game or build is running.

`launcher.json` in `~/Library/Application Support/Dragoon` keeps the disc's bookmark and whether Welcome was seen. Every string the window shows is in `Sources/Dragoon/Strings.swift`.

## Why a wrapper runs the tests

The Command Line Tools ship Swift Testing, but not where `swift test` looks. `Testing.framework` is in `/Library/Developer/CommandLineTools/Library/Developer/Frameworks` and `lib_TestingInterop.dylib` is in `.../Library/Developer/usr/lib`. The compiler needs the first as a framework search path, and the test runner needs both as rpaths.

`swift_test.py` asks `xcode-select -p` which developer directory is selected. If that directory holds `Library/Developer/Frameworks/Testing.framework` and has no `Platforms` directory, whatever it's called, it runs `swift test --package-path launcher` with these added, for that directory:

```
-Xswiftc -F -Xswiftc DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/usr/lib
```

Xcode's developer directory has a `Platforms` directory, so with Xcode selected it adds nothing. The launcher job on GitHub's runner logs a command with no added flags. The flags aren't `unsafeFlags` in `Package.swift`, because that would bake one Mac's paths into the package.
