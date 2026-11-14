# Status

What's true of Dragoon, measured on one Mac. Most sections name the Dragoon or gcn-recomp
commits they were measured at. The pin is gcn-recomp `5e54665`, where all twenty-four routes'
frames and audio match the goldens recorded at `b5ec329` (under gcn-recomp `5e54665`).

| Feature | Status | Note |
|---|---|---|
| Boot and memory card | Works | A blank card gets the game's prompt by frame 60, and the save file is made. The game writes the card after each title screen and when its Sound screen closes, and in one pair of runs the Sound screen's Mono and balance came back on the next launch. Mono is in the console's SRAM, which gcn-recomp keeps in `saves/sram.raw` (table under Memory card) |
| Opening movie | Plays | Then the title and the attract demos, races and mode movies |
| Title screen | Works | `tests/routes/title.txt` |
| Mode select | Works | `tests/routes/menu.txt`. The preview window at its right shows a race |
| Air Ride race | Runs | All eight courses a blank memory card can pick load and race past the countdown, one route each in `tests/routes/`, with no crash and nothing seen drawn wrong. Fantasy Meadows (`air-ride-race.txt`) has three laps and the other seven two. With nobody steering, six reach the results screen and Kirby stays stopped against a wall on the other two (table under How far it gets). Nebula Belt, the ninth course, is locked on a blank card behind an Air Ride checklist box that counts 100 laps |
| City Trial | Runs | One player (`tests/routes/city-trial.txt`) or four in split screen (`city-trial-4p.txt`), the five-minute clock running. With the clock cut to three minutes and the stadium set to Drag Race in Game Settings, one player (`city-trial-stadium.txt`) or four (`city-trial-stadium-4p.txt`) play out the clock and reach Drag Race 3 and its results. A fresh save offers only Drag Race, Target Flight and Destruction Derby besides Shuffle, and no route plays the last two, though a bot soak reached Destruction Derby's results (under Bot soak) |
| Top Ride | Runs | All seven courses a fresh save offers (Grass, Sand, Sky, Fire, Light, Water and Metal) race past the countdown with one player and three CPUs (`top-ride-<course>.txt`) |
| Audio | Partial | The mixer runs the commands of the game's ucode (`07F88145`) with its compressor among them, and ten runs' 484,400 command lists held no unknown or skipped one (under Audio). Source type 0 voices, 98.9% of the voice time, resample through a polyphase filter whose coefficients the runtime works out because the console's are in the DSP's ROM, and the low-pass filter isn't applied. Nobody has listened for the sound's quality since the source type 2 fix or compared it with a console, and the click counts are in [`scorecard.md`](scorecard.md), last scored at gcn-recomp `dac449e` (`audio.md`) |
| Controllers | Four ports, live | Each gamepad takes the port `saves/ports.txt` says it was last on, or else its SDL player number's or the lowest free one. The overlay menu's Controllers page swaps, removes and orders players by who presses A, and a notice says when a controller connects, disconnects or changes player (under Controllers). GameCube A is the east button on a Nintendo-layout pad such as an 8BitDo in Switch mode. Checked with SDL's virtual gamepads, not with four real controllers or under Steam Input |
| Picture | 4:3, or wider with Air Ride's and City Trial's HUD anchored and the menus centered | The window opens at 4:3. `--aspect=16:9` stretches the picture, and the world cameras widen to match in the race before and after its finish, in City Trial, 2P and 4P and in Top Ride. The HUD keeps its 4:3 shape at the race, City Trial, 2P and 4P checkpoints, anchored to the edges of the screen or of its player's view, as all four showed on Dragoon `1ff85c8`. The title, the menus, the text boxes and the opening movie keep their 4:3 frame in the middle. On Dragoon `2d68a1e` the 16:9 output dumps of the text box, the movie and the course select went from 3414x1920 at 1.7781 to 2560x1920 at 1.3333 with bars of 427, the title from 2.1815 to 1.6351 (1.6358 at 4:3) and the mode select from 1.9094 to 1.4312 (1.4318). Top Ride's HUD, which it draws outside every render callback, and a menu over play stretch with the picture. On Dragoon `ec0004a` `drawlog.py hud` listed Top Ride's 38 HUD draws at 3600 as stretched, and the race after its finish at 8400, City Trial and 2P gave the same results as on `e79f475`. At an output narrower than 4:3 the menus stretch too (`widescreen.md`) |
| Speed | Holds 60 fps | 513 frames a second in a race in a hidden window with `--fast`. `dragoon_bench`, which draws nothing, runs the race at 601. Four-player City Trial averages 16.69 ms a frame at the game's own speed, with two intervals over 20 ms, the worst 42 ms. The stadium's scene changes stall the guest for up to 160 ms (under gcn-recomp `95e1c6b`) |
| Build from the disc | Works | 23 s at gcn-recomp `67a7e30` (3.5 s to configure, 19.5 s for Ninja). That's before the build compiled SDL3 and Dear ImGui and before the default target ran the shader warm-up, which adds about 64 s (`CMakeLists.txt:69-78`, Player targets) |
| Disc check | Works | The wrong disc stops the configure step with the disc ID it found |
| `.gcm` dumps | Work | Linked as `rom/game.iso`, or passed as `-DGAME_ISO=<path>` |
| Disc path with spaces | Works | Configures, and its `dragoon_bench` builds and runs |
| Running from another directory | Works | The configured disc path is compiled in. The memory card and shader cache are in `saves/` in the current folder, so a run from another folder starts with a blank card and compiles shaders as it goes. The overlay menu's Display page writes `settings.txt` in the current folder when it changes the picture, and later runs started there read it |
| Network during the build | SDL and Dear ImGui | The first configure in a build directory downloads SDL 3.4.18's source release (15.7 MB) and Dear ImGui 1.92.9b's (2.1 MB), and checks the SHA-256 of each. `-DGCN_SYSTEM_SDL=ON` uses an installed SDL3 instead. Dear ImGui draws the overlay menu, and `-DGCN_OVERLAY=OFF` builds the game with no menu and doesn't download Dear ImGui |
| Idle loop | Works | `recomp/idle.txt` 803D9FCC is the `IDLE_CHECK` branch in the generated C |

## The build

Measured at gcn-recomp `67a7e30` on an Apple M4 Max (16 cores, 48 GB) on macOS 26.6.2 with the
Command Line Tools SDK 26.5, Apple clang 21.0.0, CMake 4.4.4, Ninja 1.13.2, Python 3.14.7 and
Homebrew's SDL2 2.32.72. Since gcn-recomp `642187a` the build also compiles SDL3 3.4.18, and
since `782d7fa` Dear ImGui, so these times leave out both.

```sh
ln -s "/path/to/Kirby Air Ride (USA).gcm" rom/game.iso
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo
ninja -C build
```

The timed configure also passed
`-DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk`. On the same Mac
a plain configure with no sysroot linked the game at gcn-recomp `782d7fa` on 2026-11-04.

| Step | Wall | CPU | Peak memory |
|---|---|---|---|
| Configure (extract `main.dol`, recompile to C) | 3.5 s | 3.5 s | 99 MB |
| Ninja (183 steps, 137 generated C files plus the runtime) | 19.5 s | 269 s | 684 MB, the largest single process |

Peak memory is the maximum resident set of one process from `/usr/bin/time -l`, not the sum
of the parallel jobs.

| Output | Size |
|---|---|
| `build/` | 631 MB |
| `build/gen/` (generated C) | 101 MB |
| `build/dragoon` | 51.0 MB |
| `build/dragoon_bench` | 50.8 MB |
| `build/libgame_recomp.a` | 195 MB |

The recompiler reads 20,003 functions from `analysis/symbols.txt` and finds 4,573 jump table
targets. It reports no unimplemented instructions and one warning.

```
warning: 803D2C78 branches to non-code 00000060
```

803D2C78 sits between `__OSDBINTEND` and `__OSDBJUMPEND`, the SDK's debugger stub that
jumps to the exception vector at 0x60. The stub is copied to low memory and never runs from
where it sits, so the warning is harmless. The compiler adds one warning, in gcn-recomp's own
renderer.

```
runtime/gx/render_gl_view.cpp:286:13: warning: enumeration value 'Screen' not handled in switch [-Wswitch]
```

### What the build downloads

By default the first configure downloads two source archives. gcn-recomp's `CMakeLists.txt`
pins each by SHA-256, so CMake stops at one that doesn't match. No program from these archives
or from GoogleTest's below was run by hand, only read in `build/_deps/` after configures at
gcn-recomp `782d7fa` with CMake 4.4.4.

| | SDL3 | Dear ImGui |
|---|---|---|
| Archive | `SDL3-3.4.18.tar.gz` from the `release-3.4.18` release of `libsdl-org/SDL` on GitHub, 15,651,004 bytes | `v1.92.9b.tar.gz`, GitHub's archive of the `v1.92.9b` tag of `ocornut/imgui`, 2,123,074 bytes |
| SHA-256, pinned and as downloaded | `9c75cf16330322c217dedd2e0609f1124f1b54b8633e763467b4684d0f4334a3` | `21d8a0a565e85dce943e375db00812c2f3f0ab21f3f0f7964e364a63422d7f99` |
| Version inside | `REVISION.txt` reads `release-3.4.18-0-g829a65d76` | `imgui.h:32` defines `IMGUI_VERSION` as `"1.92.9b"` |
| At configure | `FetchContent_MakeAvailable` runs SDL's own `CMakeLists.txt` with its shared library, tests, examples and install off. Its feature checks compile test programs and run none, and it takes its revision from `REVISION.txt` rather than git. The programs it does run are below the table | The archive has no `CMakeLists.txt` at its top, so `FetchContent_MakeAvailable` only unpacks it |
| At build | `libSDL3.a`. `build.ninja` has no custom command from SDL's scripts | Six files go into `libgcn_imgui.a`: `imgui.cpp`, `imgui_draw.cpp`, `imgui_tables.cpp`, `imgui_widgets.cpp`, `backends/imgui_impl_sdl3.cpp` and `backends/imgui_impl_opengl3.cpp`. No script or custom command from the archive runs |

At CMake 4.4.4, SDL's own `execute_process` calls on macOS run `cmake -E make_directory` and
`cmake -E copy_if_different`. Before CMake 3.29, which the build's minimum of 3.20 allows, one
more runs the linker with `-v` (`CMakeLists.txt:521`, `cmake/macros.cmake:88`).

SDL's `CMakeLists.txt:66` calls `find_package(PkgConfig)` on any CMake. When that finds
pkg-config, CMake's `FindPkgConfig.cmake:530` runs it with `--version` through
`execute_process`, before SDL's `cmake/FindLibUSB.cmake:6-9` asks it for `libusb-1.0>=1.0.16`.
Here that was `/opt/homebrew/bin/pkg-config`, which found 1.0.29 (`PC_LibUSB_VERSION` in
`build/CMakeCache.txt`).

`-DDRAGOON_TESTS=ON` adds a third download, GoogleTest 1.17.0's source release, which Dragoon's
own `CMakeLists.txt:41-45` pins by SHA-256 and CI's macOS job turns on (`tools/ci.py:79-80`).
A configure at gcn-recomp `782d7fa` with no disc and CMake 4.4.4 fetched it.

| | GoogleTest |
|---|---|
| Archive | `googletest-1.17.0.tar.gz` from the `v1.17.0` release of `google/googletest` on GitHub (Dragoon's `CMakeLists.txt:41-45`), 885,595 bytes |
| SHA-256, pinned and as downloaded | `65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c` (Dragoon's `CMakeLists.txt:43`; `shasum -a 256` on the archive) |
| Version inside | The archive's `CMakeLists.txt:7` sets `GOOGLETEST_VERSION` to `1.17.0` |
| At configure | `FetchContent_MakeAvailable` configures GoogleTest with Google Mock and installation off, then defines two libraries; no program built from the archive runs |
| At build | `googletest/src/gtest-all.cc` (which includes nine more `src/*.cc` files) makes `lib/libgtest.a`, and `googletest/src/gtest_main.cc` makes `lib/libgtest_main.a`. Their generated rules have `POST_BUILD = :` |

Dragoon disables Google Mock and installation (Dragoon's `CMakeLists.txt:39-40`). The archive's
`CMakeLists.txt:6-35` selects the GoogleTest subdirectory, whose `googletest/CMakeLists.txt:123-142`
defines both libraries. GoogleTest calls `find_package(Threads)`
(`googletest/cmake/internal_utils.cmake:64-70`), and CMake 4.4.4's `Modules/FindThreads.cmake:157-163`
compiles a test program and runs none.

The archive's CMake files have no `execute_process`, `try_compile` or `try_run`. Its Python3
lookup is conditional on GoogleTest's own tests (`googletest/cmake/internal_utils.cmake:250-251`),
which are off (`googletest/CMakeLists.txt:18`).

The archive's CMake has no custom command, but Dragoon's `gtest_discover_tests(dragoon_tests)`
adds one (Dragoon's `CMakeLists.txt:57`). CMake 4.4.4's `Modules/GoogleTest.cmake:583-587`
defaults discovery to `POST_BUILD`, and its `Modules/GoogleTest.cmake:728-736` runs `cmake -P` on
the discovery file after `dragoon_tests` links.

CMake 4.4.4's `Modules/GoogleTestAddTests.cmake:205-224` runs `dragoon_tests --gtest_list_tests`
with `--gtest_output=json:<build dir>/cmake_test_discovery_<hash>.json`. Discovery has a 5 s
timeout (`Modules/GoogleTest.cmake:580-582`), and a nonzero exit stops the build (CMake 4.4.4's
`Modules/GoogleTestAddTests.cmake:226-241`). Only `gtest` and `gtest_main` were built here,
and the discovery and CTest steps were read from CMake's files, not run.

CI's macOS job runs `ninja unit` (`tools/ci.py:82`), which builds the engine's own unit tests
and runs them under CTest with `--no-tests=error --timeout 300 --output-on-failure`
(`gcn-recomp/CMakeLists.txt:1215-1218`). It builds `dragoon_tests` too and runs it once to list
its tests and once per test (Dragoon's `CMakeLists.txt:60-61`, CMake 4.4.4's
`Modules/GoogleTestAddTests.cmake:63-67`). So CI runs code compiled from this archive.

In the game, SDL opens `libusb-1.0.dylib` with `dlopen` for controllers over USB
(`SDL_LIBUSB_DYNAMIC` in this build's `SDL_build_config.h:333`). Dear ImGui's OpenGL 3 backend
opens the system's OpenGL framework the same way (`imgui_impl_opengl3_loader.h:677`). Dear
ImGui opens a link by forking `open -- <path>` (`imgui.cpp:16320`), and its SDL3 backend swaps
that for `SDL_OpenURL` (`imgui_impl_sdl3.cpp:541`).

Only `TextLinkOpenURL` opens a link (`imgui_widgets.cpp:1578`), and gcn-recomp's overlay calls
no `TextLink` function. Dear ImGui's own tooltip for items with a duplicate ID does, with a link
to its FAQ on GitHub (`imgui.cpp:11380`). Holding Ctrl pins that tooltip so the link can be
clicked (`imgui.cpp:11408`).

`io.ConfigDebugHighlightIdConflicts` turns that tooltip on by default (`imgui.cpp:1712`), and
the overlay leaves it on. Since gcn-recomp `d1a60e5` the overlay clears
`Platform_OpenInShellFn` after both backends start (`runtime/overlay/overlay.cpp:461-463`), and
`TextLinkOpenURL` calls nothing when it's null, so a click on the link opens nothing. Since
`2246986` the tooltip has no Item Picker button (`runtime/overlay/overlay.cpp:444`,
`imgui.cpp:11366`). The overlay also sets `IniFilename` and `LogFilename` to null, so Dear
ImGui writes no file (`runtime/overlay/overlay.cpp:443-445`).

## Disc inputs

gcn-recomp looks only for `rom/*.iso` and `rom/*.ciso`. A `.gcm` is the same format as an
`.iso`, so a symlink named `rom/game.iso` builds. So does
`-DGAME_ISO="/path/to/Kirby Air Ride (USA).gcm"`, spaces and all.

The wrong disc fails at configure, before anything compiles. With Super Mario Sunshine passed
as `GAME_ISO`, `recomp/extract_dol.py` prints this and CMake stops.

```
error: .../Super Mario Sunshine (USA, Canada).gcm is disc b'GMSE01', not b'GKYE01'.
Note: only uncompressed .iso and .ciso images are supported; convert .rvz/.gcz first (see README).
CMake Error at gcn-recomp/CMakeLists.txt:472 (message):
  could not extract main.dol from
```

The disc IDs come out as Python byte strings, and the note about `.rvz` is beside the point
for a wrong disc. Both are gcn-recomp's wording.

`build/dragoon_bench --seconds=20`, run from a directory outside the repo, found
`rom/game.iso` through the path compiled in at configure time. With nobody at the controls it
sits at the memory card prompt and reports 4,770 frames a second there, which says nothing
about speed in play.

## How far it gets

Every checkpoint below was reached by a route in `tests/routes/` from a blank memory card,
run with `tools/probe.sh` (hidden window, `--fast`, 640x480). The four-player routes also
need `--pads=4`.

| Checkpoint | Route | Frame | What's on screen |
|---|---|---|---|
| Memory card | `title.txt` | 60 | The prompt to make a save file on the card in slot A |
| Title | `title.txt` | 960 | The logo and PRESS START/PAUSE |
| Mode select | `menu.txt` | 1200 | Air Ride, Top Ride, City Trial, Options, LAN |
| Fantasy Meadows | `air-ride-race.txt` | 4200 | Lap 1 of 3, 0:14 on the clock, CPUs ahead |
| Celestial Valley | `air-ride-celestial-valley.txt` | 4200 | Lap 1 of 2, 0:14, second, under a night sky with a CPU ahead |
| Sky Sands | `air-ride-sky-sands.txt` | 4200 | Lap 1 of 2, 0:14, second, on pale sand with ruins in the haze |
| Frozen Hillside | `air-ride-frozen-hillside.txt` | 4200 | Lap 1 of 2, 0:14, fourth, in a stone corridor under a purple sky |
| Magma Flows | `air-ride-magma-flows.txt` | 4200 | Lap 1 of 2, 0:14, fourth, on a rock path between lava flows |
| Beanstalk Park | `air-ride-beanstalk-park.txt` | 4200 | Lap 1 of 2, 0:14, first, on a grass slope with beanstalks against the clouds |
| Machine Passage | `air-ride-machine-passage.txt` | 4200 | Lap 1 of 2, 0:14, fourth, stopped against a dark metal wall |
| Checker Knights | `air-ride-checker-knights.txt` | 4200 | Lap 1 of 2, 0:14, fourth, beside the sea with checkered blocks overhead |
| Fantasy Meadows after Sky Sands | `air-ride-courses-1.txt` | 17300 | Lap 1 of 3, 0:14, first, at a tunnel mouth in a burst of light with a spiked enemy overhead |
| Celestial Valley after Fantasy Meadows | `air-ride-courses-1.txt` | 22900 | Lap 1 of 2, 0:14, third, on a grass ledge over the night clouds with two CPUs ahead |
| Machine Passage after Magma Flows | `air-ride-courses-2.txt` | 15600 | Lap 1 of 2, 0:14, fourth, stopped against a dark metal wall |
| Beanstalk Park after Machine Passage | `air-ride-courses-2.txt` | 19400 | Lap 1 of 2, 0:14, third, on a grass slope with CPUs ahead |
| City Trial | `city-trial.txt` | 3300 | The city, 4:54 left |
| Four-player entry | `city-trial-4p.txt` | 2700 | P1 OK to P4 OK under READY?, each player joined from its own port |
| Four-player City Trial | `city-trial-4p.txt` | 3480 | Four views, 4:51 left, ports 1 and 3 steering left and 2 and 4 right |
| Three-minute City Trial | `city-trial-stadium.txt` | 4800 | The city, 2:55 left. The entry screen before it read "Time: 3 min [Drag Race]" |
| Time up | `city-trial-stadium.txt` | 15600 | `TIME!` at 0:00:00, with Kirby seen from behind and the speedometer at the lower right. Each player's machine stats follow and wait for A |
| Machine stats | `city-trial-stadium.txt` | 15900 | Four quarters on a dim green background with PRESS A in the middle, each a list from Boost to HP beside a machine. P1 is at the top left with every value 0 and the other three are marked CPU. The four-player route's stats frames haven't been looked at |
| Drag Race 3 | `city-trial-stadium.txt` | 17100 | Under way, 0:06 on the clock, P1 fourth behind three CPUs |
| Stadium results | `city-trial-stadium.txt` | 20400 | P1 fourth in 0:50.87 behind CPUs on 0:35.83, 0:47.36 and 0:47.62, waiting for START |
| Four-player stadium | `city-trial-stadium-4p.txt` | 17100 | Drag Race 3 in four views, 0:06 on the clock |
| Four-player results | `city-trial-stadium-4p.txt` | 21000 | P3 first in 0:53.31, then P2, P4 and P1 in 1:00.15, under confetti |
| Top Ride race | `top-ride-<course>.txt` | 3600 | Each course 3.63 s into the race. Seven laps on Grass and Sand, six on Sky, Fire and Light, five on Water and Metal |
| Top Ride courses in turn | `top-ride-courses.txt` | 6100 to 18600 | Sand, Sky, Metal, Water, Light and then Fire, every 2,500 frames, each race under way after the one before |

Left alone at gcn-recomp `5e49451`, the race route finished three laps in 1:14.68 and reached
the results screen by frame 25,800, at 16:9 as at 4:3. No run since has played it to the
finish, under the console-timed reads of `bad7160` or the fast ones of `b5ec329`.

City Trial with nobody steering drives into the sea and stays there while the clock runs. The
opening movie, when it isn't skipped, plays to the end and hands over to the title and the
attract demos.

The seven other course routes were left running at Dragoon `788571c` and gcn-recomp `b848158`
for 120 s each with `--fast` and a dump every 300 frames, four and then three at a time.
Checker Knights ran again for 200 s to reach its results.

Nobody steers after the start, and the Warpstar keeps moving on its own. Whether a console's
Kirby gets stuck in the same places wasn't checked.

| Course | Left alone | Results screen by frame |
|---|---|---|
| Celestial Valley | Fourth in 2:21.00 | 21,300 |
| Sky Sands | Fourth in 2:11.43 | 20,100 |
| Frozen Hillside | Stopped against a wall between 0:14 and 0:19, still on lap 1 at 7:49 (frame 31,500) | Not reached |
| Magma Flows | Fourth in 2:28.63 | 22,200 |
| Beanstalk Park | Fourth in 2:15.73 | 20,700 |
| Machine Passage | Stopped against a wall by 0:09. It had crept to the next corner by 1:34 and was still on lap 1 at 7:49 (frame 31,500) | Not reached |
| Checker Knights | Stopped against a wall by 1:34 and moving again by 3:04, so lap 1 took 3:09.57 and lap 2 took 1:20.90. Fourth in 4:30.46 | 36,600 |

Nebula Belt's slot on the course select is gray with no name on a blank card, so it has no
route. The course select's setup (`fn_8003C114`, its call at 0x8003C21C) locks the slot unless
`fn_8000C0E0(8)` says course 8 is open, and in the wowjinxy/KAR decomp that asks for the Air
Ride checklist box of clear kind 0 (`src/kar/gm/gmautodemo.c:2902`,
`src/kar/gm/gmclearchecker.c:77`). The attract demo skips course 8 on the same check
(`gmautodemo.c:4141`).

That box is marked when a running total reaches 100 (`gmclearchecker_8004a648.c:346`). The
total is the value at 0x80536834 plus the laps of the racer slots it counts, kept per slot at
0x80536240 (`gmautodemo.c:2326`, `gmclearchecker_8004a648.c:334`).

RAM dumps from `GCN_RAM_DUMP_AT` show the race route taking 0x80536834 from 0 to 3, with Kirby's
laps counted and the CPUs' not. A race with a second player wasn't run, and whether the total
reaches the memory card wasn't checked.

Reaching 100 sets bit 0 of the box's flags (`gmclearchecker.c:211`), while the course select
reads bit 3 (`gmclearchecker.c:162`). The only store of bit 3 found, in the checklist screen's
refresh (`fn_8017DF5C`, the store at 0x8017E008), sets it for a box whose flags already have
bit 1 or 2. The search covered only the functions that call the save getter (`fn_800076A0`),
and no run has opened the course.

At gcn-recomp `7d30377` the race ran at about 500 frames a second in the hidden window with
`--fast`, 8 times the game's 60. That's 9,600 frames between frames 3600 and 13,200 in 19.3 s
of wall time, with other work on the machine at the time.

## Air Ride pacing

Each course route ran once at the game's own speed, hidden and silent, on Dragoon `4602fa1` at
gcn-recomp `dac449e`, as
`tools/probe.sh pace-ROUTE 130 tests/routes/ROUTE.txt 100000 --real-time GCN_FRAMETIME=1`. Each
started with the cache from one warm-up of all twenty-one manifest routes, so boot loaded 318
programs. The load average when each run began was 2.4 to 4.1, except the first run's 11.0,
which started right after the warm-up.

The rows are
`tools/frametime.py build/probe/pace-ROUTE/stdout.txt --from 3400 --slow 16.7 --late 25`. The sd
is the population standard deviation of the guest's frame interval, and Late counts guest
intervals over 25 ms.

Compiles are the `[shaders] compiled program` lines after boot. Boot is the `programs from cache`
line's time for 318 programs.

| Course | Frames | Guest mean | sd | 95th | 99th | Worst | Late | `[rt]` mean | `[rt]` 99th | `[rt]` worst | Compiles | Boot |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Fantasy Meadows | 4,295 | 16.68 ms | 0.064 ms | 16.77 ms | 16.95 ms | 16.99 ms | 0 | 0.66 ms | 1.22 ms | 6.39 ms | 1 (7111) | 498 ms |
| Celestial Valley | 4,293 | 16.68 ms | 0.092 ms | 16.84 ms | 16.98 ms | 17.56 ms | 0 | 0.61 ms | 1.04 ms | 2.48 ms | 0 | 486 ms |
| Sky Sands | 4,288 | 16.68 ms | 0.071 ms | 16.78 ms | 16.95 ms | 18.06 ms | 0 | 0.63 ms | 1.10 ms | 2.87 ms | 0 | 495 ms |
| Frozen Hillside | 4,291 | 16.68 ms | 0.066 ms | 16.78 ms | 16.94 ms | 16.99 ms | 0 | 0.60 ms | 1.35 ms | 3.97 ms (5752) | 1 (5752) | 495 ms |
| Magma Flows | 4,289 | 16.68 ms | 0.068 ms | 16.79 ms | 16.95 ms | 16.99 ms | 0 | 0.78 ms | 1.53 ms | 4.93 ms | 0 | 493 ms |
| Beanstalk Park | 4,300 | 16.68 ms | 0.068 ms | 16.78 ms | 16.95 ms | 17.00 ms | 0 | 0.69 ms | 1.92 ms | 6.14 ms (5649) | 1 (5649) | 473 ms |
| Machine Passage | 4,295 | 16.68 ms | 0.065 ms | 16.77 ms | 16.95 ms | 17.00 ms | 0 | 0.52 ms | 0.92 ms | 3.16 ms | 0 | 491 ms |
| Checker Knights | 4,289 | 16.68 ms | 0.106 ms | 16.85 ms | 16.99 ms | 17.99 ms | 0 | 0.62 ms | 1.10 ms | 2.73 ms | 0 | 491 ms |

Every course averaged 16.68 ms a guest frame with its 99th percentile under 17.0 ms. The worst
guest frame on any course was 18.06 ms, and no course had a guest interval over 25 ms.

Six of the eight had an sd of 0.064 to 0.071 ms. Celestial Valley's 0.092 ms and Checker
Knights' 0.106 ms stayed wide in a later session's repeat runs, Celestial Valley at 0.107 ms and
Checker Knights at 0.105 and 0.097 ms, while Machine Passage's repeat read 0.072 ms against the
table's 0.065 ms. The log doesn't say what widened them.

The `[rt]` columns didn't repeat. The four repeat runs, one of them Machine Passage's, read 0.79
to 0.86 ms mean and 2.20 to 2.51 ms at the 99th, where this table reads 0.52 to 0.62 ms and 0.92
to 1.10 ms for those courses.

Three courses compiled one program each in play. Each compile took 1.9 to 3.0 ms, and the render
frame that first drew with it took 3.97 to 6.14 ms. The 334-key warm-up builds all three (under
Chained course passes).

## Memory card

Three runs at gcn-recomp `e1016b8` under one probe NAME, so each launch found the card the
last one left. Each had `--log=exi`, which logs every card command. The page writes
(`memcard cmd F2`) were counted between the scripted presses in the log. Runs 2 and 3 dumped
a frame every 50 and run 1 dumped none. The runs shared one dump directory, so only run 3's log,
frames and `sram.raw` timestamp are kept. Runs 1 and 2's counts and frames were read as they ran
and can't be checked again.

| Run | Presses | Card writes | What the frames show |
|---|---|---|---|
| 1 | `tests/routes/title.txt` on a blank card | 1,024 pages, the new save file | Nothing was dumped |
| 2 | Options, Sound, Mono, the balance moved toward Effects, then B twice | 448 pages between START at the title and frame 700, then 320 after the first B left the Sound screen | Frame 1400 shows Stereo picked. Frame 1650 shows Mono picked, and frame 1950 shows Mono with the balance marker right of center |
| 3 | Options, Sound and no change | 448 pages between START at the title and frame 700, none after | Frame 1400 shows Mono picked and the balance marker right of center, where run 2's frame 1950 had it |

With a save on the card the game skips the card prompts and starts the opening movie at once,
so these presses come earlier than a route's. Runs 2 and 3 began
`200:A:5,400:START:5,700:RIGHT:5,800:A:5,1100:DOWN:5,1200:A:5`, and run 2 went on with
`1500:RIGHT:5,1600:A:5,1700:DOWN:5,1800:RIGHT:20,1900:RIGHT:20,2000:B:5,2300:B:5`.

Stereo or mono goes through the SDK. The Sound screen (the call at 800AEB78 in
`kar_smsoundtest__near_800aeb20`) calls `HSD_SynthSetSoundMode`, whose call at 80448534 is
`OSSetSoundMode`, and that writes bit 2 of SRAM byte 0x13. At boot `HSD_SynthInit` reads it
back with `OSGetSoundMode` at 8044EA84.

A console keeps SRAM on a battery, and since gcn-recomp `2bf7308` the runtime keeps it in
`saves/sram.raw` and loads it at boot (`runtime/hw/sram.cpp`). The blank card's run 1 left no
such file. After run 2 it was there at 64 bytes with byte 0x13 reading 0x28, and run 3 didn't
write it again.

At gcn-recomp `b848158` City Trial's Game Settings didn't come back, because the game doesn't
write them when its menus close. In one pair of runs the second showed 5 min and Shuffle
after the first set 3 min and Drag Race, and a third run with `--log=exi` logged no card write
after the change. Whether the game saves them after a match wasn't checked, and none of this
has been run since `b848158`.

## Controllers

The runtime keeps the port each gamepad was last on in `saves/ports.txt`. A gamepad the file
names takes that port again when it's free and the lowest free one when it isn't. Any other
takes the port of its SDL player number if that's free and otherwise the lowest free one
(gcn-recomp `runtime/port_memory.h:48-59`).

Once a gamepad has a port, its player number is set to the port (`runtime/gamepads.cpp:151-158`).
A gamepad gets no port when none is free, and one pulled out frees its port. The game then sees
that port unplugged, though the keyboard keeps its port plugged in and so does a port that
`--pads=N` or a `controls.txt` line covers.

Since gcn-recomp `5e54665` the overlay menu has a Controllers page. It lists each player's
controllers, with Swap with the next player and Remove, and Set player order gives player 1,
then 2 and on, the next controller whose A goes down. Each change applies at once and is saved
to `saves/ports.txt`, except the keyboard's player, which is player 1 again at the next launch.
A player a `controls.txt` `port <n>` line sets can't be changed there. A notice at the bottom of
the window says for 2 seconds that a controller connected, disconnected or changed player, and
the game keeps running under it. Frame dumps leave out the menu and the notices.

`tools/test_ports.sh` passed all 284 of its checks on Dragoon `92405f1`, among them Swap,
Remove, Set player order and the notices.

A device's `port <n>` line in `controls.txt` keeps that port from gamepads, and a
`gamecontrollerdb.txt` beside the executable adds mappings. `--pads=N` plugs in ports 1 to N
for routes, as in `2/2100:A:5`.

The GameCube's A, B, X and Y are the face buttons with those labels (gcn-recomp `29ce20e`), so
GameCube A is the east button on a Nintendo-layout pad such as an 8BitDo in Switch mode. A pad
whose faces carry no letters, as PlayStation's don't, has them where an Xbox pad does. All of
this was checked with SDL's virtual gamepads (`gcn-recomp/tools/test_ports.sh`, and a recording
replayed with no gamepad), not with four real controllers or under Steam Input.

## Four players

`city-trial-4p.txt` with `--pads=4`, at gcn-recomp `fda6926`. The game's full speed is 60
frames a second.

| Run | City Trial, from frame 3,300 to the end of the clock |
|---|---|
| `dragoon_bench`, 120 s, four players (`tools/probe.sh NAME 120 tests/routes/city-trial-4p.txt 60 --pads=4 --bench`) | 398 frames a second on average over 44 one-second samples, 289 in the slowest second and 429 in the fastest. That's 6.6 times full speed |
| `dragoon_bench`, 60 s, one player (`city-trial.txt`) | 505 a second on average over 35 samples, 443 in the slowest |
| Hidden window at the game's own speed (`--real-time`, 640x480), 130 s, four players | 60 frames in every second of the city. Over the 4,246 frames from 3,400 on, the guest's time between frames averaged 16.68 ms, with 17.27 ms at the 95th percentile and 17.68 ms at worst. None went over 20 ms. The renderer took 1.40 ms a frame on average and 12.41 ms at worst |

The benchmark has no renderer, so its figure is the guest alone. The whole 120 s run covered
118,257 frames, past the end of City Trial. The real-speed run fell behind only while the
city loaded, between frames 2,706 and 2,750. It showed 44 frames in that second and made 9
catch-up jumps of the clock there, 109 ms in all. It made no more in the city.

## Top Ride and the stadium at the game's speed

Each Top Ride and stadium route ran once in a hidden window at 640x480 as
`tools/probe.sh pace-ROUTE SECONDS tests/routes/ROUTE.txt 100000 GCN_FRAMETIME=1 --real-time`
(plus `--pads=4` for four players), at Dragoon `788571c` and gcn-recomp `b848158`. Each played
past its route's last checkpoint. A new NAME meant an empty shader cache, and other runs kept the
machine's load average between 8 and 12. The numbers are `tools/frametime.py`'s. For Top Ride
they start at frame 3,400 and cover about 1,820 frames of the race. For the stadium they start at
frame 4,400 and cover the city, the stats, Drag Race 3 and the results. The over 20 ms column
counts guest intervals of 20 ms or more.

| Route | Guest mean, 95th, worst | Guest over 20 ms | `[rt]` mean, worst | `[rt]` over 16.7 ms |
|---|---|---|---|---|
| Top Ride, Grass | 16.68, 17.92, 19.81 ms | 0 | 0.72, 34.69 ms | 2 |
| Top Ride, Sand | 16.68, 17.97, 18.81 ms | 0 | 0.81, 25.53 ms | 1 |
| Top Ride, Sky | 16.70, 17.90, 48.64 ms | 1 | 0.76, 12.98 ms | 0 |
| Top Ride, Fire | 16.68, 18.00, 21.32 ms | 1 | 0.74, 59.87 ms | 1 |
| Top Ride, Light | 16.72, 18.07, 49.14 ms | 8 | 0.61, 34.65 ms | 2 |
| Top Ride, Water | 16.72, 17.84, 46.61 ms | 3 | 0.73, 68.88 ms | 3 |
| Top Ride, Metal | 16.70, 17.91, 38.12 ms | 2 | 0.78, 15.07 ms | 0 |
| Stadium, one player | 16.73, 17.93, 134.92 ms | 24 | 0.46, 20.69 ms | 1 |
| Stadium, four players | 16.73, 17.90, 134.16 ms | 31 | 0.91, 13.99 ms | 0 |

The Fire row is a second run. The first, made while the load average was near 11, had 34 guest
intervals over 20 ms between frames 3,452 and 4,221, 14 of them between 4,140 and 4,200, and a
worst of 55.90 ms. Every
render frame over 16.7 ms in these tables compiled new shaders, which a warm cache would have
built already. From frame 300 on, the stadium runs' worst render frames were the city's first
frame (89.89 ms with 38 new programs, 96.12 ms with 34 for four players) and frame 902 (901 for
four players, 15 new programs).

The stadium's long guest intervals come where the game changes scene. On the one-player run
they were 98 ms at frame 15,606 just after time ran out, 100 ms at 16,202 as the stats screen
closed, 135 ms at 16,502 as the stadium loaded 69 new textures (4.6 MB) and 122 ms at 20,051
at the results. One more, 111 ms at frame 17,547 in the middle of Drag Race 3, came with no new
textures. What the guest was doing then wasn't checked. The four-player run stalled at the same
four scene changes. The rest of the slow intervals were between 20 and 50 ms.

## Bot soak

`tools/bot_soak.py` played the game with bots at gcn-recomp `b11ebc6`, unpaced in a hidden
window with no gamepads and `GCN_AXVOICES=1`. The walker in `tools/bot_menus.py` takes the
menus, and once a round is under way each bot holds the stick toward a walk drawn from the seed
and taps A. A race or a City Trial stadium still on after 120 s of game time is left
through its pause menu.

The frozen-picture check didn't run, since the link gives a bot no picture hash. No soak had a
console reset, so none rebuilt the shader cache.

The Dragoon column is each soak's commit as it landed. The soak ran it before a rebase onto
main, at gcn-recomp `b11ebc6`, while the landed commit pins `782d7fa`.

| Seed | Modes | Ports | Limit | Dragoon | Wall time | Rounds | End |
|---|---|---|---|---|---|---|---|
| 506028 | Air Ride | 1 | 10 min | `569e994` | 10.0 min | 37 | Time limit |
| 506694 | Top Ride | 1 | 10 min | `569e994` | 10.0 min | 39 | Time limit |
| 507330 | City Trial | 1 | 10 min | `569e994` | 7.0 min | 1 | Stop at frame 192,620: a stadium up for 601 s |
| 511308 | City Trial | 1 | 10 min | `bd5ff15` | 10.0 min | 11 | Time limit |
| 512002 | Air Ride, `-- --exit-after=12000` | 1 | 10 min | `acfb6c7` | 0.4 min | 2 | `exit_after`, exit 0 |
| 512035 | City Trial | 4 | 60 min | `acfb6c7` | 1.5 min | 1 | Stop at frame 32,471: Destruction Derby's results up for 121 s |
| 513333 | City Trial | 4 | 60 min | `df6b2ba` | 8.6 min | 5 | Stop at frame 159,374: a stadium up for 602 s |
| 544282 | City Trial | 4 | 60 min | `bd92d9d` | 10.8 min | 8 | Stop at frame 181,800: a music stream ended early |
| 545590 | All three | 1 | 60 min | `bd92d9d` | 20.5 min | 37 | Stop at frame 505,140: a music stream ended early |
| 555018 | City Trial | 4 | 60 min | `e49464e` | 60.0 min | 42 | Time limit |
| 558640 | All three | 1 | 60 min | `e49464e` | 60.0 min | 119 (40 Air Ride, 39 Top Ride, 40 City Trial) | Time limit |
| 575543 | City Trial | 4 | 60 min | `5fcd62d` | 60.0 min | 42 | Time limit |
| 579174 | All three | 1 | 60 min | `5fcd62d` | 54.3 min | 107 (35 Air Ride, 36 Top Ride, 36 City Trial) | Stop at frame 1,473,710: a hang, after an assertion in the game's audio code |
| 835686 | City Trial | 2 | 20 min | `7cf11f1` | 20.0 min | 22 | Time limit |

The first three stops were the walker's, each fixed before the next soak of that mode
(`tools/README.md` has its steps).

The two music stops came from `tools/stream_voices.py`'s rule, at list 608,157 of 544282 and
1,691,796 of 545590. In each the game stopped one of the music's two voices in a City Trial
round's city and gave the other a sound effect's sample in the same list. The rule called the
mixer's end of that sample an early end, and neither point was compared with a console.

Since `2cc5864` the `set` that gave the block a new sample ends the music voice as the game's
doing, and `stream_voices.py` found no early end in 555018's or 558640's log. Since `e35b777` a move on a voice that never had a loop flag carries
into its block's new sample, and with that rule it found none in the last three soaks' logs.

579174 stopped at frame 1,473,710 in its 107th round, a Top Ride one, when the game reported a
failed assertion in its audio code and made no frame after it. The soak called it a hang after
30 s, and its replay stopped on the same assertion at the same frame. It hasn't been compared
with a console.

Each stop's replay line ran with `GCN_SESSION` and `GCN_AXVOICES=1` added, so the replay kept
its own input log and voice lines. 579174's ran with a 4,200 s limit in place of the line's
24,622, since a hang's replay line has no `--exit-after` and the halted game makes no more
frames, so a replay waits out its seconds. Each replay's input log matched the soak's up to the stop
apart from the header's start time and epoch. Its `[axv]` lines matched the soak's byte for
byte. There were 292,085 of them for 507330, 35,964 for 512035, 227,595 for 513333, 282,093 for
544282, 982,893 for 545590 and 2,760,648 for 579174. A replay has no bot, so a screen limit can't
fire in one. On the two music stops' replays `stream_voices.py` found the same single early end
as on their soaks.

Three walker steps stay unconfirmed (`tools/bot_menus.py:69-77`). Two are A on a screen
kar_ram.json doesn't name and the press cadence, which a log can't place on a screen. The third
is RIGHT on a three-player stadium's pause menu, which no soak has played, though 835686 left 12
two-player stadiums with RIGHT, each followed by its next round.

## Audio

At gcn-recomp `bf31b7b`. `GCN_AXSTATS=1` makes the game print its mixer's counts every 400
command lists. Three runs played the race route as
`env SDL_AUDIO_DRIVER=dummy tools/probe.sh NAME 30 tests/routes/air-ride-race.txt 60 GCN_AXSTATS=1 --bench`,
unpaced. One had `GCN_AX_LAYOUT=2001` and two were default. The table covers the 257 windows
(102,800 lists) that all three reached. Before is the `GCN_AX_LAYOUT=2001` run, which reads
the control word the way the 2001 ucode does and, at `bf31b7b`, also skipped the compressor
command, as this runtime did until now. At the pinned gcn-recomp (since `b839cf6`) the
compressor follows the ucode hash alone, so `GCN_AX_LAYOUT` changes only how the mixer
control word is decoded, and the Before column can't be reproduced with that switch. After
is the default for `07F88145`.

| Race route | Before | After |
|---|---|---|
| Windows with a main L or R peak over 32,767 | 13 | 2 |
| Highest main peak | 93,113 | 71,311 |
| Samples the output clamp changed | 4,435 | 923 |
| Windows with an AuxA L or R peak over 0 | 22 | 97 |
| Highest AuxA L or R peak | 6,989 | 8,702 |
| Windows with an AuxB L or R peak over 0 | 0 | 20 |
| Highest AuxB L or R peak | 0 | 15,408 |

Surround peaks were 0 on every bus in all three runs. Peaks are what the ucode writes before
the output clamp. The two default runs printed the same hash at every list count they
share.

The commands counted come from ten default runs, two of each route (title 79 `cmds` lines
each, mode select 59, race 258 and 257, City Trial 107, four-player 103). Every line reads
`skipped=0 unknown=0` and counts commands 00, 02, 03, 07, 0E, 0F and 12 in all 400 lists of
its window, and 04 and 05 in every list after the first window (398 in it). The compressor
command (12) ran in each of them.

### Clicks

At gcn-recomp `bf31b7b` (before) and `fd1f6a8` (after), which plays source type 2 voices
with no rate conversion (`audio.md`). Each played the title route for 90 seconds with
`--real-time`, recording what went to the device (`GCN_WAV`, 48 kHz) and the DMA's own
blocks (`GCN_AIDWAV`, 32 kHz, before the audio ring). `tools/audio_clicks.py` counted them,
with `--raw 32000 --period 160` for the DMA blocks.

| Title route | Before | After |
|---|---|---|
| Clicks in the device's stream | 1,124 in 81.4 s | 81 in 80.9 s |
| Clicks in the DMA's blocks | 928 in 89.2 s | 19 in 88.7 s |
| DMA clicks within 2 samples of a 160-sample block join | 575 (29 by chance) | 5 (0.6 by chance) |

Nine of the 19 left come in threes at 2.33, 5.34 and 15.75 s, when the route's three A
presses play the menu's sounds. The 5 ms gap at 15.74 s is the opening movie being skipped.
The nine are 40 to 44 dB under full scale and the same at each press. The other ten are 18
to 38 dB under.

The device's extra clicks were the audio ring's cuts. A third run at `3f5da1e`, with
`GCN_AXSTATS=1` added, logged each time the ring held over 100 ms more than its cushion and
cut back to it. Under probe.sh the device is SDL's dummy driver, and it took 81.7 s of sound
while the DMA delivered 89.2 s, so the ring cut 75 times, about 100 ms each. 56 of the
run's 79 device clicks fell within 2 samples of a cut (`--marks`, 0.0 by chance). The
others in its first 15 seconds match the DMA's own clicks, later by the ring's delay.

At `e6ea431` gcn-recomp pulls the sound itself at a sound card's pace under the dummy
driver, and since `3ae8463` the ring's cuts and dropouts are fades instead of steps. A run
there made no cuts and no underruns, with the ring at its cushion. Its device stream had 22
clicks and its DMA blocks 19. The extra few are the same sharp onsets as the DMA's, judged
at 48 kHz instead of 32. One device click at 13.01 s is a rise of 2,522 in one sample in
the DMA's blocks, under the threshold there.

Not done or not checked:

- How often the ring cuts or runs dry with a real sound card. Either is a fade now, checked
  on a tone by gcn-recomp's `test_audio_ring` and not by ear.
- Whether the ten clicks during the attract demo are in the game's own sound. A capture of
  the same scenes from Dolphin would tell.
- No game on the 2001 ucode ran, so that layout's path is untested here beyond the
  `GCN_AX_LAYOUT=2001` run.
- One machine, one macOS version.

## Renderer cost

What the GL renderer costs at 1280x960 (`--scale=2`, twice the default 640x480 in each direction),
at gcn-recomp `642187a`, on a 16-core Mac with other work running (load average 2 to 3). The
limits they are held against are in the table at the end of this section. `[rt]` is the time the
renderer spends issuing a frame to GL, not the GPU's own time. The percentiles are nearest rank.
The window was hidden and never waited on the display's refresh. The timer behind `--real-time`
paced the guest, and the cost of presenting a frame and of vsync isn't in these numbers. So the
16.68 ms guest interval shows that timer and not a 60 Hz display. `[rt]` is part of a frame's cost,
not all of it.

| Four players, frames 3,400 to 7,647 (4,248 frames) | Mean | 95th | 99th | Worst |
|---|---|---|---|---|
| Guest interval | 16.68 ms | 17.29 ms | 17.49 ms | 17.68 ms |
| `[rt]` render time | 1.34 ms | 1.72 ms | 1.96 ms | 5.98 ms |

The command is
`tools/probe.sh ct4p-scale2 130 tests/routes/city-trial-4p.txt 600 --pads=4 --real-time --scale=2 GCN_FRAMETIME=1`,
and the table is a second run of it with a frame dump every 100,000 frames instead of every 600.

The first run, with the dumps, read 1.45 ms mean and 2.42 ms at the 95th percentile for the
renderer, with 3.64 ms at the 99th and 41.15 ms at worst. Its 7 worst frames were the dumps, and
the rest of the gap wasn't explained. No control run was made.

No guest interval ran over 20 ms in either run, and the same route at 640x480 averaged 1.40 ms
(under Four players), so doubling each side cost the renderer's issue time nothing it could
measure.

Hitches are the frames after frame 300 whose `[rt]` time is over 16.7 ms. These are first launches
with an empty shader cache, one run of each route at `--real-time --scale=2` with nothing warmed,
at Dragoon `d4de05d` and gcn-recomp `caf12a2`. These runs started with no `saves/shaders.bin`.
macOS GL keeps no program binaries, so the cache holds keys only. The warmed numbers are in the
Player targets table below. Each run was `tools/probe.sh cold-ROUTE SECONDS tests/routes/ROUTE.txt 60
GCN_FRAMETIME=1 --real-time --scale=2` (plus `--pads=4` for the four-player route), and the rows
come from `tools/frametime.py LOG --slow 16.7`. The `[shaders] compiled program N` lines that
`GCN_FRAMETIME=1` prints say when a program is built, in the frame that needs it. Every run played
past its route's last checkpoint. These runs kept the default frame dump every 60 frames, and a
dump reads the whole frame back, which puts that frame over 33 ms by itself. The rows leave out
dump frames. Frame numbers and batch shapes are `frametime.py`'s, and `draws` is its `draws A/B`.

| Route | Frame | `[rt]` | Batch | New programs |
|---|---|---|---|---|
| Title | 902 | 29.8 ms | draws 462/167, verts 12,419, idx 33,993 | 15 |
| Title | 1414 | 56.4 ms | draws 1437/162, verts 32,750, idx 84,096 | 24 |
| Title | 1535 | 22.6 ms | draws 1531/192, verts 31,527, idx 79,005 | 6 |
| Menu | 902 | 31.8 ms | draws 462/167, verts 12,419, idx 33,993 | 15 |
| Air Ride race | 902 | 30.3 ms | draws 462/167, verts 12,419, idx 33,993 | 15 |
| Air Ride race | 3122 | 60.6 ms | draws 2285/168, verts 37,730, idx 91,242 | 30 |
| Air Ride race | 4788 | 17.6 ms | draws 2417/271, verts 40,561, idx 98,709 | 5 |
| City Trial | 902 | 30.5 ms | draws 462/167, verts 12,419, idx 33,993 | 15 |
| City Trial | 2733 | 64.5 ms | draws 1937/386, verts 36,131, idx 77,673 | 38 |
| City Trial, four players | 902 | 31.5 ms | draws 462/167, verts 12,419, idx 33,993 | 15 |
| City Trial, four players | 2733 | 59.1 ms | draws 4399/635, verts 84,681, idx 185,319 | 34 |

4 of the 11 frames went over 33 ms (title 1414, City Trial 2733, four-player 2733 and race 3122).
The other seven are over 16.7 ms and under 33. The 15-program burst at frame 902 sits at 30 to 32 ms.

Every one of those frames built new programs, and no other non-dump frame after 300 went over
16.7 ms. A program takes 1.2 to 5 ms to compile. The big bursts are 15 programs at frame 902 (the
first 3D scene, in all five runs), 24 at the title's logo scene (1414), 38 and 34 at the start of
the city (2733) and 30 at the start of a race (3122). The other new programs come in ones to six,
and only the 6 at frame 1535 and the 5 at 4788 pushed a frame over 16.7 ms. The guest also stalls
for 117 to 401 ms at a handful of frames (303, 1002, 1413, 1801, 2103, 2732 and others). What it
was doing then wasn't checked.

| Check | Limit | Measured on GL |
|---|---|---|
| Four-player cost | `[rt]` 8 ms at the 99th percentile | 1.96 ms (3.64 ms with dumps) |
| Shader-compile hitches, cold cache, before the warm-up | 33 ms for any frame after frame 300 | 4 frames across the five cold runs, from 56 ms to 65 ms, each on first sight of 24 to 38 programs |

The hitches are cold-start costs. Frame 902 showed up in all five runs. The bigger bursts (1414,
2733, 3122) each showed up in the runs of the routes that reach that scene, from one run of each
route.

## Player targets

What a player's first session looks like after the warm-up, against the bars set for it.
Dragoon `e52dce1` in this table landed rebased as `fe88e8a`.

| Target | Bar | Measured | Result |
|---|---|---|---|
| Stalls in a fresh install's first session | 0 frames over 33 ms after frame 300 on all five routes | 0 frames on all five after the eight-pass warm-up, worst render frame 15.45 ms, with the race run 130 s to frame 7,701 (Dragoon `2fc9285`) | Pass |
| Shaders compiled during play after the warm-up | 0 `[shaders] compiled program` lines on the five routes | 0 on all five after the eight-pass warm-up, with the race run to frame 7,701 (Dragoon `2fc9285`). The eight Air Ride course routes compiled none, unpaced to frame 16,000 or in 130 s real-time runs (under Chained course passes) | Pass |
| How far the attract demos alone get | Report the share of each route's keys the attract pass builds by itself | The warm-up has no attract pass. Run from a blank card it sat at the "make a new save data file?" prompt and built 3 keys in 20,000 frames. Run after the routes, on the card they leave, it took 50 s and added 9 keys on top of the routes' 191, none of which a route needed | Dropped |
| Time added to the first build | 90 s or less | 63.6 s, 62.9 s and 64.7 s at loads of 2.40, 9.77 and 10.54 for the 334 keys of all twenty-four manifest routes in eight passes, five at a time on an M4 Max (Dragoon `2fc9285`, under Chained course passes) | Pass |
| Time added to every boot on macOS GL | 1,000 ms or less | 475 to 508 ms for 334 programs at loads of 1.20 to 2.25 (Dragoon `2fc9285`) | Pass |
| Frames | `tools/frame_hashes.py check` passes | All twenty-four routes' 1,906 frames match the goldens recorded at gcn-recomp `b5ec329`, at the pin `5e54665` on Dragoon `92405f1` (under gcn-recomp `5e54665`) | Pass |
| World at 16:9 | Every world camera's projection aspect is its 4:3 value times 4/3, to three figures, in one player, 2P and 4P. No HUD or menu camera changes | 1.67383 from 1.25538 in the race before and after its finish and in City Trial, 2.97524 from 2.23143 in 2P, 1.85892 from 1.39419 in 4P and 1.57333 from 1.18 in Top Ride, each steady over 600 frames or more. Every HUD 3D, minimap and menu camera kept its 4:3 aspect (Dragoon `45c52c5` at loads of 2.7 to 6.3, `widescreen.md`) | Pass |
| Edges | At every checkpoint the world makes at least as many draws at 16:9 as at 4:3, and no dump shows an object cut off at a side edge | 217 draws against 204 in the race, 124 and 124 after its finish, 376 against 371 in City Trial, 317 against 314 in 2P, 823 against 807 in 4P and 198 and 198 in Top Ride. No output dump at 16:9 shows an object cut off at a side edge. The test that culls the world wasn't found, so pop-in while moving needs a person to watch (Dragoon `45c52c5` at loads of 2.7 to 6.3) | Pass |
| Simulation | Left alone, the race finishes at 16:9 in its 4:3 time, 1:14.68 at `5e49451` | The results frame at 25,800 is the same at 16:9 as at 4:3 (Dragoon `45c52c5` at loads of 4.5 to 6.1) | Pass |
| HUD at 16:9 | Every HUD draw keeps its 4:3 width, height and distance to its anchored edge within 1 display pixel at 480 high, in the race, 1P City Trial, 2P and 4P | `drawlog.py hud` passed every anchored draw, 41 in the race (also with `GCN_GX_SYNC=1`), 33 in City Trial, 54 in 2P and 76 in 4P, on Dragoon `e52dce1` at loads of 1.5 to 3.1. It passed with the same counts under the stricter tool on Dragoon `1ff85c8` at gcn-recomp `b11ebc6`, where all twenty-four routes' frames and audio matched. Top Ride's 38 HUD draws still stretch, and so do the bars between split views, since they span the screen (`widescreen.md`) | Pass |
| Split views | Every HUD box stays inside its own view at 16:9 | No HUD box in 2P or 4P sticks out of its view by more than 1 pixel more than at 4:3. The 4P clock sits on the bars and anchors to the screen's left edge (Dragoon `e52dce1` at loads of 1.5 to 3.1) | Pass |

These runs set `DUMP_EVERY` to 100,000, since a dumped frame goes over 33 ms by itself. The
stall, compile and boot rows ran at Dragoon `2fc9285` and gcn-recomp `dac449e` on an M4 Max,
from the cache of the 63.6 s warm-up, at loads of 1.98, 2.25, 1.63, 1.27 and 1.20 for the
title, menu, City Trial, four-player and race routes. Each was
`tools/probe.sh NAME SECONDS tests/routes/ROUTE.txt 100000 GCN_FRAMETIME=1 --real-time --scale=2`
(plus `--pads=4` for four players), with SECONDS 31, 35, 70, 73 and 130.

Stalls are the frames `tools/frametime.py build/probe/NAME/stdout.txt --slow 33` lists after
frame 300. Compiles are the `[shaders] compiled program` lines, and boot is the
`programs from cache ... in N ms` line. Apple's own shader cache was warm from earlier runs,
and whether the warm-up fills it on a fresh Mac wasn't checked.

`tools/warm_shaders.py` plays one pass at once for every three cores, 6 at most
(`tools/warm_shaders.py:64-68`). That comes from the 21-pass warm-up at Dragoon `0059fce` and
gcn-recomp `e1016b8`, where every count left the same 318 keys and each pass slowed as more
played at once.

| Passes at once | Time | The 21 pass times added up | Stadium four-player pass |
|---|---|---|---|
| 1 | 249.5 s | 249.0 s | 49.3 s |
| 4 | 77.9 s | 302.6 s | 60.0 s |
| 5 | 68.9 s and 67.7 s | 328.5 s and 323.0 s | 65.3 s and 64.1 s |
| 6 | 67.1 s | 352.5 s | 66.7 s |
| 8 | 71.4 s | 417.1 s | 71.0 s |

Playing is the cost, not compiling. In a 252.7 s run that played one pass at a time, each from
the last one's cache, 245.4 s went to playing 129,840 frames and starting the game 21 times. The
318 programs compiled in play took 0.6 s, and building the cache's programs at 20 of those starts
took 6.8 s.

The table's row for 1 is `--jobs 1`, which gives each pass a cache of its own. Scale and pacing
didn't change City Trial's keys. A pass at scale 1 or 2 with `--fast` built the same 107 as one
at scale 2 with `--real-time`.

### Longer course passes

Run unpaced to frame 16,000 from the 318-key cache of a warm-up whose passes stopped 900 frames
past their routes' last required frames, six of the eight Air Ride courses compiled 21 programs
of 10 distinct keys. Sky Sands drew 8 of the 10, between frames 9,333 and 14,186, among them
every key Fantasy Meadows, Celestial Valley and Beanstalk Park drew late, and Magma Flows and
Frozen Hillside each drew one no other course did. So the `-courses` routes race Sky Sands to
frame 14,400 and Magma Flows to 12,700, and Frozen Hillside's pass plays to 6,000
(`tests/hashes/manifest.txt:15-16`, `:33`).

The runs were
`tools/probe.sh NAME 400 tests/routes/ROUTE.txt 100000 --exit-after=16000 GCN_FRAMETIME=1` at
Dragoon `3f0f8c3` and gcn-recomp `dac449e`, hidden and silent, four at once.

### Chained course passes

The warm-up plays 8 passes. Three routes race one course after another, each for as long as its
own route's pass played it, and the other five passes are the ones they were. Each route that
another route's pass plays has no pass of its own, through the manifest's `warm-from=` setting.

| Pass | Frames | What it plays |
|---|---|---|
| `title` | 1,860 | The title |
| `air-ride-frozen-hillside` | 6,000 | Frozen Hillside |
| `air-ride-checker-knights` | 5,100 | Checker Knights |
| `air-ride-courses-1` | 23,800 | Sky Sands to frame 14,400, then Fantasy Meadows (`air-ride-race`) and Celestial Valley |
| `air-ride-courses-2` | 20,300 | Magma Flows to 12,700, then Machine Passage and Beanstalk Park |
| `top-ride-courses` | 19,500 | The seven Top Ride courses |
| `city-trial-stadium` | 21,300 | City Trial and the stadium, for `menu` and `city-trial` too |
| `city-trial-stadium-4p` | 21,900 | The same with four players, for `city-trial-4p` too |

| Bar | Before | After |
|---|---|---|
| Warm-up, five passes at once (55 s for the chaining, 90 s for Player targets) | 75.2 s, 77.0 s and 76.8 s at loads of 0.85, 9.77 and 11.84 | 63.6 s, 62.9 s and 64.7 s at loads of 2.40, 9.77 and 10.54 |
| Keys the warm-up's cache lost, by `shader_cache.py diff` (0) | | 0 of 328. It gained 6, so it holds 334 |
| Compiles on the eight course routes, unpaced to 16,000 frames (0) | 0 | 0 on all eight |
| Compiles in 130 s real-time runs of those routes (0) | 0 | 0 on all eight, to frames 7,673 to 7,676 |
| Goldens for the new routes | | Frames and audio for all three, each matched by a check run after the record |

The chaining's own 55 s bar (`3eb2006`) isn't met. Both columns meet the Player targets bar of
90 s, set with the first warm-up's numbers (`c1a300d`). The eight passes add up to 291.4
pass-seconds in the `--report` run below, which is 58.3 s for five at once even if none ever
waits for another.

The four-player stadium pass ends last at 62.7 s in that run and can't be dropped, since 15 of
its keys come from no other pass. That pass builds its last key at frame 20,604 and plays on to
21,900, 900 frames past its route's last required frame, the margin every pass keeps.

A race that follows another starts from another state of the game. In the first order tried,
Sky Sands, Magma Flows and Frozen Hillside each missed one key their own passes built late, and
in the next Checker Knights missed 3. So Sky Sands and Magma Flows open the Air Ride routes as
their own routes race them, while Frozen Hillside and Checker Knights keep passes of their own.

Before is the manifest at Dragoon `3ce889a` and after is `2fc9285`, both at gcn-recomp `dac449e`
on an M4 Max. Each warm-up was `tools/warm_shaders.py --force` from an empty cache, and the load
is the 1-minute average when it began. The three after runs left byte-identical caches, and the
diff compares theirs with the 75.2 s run's, both ways.

The course runs were made as under "Longer course passes", four at once from a copy of the
after runs' 334-key cache. The 130 s runs,
`tools/probe.sh NAME 130 tests/routes/ROUTE.txt 100000 --real-time GCN_FRAMETIME=1`, reached
frames 7,673 to 7,676. All sixteen boots
loaded the cache's 334 programs in 521 to 532 ms, four games at once.

The `--report` runs under `GCN_FRAMETIME=1` split the pass time, both with this tree's tool and
the before one on `3ce889a`'s manifest. Chaining took 75.2 pass-seconds off. The starts and the
first 3,400 frames fell by 91.0 s, since 13 fewer passes boot and replay the opening, and the
rest grew by 15.8 s, since each later race's menus and start now come past frame 3,400.

| Stretch | Before | After |
|---|---|---|
| Starting the game | 8.4 s | 2.9 s |
| Frames to 2,000 | 99.6 s | 35.9 s |
| Frames 2,001 to 3,400 | 33.7 s | 11.9 s |
| The rest | 224.9 s | 240.7 s |
| All passes | 366.6 s for 21 | 291.4 s for 8 |
| Warm-up, with the load when it began | 76.8 s at 2.36 | 63.2 s at 1.58 |

## Mods

What a mods folder costs and what it catches, against the bars set for it. Times are on an M4 Max.

| Target | Bar | Measured | Result |
|---|---|---|---|
| Noticing a change | `mods.py check` on 120 MB takes 1 s or less, and any added, removed, edited or renamed file but a dotfile changes the digest | 0.08 s in each of three runs on 125,829,120 bytes in 120 files, at a load of 3.0 (`mods.py` as at Dragoon `d0f3272`). `test_mods.py` adds, removes, edits and renames a file, renames a mod and moves a file between mods, and each changes the digest | Pass |

The files were 120 pieces of 1 MiB from `/dev/urandom` in one mod's `files/audio/`, written just before, so they were in the page cache. `check` ran under the Command Line Tools' Python 3.9.6 with `/usr/bin/time -p`, and the row gives its real time.

## Goldens

The frame and audio goldens were recorded at fast disc reads on gcn-recomp `b5ec329` and Dragoon
`39c8d8f`, where the record changed 1,050 of the 1,906 frames on every route but the title, along
with all 48 audio rows. Route for route, those are the counts a check with fast reads found before
gcn-recomp took them. Two checks after the record matched all 1,906 frames and 48 audio rows.

| Routes | Frames changed |
|---|---|
| `title` | 0 of 16 |
| `menu` | 4 of 20, from frame 1,020 |
| `air-ride-race` | 37 of 100 |
| `city-trial` and `city-trial-4p` | 29 of 55 and 29 of 58 |
| Each one-course Air Ride route | 25 of 70 |
| `air-ride-courses-1` and `-2` | 126 of 229 and 96 of 194 |
| Each one-course Top Ride route | 44 of 60 |
| `top-ride-courses` | 140 of 186 |
| `city-trial-stadium` and `-4p` | 54 of 68 and 52 of 70 |

The menu's frames 1,020 to 1,200 hash as they did from `e1016b8` to `5e49451`, before reads were
timed.

All 24 checkpoint frames the record changed were dumped again on Dragoon `0bc2902`, and each
matched its golden and was looked at. How far it gets says what each shows, except
`top-ride-courses` frame 3600, which has no row and is byte for byte `top-ride-grass` frame 3600.

On Dragoon `30a3ca3` at gcn-recomp `782d7fa`, `tools/frame_hashes.py check` matched all
twenty-four routes' 1,906 frames in 14 min 37 s and `tools/audio_hashes.py check` all 48 rows in
14 min 27 s, at loads of 5.7 to 9.4.

None of those 24 bench logs has an `[interp]` line, so on those routes the code in RAM at boot
matched what the build was recompiled from and no unknown code ran. No `icbi` or code write the
engine saw changed an HLE'd function either. `GCN_INTERPRET_STATS` was off, so the logs don't
say whether any function ran interpreted.

## gcn-recomp `95e1c6b`

The pin moved from `782d7fa` to `95e1c6b`, 57 commits. Empty string switches now read as unset.
`recomp/riivolution.py` refuses a RAM patch list over the runtime's limit, and the desktop
frontend applies the `ram_patches` key in `settings.txt`. A session takes `--no-session-audio`.
The overlay's Dear ImGui opens no link and shows no Item Picker. The other commits drop code
nothing called, add tests or rework docs. A route's run directory starts with no `settings.txt`,
and no route names a patch list or a session.

Built on Dragoon `60dd08d`, `tools/frame_hashes.py check` matched all twenty-four routes and
1,906 frames in 14 min 37 s. `tools/audio_hashes.py check` then matched all 48 rows in 14 min
26 s, so no golden was recorded. The 1-minute load was 17.3 as the frame check began, just
after the build, 4.7 between the checks and 6.8 after the audio check.

None of the 24 bench logs has an `[interp]` line.

The speed runs came after the checks on the same build, one game at a time, at 1-minute loads
of 4.9 to 6.3. The race route ran hidden with `--fast` as
`tools/probe.sh speed-race 40 tests/routes/air-ride-race.txt 60`, and its dumps of frames 3,600
and 13,200 were written 18.72 s apart, 513 frames a second. In the audio check's
`dragoon_bench` run of that route, the one-second samples from 8 s to 20 s, about frames 5,000
to 12,800, averaged 601 frames a second, between 558 and 716.

`tools/probe.sh speed-ct4p 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1`
gave 4,309 guest intervals from frame 3,400 (`tools/frametime.py --from 3400`). They averaged
16.69 ms, with 16.78 ms at the 95th percentile and 16.95 ms at the 99th. Two went over 20 ms,
42.15 ms at frame 5,886 and 20.60 ms at 6,923. The frames on either side of the 42 ms one drew
the same 3,904 draws, and what held the guest wasn't checked.

`tools/probe.sh speed-stadium 360 tests/routes/city-trial-stadium.txt 100000 GCN_FRAMETIME=1 --real-time`
started with an empty shader cache and reached frame 21,553. From frame 4,400 the guest
averaged 16.72 ms, and 12 intervals went over 20 ms. The four longest were 105 ms at frame
15,613, 119 ms at 16,203, 156 ms at 16,502 and 160 ms at 20,054, each within 7 frames of a
scene change under Top Ride and the stadium at the game's speed.

In the audio check the four-player bench fell from about 360 to between 92 and 138 frames a
second for its last 7 s, with the same work per frame. A rerun of that route's check matched its
2 rows and held 256 to 380 from 8 s to the end, so the drop didn't repeat on the same build.

## gcn-recomp `5e54665`

The pin moved from `95e1c6b` to `5e54665`, 16 commits. The overlay menu has a Controllers page,
and a notice over the game says when a controller connects, disconnects or changes player
(under Controllers). `render_gl.cpp` is split into a file per job, which cut the
`GCN_ONLY_COMP`, `GCN_COMPLOG` and `GCN_NOCULL` switches and renderer state nothing read, and
`test_ports.cpp` into a file per area. The other commits merge repeated code into shared helpers,
drop code nothing called or rework comments. A probe run passes `--no-gamepads` and no route
opens the menu.

Built on Dragoon `92405f1`, `tools/frame_hashes.py check` matched all twenty-four routes and
1,906 frames in 14 min 38 s. `tools/audio_hashes.py check` then matched all 48 rows in 14 min
27 s, so no golden was recorded. The 1-minute load was 31.5 as the frame check began, just
after the build, 7.4 between the checks and 10.6 after the audio check.

None of the 24 bench logs has an `[interp]` line.

## Disc reads

gcn-recomp reads the disc fast by default, with a read costing 600 us and its length at
32 MiB/s, as Dolphin's "Speed up disc transfer rate" has it (`runtime/hw/drive.h:64-65`), and
`disc console` in `settings.txt` or `--disc=console` times reads as a console's drive does. The
speed goes into the input log and `session.json`. A replay reads at the speed its log names, and
a log with no disc line replays at `console` and says so.

The menu route ran hidden in real time to frame 1,500 with `--log=dvd`, `GCN_FRAMETIME=1` and
`GCN_CLOCKLOG=1`, once at each speed, on Dragoon `39c8d8f`. The intervals are guest time from
`tools/frametime.py --late 100`, and the reads are the `[DVD] read` lines inside them, with
KiB rounded down.

| Interval | `fast` | `console` |
|---|---|---|
| Boot, to frame 2 | 527 ms (229 reads, 3,550 KiB, 246 ms drive) | 2,521 ms (229 reads, 3,550 KiB, 2,243 ms drive) |
| After the A at 300 | f303, 401 ms (34 reads, 2,960 KiB, 111 ms drive) | f303, 1,502 ms (17 reads, 1,328 KiB, 1,271 ms drive) |
| START at 1000 to the mode select | f1003, 213 ms (17 reads, 1,267 KiB, 49 ms drive) | f1002, 1,514 ms (130 reads, 2,872 KiB, 1,579 ms drive) |
| f1032 | under 100 ms | 149 ms (6 reads, 241 KiB, 169 ms drive) |
| Route reads | 1,005, 31.4 MiB, 1,584 ms drive | 760, 27.4 MiB, 11,781 ms drive |

A second fast run made the same number of reads in each interval with the same drive time, and
its three intervals came within 2 ms of the first run's. gcn-recomp's diagnostics put the route's two scene
changes at 400 ms and 213 ms at `fast` and 1,485 ms and 1,458 ms at `console`. A playtest's input
log recorded at `bad7160`, with no disc line, replayed with a first read of 69,464 us, and the log
the replay wrote says `# disc console`.

`dragoon_bench` reads neither `settings.txt` nor `--disc`, so `tools/audio_hashes.py` records
and checks at fast reads. With every route run once at each speed under `GCN_AXVOICES=1` at
`b5ec329`, `tools/stream_voices.py` found no music stream that ended early in any of the 48 runs
(`audio.md`).
