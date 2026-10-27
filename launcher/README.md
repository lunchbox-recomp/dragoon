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

The choice is kept in `toolchain.json` in `~/Library/Application Support/Dragoon`. It's used only while the developer directory and the tool paths match and the first line of `clang --version` hasn't changed. A different developer directory or tool path forces a probe too, and so does an SDK that's gone.

## The disc check

`Dragoon --check-disc PATH` checks a disc image against the `source-info.json` in the app's source snapshot and prints the result as JSON. `--source-info FILE` names another one when the binary isn't inside the app, and it can come before or after `--check-disc`. The exit code is 0 for `ok`, 1 for any other result and 2 for a bad argument or a source-info it can't use.

The result is `ok`, `wrongGame` with the disc ID it found, `wrongRevision` with the SHA-1 of the main.dol it found, `needsConversion` with `RVZ`, `GCZ`, `WIA` or `WBFS`, or `unreadable` with a reason. A file that can't be opened, ends early or has a main.dol with no sections is `unreadable`.

It reads a disc the way `gcn-recomp/recomp/extract_dol.py` does. The disc ID is the first 6 bytes, and main.dol starts at the big-endian word at 0x420. Its length is the largest offset plus size among the 18 sections in its header that have a size, and the SHA-1 covers that many bytes.

A CISO is a 0x8000-byte header followed by the blocks its map marks with a 1. Any other block reads as zeros.

An `RVZ`, `GCZ`, `WIA` or `WBFS` image is named by its magic and has to be converted first. The magics come from Dolphin's `Source/Core/DiscIO/`.

The recipe's reader hashes whatever it gets from a short file. The check says `unreadable` there, and for a CISO read past the blocks its map covers.

The image is read through a file handle a piece at a time, with no read over 1 MiB. A 1.4 GB disc doesn't cost 1.4 GB of memory.

## Why a wrapper runs the tests

The Command Line Tools ship Swift Testing, but not where `swift test` looks. `Testing.framework` is in `/Library/Developer/CommandLineTools/Library/Developer/Frameworks` and `lib_TestingInterop.dylib` is in `.../Library/Developer/usr/lib`. The compiler needs the first as a framework search path, and the test runner needs both as rpaths.

`swift_test.py` asks `xcode-select -p` which developer directory is selected. If that directory holds `Library/Developer/Frameworks/Testing.framework` and has no `Platforms` directory, whatever it's called, it runs `swift test --package-path launcher` with these added, for that directory:

```
-Xswiftc -F -Xswiftc DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/usr/lib
```

Xcode's developer directory has a `Platforms` directory, so with Xcode selected it adds nothing. The launcher job on GitHub's runner logs a command with no added flags. The flags aren't `unsafeFlags` in `Package.swift`, because that would bake one Mac's paths into the package.
