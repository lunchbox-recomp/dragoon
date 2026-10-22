# Status

What's true of Dragoon today, measured on one machine. Build numbers are from a clean
build directory at gcn-recomp `67a7e30`, and the game was run at `7d30377`. The four-player
numbers are from `fda6926`. The controller row is from `25c4f26`, where the five frame-hash
routes also pass. The audio row is from gcn-recomp `bf31b7b` and its click counts from
`fd1f6a8` and `e6ea431`, where the five frame-hash routes and the five audio-hash routes pass.

| Feature | Status | Note |
|---|---|---|
| Boot and memory card | Works | A blank card gets the game's prompt by frame 60, and the save file is made |
| Opening movie | Plays | Then the title and the attract demos, races and mode movies |
| Title screen | Works | `tests/routes/title.txt` |
| Mode select | Works | `tests/routes/menu.txt`. The panel at its right stays plain gray |
| Air Ride race | Runs | `tests/routes/air-ride-race.txt`. Fantasy Meadows, three CPUs, three laps to the results screen with nobody steering |
| City Trial | Runs | One player (`tests/routes/city-trial.txt`) or four in split screen (`city-trial-4p.txt`), the five-minute clock running. Stadium not reached yet |
| Top Ride | Not tried | |
| Audio | Partial | The mixer reads the control word the game's ucode (`07F88145`) uses. The compressor command runs. On the race route the windows with a main peak over 32,767 fell from 13 to 2 and the samples the output clamp changed from 4,435 to 923. AuxA sound went from 22 windows to 97 and AuxB from none to 20 (table under Audio). All 1,211 `[ax] cmds` lines of ten runs (484,400 command lists) count 0 unknown and 0 skipped commands. Source type 2 voices no longer resample, and on the title route the clicks in the DMA's blocks fell from 928 to 19 (table under Audio). The low-pass filter and polyphase resampling aren't done. It crackled the one time it was listened to, before the type 2 fix. Nothing has been compared with recordings from a real console. `tools/audio_hashes.py check` holds the output hashes. Details in `audio.md` |
| Controllers | Four ports, live | Each gamepad takes the port of its SDL player number if that port is free, and otherwise the lowest free port. Its player number is then set to the port. A gamepad pulled out frees its port. The game then sees that port unplugged, unless the keyboard (port 1), `--pads=N` or a `controls.txt` line keeps it plugged in. A gamepad gets no port when none is free. Nothing is saved between launches. A device's `port <n>` line in `controls.txt` keeps that port from gamepads. A `gamecontrollerdb.txt` beside the executable adds mappings. `--pads=N` plugs in ports 1 to N for routes, as in `2/2100:A:5`. Checked with SDL's virtual gamepads (`gcn-recomp/tools/test_ports.sh`: 42 port checks, and a recording replayed with no gamepad), not with four real controllers or under Steam Input |
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

## Audio

At gcn-recomp `bf31b7b`. `GCN_AXSTATS=1` makes the game print its mixer's counts every 400
command lists. Three runs played the race route as
`env SDL_AUDIO_DRIVER=dummy tools/probe.sh NAME 30 tests/routes/air-ride-race.txt 60 GCN_AXSTATS=1 --bench`,
unpaced. One had `GCN_AX_LAYOUT=2001` and two were default. The table covers the 257 windows
(102,800 lists) that all three reached. Before is the `GCN_AX_LAYOUT=2001` run, which reads
the control word the way the 2001 ucode does and skips the compressor command, as this
runtime did until now. After is the default for `07F88145`.

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

- The low-pass filter and polyphase resampling (`audio.md`).
- It crackled the one time it was listened to, before the type 2 fix. Nothing has been
  compared with recordings from a real console.
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
and the table is a second run of it with a frame dump every 100,000 frames instead of every 600. The first
run, with the dumps, read 1.45 ms mean, 2.42 ms at the 95th percentile, 3.64 ms at the 99th and 41.15 ms
at worst for the renderer, and 16.68 ms mean, 17.28 ms at the 95th, 17.49 ms at the 99th and 17.90 ms at
worst for the guest. Its 7 worst frames are the dumps, each a readback of the whole frame (frames 3,600 to
7,200, every 600th). The rest of the gap between the two runs wasn't explained. No control run was
made. No guest interval ran over 20 ms in either run. The same route at 640x480 averaged 1.40 ms
(the table under Four players), so doubling each side cost the renderer's issue time nothing it
could measure.

Hitches are the frames after frame 300 whose `[rt]` time is over 16.7 ms. These are first launches
with an empty shader cache, one run of each route at `--real-time --scale=2` with nothing warmed,
at Dragoon `d3c9c15` and gcn-recomp `caf12a2`. These runs started with no `saves/shaders.bin`.
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
The other seven are over 16.7 ms and under 33. The 15-program burst at frame 902 sits at 30 to 32 ms
here, where an earlier set of runs saw 27 to 40 ms.

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

| Target | Bar | Measured | Result |
|---|---|---|---|
| Stalls in a fresh install's first session | 0 frames over 33 ms after frame 300 on all five routes | 0 frames on all five, worst render frame 11.1 ms | Pass |
| Shaders compiled during play after the warm-up | 0 `[shaders] compiled program` lines on the five routes | 0 on all five | Pass |
| How far the attract demos alone get | Report the share of each route's keys the attract pass builds by itself | The warm-up has no attract pass. Run from a blank card it sat at the "make a new save data file?" prompt and built 3 keys in 20,000 frames. Run after the routes, on the card they leave, it took 50 s and added 9 keys on top of the routes' 191, none of which a route needed | Dropped |
| Time added to the first build | 90 s or less | 42.6 s, 191 keys | Pass |
| Time added to every boot on macOS GL | 1,000 ms or less | 270 to 298 ms for 191 programs | Pass |
| Frames | `tools/frame_hashes.py check` passes | All five routes OK | Pass |

With the default dump every 60 frames, the dumped frames themselves go over 33 ms, so these runs set
`DUMP_EVERY` to 100,000.

How these were measured, at Dragoon `62b114b` and gcn-recomp `caf12a2`, on a Mac with an M4 Max.
Each route ran as
`tools/probe.sh NAME SECONDS tests/routes/ROUTE.txt 100000 GCN_FRAMETIME=1 --real-time --scale=2`
(plus `--pads=4` for the four-player route). SECONDS was the route's last required frame over 60,
plus 15, rounded up. That gave 31, 35, 70, 73 and 115 for the title, menu, City Trial, four-player
and race routes. Each run started from a copy of the cache of one warm-up, not from five separate warm-ups.
Stalls are the frames `tools/frametime.py build/probe/NAME/stdout.txt --slow 33` lists after frame
300. Compiles are the `[shaders] compiled program` lines, counted with `grep -c`. The boot time is
read from the `[shaders] ... programs from cache ... in N ms` line the game prints at startup. The
42.6 s is one warm-up timed with `/usr/bin/time -p`.
Apple's own shader cache was warm from earlier runs. Whether the warm-up fills it on a fresh Mac
wasn't checked.

An earlier warm-up left 35 compiles in City Trial, 33 in four-player, 9 in the race and 3 in the
title. Starting each pass from a blank card, with 900 frames (15 s) past the last checkpoint,
removed them. Before that, the title pass made a memory card in the scratch directory and every
later pass started on it, where the routes' A presses take the load menus instead of the "make a
new save data file" ones. On City Trial, a pass at scale 1 `--fast`, scale 2 `--fast` and
scale 2 `--real-time` built the same 107 keys.

## Fixes on the way

Two things stopped the game. Both were generic, so both are in gcn-recomp.

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: MMU: access to 75730040 with no page table` when the opening movie ended, and a second into every race | The effects code (`kar_efanime__near_80240084`) calls `setjmp` (803AE238) before it walks an animation tree. Its callback (8023F4E4) calls `longjmp` (803AE33C) to stop the walk. Recompiled, `longjmp` restored the stack pointer of the outer frame and then returned into the callback, and the code after it ran on the wrong stack frame | gcn-recomp `b326dcd` lets `special_calls.txt` name a `setjmp` and `longjmp`. A call site of `setjmp` records a host resume point, and `longjmp` goes there once it has restored the registers. `recomp/special_calls.txt` and `recomp/names.txt` name the pair |
| A race showed the HUD on plain sky blue | The frame's first draw is a sky quad at the far end of the frustum with a Z8 replace Z texture (texel 0xFF, bias 0). The depth test is set to run before texturing, so on the console the quad writes its own far depth. The renderer wrote the texel's depth instead (0x0000FF), and every later draw failed the test | gcn-recomp `7d30377` leaves the Z texture out of the depth when the test runs before texturing |

`analysis/symbols.txt` calls 803AE238 `ExPPC_UnwindStack` and 803AE33C
`ExPPC_IsInSpecification`. Their code is the C library's `setjmp` and `longjmp`, and
`recomp/names.txt` renames them.
