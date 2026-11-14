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

When that first read brings a banner, its pixels fly in over 900 ms on the Build step, or on Library after Change Disc. After Play checks a disc with no banner cached, the banner arrives while the launch card covers Library, so its flight isn't seen, and the card's wordmark gives way to the banner at once. Each pixel sets off from up to 520 points down and to the left after a wait of up to 45% of the time and slows into place, trailing a streak of its own color. Under Reduce Motion the banner fades in instead. A banner loaded from the cache at start just shows.

`Dragoon --dump-banner DISC OUT.png` writes the banner as a PNG and prints its format and names as JSON, with the time the read and decode took on stderr. It exits 0 when the PNG is written and 2 for a bad argument. It exits 1 when DISC is a folder or isn't a regular file, when the disc can't be opened, when it has no banner and when the PNG can't be written, and says which on stderr. Only a regular file opens, and a FIFO is refused without waiting for a writer. On the supported disc on 2026-11-13 the read and decode took 0.21 ms, and the whole command 0.20 s.

## settings.txt

The game's working directory is `<data>`, so `<data>/settings.txt` is the file it reads its picture and disc speed from as it starts, and the file its Display page saves (gcn-recomp `runtime/settings.h`). `PictureSettings` in `DragoonCore` reads the four keys the engine saves, `aspect`, `fullscreen`, `scale` and `disc`, as `settings_load` does. The last line of a key whose value the engine takes wins, and a missing file gives the engine's defaults, 4:3, a window, scale 2 and fast.

A save sets those four keys as `settings_save` does, through `SettingsText`, which works on the file's bytes. Each line of one of them is rewritten, and one the file lacks goes at the end in the line ending of the file's first newline. Every other line is kept byte for byte, comments, blank lines, unknown keys, bytes that aren't UTF-8 and a byte order mark included. The new file goes to `settings.txt.tmp` and is renamed over the old one, and a save that fails leaves the old file whole. Nothing is written for an aspect or scale the engine's load would skip, or when a file is there that can't be read.

The 19 cases in `Tests/DragoonCoreTests/SettingsFixtures/` come from `tools/settings_fixtures.py`, which builds a harness against the pinned gcn-recomp's own `runtime/settings.cpp` and `runtime/platform.cpp` and runs its `settings_save`, and `tools/test_settings_fixtures.py` checks it writes every committed file byte for byte. Each `.in` is the file before a save, and each `.out` what the engine wrote over it with the values `cases.txt` gives. `PictureSettingsTests` saves the same values over each `.in`, on the real file system and on `FakeFileSystem`, and checks the launcher writes the `.out` byte for byte.

## The Settings sheet

Settings in Library's "..." menu reads `settings.txt` and opens a sheet on it with the game's aspect, fullscreen and scale. The aspects are the game's Display page's, in its order and with its labels: 4:3, 16:9, 16:10, 21:9 and Fill window. Scale offers 1x to 8x, as the page does, since the renderer draws at 8x at most. A file's scale over 8 marks 8x, and an aspect the sheet doesn't offer marks none, with a note that settings.txt sets it, until the player picks one.

Each pick is saved at once. The flow saves only while Library is idle, so never while the game runs, which reads the file as it starts and saves it from its Display page. Settings is off while any game runs, an earlier launcher's included, and Play waits while the sheet is open. A save that fails says why in the sheet, the file is as it was, and the sheet goes back to what the file holds, so picking the same again tries again.

The preview draws the game's window, or the screen when fullscreen is on, 120 points high and as wide as its shape. Its sizes come from `PictureGeometry` in `DragoonCore`, which follows gcn-recomp's `runtime/gx/aspect.h`. The window opens at 960 points high and as wide as the aspect makes that, or the largest of that shape that fits the display's usable area less a 40 point title bar, as `main.cpp` places it. Fill window opens at 4:3. Fullscreen fits the picture to the screen with `fit_aspect`'s bars, and Fill window fills it. In the frame is a horizon, a track and the race HUD's boxes, all sized by the picture's height, so a wider aspect shows more of the track at the sides. The boxes sit where `docs/dev/widescreen.md`'s 16:9 dumps of the race have them: the position at the left, the timer in the middle, and the lap count, the minimap and the speedometer at the right. Each keeps its 4:3 size and its 4:3 distance to the picture's left edge, middle or right edge, and a dashed 4:3 frame in the middle is where the menus, text boxes and movie stay. The note under it says so for 16:9, where `docs/dev/status.md`'s HUD row measured it, and for 16:10 and 21:9, which `tests/src/test_hud_anchors.cpp` checks through the anchor arithmetic and the menu camera's mark at each. It also says the pause menu and Top Ride's HUD stretch. Top Ride's 38 HUD draws measured stretched, and the pause menu follows from the menu cameras being centered only in a frame with no world view, which no dump has checked (`widescreen.md`'s list of what 16:9 still gets wrong). Scale says what the renderer draws at, 640x480 times the scale, before the picture is stretched to its shape, beside an edge drawn in pixels of that scale's size.

From Settings to the sheet drawn takes 55 to 71 ms in `SettingsSheetTests` run alone, where the sheet is the first SwiftUI view the process draws, and 17 to 19 ms in the full suite. That covers the press, the read of a real `settings.txt`, its result and an `NSHostingView` laid out and drawn. The sheet's slide in isn't counted.

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
| Logo | The banner at 4x, 384x128 points, with its pixels kept square, over a blurred copy of itself. With no banner, "Dragoon" set in type. Left out when the window is too short for it above the boxes and the bar. An open `panic.txt` comes first, so its scroller has its full 150 points before the logo shows |
| Play bar | A 64 point Play button, a line saying what Play is doing and a "..." menu with Rebuild, Change Disc, Show Saves and Settings |
| Rebuild offer | A strip above the bar |
| Game problem | A card above the bar, whose Show panic.txt opens the file's text |
| Launch card | What Play grows into, over everything else, from Play until the game's window is up and again as the window comes back after the game |

`BannerPalette` in `DragoonCore` picks the two hues. Each opaque pixel whose channels are at least 48 of 255 apart goes into one of 12 buckets 30° wide, by its hue. The fullest bucket gives the first hue and the next fullest the second, each the mean hue of its pixels. The two buckets beside the first never give the second. With no banner, or no pixel with a hue, they're teal and magenta. Play's text is white or a near-black gray of 0.08, whichever has more contrast with the button. The button runs from brightness 0.86 at its top to 0.70 at its bottom, and the label covers rows 21 to 45 of its 64 points, from the top of the "l" to the bottom of the "y". Each ink counts its contrast where it's worst behind the label: white at row 21, brightness 0.81, and near-black at row 45, brightness 0.75. Over every whole degree of hue the ink chosen has at least 4.0:1, and the worst, at 21.6°, is 4.01:1. Play's label is 24 point bold, which WCAG counts as large text, so it passes WCAG's 3:1 for large text. It doesn't pass 4.5:1, the bar for body text.

The streaks are Core Animation layers that the window server moves at up to 30 frames a second, so a frame costs the launcher nothing. They stop while the window isn't key or is covered and while the game runs. Under Reduce Motion they're drawn at rest. A SwiftUI `Canvas` in a `TimelineView` at 30 frames a second, as first designed, cost 4 to 7% of a core, nearly all of it AppKit's layout and display pass for each frame.

Measured on 2026-11-13 on macOS 26.6.2 with `idle_cpu.py` over 60 seconds, on a release build with the disc's banner. The window can't be made key from a script, so the moving streaks were measured on a copy built to keep them moving without it.

| Library | Share of a core |
|---|---|
| Streaks moving | 0.02% |
| Window not key, streaks stopped | 0.02% |
| App hidden | 0.02% |

## The build page

A build shows one bar in segments, each as wide as its step took on the Mac it was measured on. Recompile took 4.2 s there and compile and link 18.0 s. The warm-up took 72.7 s and the package 0.1 s, as `tools/README.md` has them. The swap wasn't timed, so it gets the 0.2 s left of that build's 95.2 s, and package and swap make a sliver at the end. `BuildProgress` in `DragoonCore` keeps the recipe's events and the moments they came. The bar moves only on an event and never goes back. It's full only once `done` comes.

| Step | What the recipe tells the bar | What the page shows |
|---|---|---|
| Recompile | Its start | A shimmer in its segment, since it prints no progress |
| Compile | A progress event as make starts each file | "41 of 135 files" |
| Warm-up | A progress event as each run ends | "3 of 8 runs done" |
| Package, swap | Their start | A shimmer across the sliver they share, since they print no progress |

The time left comes once a step has 3 counts. It's the step's rate across its newest 30 counts, as DuckStation's loading screen takes it (`fullscreenui_widgets.cpp:7144-7181`), plus each later step's measured time scaled by this Mac's ratio on the steps it has finished. A step that didn't count all its work, as a warm-up whose cache was current, stays out of the ratio. Before recompile the recipe prints a `plan` event that says whether the warm-up will play. It won't under `--no-warmup` or when the player's shader cache is current by `warm_shaders.py`'s own stamp check, and then the warm-up's 72.7 s stays out of the time left and its segment out of the bar, whose other segments share its width by their measured times. The estimate changes only on an event.

Make prints quickly, so `ProgressThrottle` lets a progress event through at most every 0.1 s and holds the newest in between, and `ThrottledSend`, beside it in `DragoonCore`, sends the held one once it's due. The banner goes from gray to its own colors with the bar. When the build is done the glow behind it pulses once and the bar becomes Play. The page stays until Play or Back to Library, with Library current in the list. Under Reduce Motion the shimmer fades up and down in place, the glow only fades up and the bar fades into Play.

The clock ticks once a second. It stops only while none of the window can be seen, as when it's covered, minimized or hidden, so a player who clicks another app still sees it go on. The shimmer stops too while the window isn't key. That saves the launcher nothing it can measure, 0.20% against 0.22% with the shimmer moving, but the window server measured 0.27% against 0.57% of a core in the same runs, one run each.

Measured on 2026-11-14 with `idle_cpu.py` over 60 seconds, on a release build of a scratch copy that opens on the build page with the test banner and made-up events, and that counts the window as key unless noted.

| Build page | Share of a core |
|---|---|
| Recompile, shimmer and clock | 0.22% |
| Warm-up between runs, clock only | 0.20% |
| Recompile, window seen but not key, clock only | 0.20% |
| Window covered or hidden, nothing moving | 0.00% |
| Finished, after the pulse | 0.00% |
| 8 compile events a second | 2.8-3.4% |

The page first used 11.2% of a core through the compile. Rolling make's count with `.numericText()` on each file kept SwiftUI drawing, and so did easing the banner's color on each step. A count now rolls only when it changes at most twice a second, as the warm-up's do. The banner eases only into and out of gray.

## Launching the game

`GameLauncher.play(game:disc:data:)` starts `<data>/game/current/Dragoon.app/Contents/MacOS/dragoon` with `Process`, where `<data>` is `~/Library/Application Support/Dragoon`. The disc image's path is its one argument and `<data>` is its working directory, since the runtime finds `saves/` and writes `panic.txt` relative to that. What the game prints on stdout and stderr goes to `~/Library/Logs/Dragoon/game-<time>.log`, and the newest 10 game logs stay, pruned by the same code as the build logs.

Each launch ends in one result, which says how the game ended or why it couldn't start. After a nonzero exit or a signal, Library shows the code or the signal's number and name, and Show panic.txt opens the text of `panic.txt` when the runtime wrote one. A zero exit shows nothing.

Only a regular file at `panic.txt` is read. A link isn't followed and a FIFO isn't waited on. Library shows at most the file's first 64 KB, with a note when there's more.

That `panic.txt` then moves into the logs folder as `panic-<time>.txt`, under a name no other file has, so it never replaces one. A `panic.txt` that's there before the game starts is from an earlier run, so it moves there first and is never shown. One that can't be moved stays in `<data>` and still isn't shown, since only a `panic.txt` written after the launch began is shown.

Each `play` effect carries a launch number that its result echoes, and `Flow` ignores a result for any other launch. A late result can't end a game that's running.

## The hand-off to the game

Play grows into the launch card, which fills the window, by `matchedGeometryEffect` from the Play button. The bookmark is resolved and the disc checked behind it, while a `phaseAnimator` takes the card from idle to charge and back. At charge the glow behind the logo builds, the logo grows to 1.03 times its size and the streaks run at 2.5 times their speed. Once the game has started the logo springs to 1.08 and the streaks run at 6 times. A phase animator ends each run on its first phase, so the launch step is a spring on the flow's state instead. A disc that isn't there or fails its check takes the card down. Under Reduce Motion the card only fades, the logo keeps its size and the streaks stay at rest.

The game gets `GCN_READY_FILE=<data>/ready.txt`. The engine appends `window <ms>` at the first frame its window shows and `frame <ms>` at the game's first frame, each once, in milliseconds since its process started (gcn-recomp `runtime/ready_file.h`). An earlier run's file stays until this run's first line replaces it, and the launcher would read its `window` line as this run's and hide at once, so the file and its `.tmp` are removed before the game starts, and again once it ends. Only whole lines count, and a line that isn't `window` or `frame`, one space and a whole number is skipped.

The engine replaces the file through its `.tmp` at each line, so `ReadyWatcher` watches the data folder with a `DispatchSource` and reads the file at each change. It reads once as it begins, so a line written before then isn't missed. It stops once both lines are in or the game ends, and nothing runs between changes.

| Event | The launcher |
|---|---|
| The `window` line | Fades its window out over 0.25 s, then hides the app |
| 20 s after the game started with no `window` line | The same, and logs that it timed out. An engine from before the ready file writes nothing, and a slow disc or a first run's shader compiles can hold the line back, so the wait is long |
| The game ends or can't start | Fades its window back in with the card up, then the card shrinks back into Play |

The launcher hides on nothing else. With an engine that writes the file, its window goes only once the game's window has shown a frame.

Once the game's window is up the launcher may not be the active app. On macOS 26.6 an inactive app's fade doesn't move, nor does its completion handler run, so a timer of the fade's length ends it. `NSApplication.hide` does nothing for an inactive app, and then the window stays clear and lets clicks through until the game ends. Ordering the window out would quit the launcher, since SwiftUI ends an app whose one `Window` goes. While the game runs the launcher holds a `ProcessInfo` activity against App Nap, which once held the game's exit for over 2 minutes before its termination handler ran.

The times from Play to the game's window and to its first frame go in the system log, under the subsystem `io.github.lunchbox-recomp.dragoon` and the category `launch`, as `Play to the game's window 572 ms, to its first frame 1072 ms`. Play's time comes from the launcher's clock and the game's start from the kernel. The lines count from that start. `LaunchTimingTests` measures the launcher's own times to the game's start and to the hide on a fake game, and the window and frame times there are the fake's.

While the game runs, `<data>/game.pid` holds its pid and the time its process started, and the file goes as the result is sent. A launcher that opens in the meantime takes the game as running when that pid's process started at that time and runs the installed game. Library counts it as running until a kqueue process source sees it exit, and then shows nothing, since how it ended can't be known. The launcher holds the same activity against App Nap while it waits.

A `game.pid` that's garbled is removed and ignored, and so is one whose process has gone or isn't the game.

## Snapshots

`SnapshotTests` renders the window on each screen in `Tests/DragoonViewsTests/ScreenFixtures.swift` with SwiftUI's `ImageRenderer`, at 960x600 points and scale 2 in dark appearance on a fixed dark gray, then averages each 2x2 block of pixels into one. It compares each render with the PNG of the same name in `Tests/DragoonViewsTests/Snapshots/`. Library with the rebuild offer and a 40-line panic shown also renders at 820x520, the smallest the window goes, and at 960x558. `ImageRenderer` draws the panic's scroller as nothing, so `LibraryLayoutTests` lays that state out in an `NSHostingView` at every height from 520 to 700 points and checks the scroller is 150 points at each. A render passes when at most 100 of its pixels, of 576,000 at 960x600, have a color channel more than 16 of 255 away from the PNG's. On the Mac that recorded them every screen has 0. Quit changed to Exit on the must-move screen has 223 against its PNG, and the two buttons rendered alone have 211. Changing "play." to "play!" beside Play moves fewer than 100, so `StringsTests` checks that each of Library's sentences ends in a full stop or an ellipsis. The 100 leave room for text edges another macOS draws a little differently, which hasn't been measured. A failing render is written to `launcher/.build/snapshot-failures/` under its name, and the failure names the file.

```
RECORD=1 launcher/tools/swift_test.py --filter SnapshotTests
```

That writes every PNG again. Look at each one before committing it.

Library's streaks, the launch card, the build bar's shimmer and the build page's clock read `animationClock` from the environment. The tests fix the clock at 2027-01-15 08:00 UTC, so a render draws the same frame every time. The streaks and the shimmer move with Core Animation in the window, which `ImageRenderer` can't draw, so under a fixed clock the streaks are drawn in a `Canvas` at that moment, at the card's rate, and the shimmer's band where it is then. Under a fixed clock the card draws its step's phase with no phase animator, in `launch-card-idle`, `-charge` and `-launch`. `library-reduce-motion` and `launch-card-reduce-motion` draw the streaks at rest. The build page's fixtures draw 0.8 s later, half a shimmer on, where the band sits in the middle of its segment and the Reduce Motion fade is at its brightest. The page's snapshot sees the shimmer, but only `BuildPageTests`, which draws the bar on its own, checks that the shimmer lights the running step's segment and nothing else.

The PNGs hold only the launcher's own UI. Library and Build show the disc's banner, and their fixtures use `TestBanner`, a made-up pattern the tests build, never a real banner.

`SettingsSnapshotTests` renders the Settings sheet alone at its 640x500 points, since `ImageRenderer` doesn't draw a sheet over the window. It draws each aspect in a window, 4:3 and 21:9 fullscreen, and a save that failed, on a 1920x1080 point display whose usable area is 1920x1050, in `TestBanner`'s colors. `SettingsPreviewTests` checks the preview's window against every row of `window-sizes.txt` and its fullscreen screen and picture against every row of `fits.txt`, and its menus' frame and HUD boxes for every aspect, scale 1 to 8 and 12, windowed and fullscreen, on that display, on a 1512x982 one and on none. `PictureGeometryTests` checks `PictureGeometry` against `window-sizes.txt`, `fits.txt` and `scales.txt` in `SettingsFixtures/`, which `tools/settings_fixtures.py` prints from the engine's `aspect.h` and `kMaxInternalScale`.

The PNGs are RGB with every row Paeth-filtered and deflated at zlib's level 9 by `PNGEncoder`. ImageIO's own encoder deflates at its fastest level, and with all its row filters on its PNGs came to 1.3 MB for 19 screens at scale 2. SwiftUI dithers its gradients, which left each new Library PNG at about 700 KB, so a recorded PNG is the render averaged down to one pixel a point with each channel rounded to a multiple of 8. The 47 PNGs come to 1,720 KB, from 3 to 112 KB each.

Measured on 2026-11-13 on macOS 26.6.2 with the Command Line Tools 26.6 and Swift 6.3.3, `ImageRenderer` can't draw three of the views the window uses. The results are the same with `NSApplication.shared` made first.

| View | Drawn as | Where |
|---|---|---|
| `ProgressView`, spinning or as a bar | A yellow box with a red "no" sign, SwiftUI's stand-in for a view AppKit draws | The checking screens |
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
