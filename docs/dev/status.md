# Status

What's true of Dragoon today, measured on one machine. Build numbers are from a clean
build directory at gcn-recomp `67a7e30`, and the game was run at `7d30377`. The four-player
numbers are from `fda6926`. The controller row is from `25c4f26`, where the five frame-hash
routes also pass. The audio row is from gcn-recomp `bf31b7b` and its click counts from
`fd1f6a8` and `e6ea431`, where the five frame-hash routes and the five audio-hash routes pass.
Both sets pass again at `b848158`, after the review fixes. The other Air Ride courses, their
pacing and the twelve-route warm-up were measured on a build of Dragoon `788571c` and
gcn-recomp `b848158` with the seven course routes added. All twelve frame-hash routes and all
twelve audio-hash routes pass at `fe0c0bf`. At gcn-recomp `b97c019` eleven routes' frames and
all twelve routes' audio changed, and both sets of goldens were recorded again there. The pin
is now `e1016b8`, where all twelve matched them. The goldens of the nine Top Ride and stadium
routes were recorded at `e1016b8` on Dragoon `1a88f62`, and all twenty-one routes' frames and
audio match there (under gcn-recomp `e1016b8` below). The Top Ride and stadium pacing numbers
are from Dragoon `788571c` at gcn-recomp `b848158`. The memory card and stats screen findings
were checked again at `e1016b8` on `1a88f62`. The twenty-one-route warm-up was timed at
`2e6e6f8` and `0059fce` on gcn-recomp `e1016b8` (under Player targets).

| Feature | Status | Note |
|---|---|---|
| Boot and memory card | Works | A blank card gets the game's prompt by frame 60, and the save file is made. The game writes the card again after each title screen and when its Sound screen closes, and what it wrote comes back on the next launch. In one pair of runs the Sound screen's Mono and the music and effects balance both sat where the first run left them. Mono is kept in the console's SRAM, which gcn-recomp has saved in `saves/sram.raw` since `2bf7308`. At `b848158` it started afresh at every launch and Mono didn't come back (table under Memory card) |
| Opening movie | Plays | Then the title and the attract demos, races and mode movies |
| Title screen | Works | `tests/routes/title.txt` |
| Mode select | Works | `tests/routes/menu.txt`. Since gcn-recomp `b97c019` the preview window at its right shows a race, where it was a plain gray box (under gcn-recomp `e1016b8`) |
| Air Ride race | Runs | All eight courses a blank memory card can pick load and race past the countdown, one route each in `tests/routes/`, with no crash and nothing seen drawn wrong. Fantasy Meadows (`air-ride-race.txt`) has three laps and the other seven two. With nobody steering, six reach the results screen and Kirby stays stopped against a wall on the other two (table under How far it gets). Nebula Belt, the ninth course, is locked on a blank card behind an Air Ride checklist box that counts 100 laps |
| City Trial | Runs | One player (`tests/routes/city-trial.txt`) or four in split screen (`city-trial-4p.txt`), the five-minute clock running. With the clock cut to three minutes and the stadium set to Drag Race in Game Settings, one player (`city-trial-stadium.txt`) or four (`city-trial-stadium-4p.txt`) play out the clock and reach Drag Race 3 and its results. A fresh save offers only Drag Race, Target Flight and Destruction Derby, besides Shuffle. Target Flight and Destruction Derby weren't played |
| Top Ride | Runs | All seven courses a fresh save offers (Grass, Sand, Sky, Fire, Light, Water and Metal) race past the countdown with one player and three CPUs (`top-ride-<course>.txt`) |
| Audio | Partial | The mixer reads the control word the game's ucode (`07F88145`) uses. The compressor command runs. On the race route the windows with a main peak over 32,767 fell from 13 to 2 and the samples the output clamp changed from 4,435 to 923. AuxA sound went from 22 windows to 97 and AuxB from none to 20 (table under Audio). All 1,211 `[ax] cmds` lines of ten runs (484,400 command lists) count 0 unknown and 0 skipped commands. Source type 2 voices no longer resample, and on the title route the clicks in the DMA's blocks fell from 928 to 19 (table under Audio). Since gcn-recomp `b97c019` source type 0, 98.9% of the voice time in twelve unpaced runs, resamples through a polyphase filter whose coefficients the runtime works out, because the console's are in the DSP's ROM. None of those runs turned the low-pass filter on, and the runtime doesn't apply it. It was listened to once, before the type 2 fix. It crackled. Nobody has listened since. Nothing has been compared with recordings from a real console. `tools/audio_hashes.py check` holds the output hashes. [`scorecard.md`](scorecard.md) runs the routes on gcn-recomp `caf12a2` (before any of the audio work) and on `b848158`. On the title route played to 91 s in real time the clicks in the DMA's blocks fell from 1,097 and 979 to 22 and 22. Over the five routes the device stage's clicks a minute fell from 57.9 to 36.3 and from 45.1 to 33.1. Unpaced, over those routes' 324 s, the DMA's blocks went from 132 clicks to 136 and from 208 clipped runs to 25, and a bisect on 2026-10-22 agrees with 131 to 135 and 203 to 25. The audio work up to `b848158` didn't reduce the clicks over those seconds. Rescored with `audio_scorecard.py --no-run`, the title's first 91 s (`--margin 75`) went from 1,085 clicks to 19 and the mode select's first 170 s (`--margin 150`) from 118 to 16, so on those two routes the clicks that fell are past the scored seconds, in the same recordings (`scorecard.md`). In the scored seconds what it cut was clipping. Real-time runs showed the DMA's clicks rising, and the bisect found that most of that rise came from playing in real time. Pass 5 scored `b848158` against `b97c019`, and the pin `e1016b8` changes no audio file after it. Unpaced, over the same 324 s, the DMA's blocks went from 136 clicks to 94 and from 35 clicks on a block join to 7. In one real-time run of each build the device stage's clicks went from 191 to 70. Details in `audio.md` |
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
| City Trial | `city-trial.txt` | 3300 | The city, 4:54 left |
| Four-player entry | `city-trial-4p.txt` | 2700 | P1 OK to P4 OK under READY?, each player joined from its own port |
| Four-player City Trial | `city-trial-4p.txt` | 3480 | Four views, 4:51 left, ports 1 and 3 steering left and 2 and 4 right |
| Three-minute City Trial | `city-trial-stadium.txt` | 4800 | The city, 2:55 left. The entry screen before it read "Time: 3 min [Drag Race]" |
| Time up | `city-trial-stadium.txt` | 15600 | `TIME!` at 0:00:00, with Kirby seen from behind and the speedometer at the lower right. Each player's machine stats follow and wait for A |
| Machine stats | `city-trial-stadium.txt` | 15900 | Four quarters on a dim green background, each a list from Boost to HP beside a machine. P1 is at the top left with every value 0 and the other three are marked CPU. PRESS A sits in the middle (see Stats screen) |
| Drag Race 3 | `city-trial-stadium.txt` | 17100 | Under way, 0:06 on the clock, P1 fourth behind three CPUs |
| Stadium results | `city-trial-stadium.txt` | 20400 | P1 fourth in 0:50.87 behind CPUs on 0:35.83, 0:47.36 and 0:47.62, waiting for START |
| Four-player stadium | `city-trial-stadium-4p.txt` | 17100 | Drag Race 3 in four views, 0:06 on the clock |
| Four-player results | `city-trial-stadium-4p.txt` | 21000 | P3 first in 0:53.31, then P2, P4 and P1 in 1:00.15, under confetti |
| Top Ride race | `top-ride-<course>.txt` | 3600 | Each course 3.62 s into the race. Seven laps on Grass and Sand, six on Sky, Fire and Light, five on Water and Metal |

Left alone, the race route finishes three laps in 1:14.68 and reaches the results screen by
frame 25,800. It showed 1:12.60 when this was first written, at gcn-recomp `7d30377`. City Trial with nobody steering drives into the sea and stays there while the
clock runs. The opening movie, when it isn't skipped, plays to the end and hands over to the
title and the attract demos.

The seven other course routes were left running for 120 s each with `--fast` and a dump every
300 frames, four and then three at a time. Checker Knights ran again for 200 s to reach its
results.

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
route. The course select's setup (`fn_8003C114` in the generated C, its call at guest address
0x8003C21C) puts a locked entry in that slot unless `fn_8000C0E0(8)` says course 8 is open. In
the wowjinxy/KAR decomp that function asks
`ClearChecker_CheckUnlocked(0, 0x22)` (`src/kar/gm/gmautodemo.c:2902`), the Air Ride
checklist reward whose clear kind is 0 (`src/kar/gm/gmclearchecker.c:77`). In LAN play
(`kar_shadow__near_8007b650` in `lbnet.c`) it tests bit 0x22 of a bit array at 0x805359D8 +
0xD50 instead (`kar_gmglobal__near_80007e34`, `gmautodemo.c:2899-2900`).

Clear kind 0 is marked once a running total reaches 100 (`kar_gmclearchecker__near_8004ac34`,
`src/kar/gm/gmclearchecker_8004a648.c:346`). That total is the value at 0x80536834
(`clearchecker_total_0`) plus the lap counts of the racer slots it counts, kept per slot at
0x80536240 (`fn_8000B1EC`, `gmautodemo.c:2326`). Those are the slots whose kind is 0, plus kind
1 when the race mode is 1 (`gmclearchecker_8004a648.c:334`). Whether the value at 0x80536834
reaches the memory card wasn't checked. The attract demo skips course 8 on the same check
(`gmautodemo.c:4141`).

RAM dumps taken with `GCN_RAM_DUMP_AT` show what's counted. On the race route each racer's
count went up by one as it finished a lap, and the running total at 0x80536834 went from 0
before the race to 3 after it. Celestial Valley's route ended with every count at 2 and the
running total at 2. On these one-player routes only Kirby's laps counted, not the CPUs'. Other
players at the console likely count too, since the decomp adds up the racers of one kind. A race
with a second player wasn't run.

A blank card needs 100 Air Ride laps before the box is marked. Reaching 100 sets bit 0 of the
box's flags (`gmclearchecker.c:211`), while the course select's check reads bit 3
(`gmclearchecker.c:162`). The code that sets bit 3 isn't decompiled. The only store of it found
in the generated C is in the checklist screen's refresh,
`kar_mnclearchecker_refresh_grid_tile_models` (`fn_8017DF5C`, `build/gen/recomp_041.c:1367-1373`,
the store at 0x8017E008). It sets bit 3 only for a box whose flags already have bit 1 or 2
(`& 0x6`), so the course most likely opens once that screen shows the box. The search covered
only the functions that call the save getter (`fn_800076A0`), and the course wasn't opened in a
run.

The race runs at about 500 frames a second in the hidden window with `--fast`, 8 times the
game's 60. That's 9,600 frames between frames 3600 and 13,200 in 19.3 s of wall time, with
other work on the machine at the time.

## Air Ride pacing

Each course route ran once at the game's own speed, hidden at 640x480, as
`tools/probe.sh NAME 130 tests/routes/ROUTE.txt 100000 --real-time GCN_FRAMETIME=1`. Each
started with the cache from a warm-up of all twelve manifest routes copied to its
`saves/shaders.bin`. Two or three other copies of Dragoon were running the game on the same
machine each time `ps` was checked.

The rows are `tools/frametime.py build/probe/NAME/stdout.txt --from 3400 --slow 16.7`, from
just after the start to the end of the run. Compiles are the `[shaders] compiled program`
lines after boot, and boot is the `programs from cache` line's time for 222 programs.

| Course | Frames | Guest mean | 95th | 99th | Worst | `[rt]` mean | `[rt]` 99th | `[rt]` worst | Compiles | Boot |
|---|---|---|---|---|---|---|---|---|---|---|
| Fantasy Meadows | 4,226 | 16.69 ms | 17.95 ms | 18.37 ms | 43.94 ms (5314) | 0.60 ms | 0.91 ms | 41.57 ms (7110) | 1 (7110) | 380 ms |
| Celestial Valley | 4,227 | 16.69 ms | 17.92 ms | 18.33 ms | 41.71 ms (7359) | 0.57 ms | 1.19 ms | 2.73 ms | 0 | 362 ms |
| Sky Sands | 4,223 | 16.70 ms | 17.95 ms | 18.34 ms | 85.51 ms (5376) | 0.58 ms | 0.96 ms | 1.60 ms | 0 | 368 ms |
| Frozen Hillside | 4,230 | 16.69 ms | 18.01 ms | 18.31 ms | 32.52 ms (6425) | 0.52 ms | 0.71 ms | 3.86 ms (5752) | 1 (5752) | 376 ms |
| Magma Flows | 4,226 | 16.69 ms | 17.91 ms | 18.24 ms | 40.83 ms (6053) | 0.61 ms | 1.01 ms | 1.50 ms | 0 | 377 ms |
| Beanstalk Park | 4,228 | 16.68 ms | 17.92 ms | 18.22 ms | 18.97 ms | 0.51 ms | 0.85 ms | 2.96 ms (5648) | 1 (5648) | 374 ms |
| Machine Passage | 4,225 | 16.69 ms | 17.98 ms | 18.29 ms | 38.05 ms (7583) | 0.46 ms | 0.66 ms | 3.25 ms (6007) | 1 (6007) | 368 ms |
| Checker Knights | 4,227 | 16.69 ms | 17.92 ms | 18.24 ms | 34.43 ms (6152) | 0.57 ms | 0.94 ms | 1.46 ms | 0 | 387 ms |

Every course averaged 16.68 to 16.70 ms a guest frame, and 99 frames in 100 took under
18.4 ms. Seven of the eight courses had a guest frame over 30 ms, one on each of six and two
on Machine Passage. Beanstalk Park had none.

| Course | Guest frames over 30 ms from frame 3400 |
|---|---|
| Fantasy Meadows | 43.94 ms (5314) |
| Celestial Valley | 41.71 ms (7359) |
| Sky Sands | 85.51 ms (5376) |
| Frozen Hillside | 32.52 ms (6425) |
| Magma Flows | 40.83 ms (6053) |
| Beanstalk Park | None. The worst was 18.97 ms |
| Machine Passage | 34.53 ms (6936) and 38.05 ms (7583) |
| Checker Knights | 34.43 ms (6152) |

Each was a single late frame, with frames of 15.7 to 17.9 ms on both sides. Its `[ft]` line
shows no new texture and a front end of 0.33 to 0.55 ms, and no compile came near it, so the
log doesn't say what held it up.

Four courses compiled one program each in play, at frames past where the warm-up's pass for
that route stops (6,900 for Fantasy Meadows and 5,100 for the others). Each compile took 1.7
to 2.0 ms. The render frame that first drew with it took 41.57 ms on Fantasy Meadows and under
4 ms on the other three.

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
back with `OSGetSoundMode` at 8044EA84. A console keeps SRAM on a battery. Since gcn-recomp
`2bf7308` the runtime keeps it in `saves/sram.raw` and loads it at boot (`runtime/hw/sram.cpp`).
The blank card's run 1 left no such file. After run 2 it was there at 64 bytes with byte 0x13
reading 0x28, and run 3 didn't write it again. At `b848158` `sram_init` (`runtime/hw/exi.cpp`)
set byte 0x13 to 0x2C, stereo, at every launch and never saved it, so Mono lasted only until
the game closed.

At `b848158` City Trial's Game Settings didn't come back either, because the game doesn't
write them when its menus close. In one pair of runs the second showed 5 min and Shuffle
after the first set 3 min and Drag Race. A third run that made the same change with
`--log=exi` logged no card writes after it, as every write came before frame 700. Whether
the game saves them after a match wasn't checked, and none of this was run again at
`e1016b8`.

## Stats screen

When City Trial's clock runs out, each player's machine stats come up and wait for A. At
gcn-recomp `b848158` that screen drew black. At `e1016b8` it doesn't. Frames 15,900 and 16,200
of `city-trial-stadium.txt`, looked at in a run at `e1016b8`, each show the four quarters
described under How far it gets, with a stat list and a machine in each on a dim green
background and PRESS A in the middle. The machines sit in different poses in the two frames. Against the
hashes recorded for the route at `b848158`, four of its 68 frames differ at `e1016b8`. Two are
15,900 and 16,200. The others are 1,200 and 1,500, which the EFB copy fix moved (under
gcn-recomp `e1016b8` below). In `city-trial-stadium-4p.txt` the same four of 70 differ. The
four-player stats frames weren't looked at.

The draw log of frame 15,900 (`GCN_DRAWLOG=15900 GCN_DRAWLOG_VERBOSE=1`) at `e1016b8` still
lists draw 100 with blend register `007012` and draw 101 with `0050D9`, both under
`pecntrl=000040`, and draw 102 with `00F4A9`. The format in `pecntrl=000040` is RGB8_Z24, which
has no alpha. gcn-recomp's message for `1b77560` calls draw 101 a full-screen ZERO, DSTALPHA
pass. The renderer used to hand GL `GL_DST_ALPHA` for it whatever the format, and the frame
came out black. Since `1b77560`, `blend_factors` in `runtime/gx/blend.h` reads DSTALPHA as one
and INVDSTALPHA as zero when `efb_has_alpha` says the format has none, and `render_gl.cpp` calls
it (line 2285 at `e1016b8`), so draw 101 no longer blacks the frame out.

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

- The low-pass filter (`audio.md`). The game didn't turn it on in the twelve audio-hash runs
  at `b97c019`.
- The polyphase coefficients are worked out, not the console's own from its DSP ROM.
- The sound was listened to once, before the type 2 fix. It crackled. Nobody has
  listened since. Nothing has been compared with recordings from a real console.
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
| Stalls in a fresh install's first session | 0 frames over 33 ms after frame 300 on all five routes | 0 frames on all five to the frames those runs reached (6,900 on the race), worst render frame 11.1 ms. Run to 130 s, the race had one at frame 7110, 41.57 ms, with a compile | Fail |
| Shaders compiled during play after the warm-up | 0 `[shaders] compiled program` lines on the five routes | 0 on all five to the end of those runs. 1 on the race at frame 7110, past the warm-up's 6,900, and 1 each on Frozen Hillside (5752), Beanstalk Park (5648) and Machine Passage (6007), past 5,100 | Fail |
| How far the attract demos alone get | Report the share of each route's keys the attract pass builds by itself | The warm-up has no attract pass. Run from a blank card it sat at the "make a new save data file?" prompt and built 3 keys in 20,000 frames. Run after the routes, on the card they leave, it took 50 s and added 9 keys on top of the routes' 191, none of which a route needed | Dropped |
| Time added to the first build | 90 s or less | 47.1 s for the five routes' 191 keys. 120.5 s for all twelve routes' 222 keys. 252.8 s for all twenty-one routes' 318 keys, one pass at a time. 67.7 s and 68.9 s on an M4 Max for the same 318 keys, five passes at a time (Dragoon `0059fce`, table below) | Pass |
| Time added to every boot on macOS GL | 1,000 ms or less | 270 to 298 ms for 191 programs. 362 to 387 ms for 222 | Pass |
| Frames | `tools/frame_hashes.py check` passes | All five routes OK. All twelve at `fe0c0bf`, and all twelve at `b97c019` and `e1016b8` after the goldens were recorded at `b97c019`. All twenty-one at `e1016b8`, with the nine newer routes' goldens recorded there | Pass |

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
row's earlier figure, 42.6 s at `62b114b`, was one warm-up timed with `/usr/bin/time -p`.
Apple's own shader cache was warm from earlier runs. Whether the warm-up fills it on a fresh Mac
wasn't checked.

The 47.1 s and 120.5 s are later warm-ups at Dragoon `788571c` and gcn-recomp `b848158`, each
`tools/warm_shaders.py --force` from an empty cache under `/usr/bin/time -p`, with the manifest
at five routes and then at twelve. Other copies of Dragoon were running the game on the same
machine that afternoon, so neither is an idle machine's time. Each of the seven new passes
played 5,100 frames in 9.4 to 11.2 s.

The warm-up now plays all twenty-one manifest routes, nine more than the 120.5 s one. It
took 252.8 s at Dragoon `2e6e6f8`, and 252.7 s and 253.2 s on the tree that became `c621106`,
which only added `warm_shaders.py --report`. All three are `tools/warm_shaders.py --force`
from an empty cache at gcn-recomp `e1016b8`, one pass at a time in the manifest's order, on an
M4 Max with no other run of the game going. They left byte-identical caches of 318 keys and
254 programs (distinct generated sources, so 64 keys share a program). This table is the
252.7 s run's, except the last column, which is from the 253.2 s run, made with
`GCN_FRAMETIME=1`. `+keys` and `+programs` are what the pass added to the cache the passes
before it left. The last column is the last frame at which a pass compiled a key the passes
before it hadn't. `--report` now starts every pass from the starting cache, so its last column
is a pass's last compile of any key (City Trial 3,165 and the four-player stadium 20,604 with
four passes at once) and can't reproduce this one.

| Pass | Frames | s | Boot ms | +keys | +programs | Keys | Last new frame |
|---|---|---|---|---|---|---|---|
| title | 1,860 | 3.6 | 0 | 71 | 59 | 71 | 1,768 |
| menu | 2,100 | 6.1 | 107 | 6 | 5 | 77 | 1,012 |
| air-ride-race | 6,900 | 12.1 | 116 | 70 | 59 | 147 | 6,662 |
| city-trial | 4,200 | 9.3 | 225 | 33 | 31 | 180 | 2,950 |
| city-trial-4p | 4,380 | 11.6 | 274 | 11 | 11 | 191 | 2,865 |
| air-ride-celestial-valley | 5,100 | 8.9 | 296 | 1 | 1 | 192 | 4,359 |
| air-ride-sky-sands | 5,100 | 9.1 | 294 | 2 | 2 | 194 | 3,174 |
| air-ride-frozen-hillside | 5,100 | 8.7 | 296 | 7 | 7 | 201 | 3,223 |
| air-ride-magma-flows | 5,100 | 9.2 | 310 | 7 | 7 | 208 | 4,947 |
| air-ride-beanstalk-park | 5,100 | 8.6 | 320 | 2 | 2 | 210 | 3,219 |
| air-ride-machine-passage | 5,100 | 8.6 | 327 | 6 | 5 | 216 | 3,164 |
| air-ride-checker-knights | 5,100 | 9.2 | 335 | 6 | 5 | 222 | 4,985 |
| top-ride-grass | 4,500 | 8.1 | 343 | 30 | 16 | 252 | 4,368 |
| top-ride-sand | 4,500 | 9.4 | 391 | 11 | 8 | 263 | 4,498 |
| top-ride-sky | 4,500 | 8.6 | 407 | 13 | 8 | 276 | 3,733 |
| top-ride-fire | 4,500 | 8.4 | 426 | 7 | 4 | 283 | 3,645 |
| top-ride-light | 4,500 | 8.5 | 442 | 2 | 1 | 285 | 3,434 |
| top-ride-water | 4,500 | 8.5 | 451 | 6 | 5 | 291 | 4,356 |
| top-ride-metal | 4,500 | 8.6 | 456 | 5 | 4 | 296 | 3,968 |
| city-trial-stadium | 21,300 | 38.4 | 455 | 15 | 9 | 311 | 18,395 |
| city-trial-stadium-4p | 21,900 | 49.2 | 480 | 7 | 5 | 318 | 18,449 |

Where the 252.7 s went, one pass at a time. The cache-load row is this run's. Passes that start
from a blank cache load none, as the 0 ms boot column of the at-once runs shows.

| Part | Time | Share |
|---|---|---|
| Playing 129,840 frames, and starting the game 21 times | 245.4 s | 97.1% |
| Building every program the cache holds at each of 20 starts (macOS GL keeps no binaries, so these are compiles) | 6.8 s | 2.7% |
| The 318 programs compiled in play, 2.8 ms at most each | 0.6 s | 0.2% |

A pass of 5,100 frames took 8.6 to 9.2 s whether it added one key or seven, so compiling
isn't the cost. The guest thread sets the frame time. On the stadium route the interval
between presents averaged 1.79 ms and the renderer's issue time 0.35 ms, and on the four-player
stadium 2.22 and 0.68 ms (`frametime.py`). The first five routes took 42.7 s for 191 keys.
The other sixteen took 210.0 s for 127, 87.6 s of it for the two stadium routes' 22.

No pass can be dropped. In the manifest's order every pass adds at least one key, and the
fewest, Celestial Valley, adds one. Cutting each pass at its last new frame would play 107,174
of the 129,840 frames, 17% fewer, which comes to about 209 s at the measured 514 frames a
second. That figure is arithmetic and wasn't run. At over twice the bar, it wasn't built.

Each pass has a scratch directory and a cache of its own, and the caches are merged afterwards,
each key once, in the manifest's order, so passes can play at once. The 4, 6 and 8 runs are the
tree that became `0059fce`, which differs from it only in how it picks the default number of
passes. They set `GCN_FRAMETIME=1` and `--report`. The 5 runs are `0059fce` with its default,
a third of this machine's 16 cores.

| Passes at once | Time | The 21 pass times added up | Stadium four-player pass |
|---|---|---|---|
| 1 | 249.5 s | 249.0 s | 49.3 s |
| 4 | 77.9 s | 302.6 s | 60.0 s |
| 5 | 68.9 s and 67.7 s | 328.5 s and 323.0 s | 65.3 s and 64.1 s |
| 6 | 67.1 s | 352.5 s | 66.7 s |
| 8 | 71.4 s | 417.1 s | 71.0 s |

Each pass slows as more play at once, so the machine doesn't scale with the number of
passes. At 4 and 5 the workers were busy to the end, since 302.6 s over 4 is 75.7 s of the
77.9 s and 328.5 s over 5 is 65.7 s of the 68.9 s. Those times are throughput, not one pass.
At 6 and 8 the four-player stadium pass finished last, 66.7 s of 67.1 s and 71.0 s of 71.4 s.

Every one of these caches holds the same 318 keys and 254 programs. `shader_cache.py diff`
finds no key in the new cache that the 252.8 s one lacks, or the other way round. The 1, 4, 5, 6
and 8 caches are byte for byte the same. The 252.8 s cache lists its keys in another order,
because there each pass started from the last one's cache and the game rewrites its cache in
its own table's order at every start. The 249.5 s row is `0059fce` with `--jobs 1`, which also
gives each pass a cache of its own, and it came in a little under the 252.8 s that built each
on the last. A 5-at-a-time run started from the warm cache (67.3 s, 318 keys, same size) added
no key on any of the 21 routes.

The 362 to 387 ms boots are from the Air Ride pacing runs above, which also went past the frames
the warm-up plays and compiled one program each on four courses. On Fantasy Meadows that
compile came with a 41.57 ms render frame at frame 7110, over the 33 ms stall bar, at 640x480
rather than the scale 2 the rows above used.

An earlier warm-up left 35 compiles in City Trial, 33 in four-player, 9 in the race and 3 in the
title. Starting each pass from a blank card, with 900 frames (15 s) past the last checkpoint,
removed them. Before that, the title pass made a memory card in the scratch directory and every
later pass started on it, where the routes' A presses take the load menus instead of the "make a
new save data file" ones. On City Trial, a pass at scale 1 `--fast`, scale 2 `--fast` and
scale 2 `--real-time` built the same 107 keys.

## gcn-recomp `e1016b8`

The pin moved from gcn-recomp `b848158` to `e1016b8`, 87 commits, by way of `b97c019`, 66
commits on. Built at `b97c019`, the game ran `tools/frame_hashes.py check` and
`tools/audio_hashes.py check` against the goldens on `main` before anything was recorded.

| Check against `main`'s goldens | Matched | Changed |
|---|---|---|
| Frames | The title, all 16 of its frames | The other eleven routes, 62 frames in all, every one between frames 1020 and 1500 |
| Audio | None | All twelve routes, every row, 24 in all |

The menu route changed at frames 1020 to 1200, the eight race routes at 1020 to 1260 and the
two City Trial routes at 1020 to 1500. Each of those nine frame numbers got one new hash, the
same on every route that dumps it. The title's goldens stop at frame 960.

These are the frames gcn-recomp `affc7b5` says its EFB copy fix moves. Its message says the
game copies a render target from an RGB8 EFB to an RGBA8 texture and draws it with alpha, and
the copy took whatever alpha the GL framebuffer held, so the window that shows it drew as an
empty box. On the mode select that's the preview window at the right. Frame 1200 of the menu
route hashes to its old golden `a3f1408d` at `b848158`, where the window is a plain gray box.
At `b97c019` it hashes to `ba0a9f9b`, and the window shows a race.

The audio changes are in `audio.md`. The hashes cover the mix since boot, so they show that
every route's sound changed and not which commit changed it.

Both tools then ran `record` at `b97c019`, and a second `check` matched every route, all 739
frames and all 24 audio rows. So the three runs of each route at `b97c019` gave the same frames
at every checkpoint, and the second check's audio rows were the ones recorded. Every `[ax]
hash` line that the first and third audio runs both printed was the same.

`e1016b8` adds 21 commits to `b97c019`. Six of them touch `runtime/`, among them an IPL SRAM
write fix in `216fe38` and window sizing, and none touches the audio files there. Built at
`e1016b8`, the game ran both checks against the goldens recorded at `b97c019`, and every route
matched, all 739 frames and all 24 audio rows.

The seven Top Ride routes and the two stadium routes came onto that pin afterward, and their
goldens were recorded at `e1016b8` on Dragoon `1a88f62`. Frames use each route's seconds and
dump interval in `tests/hashes/manifest.txt`. Audio rows are at lists 12,000 and 16,000 for
Top Ride and 56,000 and 68,000 for the stadium routes. After each `record`, two `check` runs of
the nine matched every frame (558) and every audio row (18), so two runs at one build agreed.
Then `tools/frame_hashes.py check` and `tools/audio_hashes.py check` over all twenty-one routes
matched too, 1,297 frames and 42 audio rows, so the twelve goldens recorded at `b97c019` still
hold. The frame check took 10 min 43 s and the audio check 10 min 41 s.

The nine routes' goldens at `b848158` aren't in this branch. Against them, every audio row of
the nine differs at `e1016b8`, all 18. Each Top Ride route's frames differ at 7 of 60, the
ones at 1,020 to 1,380, and each stadium route's at 4 (the stats frames above and frames 1,200
and 1,500). Frame 1,200 hashes to `ba0a9f9b` on all nine, as it does on the menu route.

## Fixes on the way

Two things stopped the game. Both were generic, so both are in gcn-recomp.

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: MMU: access to 75730040 with no page table` when the opening movie ended, and a second into every race | The effects code (`kar_efanime__near_80240084`) calls `setjmp` (803AE238) before it walks an animation tree. Its callback (8023F4E4) calls `longjmp` (803AE33C) to stop the walk. Recompiled, `longjmp` restored the stack pointer of the outer frame and then returned into the callback, and the code after it ran on the wrong stack frame | gcn-recomp `b326dcd` lets `special_calls.txt` name a `setjmp` and `longjmp`. A call site of `setjmp` records a host resume point, and `longjmp` goes there once it has restored the registers. `recomp/special_calls.txt` and `recomp/names.txt` name the pair |
| A race showed the HUD on plain sky blue | The frame's first draw is a sky quad at the far end of the frustum with a Z8 replace Z texture (texel 0xFF, bias 0). The depth test is set to run before texturing, so on the console the quad writes its own far depth. The renderer wrote the texel's depth instead (0x0000FF), and every later draw failed the test | gcn-recomp `7d30377` leaves the Z texture out of the depth when the test runs before texturing |

`analysis/symbols.txt` calls 803AE238 `ExPPC_UnwindStack` and 803AE33C
`ExPPC_IsInSpecification`. Their code is the C library's `setjmp` and `longjmp`, and
`recomp/names.txt` renames them.
