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
| `launcher/tools/swift_test.py` | 36 tests in 5 suites pass |
| `Dragoon --check-tools` | Reports `MacOSX26.5.sdk` and the tools under `/Library/Developer/CommandLineTools/usr/bin/` |

## The tools check

`Dragoon --check-tools` prints what `Toolchain.detect` found as JSON and exits without opening a window. The exit code is 0 for a `ready` status and 1 for `missing` or `noLinkableSDK`.

It runs `xcode-select -p` first, because a developer tool shim under `/usr/bin` would open Apple's install prompt. Then `xcrun --find` names `clang`, `clang++`, `make` and `python3` by full path.

The SDK is the first that compiles and links a C++ file that includes `<cstdio>`. With Xcode selected it tries the one `xcrun --show-sdk-path` names first. Then it tries `SDKs/MacOSX.sdk` and every other `MacOSX*.sdk` newest first, except any newer than the tools.

The choice is kept in `toolchain.json` in `~/Library/Application Support/Dragoon`. It's probed again when the first line of `clang --version` changes or the SDK is gone.

## Why a wrapper runs the tests

The Command Line Tools ship Swift Testing, but not where `swift test` looks. `Testing.framework` is in `/Library/Developer/CommandLineTools/Library/Developer/Frameworks` and `lib_TestingInterop.dylib` is in `.../Library/Developer/usr/lib`. The compiler needs the first as a framework search path, and the test runner needs both as rpaths.

`swift_test.py` asks `xcode-select -p` which developer directory is selected. If that directory holds `Library/Developer/Frameworks/Testing.framework` and has no `Platforms` directory, whatever it's called, it runs `swift test --package-path launcher` with these added, for that directory:

```
-Xswiftc -F -Xswiftc DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/usr/lib
```

Xcode's developer directory has a `Platforms` directory, so with Xcode selected it adds nothing. The launcher job on GitHub's runner logs a command with no added flags. The flags aren't `unsafeFlags` in `Package.swift`, because that would bake one Mac's paths into the package.
