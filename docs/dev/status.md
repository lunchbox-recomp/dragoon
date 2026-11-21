# Status

What's true of Dragoon, measured on one Mac. Most sections name the Dragoon or gcn-recomp
commits they were measured at. The pin is gcn-recomp `b4f8ddb`, where all twenty-four routes'
frames and audio match the goldens recorded at `b5ec329` (under gcn-recomp `b4f8ddb`). The
goldens of the twenty-fifth route (`city-trial-2p`) and the 16:9 frames of every route were
recorded at the pin (under Goldens).

| Feature | Status | Note |
|---|---|---|
| Boot and memory card | Works | A blank card gets the game's prompt by frame 60, and the save file is made. The game writes the card after each title screen and when its Sound screen closes, and in one pair of runs the Sound screen's Mono and balance came back on the next launch. Mono is in the console's SRAM, which gcn-recomp keeps in `saves/sram.raw` (table under Memory card) |
| Opening movie | Plays | Then the title and the attract demos, races and mode movies |
| Title screen | Works | `tests/routes/title.txt` |
| Mode select | Works | `tests/routes/menu.txt`. The preview window at its right shows a race |
| Air Ride race | Runs | All eight courses a blank memory card can pick load and race past the countdown, one route each in `tests/routes/`, with no crash and nothing seen drawn wrong. Fantasy Meadows (`air-ride-race.txt`) has three laps and the other seven two. With nobody steering, six reach the results screen and Kirby stays stopped against a wall on the other two (table under How far it gets). Nebula Belt, the ninth course, is locked on a blank card behind an Air Ride checklist box that counts 100 laps |
| City Trial | Runs | One player (`tests/routes/city-trial.txt`), or two or four in split screen (`city-trial-2p.txt`, `city-trial-4p.txt`), the five-minute clock running. With the clock cut to three minutes and the stadium set to Drag Race in Game Settings, one player (`city-trial-stadium.txt`) or four (`city-trial-stadium-4p.txt`) play out the clock and reach Drag Race 3 and its results. A fresh save offers only Drag Race, Target Flight and Destruction Derby besides Shuffle, and no route plays the last two, though a bot soak reached Destruction Derby's results (under Bot soak) |
| Top Ride | Runs | All seven courses a fresh save offers (Grass, Sand, Sky, Fire, Light, Water and Metal) race past the countdown with one player and three CPUs (`top-ride-<course>.txt`) |
| Audio | Partial | The mixer runs the commands of the game's ucode (`07F88145`) with its compressor among them, and ten runs' 484,400 command lists held no unknown or skipped one (under Audio). Source type 0 voices, 98.9% of the voice time, resample through a polyphase filter whose coefficients the runtime works out because the console's are in the DSP's ROM, and the low-pass filter isn't applied. Nobody has listened for the sound's quality since the source type 2 fix or compared it with a console, and the click counts are in [`scorecard.md`](scorecard.md), last scored at gcn-recomp `dac449e` (`audio.md`) |
| Controllers | Four ports, live | Each gamepad takes the port `saves/ports.txt` says it was last on, or else its SDL player number's or the lowest free one. The overlay menu's Controllers page swaps, removes and orders players by who presses A, and a notice says when a controller connects, disconnects or changes player (under Controllers). GameCube A is the east button on a Nintendo-layout pad such as an 8BitDo in Switch mode. Checked with SDL's virtual gamepads, not with four real controllers or under Steam Input |
| Picture | 4:3, or wider with Air Ride's and City Trial's HUD anchored and the menus centered | The window opens at 4:3. `--aspect=16:9` stretches the picture, and the world cameras widen to match in the race before and after its finish, in City Trial, 2P and 4P and in Top Ride. The HUD keeps its 4:3 shape at the race, City Trial, 2P and 4P checkpoints, anchored to the edges of the screen or of its player's view, as all four showed on Dragoon `1ff85c8`. The title, the menus, the text boxes and the opening movie keep their 4:3 frame in the middle. On Dragoon `2d68a1e` the 16:9 output dumps of the text box, the movie and the course select went from 3414x1920 at 1.7781 to 2560x1920 at 1.3333 with bars of 427, the title from 2.1815 to 1.6351 (1.6358 at 4:3) and the mode select from 1.9094 to 1.4312 (1.4318). Top Ride's HUD, which it draws outside every render callback, and a menu over play stretch with the picture. On Dragoon `ec0004a` `drawlog.py hud` listed Top Ride's 38 HUD draws at 3600 as stretched, and the race after its finish at 8400, City Trial and 2P gave the same results as on `e79f475`. At an output narrower than 4:3 the menus stretch too (`widescreen.md`). The HUD the table anchors still remaps there, each piece widened from its anchor by 4/3 over the output's aspect (4/3 at 1:1). No run measured it. At 16:9 every route has goldens of its own in `tests/hashes/gl-16x9/`, which `tools/frame_hashes.py check --aspect=16:9` checks. None of their 1,964 frames hashes as at 4:3. Four players at 16:9 and `--scale=2` hold `[rt]` to 4.20 ms at the 99th percentile. The race finishes in 1:14.68 as at 4:3. The picture compiles no program that 4:3 doesn't (Player targets) |
| Speed | Holds 60 fps | 517 to 524 frames a second in four runs of a race in a hidden window with `--fast` at loads of 3.2 to 5.6, against 515 to 536 at `236e1f4` and 517 to 540 at `541a6ae` (under gcn-recomp `b4f8ddb`). `dragoon_bench`, which draws nothing, runs the race at about 560 to 590. Run in turn at loads of 5.3 to 6.8, builds at `b4f8ddb` and `236e1f4` gave 561.6 to 578.4 and 558.7 to 588.9, so the bump didn't move it (under gcn-recomp `b4f8ddb`). Four-player City Trial averages 16.68 ms a frame in each of two runs at the game's own speed, with no interval over 20 ms in one and two in the other, the worst 21.94 ms, not traced. The stadium's scene changes stall the guest for up to 161 ms (under gcn-recomp `14712b8`). Four-player City Trial and the stadium weren't run again at `80ef3a7`, `541a6ae`, `236e1f4` or `b4f8ddb` |
| Build from the disc | Works | 23 s at gcn-recomp `67a7e30` (3.5 s to configure, 19.5 s for Ninja). That's before the build compiled SDL3 and Dear ImGui and before the default target ran the shader warm-up, which added about 64 s with its eight passes (`CMakeLists.txt:69-78`). Its ninth pass came later with `city-trial-2p`. Nine passes five at a time haven't been timed (Player targets) |
| Disc check | Works | The wrong disc stops the configure step with the disc ID it found |
| `.gcm` dumps | Work | Linked as `rom/game.iso`, or passed as `-DGAME_ISO=<path>` |
| Disc path with spaces | Works | Configures, and its `dragoon_bench` builds and runs |
| Running from another directory | Works | The configured disc path is compiled in. The memory card and shader cache are in `saves/` in the current folder, so a run from another folder starts with a blank card and compiles shaders as it goes. The overlay menu's Display page writes `settings.txt` in the current folder when it changes the picture or its Menu sounds box, and later runs started there read it |
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
own `CMakeLists.txt:41-45` pins by SHA-256 and CI's macOS job turns on (`tools/ci.py:108-109`).
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

CI's macOS job runs `ninja unit` (`tools/ci.py:111`), which builds the engine's own unit tests
and runs them under CTest with `--no-tests=error --timeout 300 --output-on-failure`
(`gcn-recomp/CMakeLists.txt:1463-1466`). It builds `dragoon_tests` too and runs it once to list
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
`Platform_OpenInShellFn` after both backends start (`runtime/overlay/overlay.cpp:255-257`), and
`TextLinkOpenURL` calls nothing when it's null, so a click on the link opens nothing. Since
`2246986` the tooltip has no Item Picker button (`runtime/overlay/overlay.cpp:240`,
`imgui.cpp:11366`). The overlay also sets `IniFilename` and `LogFilename` to null, so Dear
ImGui writes no file (`runtime/overlay/overlay.cpp:239-241`).

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
need `--pads=4`, and the two-player route `--pads=2`.

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
| Machine Passage after Magma Flows | `air-ride-courses-2.txt` | 16100 | Lap 1 of 2, 0:14, fourth, stopped against a dark metal wall |
| Beanstalk Park after Machine Passage | `air-ride-courses-2.txt` | 19900 | Lap 1 of 2, 0:14, third, on a grass slope with CPUs ahead |
| City Trial | `city-trial.txt` | 3300 | The city, 4:54 left |
| Four-player entry | `city-trial-4p.txt` | 2700 | P1 OK to P4 OK under READY?, each player joined from its own port |
| Four-player City Trial | `city-trial-4p.txt` | 3480 | Four views, 4:51 left, ports 1 and 3 steering left and 2 and 4 right |
| Two-player entry | `city-trial-2p.txt` | 2700 | P1 OK and P2 OK under READY?, P3 and P4 empty, "Time: 5 min [Shuffle]" |
| Two-player City Trial | `city-trial-2p.txt` | 3480 | Two views, one over the other, 4:51:10 on the clock between them, port 1 steering left and port 2 right |
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

Once a gamepad has a port, its player number is set to the port (`runtime/gamepads.cpp:166-173`).
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
| Shaders compiled during play after the warm-up | 0 `[shaders] compiled program` lines on the five routes | 0 on all five after the eight-pass warm-up, with the race run to frame 7,701 (Dragoon `2fc9285`). The eight Air Ride course routes compiled none, unpaced to frame 16,000 or in 130 s real-time runs (under Chained course passes). On a build of Dragoon `c147cec`, unpaced to frame 6,900 from the nine-pass cache, the race compiled 1, as did four Top Ride routes (Shaders compiled at 16:9). A bisect put the race's compile at Dragoon `39c8d8f`, the gcn-recomp `b5ec329` bump for fast disc reads. The race compiled 0 at `2fc9285` (gcn-recomp `dac449e`) and at `ab9f443` (`bad7160`), and 1 at `39c8d8f`. The fast reads changed two chained races, and the Checker Knights and `top-ride-courses` passes now play on to 8,600 and 20,050 for the two programs (under Chained course passes). From that warm-up's 343-key cache all twenty-five routes compiled 0, each played unpaced to the frame its warm-up pass plays it to, the race to 6,900, one at a time at `nice -n 19` and loads of 13 to 121 (a build of Dragoon `ae3bfe8`) | Pass |
| How far the attract demos alone get | Report the share of each route's keys the attract pass builds by itself | The warm-up has no attract pass. Run from a blank card it sat at the "make a new save data file?" prompt and built 3 keys in 20,000 frames. Run after the routes, on the card they leave, it took 50 s and added 9 keys on top of the routes' 191, none of which a route needed | Dropped |
| Time added to the first build | 90 s or less | 63.6 s, 62.9 s and 64.7 s at loads of 2.40, 9.77 and 10.54 for the 334 keys of all twenty-four manifest routes in eight passes, five at a time on an M4 Max (Dragoon `2fc9285`, under Chained course passes). A ninth pass, `city-trial-2p`'s, has 7 keys no other pass builds (`manifest.txt`). One at a time on a build of Dragoon `c147cec` the nine passes took 230.4 s for 340 keys at loads of 4.0 to 5.1. With the longer Checker Knights and `top-ride-courses` passes, on a build of Dragoon `ae3bfe8`, the nine passes took 233.7 s for 343 keys one at a time at a load of 5.1, and 69.7 s five at a time at 5.3, in one run each, not niced | Pass, 69.7 s for nine passes in one run |
| Time added to every boot on macOS GL | 1,000 ms or less | 475 to 508 ms for 334 programs at loads of 1.20 to 2.25 (Dragoon `2fc9285`). The four-player runs at 16:9 and 4:3 built the nine-pass cache's 340 in 837 ms and 529 ms at loads of 2.9 and 4.2 (a build of Dragoon `c147cec`) | Pass |
| Frames | `tools/frame_hashes.py check` passes | All twenty-four routes' 1,906 frames match the goldens recorded at gcn-recomp `b5ec329`, at the pin `b4f8ddb` on Dragoon `ae7ebd1`, in one pass of 15 min at `nice -n 19` and loads of 4.8 to 6.1. At `236e1f4` it took three passes, where a busier Mac cut runs short (under gcn-recomp `b4f8ddb`). With `city-trial-2p` added, all twenty-five routes' 1,964 frames matched on a build of Dragoon `c147cec` in 15 min at `nice -n 19` and loads of 3.4 to 5.3 | Pass |
| World at 16:9 | Every world camera's projection aspect is its 4:3 value times 4/3, to three figures, in one player, 2P and 4P. No HUD or menu camera changes | 1.67383 from 1.25538 in the race before and after its finish and in City Trial, 2.97524 from 2.23143 in 2P, 1.85892 from 1.39419 in 4P and 1.57333 from 1.18 in Top Ride, each steady over 600 frames or more. Every HUD 3D, minimap and menu camera kept its 4:3 aspect (Dragoon `45c52c5` at loads of 2.7 to 6.3, `widescreen.md`) | Pass |
| Edges | At every checkpoint the world makes at least as many draws at 16:9 as at 4:3, and no dump shows an object cut off at a side edge | 217 draws against 204 in the race, 124 and 124 after its finish, 376 against 371 in City Trial, 317 against 314 in 2P, 823 against 807 in 4P and 198 and 198 in Top Ride. No output dump at 16:9 shows an object cut off at a side edge. The test that culls the world wasn't found, so pop-in while moving needs a person to watch (Dragoon `45c52c5` at loads of 2.7 to 6.3) | Pass |
| Simulation | Left alone, the race finishes at 16:9 in its 4:3 time, 1:14.68 at `5e49451` | The results frame at 25,800 is the same at 16:9 as at 4:3 (Dragoon `45c52c5` at loads of 4.5 to 6.1). On a build of Dragoon `c147cec` at gcn-recomp `b4f8ddb`, the race left alone finished first in 1:14.68 at both aspects, with the CPUs on 1:15.40, 1:15.57 and 1:16.36, read from each run's frame 25,800. Since the results screen now keeps its 4:3 frame between bars, the two frames no longer hash the same. Each was `tools/probe.sh NAME 150 tests/routes/air-ride-race.txt 300 --exit-after=26700`, plus `--aspect=16:9`, at `nice -n 19` and loads of 2.9 to 4.1. Until gcn-recomp rounded frC as Gekko does, `air-ride-courses-2` played differently at 16:9: by 19,400 on Beanstalk Park every rider's speed and position was off by up to about 1.1 units. That bump moved the route's races and checkpoints, and since then every route's state matches 4:3 at its checkpoints (`state_goldens.py check --aspect=16:9`). At gcn-recomp `3444827`, `ram_peek.py` read every rider's speed and position as raw bytes every 100 frames from 18,800 to 20,700 at both aspects, through Beanstalk Park's race from 18,900. All 20 reads matched bit for bit, 19,400 among them. Each was `tools/ram_peek.py --at 18800-20700/100 --script tests/routes/air-ride-courses-2.txt NAME 300 8053627C:16 8055AA2C/2C/300:12 8055B338/2C/300:12 8055BC44/2C/300:12 8055C550/2C/300:12 -- --exit-after=20800`, plus `--aspect=16:9`, on AC power, one game at a time | Pass |
| HUD at 16:9 | Every HUD draw keeps its 4:3 width, height and distance to its anchored edge within 1 display pixel at 480 high, in the race, 1P City Trial, 2P and 4P | `drawlog.py hud` passed every anchored draw, 41 in the race (also with `GCN_GX_SYNC=1`), 33 in City Trial, 54 in 2P and 76 in 4P, on Dragoon `e52dce1` at loads of 1.5 to 3.1. It passed with the same counts under the stricter tool on Dragoon `1ff85c8` at gcn-recomp `b11ebc6`, where all twenty-four routes' frames and audio matched. Top Ride's 38 HUD draws still stretch, and so do the bars between split views, since they span the screen (`widescreen.md`) | Pass |
| Split views | Every HUD box stays inside its own view at 16:9 | No HUD box in 2P or 4P sticks out of its view by more than 1 pixel more than at 4:3. The 4P clock sits on the bars and anchors to the screen's left edge (Dragoon `e52dce1` at loads of 1.5 to 3.1) | Pass |
| Frames at 16:9 | Every route recorded twice at 16:9, and the two passes match | `tools/frame_hashes.py record --aspect=16:9` wrote all twenty-five routes' 1,964 frames in 17 min, and `check --aspect=16:9` straight after matched all 1,964 in 15 min, at `nice -n 19` and loads of 3.2 to 5.1 (a build of Dragoon `c147cec`, gcn-recomp `b4f8ddb`). A third pass, the check after the tools suite, matched all 1,964 again in 16 min at loads of 5.0 to 5.3. Every frame differs from its 4:3 golden, from frame 60 on, since the game's 640x480 dump holds the picture before the window stretches it | Pass |
| Four players at 16:9 | `[rt]` 8 ms or less at the 99th percentile, as at 4:3 | From frame 3,400, over 4,265 frames, `[rt]` was 1.90 ms on average, 2.81 ms at the 95th percentile, 4.20 ms at the 99th and 6.77 ms at worst, with no frame over 8 ms. The guest interval was 16.69 ms on average and 16.97 ms at the 99th, with one of 42.19 ms at frame 3,679. A 4:3 run straight after gave 1.84, 2.73, 4.26 and 5.48 ms over 4,287 frames, and one interval of 45.09 ms at 6,645. Neither compiled a program. Each was `tools/probe.sh NAME 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time --scale=2 --aspect=16:9 GCN_FRAMETIME=1`, the second without `--aspect`, from a copy of the nine-pass warm-up's 340-key cache, read with `tools/frametime.py LOG --from 3400`, not niced, at loads of 2.9 to 4.2 (a build of Dragoon `c147cec`) | Pass |
| Shaders compiled at 16:9 after the warm-up | 0 `[shaders] compiled program` lines on every route. The warm-up's claim at 4:3 covered the five routes of the row above and the eight Air Ride course routes, not every route | 6 programs on 6 of the twenty-five routes, one each. Two are `air-ride-race` and `air-ride-courses-2`. Four are the Top Ride Sky, Fire, Water and Metal routes. Those six compiled the same 6 when they ran again. They are two keys, one on the two Air Ride routes and one on the four Top Ride ones. At 4:3 the same cache compiled 5, the same two keys on the same routes but `air-ride-courses-2`. So 16:9 builds no key 4:3 doesn't, and draws the Air Ride one on one more route, but the warm-up misses both keys at either aspect. Each route played unpaced to the frame its warm-up pass plays it to (`warm=` or 900 past its last required frame), as `tools/probe.sh NAME SECONDS tests/routes/ROUTE.txt 100000 --exit-after=N GCN_FRAMETIME=1` plus its manifest settings and `--aspect=16:9`, from a copy of a nine-pass warm-up's 340-key cache, at `nice -n 19` and loads of 3.7 to 6.7 (a build of Dragoon `c147cec`). From the 343-key cache of the warm-up with the longer Checker Knights and `top-ride-courses` passes, the six compiled 0 at 16:9, played the same way at loads of 7.0 to 8.7 (a build of Dragoon `ae3bfe8`). The other nineteen compiled 0 at 16:9 from the 340 keys, all of which the 343 hold | Pass |
| Launcher's settings.txt writes | Byte for byte what the engine's `settings_save` writes, on shared fixtures | 22 of 22 fixtures the same on the real and the fake file system: BOM, CR LF, a first newline in CR LF and a last in LF, a last line with no newline, comments, unknown keys, bytes that aren't UTF-8, missing, duplicate and bad keys, and a `menu_sounds on` kept, a bad one skipped and an `off` after an `on` taken (`PictureSettingsTests`) | Pass |
| Launcher's Settings preview | Every size it shows is the engine's | 50 window sizes for the five aspects in ten usable areas, 40 fullscreen pictures on eight displays and the internal picture at scales 1 to 10 match the engine's `aspect.h` and `kMaxInternalScale` (`PictureGeometryTests`), and the preview draws each of those windows and fullscreen pictures, checked row by row against the same tables (`SettingsPreviewTests`) | Pass |
| Launcher's Settings sheet opening | 100 ms from Settings to the sheet drawn | 55 to 71 ms in a test process of its own and 17 to 19 ms in the full suite (`SettingsSheetTests`) | Pass |
| Launcher writing settings.txt while the game runs | Never | Never, in `FlowSettingsTests`: Settings does nothing and a pick saves nothing while the launcher's or an earlier launcher's game runs, and Play waits while the sheet is open. Never in `FlowPictureCardTests` either: the Picture card doesn't show while a game runs, a pick saves nothing once one does, and Play and Back to Library wait while the card's read or save is on its way, so Library's Play can't start the game before the card's save is done | Pass |
| Launcher's Picture card | Shown once, after the first build, only when settings.txt has no `aspect` line; a pick writes what the Settings sheet's does; Keep 4:3 writes nothing | Shown after the build that made the first game and remembered in `launcher.json`, not after a rebuild, not by a launcher that showed it, not over any `aspect` line or a file that can't be read (`FlowPictureCardTests`). Each pick, 4:3 and 16:9, over four files without an aspect line writes the sheet's bytes, and over `bom-only` and `empty` the engine's own `settings_save` bytes (`PictureCardWriteTests`) | Pass |
| Opening the menu pauses | The guest is held within 2 host frames, as before | `test_ports` passes "a gamepad's Back opens the overlay, and the guest is held within 2 host frames" (`tools/test_ports_menu_no_window.cpp:66`), one of the 499 port checks `gcn-recomp/tools/test_ports.sh build/test_ports DIR` passed at a load of 7.2 | Pass |
| Menu open to fully shown | 200 ms or less, and its first frame with `menu_motion off` | 20 opens over the title at frame 600 said `[overlay] shown after` 180 to 190 ms: 180 ms six times, 181 twice, 182 three times, 188 four times, 189 three times and 190 twice, at loads of 3.0 to 3.3. With `menu_motion off` in the run's `settings.txt` it said 3 ms at 2.7, and `test_ports` passes "with menu_motion off it opens whole and closes at once". That check finds the menu not moving after the press and release host frames. The game's 3 ms line is what shows it whole within one frame. It prints no frame count. Each run was `tools/probe.sh NAME 40 "" 100000 GCN_OVERLAY_AT=600:60 --exit-after=900`, not niced | Pass |
| Menu smooth while it moves | The held frame redrawn every 17 ms or less at the 99th percentile, and the menu's CPU time a frame 1.5 ms or less at the 99th, at 1920x1080 | 21 opens over the title at frame 600, one a process and so each its process's first, seven on each of `GCN_OVERLAY_PAGE` 0, 1 and 2, in a 3414x1920 window, since nothing sets the game's size. At gcn-recomp `b4f8ddb` the 1,260 `held 1` redraw intervals of their `[overlay] frame` lines were 16.67 ms at p50, 17.00 ms at p99 and 25.08 ms at most, with 12 over 17 ms, the most its p99 allows at the line's 0.01 ms, and the menu's CPU time over all 1,428 frames was 0.055 ms at p50, 0.722 ms at p99 and 3.431 ms at most. The tail is the loop thread waking on efficiency cores. The 13 intervals from 17.00 to 17.26 ms had a `thread` of 0.343 to 0.399 ms and a `swap` of 0.262 to 0.855 ms, where the other 1,246 had 0.056 ms and 0.373 ms at p50. In 12 of the 13 `thread` came within 0.023 ms of `present` and `blur`, so the thread mostly ran slower rather than waited, and the swap stayed as it was. The 25.08 ms came after a `swap` of 24.776 ms, the run's longest. Each run was `tools/probe.sh NAME 40 "" 100000 --real-time --aspect=16:9 GCN_FRAMETIME=1 GCN_OVERLAY_AT=600:60 GCN_OVERLAY_PAGE=N --exit-after=900` from a copy of the warm-up's cache, read with `tools/frametime.py --menu`, not niced, at loads from 7.1 falling to 3.2 (Dragoon `ae7ebd1`, read at `360dd44`). The gcn-recomp `80ef3a7`, `541a6ae`, `236e1f4` and `b4f8ddb` sections hold each pin's numbers | Pass, with the redraw interval's p99 on the bar |
| Menu closed costs nothing | Four players at `--real-time --scale=2`, `[rt]` at the 99th percentile within the two-run spread; no Dear ImGui menu frame over 600 closed frames | `[rt]` at the 99th percentile from frame 3,400 was 2.08 and 2.09 ms with the menu built in and closed, and 2.11 and 2.12 ms in a build with `-DGCN_OVERLAY=OFF`, over 4,230 to 4,283 frames. Each build's two runs are 0.01 ms apart, and the menu's build is 0.02 to 0.04 ms under the other. That's outside the 0.01 ms spread on the cheap side. The bar is read as no cost above the spread. The runs took turns, on, off, on, off, from a copy of the warm-up's 333-key cache, not niced, at loads from 17.2 just after the build down to 3.9, each `tools/probe.sh NAME 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time --scale=2 GCN_FRAMETIME=1`, plus `--bin=build-nooverlay/dragoon` for the second build. `test_ports --pages` counted 0 menu frames over 300 closed host frames at 1920x1080 and 300 at 1440x1080, and `test_ports` passes "a closed menu with no notice costs zero Dear ImGui menu frames" | Pass |
| Menu leaves 4:3 unchanged | `tools/frame_hashes.py check` passes | The Frames row, at the same pin and build | Pass |
| Audio unchanged with the menu's sounds on | The route audio hashes match with sounds on | All 48 rows of the twenty-four routes match in windowed runs with `menu_sounds on` in each run's `settings.txt` and the menu opened over frame 600 and closed after 60 redraws, and each log has its `[overlay] open` and `[pause] resumed` lines. That's `tools/audio_hashes.py menu`, which runs each route as `tools/probe.sh NAME SECONDS tests/routes/ROUTE.txt 100000 GCN_AXSTATS=1 GCN_OVERLAY_AT=600:60` plus its manifest settings, at twice its manifest seconds. It took 29 min 6 s at `nice -n 19`, with 1-minute loads of 4.4 as it began and 5.5 as it ended (Dragoon `ae7ebd1`, gcn-recomp `b4f8ddb`), against 29 min 23 s at `236e1f4` and 29 min 7 s at `541a6ae`. `dragoon_bench` has no menu, so `tools/audio_hashes.py check` can't open it. No line says whether a sound played under SDL's dummy audio driver, and the hashes are of the mixer's blocks, which the sounds join later (`test_ui_sound` checks a `GCN_WAV` capture never holds them) | Pass |
| Menu sounds clean | Peak -12 dBFS or lower, first and last sample 0, 2 ms attack and release, no click from `tools/audio_clicks.py`, heard within one callback | `test_ui_sound` passed 366 of 366 checks. Each of the eight voices peaks at -14 dBFS, starts and ends on a zero sample in both channels, rises over its first 2 ms and falls no faster than a 2 ms raised cosine, and "the next pull takes it and it's audible in that pull, over -60 dBFS". `tools/audio_clicks.py` on each voice, as `test_ui_sound DIR WAVDIR` wrote it, found 0 clicks, 0 gaps and 0 clipped runs. At a load of 5.5 | Pass |
| Menu contrast | Text 4.5:1 and the focus ring 3:1, in both themes | `test_overlay_theme` passed all 147 checks on the engine's default theme, the one Dragoon draws: text at 4.52:1 at least (Text on the selected tab) and the ring at 6.00:1 at least (beside a pressed item). Dragoon has no theme of its own, so there's no second theme to measure. Run as `build/test_overlay_theme`, untimed, so load doesn't bear on it | Pass for the default theme |
| Menu at couch size | Body text 22 px and targets 48 px at 1080 lines | `test_overlay_theme` passes "body text is at least 22 px at 1080 lines" and "nothing to press is under 48 px at 1080 lines, items included". Run as `build/test_overlay_theme`, untimed | Pass |
| Menu fonts | A theme with no font uses Dear ImGui's embedded font and says so once; the atlas 8 MB or less | `test_overlay_fonts` passed 32 checks. A theme that lists no font takes the embedded font and says so in one `[overlay] font` line, and with no font file there it says so once for each of the ten faces. With the Mac's Avenir Next faces up to 2,160 lines and with the embedded font up to 1,440, both at twice the density, no glyph fell back in an atlas texture held to the test's cap of 8.00 MB, so 8.00 MB is the cap, not a size measured. Run as `build/test_overlay_fonts DIR`, untimed | Pass |
| Notices | Gone at exactly 2 s | `test_ports` passes "it's there a nanosecond before 2 s and gone at exactly 2 s, with no frame after" with `menu_motion` on, off and under `--dump-output`, on the test's own host clock. Run in `gcn-recomp/tools/test_ports.sh build/test_ports DIR`, untimed | Pass |
| Menu pages switch | A shoulder or trigger moves one page. One held as the menu opens moves nothing, and none moves a page while an item is active | `test_ports` passes "R1, L1, the right and left triggers, E and Q each move exactly one page, on and back", "L1 held as the menu opens moves nothing, nor does letting it go" and the same for the left trigger and Q, "while a slider is active no shoulder, trigger or key moves a page". On a GameCube pad it passes "Z and each click turn a page as they're let go" and "Z held while a slider is active steps it faster and turns no page". Run in `gcn-recomp/tools/test_ports.sh build/test_ports DIR`, untimed | Pass |
| Menu review dumps | Each page dumped once settled at 16:9 and at 4:3 over a plain background. No golden holds them | `test_ports --pages` dumped its three pages in 1920x1080 and 1440x1080 windows over plain grey once each had settled, 37 of 37 checks, run as `env SDL_AUDIO_DRIVER=dummy build/test_ports --pages DIR`, whose dumps are untimed. In the game, `GCN_OVERLAY_PAGE` 0, 1 and 2 with `GCN_OVERLAY_PLAIN=1` dumped Display, Controllers and Mods at 2560x1920 and, with `--aspect=16:9`, at 3414x1920, each run `tools/probe.sh NAME 40 "" 100000 GCN_OVERLAY_AT=600:60 GCN_OVERLAY_PAGE=N GCN_OVERLAY_PLAIN=1 --output --exit-after=900` (plus `--aspect=16:9`) at loads of 3.4 to 4.0. No golden holds them, and the dumps were deleted | Pass |

The five launcher rows were measured on 2026-11-14 on macOS 26.6.2 with Swift 6.3.3. The
fixtures and the geometry tables come from `tools/settings_fixtures.py`, which builds a harness
against the pinned gcn-recomp's `runtime/settings.cpp`, `runtime/platform.cpp` and
`runtime/gx/aspect.h`, and its test checks it writes every committed file. They were last
written at gcn-recomp `864d9d4`, whose `settings_save` also writes `menu_sounds`. The sheet's time runs from the press through
reading a real `settings.txt` to an `NSHostingView` laid out and drawn, and leaves out AppKit's
slide in. Alone it's the first SwiftUI view the process draws. `SettingsSheetTests` fails over
100 ms on a Mac and only prints its time where `CI` is set, since a loaded runner took 126 ms.

The menu rows were measured on 2026-11-14 at Dragoon `05d18f1` and gcn-recomp `14712b8` on an
M4 Max, one game at a time. The smooth-while-moving and audio rows were measured again on
2026-11-15 at Dragoon `374b288` and gcn-recomp `80ef3a7`, which has the `[overlay] frame` line,
and again the same day at Dragoon `741b62c` and gcn-recomp `541a6ae`, which paces the held redraw,
and at Dragoon `a4cdc27` and gcn-recomp `236e1f4`, whose line splits the interval. They were
measured again on 2026-11-16 on a build of Dragoon `ae7ebd1` and gcn-recomp `b4f8ddb`, whose
line adds the loop thread's CPU time and the swap, and read with `360dd44`'s `frametime.py`. The engine's checks were built in the game's build directory with
`ninja test_ports test_overlay_theme test_overlay_motion test_overlay_fonts test_ui_sound` and
run at `nice -n 19`, except `test_ports --pages`, which times frames. The game runs that time
something weren't niced. A probe run starts the game in `build/probe/NAME/`, so its Mods page
says `tools/mod_choices.py` isn't there and offers Read again.

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
frame 14,400 and Magma Flows to 13,200, and Frozen Hillside's pass plays to 6,000
(`tests/hashes/manifest.txt:15-16`, `:33`).

The runs were
`tools/probe.sh NAME 400 tests/routes/ROUTE.txt 100000 --exit-after=16000 GCN_FRAMETIME=1` at
Dragoon `3f0f8c3` and gcn-recomp `dac449e`, hidden and silent, four at once.

### Chained course passes

The warm-up plays 9 passes. Three routes race one course after another, each for as long as its
own route's pass played it, and five more passes are the ones they were. The ninth,
`city-trial-2p`'s, joined after the chaining (under Goldens). Each route that
another route's pass plays has no pass of its own, through the manifest's `warm-from=` setting.

| Pass | Frames | What it plays |
|---|---|---|
| `title` | 1,860 | The title |
| `air-ride-frozen-hillside` | 6,000 | Frozen Hillside |
| `air-ride-checker-knights` | 8,600 | Checker Knights, played on for a program of `air-ride-race`'s |
| `air-ride-courses-1` | 23,800 | Sky Sands to frame 14,400, then Fantasy Meadows (`air-ride-race`) and Celestial Valley |
| `air-ride-courses-2` | 20,800 | Magma Flows to 13,200, then Machine Passage and Beanstalk Park |
| `top-ride-courses` | 20,050 | The seven Top Ride courses, Fire played on for a program of four Top Ride routes' |
| `city-trial-stadium` | 21,300 | City Trial and the stadium, for `menu` and `city-trial` too |
| `city-trial-stadium-4p` | 21,900 | The same with four players, for `city-trial-4p` too |
| `city-trial-2p` | 4,380 | City Trial with two players, added after the chaining |

The disc's fast reads (gcn-recomp `b5ec329`, Dragoon `39c8d8f`) cost the nine-pass warm-up two
programs, by changing how two chained races play out. The routes' own races hardly moved. With
`--disc=console`, which times reads as before, `air-ride-race` ran about one frame off its fast
run and compiled the same program at the same frame.

- `air-ride-race` draws a 36-vertex piece over a CPU rider (texture `9b701d0845da8f72`, four TEV
  stages) at frame 5,338. With timed reads, `air-ride-courses-1`'s Fantasy Meadows race drew it
  at 18,348. With fast reads it doesn't before the pause at 20,000, and played on it first draws
  it at 29,055. Checker Knights' race draws it at 8,436, so that pass plays to 8,600.
- Top Ride Sky, Fire, Water and Metal draw an item a CPU holds (texture `9f9f78513c8493a4`,
  three stages, the material the Air Ride passes build on an EFB with alpha) by frame 4,500,
  Sky at 3,965. With timed reads `top-ride-courses` drew it in its Grass race, at 4,232. With
  fast reads its Fire race draws it at 19,864, so that pass plays to 20,050.

Frozen Hillside played on to 12,000 and `air-ride-courses-2` to 27,000 never drew the race's
program. A pass of its own for `air-ride-race` would play 6,900 frames, and the two longer
passes add 4,050. `RealPassesTest` in `tools/test_warm_shaders.py` holds both passes past those
frames. From an empty cache the warm-up builds 343 keys, the 340 it built before and 3 more
(build of Dragoon `ae3bfe8`, gcn-recomp `b4f8ddb`, `shader_cache.py diff` both ways). Each run
was `tools/probe.sh NAME SECONDS tests/routes/ROUTE.txt 100000 --exit-after=N GCN_FRAMETIME=1`
from a copy of the 340-key cache, at `nice -n 19`.

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

### Two players and 16:9

`city-trial-2p` joined the manifest on a build of Dragoon `c147cec` at gcn-recomp `b4f8ddb`.
Its checkpoints are picked as the four-player route's were. 2700 is the entry screen with every
player OK, on the frame START is pressed. 3480 is the city in its views, 80 frames into the two
seconds of steering. Its 58 frames were recorded and matched by the check straight after.
Its audio rows are at lists 12,000 and 24,000, as the four-player route's are. Its hash first
differs from the one- and four-player City Trial routes' at list 8,400, and four bench runs gave
the same hashes at both rows.

The 16:9 goldens in `tests/hashes/gl-16x9/` hold all twenty-five routes, 1,964 frames, recorded
on the same build at `nice -n 19` and matched by `check --aspect=16:9` straight after (Frames at
16:9, under Player targets). Before the record a 4:3 check of the twenty-four older routes
matched all 1,906 frames in 18 min at loads of 3.2 to 4.5.

## Nightly

`tools/nightly.py run` reruns the frame, state and audio goldens, the Dolphin diff, the shader
compiles from a fresh warm-up, the timed rows above and four bot soaks on the real game, one
game at a time and only on AC power. The rows it reruns stay as measured here, and it never
edits this file. Its table of steps and bars is in `tools/README.md`.

```
tools/nightly.py run
tools/nightly.py run --only shaders timed
tools/nightly.py run --only dolphin
tools/nightly.py install-agent
```

The `dolphin` step runs after the goldens. It plays every route `tests/hashes/dolphin-triage.txt`
triages, Dragoon pinned against Dolphin, and compares each triaged checkpoint with its line. A
checkpoint fails the night when:

- its class changes: a `within` line is over the budget, has a state that isn't the same or a
  frame off, or is refused, or another line is refused
- its share moves more than the budget, 0.1%, above its line's, at the line's tolerance of 4
- its state differs or isn't read where its line's was the same or a frame off
- its race's first difference comes at an earlier pass than its lines say: City Trial pass 273,
  Air Ride pass 763, and Top Ride matching through pass 564
- its race shows no difference but Dragoon's run never reached Dolphin's last pass of it

A checkpoint that gets better comes under Improved and fails nothing. That's a later first
difference or none through Dolphin's last pass, a line now within, a share more than the budget
lower, a refused line now matched or a state that matches again. It says to update the triage
file. Each failure names the checkpoint, its line's class and score and tonight's, and the
side-by-side kept in the report's `dolphin/`. Each route plays the fields its `ROUTE fields=N`
line in the triage file gives. Dolphin's run of a route is reused from
`build/nightly/dolphin-cache/` while its `key.json` matches. The key holds the movie's and the
disc's sha256, Dolphin's binary and build record, its config and game INI, its watches, the disc
speed and fields, the triage file's head line and the macOS version. The movie also has to be
the route's fixed point still, and every dump has to match the sha256 `frames.txt` lists for
it. With no Dolphin in `dolphin-ref/` beside the clone the step is skipped and fails nothing.

On 2026-11-20 the step took 36 min with no saved runs, converging each movie in 7 Dolphin runs,
and 4 min 41 s reusing them. Its three Dragoon runs found the races' first differences where
the triage file has them: City Trial at frame 3005, pass 273, Air Ride at frame 3884, pass 763,
and Top Ride matching through pass 564. With gcn-recomp `6586763` reverted, 36 of its 47
checks failed. The menu checkpoints came back at their scores from before the pixel centre, such
as 2.677% at 60, 3.444% at 314 and 3.896% at 1013. On the unchanged build all 47 passed.

Read `build/nightly/YYYY-MM-DD-HHMM/summary.txt` first. Its regressions section lists each check
that passed in the last report and fails now, each new failure and each timed number more than
10% and 0.25 ms slower than the last report or this file's number, with the route, the frame or
field and the dump or log to open. A check that failed in the last report and passes now comes
under Improved and fails nothing. "Drew differently" is a frame whose hash changed, and "played
differently" a checkpoint whose state from guest RAM changed. A state check that differs from
its golden only by the values `tests/hashes/known-issues.txt` lists for it comes under Known
issues and fails nothing, and a number that far
faster than this file's comes under Improved, as a cue to measure the row again. A side-by-side
PNG puts the golden frame on the left when `build/nightly/golden-build/` can draw it again.
`report.json` holds every check, and the run exits 2 with the step marked skipped-battery when
the Mac was on battery.

`install-agent` writes the launchd job for 01:30 and prints it, and nothing loads it until
`launchctl bootstrap gui/UID FILE` does or the next login. The job runs in a clone of its own,
`dragoon-nightly` beside this one, with its own `build/` configured once as this one's is and
`rom/game.iso` linked to the disc. Each night it fast-forwards that clone to `origin/main`,
builds `dragoon` and `dragoon_bench` and refuses a clone with changes or off `origin/main`. It
skips a night it starts outside 01:00 to 06:00, and no run starts while another does or while a
`dragoon` or `dragoon_bench` process runs.

## Dolphin reference

Dolphin is the reference for what the game should do and how its 4:3 picture should look. The
goldens only say a frame hasn't changed, so the plan is to play our routes in Dolphin too and
compare the state and the picture at each checkpoint. `tools/dolphin_ref.py` pins Dolphin 2609a
(`409881c`), builds it from source with auto-update, analytics, RetroAchievements and the rest
of its online parts off, and runs it in `dolphin-ref/` beside this clone under a sandbox that
denies all network, DNS included. The build may write only `dolphin-ref/build` and Dolphin
only `dolphin-ref/user`, besides this user's temp and cache folders. The one socket Dolphin may
send to is its memory watcher's, inside `dolphin-ref/user`:

```
tools/dolphin_ref.py fetch
tools/dolphin_ref.py audit-notes
tools/dolphin_ref.py build
tools/dolphin_ref.py boot rom/game.iso --frames 2000 --dump --out DIR
```

`audit-notes` lists what the audit of the tree found and what each finding became.

Dolphin now plays our routes as input movies. The tag's headless frontend took `-m` and never
played it, so `tools/dolphin-ref/headless-movie.patch` has it call `PlayInput` before boot, as
the Qt frontend does, and opt out of relaunch at login. It changes `MainNoGUI.cpp` and nothing
else, and `build` and `boot` refuse a tree whose `git diff` isn't that patch, or that git was
told to hide an edit in. `tools/dtm.py` turns a route into a `.dtm`. The game polls the pad
twice a field from field 48 on, counted with the triggers on top-ride-grass from the title to
the race. Each poll gets the route's input at the game frame the field before its read had
reached in the movie's own last run, as `input_script_apply` gives it by
`gx::g_frames_submitted`. `dtm.py converge` makes the movie again from its run until it comes
out the same. From a first movie that maps field f to frame f, top-ride-grass took 7 runs at
console disc speed and 3 fast. On each speed's last run `dtm.py presses` read the game's queue
of pad reads and found all 11 presses read on their route frames.

Dragoon reads the disc fast by default ("Disc reads"), and the first movie ran Dolphin at
console speed, where a press counted in fields is held longer than it says. So the movie was
made at both speeds, and Dragoon `2702645` played the route at both with `tools/ram_peek.py`
printing scene.major and scene.minor every frame. The game frame each scene started at on
top-ride-grass on 2026-11-19, with Dolphin's field in brackets:

| scene.major/minor | Dolphin console | Dolphin fast | Dragoon console | Dragoon fast |
|---|---|---|---|---|
| 18/0, then 18/38, booting | 0 (169, 223) | 0 (62, 116) | 2 | 2 |
| 2/0, the opening and title | 304 (552) | 303 (429) | 303 | 303 |
| 3/2, the main menu | 1003 (1342) | 1004 (1157) | 1003 | 1003 |
| 5/24, Top Ride's movie | 1704 (2148) | 1704 (1877) | 1703 | 1702 |
| 5/7, course select | 2004 (2476) | 2004 (2196) | 2003 | 2004 |
| 5/9, machine select | 2608 (3128) | 2608 (2816) | 2608 | 2607 |
| 5/19, the race | 3234 (3793) | 3234 (3459) | 3234 | 3233 |
| game frame 3600 | (4264) | (3858) | | |

Frame numbers don't line up while booting. Dolphin's game shows no frame until field 244 at
console speed, so its boot scenes all come at game frame 0. By frame 3600 the fast disc is
406 fields ahead, but it moves Dolphin's scene changes by one game frame at most. Against
Dolphin at console speed, Dragoon at console speed is one frame off or less at every change and
the same at three. Dolphin fast against Dragoon fast is up to two off and the same at two. So
Q4c compares Dolphin and Dragoon both at console speed, by game frame. It's the closest
pairing, and both sides read as a console's drive does. `dolphin_ref.py boot` reads at console
speed unless `--disc fast` says otherwise. The one-frame differences are Q4c's to explain.

Two runs of the first movie gave the same watched words on every field and the same frame
dumps, 3657 shared; one run stopped a dump later than the other. For the new mapping, the
reviewer of `84b6876` played its console-speed movie, the seventh, again and got the same
`ram.txt`. Comparing the pictures is Q4c.

### Dolphin comparison

`tools/dolphin_diff.py` plays a route in Dolphin from its converged movie and in Dragoon, both
at console disc speed and one game at a time. It compares them at the route's goldens and at
each scene's first frame and 10 frames in, from frame 60 on.

```
tools/dtm.py converge tests/routes/ROUTE.txt rom/game.iso --fields N --dir DIR --disc console
caffeinate -i nice -n 19 tools/dolphin_diff.py run ROUTE --movie DIR/movie-K.dtm
```

Read `build/dolphin-diff/ROUTE/summary.txt` first. Each checkpoint has the Dolphin dump it was
matched to and how sure the match is, then the picture score and, apart from it, the state.
"still" means the dumps around it look alike, so the match can't be told from the picture.
"refused" means no match, with the reason given. Nothing is scored there. The score is the share
of pixels off by more than 4 in any channel, then the largest and mean channel error. Over
0.1% goes to triage. Look at `sides/ROUTE-FRAME.png`, Dragoon, Dolphin and the difference, and
record what it shows in `tests/hashes/dolphin-triage.txt`. Two runs of each side on top-ride-grass
gave identical pictures and state, so any difference is between the two, not noise. That
holds for those runs only. The triage file is one look, not a pass or fail.

The first count of Dolphin's game frames lost a frame every 60 fields from boot on. The game
sets vi.renew_count back to 0 once every 60 fields (80410D84 to 80410DC0), and a frame it shows
on that field went uncounted. vi.renew_last (80589C70) keeps what the count reached, and
`dtm.game_frames` adds it on those fields. It now equals `vi.next_buffer`'s count of pictures on
every field of a top-ride-grass run, 4400 fields and 67 resets. At the main menu's first field
(1342) the old count gave 1003 and the new 1020, and at Top Ride's race (3793) 3234 and 3288.
The old count agreed with Dragoon's frame count at scene changes only because that loss offset
Dolphin's extra pictures. All three routes' movies were converged again on the new count, each
in 7 runs, and `dtm.py presses` found all 11 presses on their route frames on each.
top-ride-grass's scenes now start at Dolphin's frames 1003, 1704, 2004, 2609 and 3235, within a
frame of Dragoon's.

On the new count and movies, most menu checkpoints scored exactly as before. The state matched
at every checkpoint compared before City Trial's city, 1003 and 1013 included. The card prompt
at 60 is the same panel on both sides, its edges apart.

#### The seed

Both sides now draw the same random numbers in a diff. HSD_Rand's seed comes from the clock at
five places. They were found by listing the clock reads, 154 calls to OSGetTick and OSGetTime
and 36 to __OSGetSystemTime, and following each result and every store through HSD_RandSeedPtr
(805DCD38):

| Site | Call | Where the result goes | Pinned to |
|---|---|---|---|
| 80005A38 | OSGetTick | `main` stores it in HSD_RandDefaultSeed (805DCD30) at 80005A40 | 00B90000 |
| 802842D8 | OSGetTime | Top Ride's session +0x1C, made the seed at 802842F4 | low word 40000000 |
| 802842E0 | OSGetTime | the session's +0x20, doubled, swapped in by fn_80286D7C | low word 40000000 |
| 8028B9EC | OSGetTime | +0x70 of the object TopRide_GameSessionInit seeds from at 8028C04C | low word 40000000 |
| 8029CEA4 | OSGetTime | the same field, from fn_8029C650 | low word 40000000 |

The rest only time things or read the calendar. They're the card library's own generator and
unlock, pad reads, HSD_Perf, alarms, DVD, SI, GX, audio, HVQM, the IP stack and the auto demo's
calendar. The RTC isn't pinned. Dragoon's follows the wall clock in every session, yet its frame
and state goldens repeat across days, so it reaches no compared state.

Each site is one instruction, so each side replaces that one. Dolphin gets a `lis` in its place
from a game INI patch, `user/GameSettings/GKYE01.ini`, which `dolphin_ref.py` writes with the
config (`SEED_PINS`). Dolphin applies an enabled `[OnFrame]` patch after the DOL loads and again
every field, cheats setting or not. Dragoon's `recomp/patches.txt` has the same five sites call
`dragoon_seed_pinned()` (`src/seed_pin.cpp`), which loads the same register with the same value
when `DRAGOON_SEED_PIN` is 1, and otherwise makes the original call, returning to
the next instruction. Only `dolphin_diff.py` sets it, and a test fails if another tool does.
Without it `frame_hashes.py check` and `state_goldens.py check` matched on all 25 routes, four
of them at `--slow=2` or `--slow=3` after running out of seconds with no frame changed.

With both pinned on top-ride-grass, 805DCD30 reads 00B90000 at frame 1 and 967F48BF at the main
menu (1003) on both sides, and Top Ride's session seed (805DD938, +0x1C) reads E8D2826B as the
race starts, Dragoon's frame 3234 and Dolphin's game frame 3245. The grid, P1's place and the
CPUs' colours at 3235 and 3245 are the same on both sides. Unpinned, Dragoon's 805DCD30 reads
00B99CAE at boot as before.

#### The race counter

A checkpoint in a race past its first frame and 10 frames in, City Trial's city counted as a
race, is matched by `scene.passes`, the main loop's passes since the scene loaded. It's 805361C0
(gm+0x7E8), which the loop raises once a pass at 80006B08. Dragoon reads 1 at a scene's first
frame. Dolphin reads the last scene's count for a few fields after the scene word changes, then
0 while the scene loads, then 1 on. Dragoon reads the pass at its frame, and the diff finds
Dolphin's first field of the race with that pass.

It advances the same way on both sides. With the seeds pinned, `ram_peek.py` read it on every
Dragoon frame and Dolphin's memory watcher on every field. At the same pass Dolphin's game frame
is Dragoon's plus 1 at all 467 of Top Ride's passes. It's the same at 4869 of the 4875 passes
both sides share of an Air Ride race on `air-ride-race`'s route, run to 16500 fields. City Trial
has 766 of 767. The rest are at a scene's edges. The plus 1 is the sampling phase, not load
order. Dolphin reads RAM at the end of a field, partway into a pass, so which pass's values a
field shows depends on where the field ends in the loop. The review of #118 measured that phase
flip mid-race, at pass 377. That's why a race's state is compared at its pass and the one either
side. The RNG seed matches there until the two first draw differently. Top Ride's session seed
matches to pass 422, Air Ride's 805DCD30 to pass 416 and City Trial's to pass 360. Top Ride
draws 9 times at pass 423 in Dragoon and 11 in Dolphin, which is probably downstream of the
rounding below.

#### The rerun

All three movies were converged again in 7 runs each. `dtm.py presses` found all 11 presses on
their route frames on each. top-ride-grass, air-ride-race and city-trial ran on AC power, one
game at a time, with `log stream` watching the sandbox. Every menu checkpoint scored as before.
The `setup` and `refused` lines are gone:

| Route | Checkpoint | Before | Now |
|---|---|---|---|
| top-ride-grass | 3235 | setup, 2.864% | same grid, 2.019%, state same |
| top-ride-grass | 3245 | setup, 21.012% | same grid, 20.273%, state same |
| top-ride-grass | 3600, pass 367 | refused | 15.575%, state same |
| air-ride-race | 4200, pass 1079 | refused | 82.259%, state differs |
| air-ride-race | 6000, pass 2879 | refused | 93.188%, state differs |
| city-trial | 2734 | timing, 28.770%, state differs | 1.753%, state same |
| city-trial | 2744 | setup, 94.318%, state differs | 5.605%, state same |
| city-trial | 3300, pass 568 | refused | 29.757%, state differs |

With the seeds pinned a state that differs is Dragoon's bug, and the triage line names the first
value to differ and the frame. `ram_peek.py` read every compared value on each Dragoon frame
against Dolphin's at the same pass or one either side, and the review of #118 checked each at
the matching row. Every word read raw is bit-equal before the first difference. In Air Ride's
race that's all four players' speed, x, y and z and the seed over frames 3330 to 3335, and in
City Trial passes 1 to 69:

- In Air Ride's race player2.x is 1 ulp off at frame 3336, pass 215 (c15a1723 against
  c15a1724) as the racers set off. player2.speed is 23 ulp off with it. From there it grows
  chaotically, and the RNG first draws differently at pass 417.
- In City Trial player1.x and player1.y are 1 ulp off at frame 2802, pass 70, as Kirby drops
  into the city.
- Top Ride matches to the end of its checkpoints, though it compares only the scene and the
  seeds there. Its session seed first differs at frame 3656, pass 423.

The likely shared cause, not proven, is Gekko's single-precision arithmetic, which Dolphin
models and gcn-recomp doesn't. Gekko rounds frC to 25 bits in fmuls, fmadds, ps_mul and
ps_madd, and fres and frsqrte give its estimate tables' values, where gcn-recomp computes them
exactly. The fix belongs in gcn-recomp, in a step of its own.

#### Gekko's single-precision rounding

That cause is now proven, and gcn-recomp models both halves of it. A test build of gcn-recomp
put each quirk behind a switch, and `ram_peek.py` read every compared word on each Dragoon
frame against Dolphin's:

| Switches | City Trial, first difference | Air Ride race | Top Ride seed |
|---|---|---|---|
| none | pass 70 | pass 215 | pass 423 |
| frC rounding | pass 70 | pass 215 | pass 325 |
| estimates | pass 218 | pass 224 | not run |
| estimates and frC rounding | pass 273 | pass 763 | matches to pass 467, the last read |

Narrowed by address, City Trial's pass 70 is the frsqrte in the SDK's PSVECMag (803D217C).
Its exact 1/sqrt isn't the hardware's estimate, and PSVECMag's one Newton step keeps the
difference. frC rounding is the second cause once the estimates are in. Dolphin's single
rounding in fmadds moved nothing in City Trial.

gcn-recomp `c781a86` rounds frC to 25 bits in every single-precision multiply (`ROUND_FRC`).
gcn-recomp `bfce46f` gives fres, frsqrte, ps_res and ps_rsqrte the 750's estimates
(`GEKKO_FRES` and `GEKKO_FRSQRTE`). Their tables and arithmetic are in
`gcn-recomp/runtime/gekko_estimate.h`, which is MPL-2.0 and taken from Cemu. The special
values come from the IBM 750CL manual, the NaN rules from the PowerPC PEM. gcn-recomp
`aa69506` makes fres a zero of its operand's sign from 2^126 up, as Dolphin does, and
`3444827` puts the MPL's text in `LICENSE.MPL-2.0`, which the engine kit carries. Every frame,
state and audio golden matched on `3444827` unchanged. On `bfce46f` the Dolphin diff matches
the test build's last row:

- In City Trial player2.speed first differs at frame 3005, pass 273 (41B34B42 against
  41B31EA5), with player2.x, y and z. It was frame 2802, pass 70. That jump is about 11,000 ulp.
- In Air Ride's race player4.speed first differs at frame 3884, pass 763 (4271F994 against
  4271EE03), with player4.x, y and z. It was frame 3336, pass 215. That's about 3,000 ulp in
  one pass, so a smaller difference in a value not compared likely comes first. It isn't
  chased here.
- In Top Ride the seeds match to pass 564, frame 3797, the last pass Dolphin's 4,400 fields
  reach. On frC rounding alone it was pass 325 (frame 3558). Before either it was pass 423. Its
  checkpoint at 3600, pass 367, has its state the same again, every racer where Dolphin has
  it and only edges off (14.614%).

The movies were converged again from scratch, since the last runs' timelines were gone, in 7
runs each to fixed points. `dtm.py presses` found all 11 presses on their route frames on
each. The three routes ran on AC power, one game at a time with `log stream` watching the
sandbox. Dolphin was denied only writes to `/dev/dtracehelper`. Every menu checkpoint scored
as before, and Top Ride's title card moved by two thousandths of a percent:

| Route | Checkpoint | frC rounding only | Both quirks |
|---|---|---|---|
| top-ride-grass | 3235 | 2.019%, state same | 2.021%, state same |
| top-ride-grass | 3245 | 20.273%, state same | 20.275%, state same |
| top-ride-grass | 3600, pass 367 | 90.731%, state differs | 14.614%, state same |
| air-ride-race | 4200, pass 1079 | 76.116%, state differs | 82.486%, state differs |
| air-ride-race | 6000, pass 2879 | 81.226%, state differs | 93.241%, state differs |
| city-trial | 3300, pass 568 | 29.820%, state differs | 26.346%, state differs |

The bump to `bfce46f` changed every route's frame goldens, recorded once over both quirks. At
4:3 each first changes at its first dump after frame 120. That's 180, or 200 for the routes
dumped every 100 frames and 300 for the stadium routes. Frame 180 is the notice that the data
file was made, a still screen. Against `c781a86`, 74 of its 307,200 pixels change, by 2
levels at most, all inside the notice's text, likely placed through an estimate. At
16:9 the first change is the card prompt at 60, or 100, with its picture stretched. The state
goldens change at every Air Ride, City Trial and stadium checkpoint, all in play. The title's,
the menu's and Top Ride's states are unchanged, though Top Ride's golden holds only the scene
and the player counts, its speeds 0 and its positions none. The audio goldens change on every
route but `menu`. `air-ride-courses-1` and `air-ride-courses-2` still race their three
courses in turn, read by `ram_peek.py` every 100 frames, so their presses stay where they were.

What the triage found:

- Edges were a Dragoon bug. Dragoon drew about 0.085 to 0.097 of a pixel right and down of
  Dolphin, which showed where edges weren't on whole pixels. A console samples a pixel at 7/12,
  and Dolphin applies a 1/12 correction for it (VertexShaderManager.cpp, lines 341 to 357).
  gcn-recomp had none. "The pixel centre" below fixes it.
- The starts differed by the seed, which "The seed" above pins. Unpinned, the two sides boot
  with seeds 198 ticks apart (Dolphin 0x00B99D74, Dragoon 0x00B99CAE). Dolphin's timebase
  counts cycles/12 from 0 at the movie's RTC, and Dragoon's counts 2 a loop back-edge with the
  wall clock as its RTC.
- The card prompt and the SAVE icon are timing. Dolphin's prompt has its text from game frame
  58 and Dragoon's from frame 4, so the first checkpoint is frame 60. Dolphin shows course
  select without the SAVE icon, then 40 fields later the icon. The three timing lines in the
  triage file share one open cause. Dragoon finishes a scene's load before its first frame, and
  Dolphin after it. City Trial's first city frame was a fourth, and with the seeds pinned both
  sides show the same frame there with their players loaded.
- The main menu Kirby's state differed on the old count, where Dragoon's was 0 to 2 frames
  behind Dolphin's over frames 909 to 1001. On the new count it matches at 1003 and 1013 on
  all three routes.

#### The pixel centre

gcn-recomp `6586763` draws every vertex 1/12 of a pixel left and up of where GX's viewport puts
it, so GL's sample at a pixel's middle covers what the console's at 7/12 does. It's 1/12 of a
sample at any internal scale, as in Dolphin. It comes after a 16:9 anchor's squeeze. The
fork's `docs/graphics.md` ("The pixel centre") has the rest. EFB copies and the XFB take no
correction, as in Dolphin.

Every frame golden changed at both aspects, from each route's first dump. That's 60, or 100 for
the routes dumped every 100 frames and 300 for the stadium routes. Dumped every frame on `title`,
frame 1 is one flat colour and the same on both builds, and frame 2, the first one drawn, the
card's panel, differs in 6,378 pixels. Each golden was rewritten by `frame_hashes.py record`.
The state goldens matched at both aspects and the audio goldens on every route, unchanged.

The three movies were converged again in 7 runs each to fixed points, since the last runs'
were gone. `dtm.py presses` found all 11 presses on their route frames on each. The three
routes ran on AC power, one game at a time, with Dolphin sandboxed and `log stream` watching.
Dolphin was denied only writes to `/dev/dtracehelper`.

| Checkpoint | Before | Now |
|---|---|---|
| 60 on all three routes, the card prompt | 2.677%, max 46 | 0.000%, max 3 |
| 314 on all three, the title's logos | 3.444%, max 24 | 0.001%, max 5 |
| 1003 on all three, the main menu's gears | 0.421%, max 88 | 0.000%, max 2 |
| 1013 on all three, mode select | 3.896%, max 139 | 0.000%, max 3 |
| top-ride-grass 2004, course select | 2.826% | 1.342%, the SAVE icon |
| top-ride-grass 2014 | 10.201% | 0.770%, max 10 |
| top-ride-grass 2609 | 0.554% | 0.000% |
| top-ride-grass 2619 | 2.879% | 0.000% |
| top-ride-grass 3235 | 2.021% | 0.011% |
| top-ride-grass 3245 | 20.275% | 0.173% |
| top-ride-grass 3600, pass 367 | 14.614% | 0.467% |
| air-ride-race 1904, course select | 2.658% | 1.322%, the SAVE icon |
| air-ride-race 1914 | 10.436% | 0.620%, max 10 |
| air-ride-race 2209 | 0.491% | 0.000% |
| air-ride-race 2219 | 2.736% | 0.008% |
| air-ride-race 3123 | 2.674% | 0.001% |
| air-ride-race 3133 | 4.787% | 0.036% |
| air-ride-race 4200, pass 1079 | 82.486% | 81.192%, state differs |
| air-ride-race 6000, pass 2879 | 93.241% | 91.443%, state differs |
| city-trial 1814 | 3.159% | 0.004% |
| city-trial 2105, course select | 3.166% | 1.206%, the SAVE icon |
| city-trial 2115 | 2.655% | 0.000% |
| city-trial 2734 | 1.753% | 0.000% |
| city-trial 2744 | 5.605% | 1.944%, max 11 |
| city-trial 3300, pass 568 | 26.346% | 24.476%, state differs |

30 of the 41 checkpoints are now within the budget, where 8 were. 30 were bugs, 27 of them by
their edges and 3 by the races' state. 22 of the 27 are within now. The other five show no
edges. Inside the course thumbnails at 2014 and 1914, and along the buildings' window texture
at city-trial 2744, the detail is off by 10 or 11 levels at most. At 3245 and 3600 lone pixels
are scattered over the course's fine texture. Those five are `unclear` in the triage file. The
races' three stay bugs, since a drawing change doesn't move their state.

A bot run read every compared value on each Dragoon frame of the three races, as
`dolphin_diff.py` reads a checkpoint's, against Dolphin's at the same pass or one either side,
on this pin.

- City Trial first differs at frame 3005, pass 273, player2.speed at 41B34B42, as before.
- Air Ride's race first differs at frame 3884, pass 763, player4.speed at 4271F994 against
  4271EE03, as before.
- Top Ride matches every compared value through pass 564, frame 3797, the last pass Dolphin's
  run reaches, as before.

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

## gcn-recomp `1abcf10`

The pin moved from `5e54665` to `1abcf10`, 125 commits. The overlay menu has a theme, fades in
and out, and draws its text in macOS's own fonts, read from `/System/Library/Fonts` at run time.
Its Buttons view rebinds a gamepad by pressing, saved in `saves/pads.txt`. The window opens on a
boot splash of the disc's banner, `GCN_READY_FILE` writes a line at its first frame and the
game's, and saves sync to the disk before their rename. A `settings.txt` key whose overlay or
patch list is missing is skipped for the run, and the engine kit's `runtime_check` has the
overlay. The other commits add tests or rework docs. A probe run is hidden, so it shows no
splash, and no route opens the menu or names a patch list.

These runs were on Dragoon `b567ae0`, this bump before its rebase onto #93's fixes, with the
same code in `src/` and the same pin. Built there, `tools/frame_hashes.py check` matched all
twenty-four routes and 1,906 frames in 14 min 40 s. `tools/audio_hashes.py check` then matched all 48 rows in 14 min
27 s, so no golden was recorded. The 1-minute load was 16.4 as the frame check began, just
after the build, 7.0 between the checks and 6.5 after the audio check.

None of the 24 bench logs has an `[interp]` line.

The speed runs came after the checks on the same build, one game at a time, at 1-minute loads
of 4.8 to 7.2 while other jobs built on the machine. The race route ran hidden with `--fast` as
`tools/probe.sh speed-race 40 tests/routes/air-ride-race.txt 60`, and its dumps of frames 3,600
and 13,200 were written 20.73 s apart, 463 frames a second, at a load of 6.4 to 6.9. A second
run at 4.8 wrote them 19.28 s apart, 498 a second. In the audio check's `dragoon_bench` run of
that route, the one-second samples from 8 s to 20 s averaged 527 frames a second, between 335
and 702. Both are below the 513 and 601 at `95e1c6b`, and whether the engine or the load made
the difference wasn't checked.

`tools/probe.sh speed-ct4p 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1`
gave 4,311 guest intervals from frame 3,400 (`tools/frametime.py --from 3400`). They averaged
16.68 ms, with 16.79 ms at the 95th percentile and 16.96 ms at the 99th. None went over 20 ms,
and the worst was 19.23 ms.

`tools/probe.sh speed-stadium 360 tests/routes/city-trial-stadium.txt 100000 GCN_FRAMETIME=1 --real-time`
started with an empty shader cache and reached frame 21,551. From frame 4,400 the guest
averaged 16.71 ms, and 7 intervals went over 20 ms. The four longest were 106 ms at frame
15,614, 120 ms at 16,203, 155 ms at 16,502 and 160 ms at 20,054, within a frame of the four
at `95e1c6b`.

## gcn-recomp `864d9d4`

The pin moved from `1abcf10` to `864d9d4`, 94 commits. The overlay menu has a header with a pill
for each page, turned by L1, R1, the triggers, a GameCube pad's Z, L or R let go alone, Q and E,
a footer of hints with Restart and Quit asking in a card, a focus ring that eases between items,
controller glyphs in each family's colours, notices as toasts and sounds that stay off until the
Display page's Menu sounds box turns them on, saved as `menu_sounds on`. The held frame behind
the menu is blurred on the GL path, and the Buttons view scrolls its rows between a header and
footer that stay put. A theme or page a game gives from a static initializer is kept through the
overlay's own (gcn-recomp #102). Without that, from the header's `8700d67` the Mods page had no
pill and `GCN_OVERLAY_PAGE=2` opened Controllers. At `864d9d4` the Mods pill is back after
Controllers, and page 2 is Mods. `GCN_PROGRESS` prints the presented-frame count. No route opens
the menu, and `--dump-output` leaves out the blur.

Built on Dragoon `2525ea1`, `tools/frame_hashes.py check` matched all twenty-four routes and
1,906 frames in 14 min 40 s. `tools/audio_hashes.py check` then matched all 48 rows in 14 min
27 s, so no golden was recorded. The 1-minute load was 23.0 as the frame check began, 5.8
between the checks and 3.7 after the audio check.

None of the 24 bench logs has an `[interp]` line.

The speed runs came after the checks on the same build, one game at a time, at 1-minute loads
of 2.6 to 6.5. The race route ran hidden with `--fast` as
`tools/probe.sh speed-race 40 tests/routes/air-ride-race.txt 60`, and its dumps of frames 3,600
and 13,200 were written 18.27 s apart, 525 frames a second, at a load of 3.0 to 3.8. A second
run, with the load at 6.5 as it ended, wrote them 18.33 s apart, 524 a second. In the audio
check's `dragoon_bench` run of that route, the one-second samples from 8 s to 20 s averaged 600
frames a second, between 565 and 722. Both are above the 463 to 498 and 527 at `1abcf10`, whose
runs had loads of 4.8 to 7.2, and close to the 513 and 601 at `95e1c6b`.

`tools/probe.sh speed-ct4p 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1`
gave 4,312 guest intervals from frame 3,400 (`tools/frametime.py --from 3400`). They averaged
16.69 ms, with 16.78 ms at the 95th percentile and 16.95 ms at the 99th. One went over 20 ms,
48.61 ms at frame 6,721, with no shader compiled and no new texture around it. A second run
gave 4,305 intervals averaging 16.68 ms, 16.77 ms at the 95th percentile and 16.95 ms at the
99th, and one over 20 ms, 25.09 ms at frame 4,892. What held those two frames wasn't traced.

`tools/probe.sh speed-stadium 360 tests/routes/city-trial-stadium.txt 100000 GCN_FRAMETIME=1 --real-time`
started with an empty shader cache and reached frame 21,588. From frame 4,400 the guest
averaged 16.71 ms, and 6 intervals went over 20 ms. The four longest were 106 ms at frame
15,614, 120 ms at 16,202, 159 ms at 16,503 and 160 ms at 20,056, within two frames of the four
at `1abcf10`.

## gcn-recomp `14712b8`

The pin moved from `864d9d4` to `14712b8`, 6 commits (gcn-recomp #105). What a game gives the
overlay, the menu's sounds, telemetry and the renderer's hooks from a static initializer is kept
through the engine's own, since their storage is now `constinit` or a function-local static. `test_ports`
links `telemetry.cpp` and checks at `--init-order` that a telemetry default and a menu sound theme
set before main are there at main, beside the theme and the page. Dragoon's build needed no
change for it, since `test_ports` comes from the engine's `gcn_add_game`. The bump moved seven
cites by two or three lines, which `tools/fork_cites.py 864d9d4 14712b8` found.

Built on Dragoon `05d18f1`, `tools/frame_hashes.py check` matched all twenty-four routes and
1,906 frames in 14 min 40 s. `tools/audio_hashes.py check` then matched all 48 rows in 14 min
27 s, so no golden was recorded. The 1-minute load was 32.5 as the frame check began, just after
the build, 6.1 between the checks and 3.6 after the audio check.

None of the 24 bench logs has an `[interp]` line.

The speed runs came after the checks on the same build, one game at a time, at 1-minute loads
of 2.4 to 6.0. The race route ran hidden with `--fast` as
`tools/probe.sh speed-race 40 tests/routes/air-ride-race.txt 60`, and its dumps of frames 3,600
and 13,200 were written 18.15 s apart, 529 frames a second, at a load of 2.7 to 3.6. A second
run wrote them 18.35 s apart, 523 a second, at 3.4 to 3.8. In the audio check's
`dragoon_bench` run of that route, at `nice -n 19`, the one-second samples from 8 s to 20 s
averaged 591 frames a second, between 505 and 728. A run of the same bench on its own and not
niced, at a load of 3.5, averaged 590, between 535 and 719. Both are under the 600 at
`864d9d4`, and whether the engine or the load made the difference wasn't checked.

`tools/probe.sh speed-ct4p 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1`
gave 4,307 guest intervals from frame 3,400 (`tools/frametime.py --from 3400`). They averaged
16.68 ms, with 16.79 ms at the 95th percentile and 16.96 ms at the 99th. None went over 20 ms,
and the worst was 17.16 ms. A second run gave 4,313 intervals averaging 16.68 ms, 16.79 ms at
the 95th percentile and 16.96 ms at the 99th, and two over 20 ms, 20.31 ms at frame 5,722 and
21.94 ms at 5,727. What held those two frames wasn't traced.

`tools/probe.sh speed-stadium 360 tests/routes/city-trial-stadium.txt 100000 GCN_FRAMETIME=1 --real-time`
started with an empty shader cache and reached frame 21,595. From frame 4,400 the guest
averaged 16.71 ms, and 10 intervals went over 20 ms against 6 at `864d9d4`, not traced. The four longest were 106 ms at frame
15,614, 126 ms at 16,202, 161 ms at 16,502 and 160 ms at 20,054, within two frames of the four
at `864d9d4`.

`tools/warm_shaders.py --force`, five passes at once from an empty cache and not niced, took
65.7 s at a load of 2.5, under the Player targets bar of 90 s. Its cache holds 333 keys, one
fewer than the 334 at Dragoon `2fc9285` and gcn-recomp `dac449e`. Which key it lacks wasn't
checked.

## gcn-recomp `80ef3a7`

The pin moved from `14712b8` to `80ef3a7`, 14 commits (gcn-recomp #106). Under `GCN_FRAMETIME=1`
each frame the overlay draws its menu in prints an `[overlay] frame` line with whether the guest
is held, the interval from the last such frame and the menu's CPU time (`docs/diagnostics.md`),
which `tools/frametime.py --menu` reads. `overlay_init` makes the menu's and the notices' GL
renderers ready and draws once with each, so macOS's GL compiles their program there and not on
the menu's first frame, and `test_ports --pages` holds each page's first menu frame to 1.5 ms
where `CI` is unset. Dragoon's build needed no change. The bump moved three cites in the Dear
ImGui section by 64 or 65 lines, which `tools/fork_cites.py 14712b8 80ef3a7` found.

Built on Dragoon `374b288`, `tools/frame_hashes.py check` matched all twenty-four routes and
1,906 frames in 14 min 41 s. `tools/audio_hashes.py check` then matched all 48 rows in 14 min
32 s, so no golden was recorded. Both ran at `nice -n 19`. The 1-minute load was 12.8 as the
build ended, 3.6 between the checks and 4.9 after the audio check.

None of the 24 bench logs has an `[interp]` line.

The speed runs came after the checks on the same build, one game at a time and not niced. The
race route ran hidden with `--fast` as `tools/probe.sh speed-race 40 tests/routes/air-ride-race.txt 60`,
and its dumps of frames 3,600 and 13,200 were written 18.12 s apart, 530 frames a second, at a
load of 3.5 to 4.4. A second run wrote them 18.23 s apart, 527 a second, at 4.4 to 4.8. In the
audio check's `dragoon_bench` run of that route, at `nice -n 19`, the one-second samples from 8 s
to 20 s averaged 582 frames a second, between 489 and 714. A run of the same bench on its own,
at a load of 4.8 to 5.2, averaged 599, between 534 and 730. Four-player City Trial and the
stadium weren't run again, so the Speed row's numbers for them are from `14712b8`.

`tools/warm_shaders.py --force`, five passes at once from an empty cache and not niced, took
67.0 s at a load of 5.0 as it began, under the Player targets bar of 90 s. Its cache holds 333
keys, as at `14712b8`.

`overlay_init` runs on the main thread after `render_init` loads the shader cache and before
`boot_load` and the guest start (`gcn-recomp/runtime/main.cpp:934`, `:953-960`). Ten hidden boots
from a copy of the warm-up's cache, a build at `14712b8` and one at `80ef3a7` in turn, each
`tools/probe.sh NAME 20 "" 100000 GCN_READY_FILE=ready.txt --exit-after=120`, plus `--bin=` for
the older build, not niced at loads of 9.8 to 8.8, gave these.

| Build | `[shaders] 333 programs from cache ... in N ms` | Ready file's `frame` line |
|---|---|---|
| `14712b8` | 518 to 539 ms | 697 to 725 ms, 701 at p50, leaving out the first run's 1,907 ms, not explained |
| `80ef3a7` | 517 to 576 ms | 691 to 780 ms, 706 at p50 |

The cache line times the cache alone, before `overlay_init`, so the boot bar of 1,000 ms isn't
moved by the warm-up and still passes. Every run compiled all 333 programs and took none from
binaries. The warm-up's own time wasn't measured. At the 12 to 15 ms gcn-recomp's
`docs/diagnostics.md` gives the compile, it's inside the runs' spread of 691 to 780 ms, so these runs can't show the ready file's frame line moving. A
hidden run writes its `window` and `frame` lines at the same first frame.

The Menu smooth while it moves row was first measured here, at Dragoon `374b288` at loads from
8.0 falling to 2.0. The 1,260 `held 1` redraw intervals were 18.58 ms at p50, 19.87 ms at p99
and 21.24 ms at most. The menu's CPU time over all 1,428 frames was 0.167 ms at p50, 1.116 ms at
p99 and 3.858 ms at most. Each process's first menu frame, `f0`, took 0.608 to 3.858 ms, 1.139
ms at p50, the 3.858 ms at a load of 8.0. `test_ports --pages` timed 13.08 ms for the first
frame at gcn-recomp `14712b8`, but that isn't the same measure. The game's are `[overlay] frame`
CPU times on the steady clock in a 3414x1920 window, and the 13.08 ms came from the engine's
test process in a 1920x1080 window. No run turned a page while open, since `GCN_OVERLAY_AT`
opens once a process and a route's presses reach only the guest, which the menu holds.

## gcn-recomp `541a6ae`

The pin moved from `80ef3a7` to `541a6ae`, 10 commits (gcn-recomp #107). While the guest is
held, the desktop frontend waits for a batch until a display frame has passed since its last
wait ended, or half of one while the menu or a notice moves, and draws the held frame again when
none comes. The display frame is from SDL's refresh rate but never shorter than 1/60 s. A rate
under 23 Hz is taken for 60 Hz. A batch ends the wait at once. The batch queue moved from
`gx/xf.cpp` to `gx/batch_queue.cpp` and the pacer's sleep steps from `cpu.cpp` to `pace.h`, and
`test_ports --held` (`test_overlay_held` in `ninja unit`) times the held redraw. The guest's
pacer calls the same steps from `pace.h`. Dragoon's build needed no change. The bump moved
seven cites, five in `main.cpp` by 36 lines, one of the CMake unit target by 8 and one of the
`[ft]` line in `xf.cpp` by 49, which `tools/fork_cites.py 80ef3a7 541a6ae` found.

Built on Dragoon `741b62c`, `tools/frame_hashes.py check` matched all twenty-four routes and
1,906 frames in 14 min 39 s. `tools/audio_hashes.py check` then matched all 48 rows in 14 min
27 s, so no golden was recorded. `tools/audio_hashes.py menu` matched all 48 with the menu's
sounds on in 29 min 7 s (the Audio unchanged with the menu's sounds on row). All three
ran at `nice -n 19`. The 1-minute load was 26.4 as the frame check began, just after the build,
8.3 to 7.3 between the first two checks, 3.6 as the menu check began and 5.0 after it.

None of the 24 bench logs has an `[interp]` line.

The speed runs came after the checks on the same build, one game at a time and not niced but
for one bench run. The race route ran hidden with `--fast` as
`tools/probe.sh NAME 40 tests/routes/air-ride-race.txt 60`, four times. Its dumps of frames
3,600 and 13,200 were written 18.56 s apart, 517 frames a second, at a load of 4.5 to 4.4, then
17.90 s apart, 536 a second, at 4.4. Two later runs wrote them 17.78 s apart, 540 a second, at
2.6 rising to 13.2 from other work on the Mac, then 18.04 s apart, 532 a second, at 13.2 to 9.6.
The four runs at `14712b8` and `80ef3a7` gave 523 to 530, and these go past that on both sides.
A `--fast` run never holds the guest, and what widened the spread wasn't checked.

In the audio check's `dragoon_bench` run of that route, at `nice -n 19`, the one-second samples
from 8 s to 20 s averaged 598 frames a second, between 550 and 711, against 582 at `80ef3a7`.
A run of the same bench on its own at `nice -n 19` with `GCN_AXSTATS=1`, at a load of 4.4 to
6.0, averaged 601, between 554 and 727. One not niced, at 6.0 to 5.0, averaged 601, between 558
and 727, against 599 at `80ef3a7`. Four-player City Trial and the stadium weren't run again.

`tools/warm_shaders.py --force`, five passes at once from an empty cache and not niced, took
66.9 s at a load of 4.1 as it began, under the Player targets bar of 90 s. Its cache holds 333
keys, as at `80ef3a7`.

The menu's held redraw was measured again for the Menu smooth while it moves row, at Dragoon
`741b62c` at loads from 10.9 falling to 2.1. Its p50 went from 18.58 ms to 16.67 ms, its p99
from 19.87 ms to 19.19 ms and its max from 21.24 ms to 26.64 ms, still over the 17 ms bar. 460
intervals were under 9 ms, 1 from 9 to 16 ms, 759 from 16 to 17 ms and 40 over 17 ms. Each open's
first held interval, from the open's first frame to the first redraw, ran 18.07 to 26.64 ms.
Leaving those 21 out, the other 1,239 were 16.67 ms at p50, 17.03 ms at p99 and 17.07 ms at most.
The menu's CPU time over 1,428 frames was 0.142 ms at p50, 1.075 ms at p99 and 3.207 ms at most,
and `f0` took 0.565 to 3.207 ms, 1.118 ms at p50, the 3.207 ms the first run's at 10.9.
`test_ports --held`, the engine's own held redraw over the menu in a hidden 1920x1080 window,
gave the loop's thread 1.07 ms of CPU a held frame with `overlay_draw`'s, and a held interval of
16.70 ms at p50 and 16.73 ms at p99, in each of two runs, not niced, at loads of 2.0 to 3.0.

## gcn-recomp `236e1f4`

The pin moved from `541a6ae` to `236e1f4`, 13 commits (gcn-recomp #108). `overlay_init` warms
the menu's blurred backdrop and keeps its targets for the process, so a hold's first frame
compiles and allocates nothing for it. `pause_gate` wakes the loop's wait for a batch as it holds
the guest, so the frontend draws the held frame at once. The `[overlay] frame` line keeps its
fields and adds `late`, `present` and `blur` at its end (`docs/diagnostics.md`), which
`tools/frametime.py --menu` now reads. Dragoon's build needed no change. The bump moved nine
cites, which `tools/fork_cites.py 541a6ae 236e1f4` found. Five were of `main.cpp`, by 14 lines,
one of them in the tools README's cite table. Three were of `overlay.cpp` by 7 and one of the
CMake unit target by 18.

Built on Dragoon `9a98673`, `tools/frame_hashes.py check` took three passes, all at
`nice -n 19`. The first, in 14 min 47 s at loads of 14.3 falling to 9.8 with the tools suite
running beside it, matched every other frame it reached. Seven routes stopped short, and
`city-trial-stadium`'s last dump, cut off as the run ended, hashed as an empty file and showed
as a mismatch at frame 6,000. Run again at 3.0 to 6.6, five of the seven passed. The two
stadium routes stopped short again, `city-trial-stadium` at frame 15,300 of the 20,400 it needs
and `city-trial-stadium-4p` at 14,100 of 21,000. At `541a6ae` both passed in one pass at loads
of 26.4 to 8.3. They then passed with `--slow=2` at 5.4 to 4.4. Between the three passes all
twenty-four routes and 1,906 frames matched.

`city-trial-stadium` was then checked against a build at `541a6ae` (Dragoon `69ce098`), each
through the same `tools/frame_hashes.py check city-trial-stadium` at `nice -n 19`, one game at a
time and in turn, old, new, new, old, at loads of 17.7 falling to 5.6. In its 60 s the
`541a6ae` build reached frames 64,800 and 66,000, and this one 65,100 and 67,200. All 68 frames
matched each time. So `236e1f4` runs the stadium no slower, and the earlier short runs were the
Mac's.
`tools/audio_hashes.py check` matched all 48 rows in 14 min 27 s at 4.0 to 3.2, so no golden was
recorded, and `tools/audio_hashes.py menu` matched all 48 in 29 min 23 s at 2.9 to 12.7, both at
`nice -n 19`. None of the 24 bench logs has an `[interp]` line.

The Mac's own indexing and media analysis ran through the speed runs, with 1-minute loads up to
96. The race route ran hidden with `--fast` as `tools/probe.sh NAME 40 tests/routes/air-ride-race.txt 60`,
not niced. Its dumps of frames 3,600 and 13,200 were written 18.08 s, 18.63 s, 17.92 s and 18.47 s
apart, 531, 515, 536 and 520 frames a second, at loads of 9.3 falling to 5.2. A build at
`541a6ae` run after them wrote them 18.81 s apart, 510 a second, at 5.4. The 515 is under the
517 to 540 at `541a6ae`, and the older build's run after them was slower. Of eleven earlier
runs, at loads of 5.5 to 68, one gave 532 and ten ran 200 to 314 frames a second. The six of
those that took turns with the `541a6ae` build ran frames 3,600 to 9,000 at 200 to 231 a second,
203, 200 and 231 on the older build and 209, 216 and 210 on this one.

`dragoon_bench` on its own, not niced, at 2.5 to 2.9, averaged 600 frames a second over the
one-second samples from 8 s to 20 s, between 540 and 720, against 601 at `541a6ae`. At
`nice -n 19` it averaged 518, between 322 and 685, at 2.7 to 3.1, where `541a6ae`'s niced run on
its own gave 601. In the audio check's run of the race it averaged 357, between 264 and 424, at
about 4, against 598 in `541a6ae`'s. What held the niced runs back wasn't checked.

`tools/warm_shaders.py --force`, five passes at once from an empty cache and not niced, took
66.3 s at a load of 8.2 as it began, under the Player targets bar of 90 s, with 333 keys as at
`541a6ae`. A run before it took 456.9 s, five times the bar, at loads of 7.5 rising to 96.5,
and built the same keys.
The blur warm-up runs in `overlay_init`, which `render_init` comes before. Ten hidden boots from
a copy of the warm-up's cache, a build at `236e1f4` and one at `541a6ae` in turn, each
`tools/probe.sh NAME 20 "" 100000 GCN_READY_FILE=ready.txt --exit-after=120`, plus `--bin=` for
the older build, not niced at loads of 32 falling to 27.6, gave these.

| Build | `[shaders] 333 programs from cache ... in N ms` | Ready file's `frame` line |
|---|---|---|
| `541a6ae` | 484 to 825 ms, 508 at p50 | 674 to 1,131 ms, 681 at p50 |
| `236e1f4` | 486 to 834 ms, 503 at p50 | 664 to 1,098 ms, 770 at p50 |

The cache line is within the boot bar of 1,000 ms. The ready file's p50 moved from 681 ms to
770 ms, the way a warm-up in `overlay_init` would push it, but five boots a build at a load of
30 can't settle that. Both builds' worst came back to back, the older's third boot and the
newer's fourth. Ten more boots the same way, with the older build first, at loads of 4.2 to 4.4,
gave these.

| Build | `[shaders] 333 programs from cache ... in N ms` | Ready file's `frame` line |
|---|---|---|
| `541a6ae` | 518 to 796 ms, 523 at p50 | 703 to 1,210 ms, 738 at p50 |
| `236e1f4` | 516 to 547 ms, 518 at p50 | 704 to 768 ms, 712 at p50 |

At the lower load the newer build's p50 is 26 ms under the older's, so the 89 ms the busier runs
showed was their spread. The 0.5 to 1.4 ms gcn-recomp's diagnostics give the blur warm-up is
inside both spreads, so neither shows it.

The menu's held redraw was measured again for the Menu smooth while it moves row, at Dragoon
`a4cdc27` at loads from 12.0 falling to 2.6. Its p50 went from 16.67 ms to 16.65 ms, its p99 from
19.19 ms to 17.04 ms and its max from 26.64 ms to 17.46 ms, still over the 17 ms bar. 478
intervals were under 9 ms, 9 from 9 to 16 ms, 748 from 16 to 17 ms and 25 over 17 ms. Leaving out
the 21 first held intervals, the other 1,239 were 16.65 ms at p50, 17.04 ms at p99 and 17.46 ms
at most. The menu's CPU time over 1,428 frames was 0.154 ms at p50, 1.049 ms at p99 and 3.889 ms
at most, and `f0` took 0.741 to 3.889 ms, 1.220 ms at p50, the 3.889 ms the fifteenth run's at
3.0. Each open's first held interval ran 15.28 to 17.25 ms, with a `late` of 0 to 0.022 ms, a
`present` of 0.034 to 1.027 ms and a `blur` of 0.076 to 0.322 ms, leaving 15.07 to 16.62 ms.

The 23 intervals from 17.0 to 17.1 ms, 22 of them over 17 ms, each came on the frame where the
drawing span stepped up. Its `present` was 0.317 to 0.369 ms after a frame with 0.033 to 0.073 ms
of draw and blur, and its `late` 0.032 to 0.051 ms. So the time falls in the frame's drawing
span, not in the wait. `present` is the held frame's redraw (`render_present_last`) and the
wait for the gamepads' lock, timed before `overlay_draw`, so the menu's content can't raise it.
The same GL work took about ten times as long, and the menu's CPU time, about three times, and
its blur stepped up on the same frame and stayed up. That points to the main thread running
slower or blocked, which wasn't checked further. Each long interval is paid back gradually as
the draw falls over the frames after, the next running 16.38 to 16.72 ms, 16.63 at the median,
and a p99 bar doesn't gain from that.

Of the other three over 17 ms, one open's first held
interval took 17.25 ms with a draw of 1.027 ms, one redraw took 17.46 ms with a draw of 1.202 ms,
followed by one of 15.62 ms, and one took 17.20 ms after a wait that ended 0.416 ms late, the
only `late` over 0.08 ms in all 1,260.

## gcn-recomp `b4f8ddb`

The pin moved from `236e1f4` to `b4f8ddb`, three merged PRs. Fork #110 makes the held wait wake
in steps and adds `thread` and `swap` to the end of the `[overlay] frame` line. `thread` is the
loop thread's CPU time over the frame's draw and blur, and `swap` the last frame's buffer swap
(`docs/diagnostics.md`). Fork #112 changes CI only. Fork #113 moves the menu's blur into
`render_gl_blur.cpp` and gives the overlay and GL tools shared headers, with no change in
behavior. The fit line `tools/settings_fixtures.py` checks moved with the blur and is now once
in `render_gl_present.cpp` and once in `render_gl_blur.cpp`, so the tool names both and its
count of copies went. `tools/frametime.py --menu` read no line from #110 on, and now reads any
trailing field. The bump moved nine cites, which `tools/fork_cites.py 236e1f4 b4f8ddb` found.
Five were of `main.cpp`, by 11 lines, one of them in the tools README's cite table. Three were of
`overlay.cpp` by 39 and one of the CMake unit target by 16.

Built on Dragoon `ae7ebd1`, `tools/frame_hashes.py check` matched all twenty-four routes and
1,906 frames in one pass of 15 min at loads of 4.8 to 6.1. `tools/audio_hashes.py check` then
matched all 48 rows in 14 min 27 s at 6.8 to 4.4, so no golden was recorded, and
`tools/audio_hashes.py menu` matched all 48 in 29 min 6 s at 4.4 to 5.5. All three ran at
`nice -n 19`. None of the 24 bench logs has an `[interp]` line.

The speed runs came after the checks on the same build, one game at a time and not niced. The
race route ran hidden with `--fast` as `tools/probe.sh NAME 40 tests/routes/air-ride-race.txt 60`,
four times. Its dumps of frames 3,600 and 13,200 were written 18.33 s, 18.58 s, 18.35 s and
18.38 s apart, 524, 517, 523 and 522 frames a second, at loads of 3.2 rising to 5.6, inside the
515 to 536 at `236e1f4`.

`dragoon_bench` on its own, not niced, averaged 575, 586 and 584 frames a second over the
one-second samples from 8 s to 20 s in three runs at loads of 3.8 to 8.4, under the 600 at
`236e1f4` and 601 at `541a6ae`. At `nice -n 19` it averaged 573 at 3.8 to 8.8, and 595 in the
audio check's run of the race. Each run was
`env SDL_AUDIO_DRIVER=dummy tools/probe.sh NAME 30 tests/routes/air-ride-race.txt 60 --bench GCN_AXSTATS=1`.
An alternating run on 2026-11-16 then took turns with a build at `236e1f4` through the same
command plus `--bin=`, not niced, one game at a time, with `fseventsd` at 100% of a core
throughout. Each mean is over the 13 samples from 8 s to 20 s.

| Run | Build | Load | Mean | Min | Max | Whole run |
|---|---|---|---|---|---|---|
| 1 | `b4f8ddb` | 6.79 | 578.4 | 537.1 | 695.9 | 942.08 |
| 2 | `236e1f4` | 5.60 | 563.4 | 521.3 | 645.4 | 921.02 |
| 3 | `b4f8ddb` | 5.33 | 561.6 | 519.7 | 608.4 | 902.39 |
| 4 | `236e1f4` | 6.37 | 561.1 | 480.1 | 688.7 | 899.76 |
| 5 | `b4f8ddb` | 5.81 | 563.6 | 504.7 | 663.1 | 905.19 |
| 6 | `236e1f4` | 5.81 | 558.7 | 506.6 | 689.6 | 880.30 |
| 7 | `b4f8ddb` | 6.19 | 562.3 | 516.1 | 694.6 | 893.02 |
| 8 | `236e1f4` | 6.37 | 588.9 | 539.5 | 673.7 | 953.88 |

`b4f8ddb` gave 561.6 to 578.4 with a mean of 566.5. `236e1f4` gave 558.7 to 588.9 with a mean
of 568.0. The loads ran 5.3 to 6.8, so the bump didn't move the bench. The drop from about 600
isn't the build's, and what in the Mac caused it wasn't checked.

`tools/warm_shaders.py --force`, five passes at once from an empty cache and not niced, took
70.3 s at a load of 2.7 as it began, under the Player targets bar of 90 s, with 333 keys as at
`236e1f4`. That's past the 66.3 to 67.0 s of the last three pins. `fseventsd` and a virtual
machine took most of two cores as it ran. A run just before it took 104.0 s and built the same
keys. It began straight after a warm-up from the full cache, at a load of 8.9 rising to 14.1.

The menu's held redraw was measured again for the Menu smooth while it moves row, which now
gives this pin's numbers. Its p50 went from 16.65 ms to 16.67 ms and its p99 from 17.04 ms
to 17.00 ms, on the bar. Its max went from 17.46 ms to 25.08 ms. 486 intervals were under 9 ms,
none from 9 to 16 ms, 762 from 16 to 17 ms and 12 over 17 ms, the most a p99 of 17.00 ms allows
at the line's 0.01 ms. Each open's first held interval ran 1.16 to 16.82 ms. The logs show that
1.16 ms and nothing that explains it. Leaving those 21 out, the other 1,239 were 16.67 ms at
p50, 17.00 ms at p99 and 25.08 ms at most. The menu's CPU time over 1,428 frames was 0.055 ms at
p50, 0.722 ms at p99 and 3.431 ms at most, against 0.154, 1.049 and 3.889 ms at `236e1f4`. The
p50's drop isn't explained. `f0` took 0.434 to 3.431 ms, 1.149 ms at p50.

`thread` and `swap` split the tail. Of the 14 intervals from 17.0 ms, the 13 from 17.00 to
17.26 ms had a `present` of 0.323 to 0.584 ms and a `thread` of 0.343 to 0.399 ms, with a `late`
of 0.030 to 0.043 ms. The other 1,246 had a `present` of 0.049 ms and a `thread` of 0.056 ms at
p50. `thread` spans `present` and `blur`. In 12 of the 13 it came within 0.023 ms of their sum,
so for most of the tail the thread ran slower rather than waited off a core. That fits it
waking on an efficiency core. The 17.26 ms one had a `present` of 0.584 ms, a `blur` of
0.029 ms and a `thread` of 0.382 ms, so about 0.23 ms of its span was off the CPU. `present`
includes the wait for the gamepads' lock, and where in the span that time went wasn't checked.
Their `swap` of 0.262 to 0.855 ms is as the rest's, 0.373 ms at p50 and 2.252 ms at p99, so the
swap played no part. The fourteenth, 25.08 ms, came after the frame before's `swap` took 24.776 ms, the longest in all
1,260, and its wait ended 8.378 ms late. Its `thread` was 0.119 ms. What held that swap wasn't
checked.

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

## Launcher

The macOS launcher in `launcher/`, against the bars set for it, measured on 2026-11-13 on
macOS 26.6.2.

| Check | Bar | Measured | Result |
|---|---|---|---|
| Library's share of a core, streaks moving | 3% | 0.02% | Pass |
| Window not key, streaks stopped | 0.2% | 0.02% | Pass |
| App hidden | 0.2% | 0.02% | Pass |
| Window covered, streaks stopped | 0.2% | Not measured | Not measured |
| Reduce Motion, streaks at rest | 0.2% | Not measured | Not measured |
| Reading and decoding the disc's banner | 20 ms | 0.21 ms, and 0.20 s for the whole `Dragoon --dump-banner` | Pass |

Each share is `launcher/tools/idle_cpu.py` over 60 s on a release build's Library as it has
been since Dragoon `93d5d00`, with the disc's banner. `ps` counts CPU time in hundredths of a second, so 0.02% is
0.01 s in 60 s, the least it shows above nothing. The not-key and hidden rows ran the release
build as it ships. A window can't be made key from a script, so the moving streaks were
measured on a copy built to keep them moving without it. Covering the window and turning on
Reduce Motion both need the user's screen, so those two rows haven't been measured. The banner
time is what `--dump-banner`, added in `29cc77b`, prints for the supported disc.

### Build progress

The build page's warm-up segment fills by the frames the warm-up's runs have played, of the
119,760 the manifest gives its eight runs, from gcn-recomp's `GCN_PROGRESS` (in the pin since
`864d9d4`). The line under the bar gives the share of them played, "51% warmed up". A game
from before `GCN_PROGRESS` prints no frames, and then the runs fill the segment and the line
says "3 of 8 runs done" as before. The launcher README's build page section has the event
format.

| Check | Bar | Measured | Result |
|---|---|---|---|
| Frames add up across runs playing at once and never fall | Each end counts its run's frames once | `test_warm_shaders.py` on fake games, two at once, with lines missing, garbled or past the run's end | Pass |
| An engine without `GCN_PROGRESS` | Warms and shows the runs as before | A fake game that prints no `[progress]` line warms with only the pass lines, and the recipe's events carry no frames (`test_warm_shaders.py`, `test_launcher_build.py`) | Pass |
| The segment and the time left from frame events, and from runs alone | Never falls, full only on `done` | `BuildProgressTests` on a whole build of each | Pass |
| Launcher's share of a core through the warm-up's frame events | 5% | Not measured, since it needs the page on screen. `warm_shaders.py` prints a frames line at most every 0.25 s, plus one as each run ends. `ProgressThrottle` passes at most 10 events a second. The compile's 8 events a second measured 2.8 to 3.4% | Not measured |
| The time left on a real warm-up at 25, 50 and 75% | Within 20% of the real time left | Not measured. No real warm-up ran with the frame events, so neither the fill's pace nor how often the game's lines come was seen | Not measured |

### The hand-off to the game

Measured on 2026-11-14 on macOS 26.6.2, on fake games only. No real engine ran, so the
real game's own time to its window isn't here.

| Check | Bar | Measured | Result |
|---|---|---|---|
| Play to the game's process starting, by the launcher's clock and the kernel's start time, as `LaunchTimingTests` prints it | 250 ms | 0.7 to 2.1 ms | Pass |
| The `window` line going in, by the file's time, to the flow hiding on it, as `LaunchTimingTests` prints it | 100 ms | 1.9 to 3.9 ms | Pass |
| Play to the game's process starting in a release app, by its logged times less the fake's 500 ms | none set | 57 to 77 ms | Recorded |
| An engine that writes no ready file, Play to the hide | the 20 s timeout and a log line | 5.0 s and the line, when the timeout was 5 s; not measured at 20 s | Not measured at 20 s |
| The game ending to the window back in, App Nap held off | 0.5 s | 265 and 380 ms | Pass |
| The same before App Nap was held off | 0.5 s | 270 ms, or 26 s to over 2 minutes | Fail, fixed in `424da2f` |
| Launcher's share of a core while clear, the game running | 0.2% | 0.02% | Pass |
| Hiding with neither a `window` line nor the timeout | never | never, in `FlowHandOffTests` | Pass |
| The bars above on the real game | an engine that writes `GCN_READY_FILE`, which gcn-recomp `1abcf10` brings; the launcher's commits sit on the pin at `864d9d4`, past it | Not measured | Not measured |

The first two rows are from 2026-11-14, ten runs of `LaunchTimingTests`, five alone and five in
the full suite. It prints each run's times and holds none to a bar, as a loaded runner can
take many times as long. Its fake game is a shell script that writes `window 300` and
`frame 700` as the engine does, so the times the file gives are the fake's own and aren't
measured here. By the file's time its `window` line went in 443 to 475 ms after the process
started alone and 443 to 4,515 ms in the full suite.
The release app was a scratch build answering the bookmark and the disc check at once, under
a scratch HOME, with a fake `dragoon` that writes `window 500` and `frame 1000` and then idles.
So Play to the game's start took 57 to 77 ms in that app. A launcher started from a shell
isn't the active app, so `NSApplication.hide` did nothing. The window stayed clear and let
clicks through, and did the same with `activate` called before Play.

Once the launcher had called `activate`, its 80 s runs got the game's end late, by 57 s and
26 s. In a third the game sat as a zombie and the termination handler hadn't run 2 minutes
after it exited. Runs of 20 s and 80 s that never called `activate` were on time. App Nap fits
what was seen, so since `424da2f` the launcher holds a `ProcessInfo` activity until the game
ends. With it, two 80 s runs after `activate` were on time, one of them with a fake that
writes no ready file. The share is `launcher/tools/idle_cpu.py` over 60 s while the
window was clear, 0.00% before the activity and 0.02% with it.
