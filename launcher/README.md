# Launcher

The macOS launcher for Dragoon, as a SwiftPM package meant to build with the Command Line Tools alone. `Dragoon` is the SwiftUI app and stays thin, and `DragoonCore` holds everything that can be tested. That includes the `ProcessRunner` and `FileSystem` protocols, which each have a real version in `Sources/DragoonCore/` and a fake in `Tests/DragoonCoreTests/`. One set of tests runs against both file systems.

```
swift build --package-path launcher
launcher/tools/swift_test.py
```

Arguments after `swift_test.py` go to `swift test`, so `launcher/tools/swift_test.py --filter FileSystemTests` runs one suite. Its tests are in `launcher/tools/test_swift_test.py`, and the other launcher tools live beside it.

## On this Mac

Measured on 2026-10-26 on macOS 26.6.2 with the Command Line Tools 26.6 (`CLTools_Executables` 26.6.0.0.1781586589) and Swift 6.3.3, with no Xcode.

| What was run | Result |
|---|---|
| `swift build --package-path launcher` | Builds on the default SDK, which is `MacOSX26.5.sdk` now. No `SDKROOT` is needed |
| `swift test --package-path launcher` | Fails with `no such module 'Testing'` |
| `swift test` with only `-Xswiftc -F` | The tests compile, then the runner can't load `Testing.framework` |
| `launcher/tools/swift_test.py` | 11 tests in 3 suites pass |

A run on 2026-10-22 needed `SDKROOT` set to that SDK, because the default then was `MacOSX27.0.sdk` and the tools' compiler refused it. That SDK is gone, so the default links.

## Why a wrapper runs the tests

The Command Line Tools ship Swift Testing, but not where `swift test` looks. `Testing.framework` is in `/Library/Developer/CommandLineTools/Library/Developer/Frameworks` and `lib_TestingInterop.dylib` is in `.../Library/Developer/usr/lib`. The compiler needs the first as a framework search path, and the test runner needs both as rpaths.

`swift_test.py` asks `xcode-select -p` which developer directory is selected. If that's the Command Line Tools and it holds `Library/Developer/Frameworks/Testing.framework`, it runs `swift test --package-path launcher` with these added, for that directory:

```
-Xswiftc -F -Xswiftc DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/usr/lib
```

With Xcode selected it adds nothing, so it runs the same command on GitHub's runner as a bare `swift test` would. The flags aren't `unsafeFlags` in `Package.swift`, because that would bake one Mac's paths into the package.
