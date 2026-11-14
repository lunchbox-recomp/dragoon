# Launcher

The macOS launcher for Dragoon, as a SwiftPM package that builds with the Command Line Tools alone. `Dragoon` is the SwiftUI app and stays thin. `DragoonViews` holds the window's views and strings so tests can render them. `DragoonCore` holds everything else that can be tested. That includes the `ProcessRunner` and `FileSystem` protocols, which each have a real version in `Sources/DragoonCore/` and a fake in `Tests/DragoonCoreTests/`, and one set of tests runs against both file systems.

```
swift build --package-path launcher
launcher/tools/swift_test.py
```

Every argument after `swift_test.py` goes to `swift test`, `--help` included, so `launcher/tools/swift_test.py --filter FileSystemTests` runs one suite and the wrapper has no help of its own. Its tests are in `launcher/tools/test_swift_test.py`, and the other launcher tools live beside it.

## With only the Command Line Tools

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

The choice is kept in `toolchain.json` in `~/Library/Application Support/Dragoon`. It's used only while the developer directory, the tool paths and the first line of `clang --version` match and its SDK is still there.

## The disc check

`Dragoon --check-disc PATH` checks a disc image against the `source-info.json` in the app's source snapshot and prints the result as JSON. `--source-info FILE` names another one when the binary isn't inside the app, and it can come before or after `--check-disc`. The exit code is 0 for `ok`, 1 for any other result and 2 for a bad argument or a source-info it can't use.

| Result | When | Carries |
|---|---|---|
| `ok` | The right game and revision | |
| `wrongGame` | Another game | The disc ID found |
| `wrongRevision` | Another build of the right game | The main.dol's SHA-1 |
| `needsConversion` | An RVZ, GCZ, WIA or WBFS image | The format |
| `unreadable` | It can't be opened, ends early or its main.dol has no sections | A reason |

It reads a disc the way `gcn-recomp/recomp/extract_dol.py` does. The disc ID is the first 6 bytes, and main.dol starts at the big-endian word at 0x420. Its length is the largest offset plus size among the 18 sections in its header that have a size, and the SHA-1 covers that many bytes.

A CISO is a 0x8000-byte header followed by the blocks its map marks with a 1. Any other block reads as zeros.

The magics that name a `needsConversion` format come from Dolphin's `Source/Core/DiscIO/`.

`extract_dol.py` stops with a Python error when the file ends before the DOL offset or the DOL's section table, and hashes what it gets when the file ends later in the DOL. The check says `unreadable` for all of these, and for a CISO read past the blocks its map covers.

The image is read through a file handle at most 1 MiB at a time, so a 1.4 GB disc never costs 1.4 GB of memory.

## The disc banner

`DiscBanner.read(at:)` reads the `opening.bnr` on a disc's root, from a plain image or a CISO. The only reads are the disc's first 0x440 bytes, its file system table and the banner. On the supported disc that's 0x440 + 0x2478 + 0x1960 bytes.

There's no banner when the table is under 12 bytes or over 1 MiB, its entries don't fit in it, its last byte isn't NUL or a name starts past its end. Only the root's own files count, and the name has to be `opening.bnr` exactly.

A banner is `BNR1` and 0x1960 bytes, or `BNR2` and 0x1FA0 bytes, the pairs Dolphin's `VolumeGC.cpp` takes. Its 96x32 picture decodes from RGB5A3 tiles to RGBA. Dolphin lays the picture on black, and here it keeps its alpha. Its strings are Shift-JIS when the disc ID's fourth character is `J` and Windows-1252 otherwise. Dolphin picks Shift-JIS by the region word at 0x458 instead, when it says NTSC-J (`Volume.cpp`'s `DecodeString` and `VolumeGC.cpp`'s `GetRegion`), so the two differ only on a disc whose ID and region word disagree.

The first time a disc passes its check with no banner cached, the launcher reads the banner and keeps the file as the disc holds it in `disc/opening.bnr` in `~/Library/Application Support/Dragoon`. It loads that file at start, so Library has the banner with the drive unplugged. A disc that fails its check is never read for one.

When that first read brings a banner, its pixels fly in over 900 ms on the Build step, or on Library when the game is already built. Each sets off from up to 520 points down and to the left after a wait of up to 45% of the time and slows into place, trailing a streak of its own color. Under Reduce Motion the banner fades in instead. A banner loaded from the cache at start just shows.

`Dragoon --dump-banner DISC OUT.png` writes the banner as a PNG and prints its format and names as JSON, with the time the read and decode took on stderr. It exits 0 when the PNG is written and 2 for a bad argument. It exits 1 when the disc can't be opened, when it has no banner and when the PNG can't be written, and says which on stderr. On the supported disc on 2026-11-13 the read and decode took 0.21 ms, and the whole command 0.20 s.

## Running the recipe

`BuildRunner.run(_:)` runs the build recipe with the tools the tools check found and gives its JSON lines back as `BuildEvent` values. The command is `<python3> -B -s <bundle>/Contents/Resources/source/tools/launcher_build.py` and then the recipe's options as a list, so a path with spaces stays one argument. `-B` keeps `__pycache__` out of the signed bundle, `-s` keeps the player's user site-packages off the path, and the kit comes from `Contents/Resources/kit`.

The recipe gets an environment of its own with a fixed `PATH`, `HOME`, `TMPDIR`, `LANG`, `PYTHONDONTWRITEBYTECODE`, `PYTHONNOUSERSITE` and `DEVELOPER_DIR`. Nothing from the player's shell reaches its Python.

It starts as the leader of a new process group, so the recipe, make, clang and the warm-up's game stop together. `BuildRunner.cancel()` or dropping the stream sends that group SIGTERM, and SIGKILL 10 seconds later if anything is left. Every `SystemProcessRunner` call starts its process this way too, so canceling a task that waits on `Toolchain.detect` stops its command the same way.

A stdout line that isn't an event is logged and never counted as an error. Everything the recipe prints on stderr is logged too. Both go into `~/Library/Logs/Dragoon/build-<time>.log` beside what the recipe writes there, and the newest 10 build logs stay.

The recipe's exit code decides how the stream ends.

| Exit or call | The stream |
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

During setup the window has the steps on the left and the current step on the right. Library has a layout of its own with no list. What it does is `Flow`, a pure state machine in `DragoonCore` whose `reduce` takes a state and an event and gives the next state and a list of effects. The app carries out each effect and sends its result back as an event, so the tests drive every path with no window, the tools check's 5 second timer included.

The first run walks the steps in order from Welcome down to Library, and every later launch with a built game opens on Library. While the tools are missing, the Tools step offers Apple's installer and looks for them again every 5 seconds. Before each build the launcher wants 2 GB free by `volumeAvailableCapacityForImportantUsage`, then resolves the disc's bookmark and checks the disc, then checks the tools.

Play resolves the bookmark and checks the disc too. A stale bookmark or a disc that's gone goes back to the Disc step, and the game stays where it was. Look Again tries the bookmark again only for a disc that's gone, such as one on an unplugged drive.

From the `play` effect until its result comes back, Library counts the game as running and keeps Play, Rebuild and Change Disc off.

A launcher whose path holds `/AppTranslocation/`, or that's on a read-only volume, asks to be moved to Applications and does nothing else. So does one whose path holds a character the kit's Makefile refuses, which is `$`, `"`, a backtick, `:` or `;`. Finder shows a `:` in a folder's name as `/`, so that's how the window names it.

Library offers a rebuild when `game/current/stamp.json` names other commits than the app's `source-info.json` or can't be read, and the old game plays until a rebuild starts. A rebuild that fails or is canceled leaves the old game current. Builds other than the current one are deleted while no game or build is running.

`launcher.json` in `~/Library/Application Support/Dragoon` keeps the disc's bookmark and whether Welcome was seen. Every string the window shows is in `Sources/DragoonViews/Strings.swift`.

The window is dark whatever the system's appearance. Its title bar is hidden, and it opens at 960x600 points and goes no smaller than 820x520.

## Library

Library fills the window, in the disc banner's colors.

| Part | What it is |
|---|---|
| Hero | The banner's first hue fading down to near-black, with 56 speed streaks drifting up and to the right |
| Logo | The banner at 4x, 384x128 points, with its pixels kept square, over a blurred copy of itself. With no banner, "Dragoon" set in type. Left out when the window is too short for it above the boxes and the bar |
| Play bar | A 64 point Play button, a line saying what Play is doing and a "..." menu with Rebuild, Change Disc and Show Saves |
| Rebuild offer | A strip above the bar |
| Game problem | A card above the bar, whose Show panic.txt opens the file's text |

`BannerPalette` in `DragoonCore` picks the two hues. Each opaque pixel whose channels are at least 48 of 255 apart goes into one of 12 buckets 30° wide, by its hue. The fullest bucket gives the first hue and the next fullest the second, each the mean hue of its pixels. The two buckets beside the first never give the second. With no banner, or no pixel with a hue, they're teal and magenta. Play's text is white or a near-black gray of 0.08, whichever has more contrast with the button. Each ink counts its lower contrast of two, at the gradient's middle where the text sits and at its darker end. Over every whole degree of hue the ink chosen has at least 3.9:1. Play's label is 24 point bold, which WCAG counts as large text, so it passes WCAG's 3:1 for large text. It doesn't pass 4.5:1, the bar for body text.

The streaks are Core Animation layers that the window server moves at up to 30 frames a second, so a frame costs the launcher nothing. They stop while the window isn't key or is covered and while the game runs. Under Reduce Motion they're drawn at rest. A SwiftUI `Canvas` in a `TimelineView` at 30 frames a second, as first designed, cost 4 to 7% of a core, nearly all of it AppKit's layout and display pass for each frame.

Measured on 2026-11-13 on macOS 26.6.2 with `idle_cpu.py` over 60 seconds, on a release build with the disc's banner. The window can't be made key from a script, so the moving streaks were measured on a copy built to keep them moving without it.

| Library | Share of a core |
|---|---|
| Streaks moving | 0.02% |
| Window not key, streaks stopped | 0.02% |
| App hidden | 0.02% |

## Launching the game

`GameLauncher.play(game:disc:data:)` starts `<data>/game/current/Dragoon.app/Contents/MacOS/dragoon` with `Process`, where `<data>` is `~/Library/Application Support/Dragoon`. The disc image's path is its one argument and `<data>` is its working directory, since the runtime finds `saves/` and writes `panic.txt` relative to that. What the game prints on stdout and stderr goes to `~/Library/Logs/Dragoon/game-<time>.log`, and the newest 10 game logs stay, pruned by the same code as the build logs.

Each launch ends in one result, which says how the game ended or why it couldn't start. After a nonzero exit or a signal, Library shows the code or the signal's number and name, and Show panic.txt opens the text of `panic.txt` when the runtime wrote one. A zero exit shows nothing.

Only a regular file at `panic.txt` is read. A link isn't followed and a FIFO isn't waited on. Library shows at most the file's first 64 KB, with a note when there's more.

That `panic.txt` then moves into the logs folder as `panic-<time>.txt`, under a name no other file has, so it never replaces one. A `panic.txt` that's there before the game starts is from an earlier run, so it moves there first and is never shown. One that can't be moved stays in `<data>` and still isn't shown, since only a `panic.txt` written after the launch began is shown.

The window hides while the game runs and comes back when it exits or can't start. Each `play` effect carries a launch number that its result echoes, and `Flow` ignores a result for any other launch. A late result can't end a game that's running.

The launcher hides its window as it starts the game (`Sources/Dragoon/EffectRunner.swift:123-125`), not at the game's first frame. Since gcn-recomp `1abcf10` the game's own window opens on a boot splash, the disc's banner over a dark grey with a bar for the shader cache's load, which stays up until the game's first frame (gcn-recomp `docs/graphics.md`, "The boot splash"). The engine can also tell a launcher when that first frame is up through `GCN_READY_FILE` (gcn-recomp `docs/diagnostics.md`, "Starting a run"), which this launcher doesn't set.

While the game runs, `<data>/game.pid` holds its pid and the time its process started, and the file goes as the result is sent. A launcher that opens in the meantime takes the game as running when that pid's process started at that time and runs the installed game. Library counts it as running until a kqueue process source sees it exit, and then shows nothing, since how it ended can't be known.

A `game.pid` that's garbled is removed and ignored, and so is one whose process has gone or isn't the game.

## Snapshots

`SnapshotTests` renders the window on each screen in `Tests/DragoonViewsTests/ScreenFixtures.swift` with SwiftUI's `ImageRenderer`, at 960x600 points and scale 2 in dark appearance on a fixed dark gray, then averages each 2x2 block of pixels into one. It compares each render with the PNG of the same name in `Tests/DragoonViewsTests/Snapshots/`. Library with the rebuild offer and a 40-line panic shown also renders at 820x520, the smallest the window goes. A render passes when at most 100 of its pixels, of 576,000 at 960x600, have a color channel more than 16 of 255 away from the PNG's. On the Mac that recorded them every screen has 0, and one word changed on a button, Quit to Exit, has 211. The 100 leave room for text edges another macOS draws a little differently, which hasn't been measured. A failing render is written to `launcher/.build/snapshot-failures/` under its name, and the failure names the file.

```
RECORD=1 launcher/tools/swift_test.py --filter SnapshotTests
```

That writes every PNG again. Look at each one before committing it.

Library's streaks are the one view that reads `animationClock` from the environment. The tests fix the clock at 2027-01-15 08:00 UTC, so a render draws the same frame every time. The streaks move with Core Animation in the window, which `ImageRenderer` can't draw, so under a fixed clock they're drawn in a `Canvas` at that moment. `library-reduce-motion` draws them at rest.

The PNGs hold only the launcher's own UI. Library and Build show the disc's banner, and their fixtures use `TestBanner`, a made-up pattern the tests build, never a real banner.

The PNGs are RGB with every row Paeth-filtered and deflated at zlib's level 9 by `PNGEncoder`. ImageIO's own encoder deflates at its fastest level, and with all its row filters on its PNGs came to 1.3 MB for 19 screens at scale 2. SwiftUI dithers its gradients, which left each new Library PNG at about 700 KB, so a recorded PNG is the render averaged down to one pixel a point with each channel rounded to a multiple of 8. The 27 PNGs come to 916 KB, from 3 to 112 KB each.

Measured on 2026-11-13 on macOS 26.6.2 with the Command Line Tools 26.6 and Swift 6.3.3, `ImageRenderer` can't draw three of the views the window uses. The results are the same with `NSApplication.shared` made first.

| View | Drawn as | Where |
|---|---|---|
| `ProgressView`, spinning or as a bar | A yellow box with a red "no" sign, SwiftUI's stand-in for a view AppKit draws | The checking screens and the running build |
| `GroupBox` | Nothing, its contents included | Nowhere now |
| `ScrollView` | Nothing, its contents included | The end of a failed build's log, and a `panic.txt` of over 8 lines or with a line over 100 characters |

So Library draws its strip and card in shapes and a short `panic.txt` as plain text, and its snapshots show them. Apple's documentation says `ImageRenderer` doesn't draw views that AppKit provides. That wasn't checked with Xcode, which this Mac doesn't have.

## Why a wrapper runs the tests

The Command Line Tools keep `Testing.framework` and `lib_TestingInterop.dylib` where neither the compiler nor the test runner looks. `swift_test.py` asks `xcode-select -p` which developer directory is selected. If that directory holds `Library/Developer/Frameworks/Testing.framework` and has no `Platforms` directory, whatever it's called, it runs `swift test --package-path launcher` with these added, for that directory:

```
-Xswiftc -F -Xswiftc DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/Frameworks
-Xlinker -rpath -Xlinker DEV/Library/Developer/usr/lib
```

Xcode's developer directory has a `Platforms` directory, so with Xcode selected it adds nothing. The launcher job on GitHub's runner logs a command with no added flags. The flags aren't `unsafeFlags` in `Package.swift`, because that would bake one Mac's paths into the package.
