# Status

What's true of Dragoon today, measured on one machine. Build numbers are from a clean
build directory at gcn-recomp `67a7e30`, and the game was run at `7d30377`. The four-player
numbers are from `fda6926`.

| Feature | Status | Note |
|---|---|---|
| Boot and memory card | Works | A blank card gets the game's prompt by frame 60, and the save file is made |
| Opening movie | Plays | Then the title and the attract demos, races and mode movies |
| Title screen | Works | `tests/routes/title.txt` |
| Mode select | Works | `tests/routes/menu.txt`. The panel at its right stays plain gray |
| Air Ride race | Runs | `tests/routes/air-ride-race.txt`. Fantasy Meadows, three CPUs, three laps to the results screen with nobody steering |
| City Trial | Runs | One player (`tests/routes/city-trial.txt`) or four in split screen (`city-trial-4p.txt`), the five-minute clock running. Stadium not reached yet |
| Top Ride | Not tried | |
| Audio | Partial | Details in `audio.md` |
| Controllers | Four ports, live | Each gamepad takes the next free port as it connects and gets the same one next launch, kept by GUID and serial in `saves/gamepads.txt`. The keyboard stays on port 1. A gamepad pulled out mid-game leaves its port plugged in until it's back. `--pads=N` plugs in ports 1 to N for routes, as in `2/2100:A:5`. Checked with SDL's virtual gamepads (`--test-ports`), not yet with four real controllers |
| Picture | 4:3 | gcn-recomp letterboxes the desktop window to 4:3 |
| Speed | See below | About 500 frames a second in a race, hidden window, `--fast`. Four-player City Trial holds 60 at the game's own speed |
| Build from the disc | Works | 23 s from an empty build directory: 3.5 s to configure, 19.5 s for Ninja |
| Disc check | Works | The wrong disc stops the configure step with the disc ID it found |
| `.gcm` dumps | Work | Linked as `rom/game.iso`, or passed as `-DGAME_ISO=<path>` |
| Disc path with spaces | Works | Configures, and its `dragoon_bench` builds and runs |
| Running from another directory | Works | The configured disc path is compiled in |
| Network during the build | SDL only | The first configure in a build directory downloads SDL 3.4.18's source release (15.7 MB) and checks its SHA-256. `-DGCN_SYSTEM_SDL=ON` uses an installed SDL3 instead, with no download |
| Idle loop | Works | `recomp/idle.txt` 803D9FCC is the `IDLE_CHECK` branch in the generated C |

## The build

Measured on an Apple M4 Max (16 cores, 48 GB) on macOS 26.6.2 with the Command Line Tools
SDK 26.5, Apple clang 21.0.0, CMake 4.4.4, Ninja 1.13.2, Python 3.14.7 and SDL2 2.32.72.

```sh
ln -s "/path/to/Kirby Air Ride (USA).gcm" rom/game.iso
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk
ninja -C build
```

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
runtime/gx/render_gl.cpp:3189:13: warning: enumeration value 'Screen' not handled in switch [-Wswitch]
```

## Disc inputs

gcn-recomp looks only for `rom/*.iso` and `rom/*.ciso`. A `.gcm` is the same format as an
`.iso`, so a symlink named `rom/game.iso` builds. So does
`-DGAME_ISO="/path/to/Kirby Air Ride (USA).gcm"`, spaces and all. A `dragoon_bench` built
that way and run from a directory outside the repo found the disc through the compiled-in
path.

The wrong disc fails at configure, before anything compiles. With Super Mario Sunshine passed
as `GAME_ISO`, `recomp/extract_dol.py` prints this and CMake stops.

```
error: .../Super Mario Sunshine (USA, Canada).gcm is disc b'GMSE01', not b'GKYE01'.
Note: only uncompressed .iso and .ciso images are supported; convert .rvz/.gcz first (see README).
CMake Error at gcn-recomp/CMakeLists.txt:280 (message):
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
run with `tools/probe.sh` (hidden window, `--fast`, 640x480). The four-player route also
needs `--pads=4`.

| Checkpoint | Route | Frame | What's on screen |
|---|---|---|---|
| Memory card | `title.txt` | 60 | The prompt to make a save file on the card in slot A |
| Title | `title.txt` | 960 | The logo and PRESS START/PAUSE |
| Mode select | `menu.txt` | 1200 | Air Ride, Top Ride, City Trial, Options, LAN |
| Air Ride race | `air-ride-race.txt` | 4200 | Fantasy Meadows, lap 1, 0:14 on the clock, CPUs ahead |
| City Trial | `city-trial.txt` | 3300 | The city, 4:54 left |
| Four-player entry | `city-trial-4p.txt` | 2700 | P1 OK to P4 OK under READY?, each player joined from its own port |
| Four-player City Trial | `city-trial-4p.txt` | 3480 | Four views, 4:51 left, ports 1 and 3 steering left and 2 and 4 right |

Left alone, the race route finishes three laps in 1:12.60 and reaches the results screen by
frame 25,800. City Trial with nobody steering drives into the sea and stays there while the
clock runs. The opening movie, when it isn't skipped, plays to the end and hands over to the
title and the attract demos.

The race runs at about 500 frames a second in the hidden window with `--fast`, 8 times the
game's 60. That's 9,600 frames between frames 3600 and 13,200 in 19.3 s of wall time, with
other work on the machine at the time.

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

## Renderer cost

What the GL renderer costs at 1280x960 (`--scale=2`, twice the default 640x480 in each direction),
at gcn-recomp `642187a`, on a 16-core Mac with other work running (load average 2 to 3). These are
the baseline for the Metal renderer's two triggers. `[rt]` is the time the renderer spends
issuing a frame to GL, not the GPU's own time. The percentiles are nearest rank. The window was
hidden and never waited on the display's refresh. The timer behind `--real-time` paced the guest, and
the cost of presenting a frame and of vsync isn't in these numbers. So the 16.68 ms guest interval
shows that timer and not a 60 Hz display. `[rt]` is part of a frame's cost, not all of it.

| Four players, frames 3,400 to 7,647 (4,248 frames) | Mean | 95th | 99th | Worst |
|---|---|---|---|---|
| Guest interval | 16.68 ms | 17.29 ms | 17.49 ms | 17.68 ms |
| `[rt]` render time | 1.34 ms | 1.72 ms | 1.96 ms | 5.98 ms |

The command is `tools/probe.sh ct4p-scale2 130 tests/routes/city-trial-4p.txt 600 --pads=4 --real-time --scale=2 GCN_FRAMETIME=1`,
and the table is a second run of it with a frame dump every 100,000 frames instead of every 600. The first
run, with the dumps, read 1.45 ms mean, 2.42 ms at the 95th percentile, 3.64 ms at the 99th and 41.15 ms
at worst for the renderer, and 16.68 ms mean, 17.28 ms at the 95th, 17.49 ms at the 99th and 17.90 ms at
worst for the guest. Its 7 worst frames are the dumps, each a readback of the whole frame (frames 3,600 to
7,200, every 600th). The rest of the gap between the two runs is probably other work on the machine, though no control run was made. No guest interval ran
over 20 ms in either run. The same route at 640x480 averaged 1.40 ms (the table under Four players), so
doubling each side cost the renderer's issue time nothing it could measure.

Hitches are the frames after frame 300 whose `[rt]` time is over 16.7 ms. These are first launches
with an empty shader cache, one run of each route at `--real-time --scale=2` with nothing warmed.
macOS GL has no program binaries, so the cache started empty. The warmed numbers are in the Player
targets table below. Each run was `tools/probe.sh w3-cold-ROUTE SECONDS tests/routes/ROUTE.txt 60
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
The other seven are over 16.7 ms and under 33. The 15-program burst at frame 902 sits at 30 to 32 ms
here, where an earlier set of runs saw 27 to 40 ms.

Every one of those frames built new programs, and no other non-dump frame after 300 went over
16.7 ms. A program takes 1.2 to 5 ms to compile, so a frame with 30 new ones takes about 55 ms of
compiling. The big bursts are 15 programs at frame 902 (the first 3D scene, in all five runs), 24 at
the title's logo scene (1414), 38 and 34 at the start of the city (2733) and 30 at the start of a
race (3122). The other new programs come in ones to six, and only the 6 at frame 1535 and the 5 at
4788 pushed a frame over 16.7 ms. The guest also stalls for 117 to 401 ms at a handful of frames
(303, 1002, 1413, 1801, 2103, 2732 and others). What it was doing then wasn't checked.

| Trigger | Threshold | Measured on GL | Verdict |
|---|---|---|---|
| Four-player cost | `[rt]` 99th percentile over 8 ms | 1.96 ms (3.64 ms with dumps) | Doesn't fire |
| Shader-compile hitches | Any frame after 300 over 33 ms | 4 frames across the five cold runs, from 56 ms to 65 ms, each on first sight of 24 to 38 programs | Fires |

The hitches are cold-start costs. Frame 902 showed up in all five runs. The bigger bursts (1414,
2733, 3122) each showed up in the runs of the routes that reach that scene, from one run of each
route.

## Player targets

What a player's first session looks like after the warm-up, against the bars set for it.

| Target | Bar | Measured | Result |
|---|---|---|---|
| Stalls in a fresh install's first session | 0 frames over 33 ms after frame 300 on all five routes | 0 frames on all five, worst frame 28.2 ms | Pass |
| Shaders compiled during play after the warm-up | 0 `[shaders] compiled program` lines on the five routes | Title 3, menu 0, City Trial 35, four players 33, race 9 | Fail |
| How far the attract demos alone get | Report the share of each route's keys the attract pass builds by itself | The attract pass builds 3 keys. Title 3 of 66 (4.5%), menu 3 of 27 (11.1%), City Trial 3 of 107 (2.8%), four players 3 of 110 (2.7%), race 3 of 141 (2.1%) | Reported |
| Time added to the first build | 90 s or less | 42.8 s (attract 7.1 s, routes 35.7 s), 136 keys | Pass |
| Time added to every boot on macOS GL | 1,000 ms or less | 198 to 221 ms for 136 programs | Pass |
| Frames | `tools/frame_hashes.py check` passes | All five routes OK | Pass |

With the default dump every 60 frames, the dumped frames themselves go over 33 ms, so these runs set
`DUMP_EVERY` to 100,000.

The compiles that remain after the warm-up are the keys the warm-up's `--fast` passes didn't build.
The 136-key cache lacks 3 of the title's 66 keys, none of the menu's 27, 35 of City Trial's 107, 33
of the four-player route's 110 and 9 of the race's 141. The worst frames are City Trial
2733 (28.2 ms, 10 programs, draws 1937/386, verts 36,131, idx 77,673) and four-player 2734
(24.0 ms, 9 programs, draws 4399/635, verts 84,681, idx 185,319).

Measured on a Mac with an M4 Max at `--real-time --scale=2`, with the build's `tools/warm_shaders.py`
(`--saves` a fresh directory for each route) and the Dragoon commit `d3c9c15`. Apple's own shader
cache was warm from earlier runs, and the warm-up fills it on a player's Mac too. The 42.8 s is the
first warm-up, timed with `/usr/bin/time -p`. The other four warm-ups ran for real as well, because
each used a fresh saves directory with no stamp, and took 44.2 to 45.7 s. The runs with dumps off
used a copy of a sixth, separate warm-up's cache.

## Fixes on the way

Two things stopped the game. Both were generic, so both are in gcn-recomp.

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: MMU: access to 75730040 with no page table` when the opening movie ended, and a second into every race | The effects code (`kar_efanime__near_80240084`) calls `setjmp` (803AE238) before it walks an animation tree. Its callback (8023F4E4) calls `longjmp` (803AE33C) to stop the walk. Recompiled, `longjmp` restored the stack pointer of the outer frame and then returned into the callback, and the code after it ran on the wrong stack frame | gcn-recomp `b326dcd` lets `special_calls.txt` name a `setjmp` and `longjmp`. A call site of `setjmp` records a host resume point, and `longjmp` goes there once it has restored the registers. `recomp/special_calls.txt` and `recomp/names.txt` name the pair |
| A race showed the HUD on plain sky blue | The frame's first draw is a sky quad at the far end of the frustum with a Z8 replace Z texture (texel 0xFF, bias 0). The depth test is set to run before texturing, so on the console the quad writes its own far depth. The renderer wrote the texel's depth instead (0x0000FF), and every later draw failed the test | gcn-recomp `7d30377` leaves the Z texture out of the depth when the test runs before texturing |

`analysis/symbols.txt` calls 803AE238 `ExPPC_UnwindStack` and 803AE33C
`ExPPC_IsInSpecification`. Their code is the C library's `setjmp` and `longjmp`, and
`recomp/names.txt` renames them.
