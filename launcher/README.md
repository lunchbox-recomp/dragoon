# Launcher

The macOS launcher for Dragoon, as a SwiftPM package meant to build with the Command Line Tools alone. `Dragoon` is the SwiftUI app and stays thin. `DragoonCore` holds everything that can be tested, including the `ProcessRunner` and `FileSystem` protocols. Each has a real version in `Sources/DragoonCore/` and a fake in `Tests/DragoonCoreTests/`, and one set of tests runs against both file systems.

```
env SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk swift build --package-path launcher
env SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk swift test --package-path launcher
```

## On this Mac

Measured on 2026-10-22 on an M4 Max with macOS 26.6.2 and the Command Line Tools 26.6 (`CLTools_Executables` 26.6.0.0.1781586589), with no Xcode. Neither command above runs here yet.

| What was run | Result |
|---|---|
| `swift build` or `swift test`, with or without `SDKROOT` | Stops in dyld before reading the package. `swift-package` needs a symbol its `BuildServerProtocol.framework` doesn't have |
| `swiftc` on the default SDK, `MacOSX27.0.sdk` | Refused, since that SDK was built by Swift 6.4 and the tools' compiler is 6.3.3 |
| `swiftc` on `MacOSX26.5.sdk` | `DragoonCore` compiles in Swift 6 mode and the app links |
| `swiftc` on the tests | The fakes compile. The Swift Testing files don't, because the tools' macro plugin expands `@Test` with an argument their `Testing.framework` no longer takes |

The tools hold files from two builds under one package receipt. `swift-package`, the compiler and `libTestingMacros.dylib` are dated June 8, while `Testing.framework` (August 25), SwiftPM's `BuildServerProtocol.framework` (September 1) and the 27.0 SDK are newer. So the package's tests haven't run on this Mac, and the 26.5 SDK above comes from the `swiftc` runs.
