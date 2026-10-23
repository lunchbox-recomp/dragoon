# Audio scorecard

What gcn-recomp's audio work changed, measured by program with nobody listening.
`tools/audio_scorecard.py` played the five routes in `tests/hashes/manifest.txt` on two builds
and counted clicks, gaps and clipping before and after the audio ring. The baseline is gcn-recomp
`caf12a2`, with none of the audio work. Current is gcn-recomp `b848158`. Each pair ran twice on
2026-10-22, and each cell below gives the first pass, then the second.

On the title route played to 91 s, the clicks in the DMA's blocks fell from 1,097 to 22 in the
first pass and from 979 to 22 in the second. Across the five routes at their usual length, the
device stage's clicks a minute fell from 57.9 to 36.3 and from 45.1 to 33.1, and the mixer
stage's clipped samples from 5,942 to 378 and from 2,206 to 415. The mixer stage's clicks a
minute over the five routes rose, from 22.3 to 26.4 and from 24.4 to 30.2. Its gaps and its
clicks on block joins rose too.

## The two builds

| | Baseline | Current |
|---|---|---|
| Dragoon | `6b81b6e` | `788571c`, run from the `scorecard` branch, whose commits add only the tool and docs |
| gcn-recomp | `caf12a2` | `b848158` |
| PB mixer control word | 2001 layout | Later layout for this game's ucode (`07F88145`) |
| Compressor, command `12` | Skipped | Runs |
| Source type 2 voices | Stepped through by the rate ratio | One sample in for each sample out |
| Ring cuts and dropouts | Step | Fade |
| Pace under SDL's dummy driver | The driver's own | The runtime pulls the sound on 48 kHz deadlines |
| `[ring]` lines | Underruns | Underruns, cuts and each cut's output frame |
| `[ax] bus` lines, with the samples the clamp changed | None | Every 400 lists |

`git -C gcn-recomp log --oneline 9b0a2fe..caf12a2` lists the 13 commits the baseline adds to
upstream `9b0a2fe`. They're two runtime fixes, controller and input support, the SDL3 frontend
and two commits for tooling.

- `b326dcd` resumes a guest `longjmp` at its `setjmp`'s call site.
- `7d30377` leaves a Z texture out of the depth when Z compares before texturing.
- `d558e3d`, `0197460`, `3aebdc9` and `fda6926` plug in controllers on ports 2 to 4 and let
  scripts press them.
- `340da84` gives each gamepad a port of its own.
- `1c164b2` loads controller mappings from a `gamecontrollerdb.txt`, so a controller SDL has
  no mapping for can get a port.
- `642187a` adds `--test-ports`, which checks the port rules against SDL's virtual joysticks.
- `e08cde3` and `d9ee73d` move the frontend to SDL3.
- `caf12a2` adds `--exit-after`, and `67a7e30` adds this game's names to `tools/game_terms.txt`.

None of them changes `runtime/hw/ax.cpp`, `dsp.cpp`, `dsp_hle.cpp` or `runtime/audio.cpp`. The
only audio file they touch is `runtime/audio_sdl.cpp`, which `d9ee73d` moved onto SDL3's audio
stream.

The audio work between the two is these commits of `caf12a2..b848158`. The others in that range
are gamepad ports and line wrapping.

| Commit | Change |
|---|---|
| `8fabc65` | `GCN_AXSTATS` counts commands, bus peaks and clamped samples and hashes the output |
| `6616d55`, `3bde515` | The mixer control word decodes per bus, with the later layout for every ucode but `4E8A8B21` |
| `bf31b7b`, `b839cf6` | The compressor runs on every ucode but `4E8A8B21` |
| `fd1f6a8` | Source type 2 voices play with no rate conversion |
| `3f5da1e` | Each ring cut is logged with its output frame |
| `3ae8463`, `dbd8c99` | The ring's cuts and dropouts fade instead of stepping |
| `e6ea431` | Under SDL's dummy driver the runtime pulls the sound at a sound card's pace |
| `7a5f554`, `b848158` | The ring's test and the docs |

## How it was measured

Each pass was one run of the tool from this clone, with the baseline clone's build directory
as `base`.

```sh
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --json
```

It plays a route on the baseline, then on current, then moves to the next route. Each run goes
through its own clone's `tools/probe.sh` in a hidden window with SDL's dummy audio driver,
`--real-time` and `GCN_AXSTATS=1`, and both builds play this clone's route files. A run lasts
the route's last checkpoint at 60 frames a second plus 15 s. That's 31 s for the title, 35 s
for mode select, 115 s for the race, 70 s for City Trial and 73 s for four players. Every run
starts from a blank memory card and an empty shader cache, and every run reached its last
checkpoint. A pass took 675 s the first time and 674 s the second.

The mixer stage is `GCN_AIDWAV`, every block the DMA delivered before the ring, at 32 kHz.
The device stage is `GCN_WAV`, what went to the device at 48 kHz, ring included. The tool
scores both with `audio_clicks.py`'s functions, as `tools/README.md` describes. A click is a
sample whose second difference is over 8 times the RMS second difference of the 5 ms either
side, and at least 128. A gap is 5 ms or more of digital silence on every channel straight
after sound. A clipped run is two or more samples at 32,767 or -32,768 on one channel.

The log gives the rest. `[ax] frames` lines carry the highest main L magnitude before the output
clamp, and `[ax] bus` lines the L and R samples the clamp changed. The baseline prints the
first and not the second. Its `[ring]` lines carry underruns but no cuts, so the baseline's
cuts aren't counted anywhere below.

## Totals

All five routes together. Clicks a minute is over the summed seconds.

| Five routes | Baseline, pass 1 | Baseline, pass 2 | Current, pass 1 | Current, pass 2 |
|---|---|---|---|---|
| Mixer seconds | 319.78 | 319.87 | 319.87 | 319.87 |
| Mixer clicks | 119 | 130 | 141 | 161 |
| Mixer clicks a minute | 22.3 | 24.4 | 26.4 | 30.2 |
| Mixer clicks within 2 samples of a block join (by chance) | 35 (3.7) | 42 (4.1) | 43 (4.4) | 52 (5.0) |
| Mixer gaps | 3 | 4 | 9 | 9 |
| Mixer clipped runs (samples) | 525 (5,942) | 207 (2,206) | 34 (378) | 31 (415) |
| Device seconds | 296.45 | 296.80 | 322.60 | 322.56 |
| Device clicks | 286 | 223 | 195 | 178 |
| Device clicks a minute | 57.9 | 45.1 | 36.3 | 33.1 |
| Device gaps | 2 | 4 | 9 | 9 |
| Device clipped runs (samples) | 475 (7,984) | 190 (2,977) | 27 (510) | 27 (573) |
| Ring cuts | Not logged | Not logged | 0 | 0 |
| Ring underruns | 0 | 0 | 0 | 0 |
| Highest main L peak before the clamp | 82,740 | 86,191 | 66,056 | 63,229 |
| Samples the clamp changed | Not logged | Not logged | 633 | 657 |

## Route by route

Each cell is the first pass, then the second.

| Clicks a minute | Mixer, baseline | Mixer, current | Device, baseline | Device, current |
|---|---|---|---|---|
| Title | 20.0, 17.9 | 23.9, 23.9 | 23.3, 14.8 | 21.5, 19.5 |
| Mode select | 26.3, 22.8 | 28.1, 29.8 | 46.9, 43.2 | 27.6, 19.0 |
| Air Ride race | 20.5, 25.2 | 24.7, 28.4 | 73.0, 50.6 | 40.3, 32.4 |
| City Trial | 19.9, 18.2 | 23.4, 27.8 | 53.3, 46.8 | 29.3, 35.3 |
| City Trial, four players | 26.6, 32.4 | 32.4, 38.2 | 58.4, 48.5 | 47.0, 44.6 |

| Mixer clicks within 2 samples of a block join (by chance) | Baseline | Current |
|---|---|---|
| Title | 3 of 10 (0.3), 3 of 9 (0.3) | 5 of 12 (0.4), 5 of 12 (0.4) |
| Mode select | 6 of 15 (0.5), 4 of 13 (0.4) | 6 of 16 (0.5), 5 of 17 (0.5) |
| Air Ride race | 11 of 39 (1.2), 18 of 48 (1.5) | 17 of 47 (1.5), 18 of 54 (1.7) |
| City Trial | 8 of 23 (0.7), 7 of 21 (0.7) | 9 of 27 (0.8), 14 of 32 (1.0) |
| City Trial, four players | 7 of 32 (1.0), 10 of 39 (1.2) | 6 of 39 (1.2), 10 of 46 (1.4) |

| Clipped runs (samples) | Mixer, baseline | Mixer, current | Device, baseline | Device, current |
|---|---|---|---|---|
| Title | 355 (4,009), 59 (485) | 0 (0), 4 (14) | 325 (5,379), 52 (626) | 0 (0), 4 (16) |
| Mode select | 0 (0), 0 (0) | 0 (0), 0 (0) | 0 (0), 0 (0) | 0 (0), 0 (0) |
| Air Ride race | 160 (1,840), 142 (1,662) | 34 (378), 27 (401) | 140 (2,482), 132 (2,272) | 27 (510), 23 (557) |
| City Trial | 0 (0), 0 (0) | 0 (0), 0 (0) | 0 (0), 0 (0) | 0 (0), 0 (0) |
| City Trial, four players | 10 (93), 6 (59) | 0 (0), 0 (0) | 10 (123), 6 (79) | 0 (0), 0 (0) |

| Level | Highest main L peak, baseline | Highest main L peak, current | Samples the clamp changed, current |
|---|---|---|---|
| Title | 69,288, 55,039 | 33,047, 36,320 | 3, 21 |
| Mode select | 17,628, 17,628 | 15,832, 32,768 | 0, 4 |
| Air Ride race | 82,740, 86,191 | 66,056, 63,229 | 627, 632 |
| City Trial | 27,116, 28,540 | 31,781, 30,571 | 3, 0 |
| City Trial, four players | 45,935, 42,418 | 29,234, 28,982 | 0, 0 |

| Gaps and seconds | Mixer gaps, baseline | Mixer gaps, current | Device gaps, baseline | Device gaps, current | Device seconds, baseline | Device seconds, current |
|---|---|---|---|---|---|---|
| Title | 0, 0 | 1, 1 | 0, 0 | 1, 1 | 28.37, 28.33 | 30.69, 30.72 |
| Mode select | 0, 0 | 2, 1 | 0, 0 | 2, 1 | 31.97, 31.98 | 34.72, 34.71 |
| Air Ride race | 1, 1 | 2, 3 | 0, 1 | 2, 3 | 105.17, 105.49 | 114.72, 114.72 |
| City Trial | 1, 1 | 2, 2 | 1, 1 | 2, 2 | 64.18, 64.15 | 69.73, 69.72 |
| City Trial, four players | 1, 2 | 2, 2 | 1, 2 | 2, 2 | 66.75, 66.85 | 72.75, 72.69 |

Neither build had an underrun in any run, and current made no ring cut in any run.

## The title route at 91 s

`status.md`'s source type 2 counts come from 90-second title runs, and the five-route pass
plays the title for 31 s. `--routes title --margin 75` plays the same route for 91 s. It ran twice on each
build, with the tool at `13acaf4`. The second pass printed `13acaf4-dirty`, because
`docs/dev/audio.md` had been edited after the first pass and wasn't committed until this doc.
No file under `tools/` differs between `13acaf4` and that commit, and rescoring the second
pass's recordings from a clean tree gives the same numbers.

| Title route, 91 s | Baseline | Current |
|---|---|---|
| Mixer seconds | 90.21, 90.18 | 90.21, 90.21 |
| Mixer clicks | 1,097, 979 | 22, 22 |
| Mixer clicks a minute | 729.6, 651.4 | 14.6, 14.6 |
| Mixer clicks within 2 samples of a block join (by chance) | 662 (34.3), 589 (30.6) | 8 (0.7), 8 (0.7) |
| Mixer gaps | 0, 0 | 1, 1 |
| Mixer clipped runs (samples) | 58 (453), 57 (506) | 3 (15), 2 (6) |
| Device seconds | 83.45, 83.30 | 90.74, 90.73 |
| Device clicks | 1,421, 1,216 | 26, 24 |
| Device clicks a minute | 1,021.7, 875.9 | 17.2, 15.9 |
| Device gaps | 0, 0 | 1, 1 |
| Device clipped runs (samples) | 48 (580), 48 (658) | 3 (18), 2 (6) |
| Ring cuts | Not logged | 0, 0 |
| Ring underruns | 0, 0 | 0, 0 |
| Highest main L peak before the clamp | 51,738, 57,485 | 33,845, 34,590 |
| Samples the clamp changed | Not logged | 16, 20 |

The clicks come after the five-route run's 31 s. In the baseline's second run, 970 of the 979 came
later than that, the first of them at 41.71 s. 586 of those 970 fell on a block join, where
chance gives 30.3. In current's second run, 10 of its 22 came after 31 s.

## What got worse, and what moved

The mixer stage clicks more often in current, on every route in both passes. Its gaps went from
3 and 4 to 9 and 9, and its clicks on a block join from 35 and 42 to 43 and 52, where chance gives
3.7 to 5.0. Many clicks come at the same times in both builds. In the second pass's race runs both
have three within 15 ms of 2.33 s, where the route's first A press plays. Both have a run between
57.98 s and 59.74 s, 13 in the baseline and 14 in current. Current also has a group of three at
22.55 s and another at 27.57 s, the same sizes as the A press's, which the baseline doesn't. Why
current has more wasn't looked into.

The passes move. The baseline's title route clipped 4,009 samples in the mixer stage in one pass
and 485 in the other, and its race made 128 device clicks in one and 89 in the other. A
`--real-time` run's clock jumps to catch up wherever the host falls behind (gcn-recomp
`docs/diagnostics.md`, The clock), so two runs of a route needn't make the same sound. Every
click, gap, clipping and peak total moved the same way from baseline to current in both passes.

## What the numbers don't show

- The baseline's device stage is what SDL's dummy driver took, not what a sound card would. Over
  the five routes it took 296.45 s and 296.80 s of sound while the DMA delivered 319.78 s and
  319.87 s, 92.7% and 92.8%. It had no underruns. It doesn't log its ring's cuts, so its log
  doesn't say where the rest went. Its device stage had 167 and 93 more clicks than its mixer
  stage. Current's had 54 and 17 more, with no cuts.
- Current's device stage is 2.73 s and 2.69 s longer than its mixer stage over the five routes.
  That includes the silence the device plays from when it opens until the ring first holds its
  cushion.
- A click here is any sharp edge, the game's own sounds included. The counts say where to look,
  not what a listener hears.
- `audio_clicks.py` counts a clipped run at 32,767 or -32,768. The mixer's clamp stops at
  -32,767, so the mixer stage's negative clipping isn't in its clipped runs. The device stage
  plays those samples through the ring, which never makes one larger, so its clipped runs miss
  negative clipping too. Only the music mix clamps at -32,768. The clamp count from `[ax] bus`
  has both signs.
- Underruns are as of each run's last `[ring] fill` line, which comes every 400 pulls of the
  device.
- Nobody listened to any of it, and nothing was compared with a real console. One machine, an
  M4 Max on macOS 26.6.2 with Python 3.14.7.

## Running it again

The baseline is a second clone at Dragoon `6b81b6e`, whose gcn-recomp is `caf12a2`, built
the same way as current.

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk -DDRAGOON_WARMUP=OFF
ninja -C build
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --routes title --margin 75
```

A later engine goes in a clone of its own and gets a label of its own, as in
`next=/path/to/that/build`. The tool reads each clone's Dragoon and gcn-recomp commits before
the first route plays, prints them and leaves them in each run's `commits.json`, which
`--no-run` reads back. The recordings stay in each clone's `build/probe/scorecard-ROUTE/` and
are never committed.

| | Commit |
|---|---|
| Baseline Dragoon | `6b81b6e` |
| Baseline gcn-recomp | `caf12a2`, upstream `9b0a2fe` plus 13 |
| Current Dragoon | `788571c` |
| Current gcn-recomp | `b848158` |
| The tool, five routes | `43ceba4` |
| The tool, title at 91 s | `13acaf4`, then `13acaf4-dirty` |
