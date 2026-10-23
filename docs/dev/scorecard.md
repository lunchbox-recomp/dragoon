# Audio scorecard

What gcn-recomp's audio work changed, measured by program with nobody listening.
`tools/audio_scorecard.py --routes title,menu,air-ride-race,city-trial,city-trial-4p` plays
five routes and counts clicks, gaps and clipping before the audio ring and after it. The
baseline is gcn-recomp `caf12a2`, with none of the audio work. Current is gcn-recomp `b848158`.

The tool scores the two stages from different runs. The mixer stage, every block the DMA
delivered, comes from an unpaced run, whose game time doesn't wait on the host. Each pair of
unpaced runs compared so far gave the same samples, as How it was measured says. The device
stage, what the ring handed the device, comes from a real-time run, since the ring's pace is
part of what it measures. Passes 1 and 2 on 2026-10-22 scored both stages from real-time runs
of both builds. Pass 3, the same day, scored current the new way. Pass 4, on 2026-10-23,
scored the baseline the new way.

Unpaced, over the same five routes and 324 s in all, the mixer stage made 132 clicks (24.4 a
minute) at the baseline in pass 4 and 136 (25.2) at current in pass 3. The audio work didn't
reduce the mixer stage's clicks over those seconds. What it cut was clipping. The clipped runs
fell from 208 (2,200 samples) to 25 (371), the highest main L peak before the clamp fell from
85,094 to 64,999, and the gaps rose from 3 to 8. A bisect on 2026-10-22 ran both builds
unpaced at passes 1 and 2's lengths, 319.8 s in all. It agrees. It counted 131 clicks (24.6 a
minute) at `caf12a2` and 135 (25.3) at `b848158`, while the clipped runs fell from 203 to 25 and
the gaps rose from 3 to 8.

The seconds scored end at each route's last checkpoint plus 15 s, and the unpaced recordings go
on past them. The clicks did fall there. Scored again with `--no-run` and a longer `--margin`
(the commands are under Running it again), the title's first 91 s have 1,085 clicks at the
baseline and 19 at current, against 9 and 10 in the first 31 s. The mode select's first 170 s
have 118 clicks and 16, with the clipped runs falling from 230 to 6, against 13 and 14 clicks in
the first 35 s. So the clicks that fell are past the seconds the totals score. Four players was
scored only to its own 73 s, where it has 43 and 44, so nothing was scored past its cut. The
race and City Trial weren't scored past their cuts either. The title played to 91 s in real time
shows the same fall (below).

Across the five routes the device stage's clicks a minute fell from 57.9 to 36.3 in pass 1 and
from 45.1 to 33.1 in pass 2, and pass 3 gave current 32.2. Passes 1 and 2 had the mixer stage's
clicks a minute rising from 22.3 to 26.4 and from 24.4 to 30.2. The bisect found that most of
that rise came from playing in real time.

## Where the numbers come from

| Source | Builds | Runs | Tool |
|---|---|---|---|
| Passes 1 and 2 | Baseline and current | Five routes, real-time | `43ceba4` |
| The title at 91 s, two passes | Baseline and current | The title, real-time | `13acaf4` |
| A bisect on 2026-10-22 | `caf12a2`, `b848158` and six audio commits between | Five routes unpaced at passes 1 and 2's lengths, and three more real-time menu runs a build | Prototypes |
| Pass 3 | Current | Five routes, real-time and unpaced | `5ff734e` |
| Pass 4 | Baseline | Five routes, real-time and unpaced | `3698f16` |
| Past the cut | Baseline and current | Pass 4's and pass 3's unpaced recordings, rescored with `--no-run` | `8aaae9a` |

All but pass 4 ran on 2026-10-22. The rescoring plays no game and was done on 2026-10-23. The
bisect's notes aren't in this repository, so its numbers are quoted below and named as its own.
`tools/block_clicks.py`, `click_diff.py` and `noise_blocks.py` are its prototypes made into
tools, and pass 3's checks below use them.

Pass 4 ran on 2026-10-23 at Dragoon `6b81b6e` and gcn-recomp `caf12a2`, with the tool at
`3698f16`. That tool scores the same as `5ff734e`. It takes the 32 kHz rate and the 160-sample
block from `aid_blocks.py` at the same values, and one docstring differs. The baseline binary
was the clone's existing build at that commit, and `ninja` had nothing to rebuild. Pass 4's
real-time device stage isn't tabulated here.

Each run's `commits.json` recorded the clone it played. Passes 1 and 2 recorded `43ceba4`,
which is `788571c` plus `tools/`. Pass 3 recorded `e9d2928`, which is `788571c` plus `tools/`
and `docs/`. Pass 3 ran at `e9d2928`, before the branch was moved onto `57b9948`. The moved
branch holds `5ff734e` in its place. The `tools/` of the two differ only in `tools/README.md`,
so pass 3 ran the code that `5ff734e` holds.

## The two builds

| | Baseline | Current |
|---|---|---|
| Dragoon | `6b81b6e` | `788571c` in passes 1 and 2, `5ff734e` in pass 3 |
| gcn-recomp | `caf12a2` | `b848158` |
| PB mixer control word | 2001 layout | Later layout for this game's ucode (`07F88145`) |
| Compressor, command `12` | Skipped | Runs |
| Source type 2 voices | Stepped through by the rate ratio | One sample in for each sample out |
| Ring cuts and dropouts | Step | Fade |
| Pace under SDL's dummy driver | The driver's own | The runtime pulls the sound on 48 kHz deadlines |
| `[ring]` lines | Underruns | Underruns, cuts and each cut's output frame |
| `[ax] bus` lines, with the samples the clamp changed | None | Every 400 lists |

Pass 3's build differed from `788571c` only in `tools/` and `docs/`, so all three passes
played the same game code. `5ff734e` itself differs from `788571c` in more places. It adds
seven course routes with their hashes and changes text in `README.md` and a message in
`CMakeLists.txt`. None of it touches the game code.

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

Passes 1 and 2 were each one run of the tool from this clone, with the baseline clone's build
directory as `base`. Pass 3 played current alone, because the baseline clone had moved on to
other commits. Pass 4 played the baseline alone, with the second command below and `base=` in
place of `current=`.

```sh
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --json \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p
tools/audio_scorecard.py current=build --json \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p
```

The tool plays a route on each build in turn, then moves to the next route. Each run goes
through its own clone's `tools/probe.sh` in a hidden window with SDL's dummy audio driver and
`GCN_AXSTATS=1`, and every build plays this clone's route files. A run lasts the route's last
checkpoint at 60 frames a second plus 15 s. That's 31 s for the title, 35 s for mode select,
115 s for the race, 70 s for City Trial and 73 s for four players. Every run starts from a blank
memory card and an empty shader cache, and every run reached its last checkpoint.

In passes 1 and 2 the tool played each route once a build with `--real-time` and scored both
stages from that run. A pass took 675 s the first time and 674 s the second. Since `5ff734e` it
plays each route twice a build. The first run is real-time as before. The second is unpaced
and records only the mixer stage, for the same wall seconds. An unpaced run gets well ahead of
the route in that time, and in pass 3 each one recorded 4.8 to 15.9 times its route's seconds.
The tool cuts the recording to the route's seconds and refuses one that falls short. Pass 3
took about 11.5 minutes.

The mixer stage is `GCN_AIDWAV`, every block the DMA delivered before the ring, at 32 kHz.
The device stage is `GCN_WAV`, what went to the device at 48 kHz, ring included. The tool
scores both with `audio_clicks.py`'s functions, as `tools/README.md` describes. A click is a
sample whose second difference is over 8 times the RMS second difference of the 5 ms either
side, and at least 128. A gap is 5 ms or more of digital silence on every channel straight
after sound. A clipped run is two or more samples at 32,767 or -32,768 on one channel.

A `--real-time` run's clock jumps to catch up wherever the host falls behind (gcn-recomp
`docs/diagnostics.md`, The clock). While it catches up, the DMA plays some blocks twice and
presses can land after dropped frames, as the bisect found, so two real-time runs of a route
needn't make the same sound. An unpaced run's guest clock doesn't wait on the host. The bisect
found two unpaced title runs at `caf12a2` gave identical recordings over 120 s. In pass 3,
`click_diff.py` found current's five unpaced recordings the same as the bisect's `b848158`
ones, sample for sample, over 1,250 s in all.

The log gives the rest. The highest main L magnitude before the output clamp comes from
`[ax] frames` lines and the L and R samples the clamp changed from `[ax] bus` lines, both from
the unpaced run and within its cut. The ring's cuts and underruns come from the real-time run's
`[ring]` lines. The baseline prints `[ax] frames` lines but no `[ax] bus` lines. Its `[ring]`
lines carry underruns but no cuts, so the baseline's cuts aren't counted anywhere below.

## The mixer stage, unpaced

Pass 4 played the baseline and pass 3 played current, each cut to the same seconds on the
same five routes. Clicks a minute is over the summed seconds.

| Five routes, unpaced | Baseline, pass 4 | Current, pass 3 |
|---|---|---|
| Mixer seconds | 324.00 | 324.00 |
| Mixer clicks | 132 | 136 |
| Mixer clicks a minute | 24.4 | 25.2 |
| Mixer clicks within 2 samples of a block join (by chance) | 35 (4.1) | 35 (4.2) |
| Mixer gaps | 3 | 8 |
| Mixer clipped runs (samples) | 208 (2,200) | 25 (371) |
| Highest main L peak before the clamp | 85,094 | 64,999 |
| Samples the clamp changed | Not logged | 587 |

The audio work didn't reduce the mixer stage's clicks over these seconds. The totals are 132
and 136, no route differs by more than one click and the race has 45 in both. The clicks on a
block join are 35 in both, against about 4 by chance. What the work cut was clipping. The
clipped runs, as `audio_clicks.py` counts them, fell from 208 to 25 and the race peak from
85,094 to 64,999. Three routes clipped at the baseline, the title with 48 runs, the race with
150 and four players with 10. At current they have 0, 25 and 0, so the race is the only one
still clipping. Every route gained exactly one gap, 3 to 8 in all. The baseline prints no
`[ax] bus` lines, so it has no clamp count to compare. Each build is one unpaced run, and the
baseline's wasn't compared with a second one.

| Pass 4, unpaced | Clicks (a minute) | On a block join (by chance) | Gaps | Clipped runs (samples) | Main L peak | Clamped samples |
|---|---|---|---|---|---|---|
| Title, 31 s | 9 (17.4) | 3 (0.3) | 0 | 48 (369) | 52,116 | Not logged |
| Mode select, 35 s | 13 (22.3) | 4 (0.4) | 0 | 0 (0) | 17,628 | Not logged |
| Air Ride race, 115 s | 45 (23.5) | 13 (1.4) | 1 | 150 (1,738) | 85,094 | Not logged |
| City Trial, 70 s | 22 (18.9) | 7 (0.7) | 1 | 0 (0) | 27,793 | Not logged |
| City Trial, four players, 73 s | 43 (35.3) | 8 (1.3) | 1 | 10 (93) | 45,935 | Not logged |

| Pass 3, unpaced | Clicks (a minute) | On a block join (by chance) | Gaps | Clipped runs (samples) | Main L peak | Clamped samples |
|---|---|---|---|---|---|---|
| Title, 31 s | 10 (19.4) | 3 (0.3) | 1 | 0 (0) | 33,741 | 2 |
| Mode select, 35 s | 14 (24.0) | 4 (0.4) | 1 | 0 (0) | 17,628 | 0 |
| Air Ride race, 115 s | 45 (23.5) | 13 (1.4) | 2 | 25 (371) | 64,999 | 585 |
| City Trial, 70 s | 23 (19.7) | 7 (0.7) | 2 | 0 (0) | 26,762 | 0 |
| City Trial, four players, 73 s | 44 (36.2) | 8 (1.4) | 2 | 0 (0) | 28,982 | 0 |

The bisect's unpaced runs, at passes 1 and 2's lengths, 319.8 s in all. Its first row and its
`b839cf6`, `b848158` row are close to passes 4 and 3, which are cut at the routes' own seconds,
so they corroborate those runs. The last column says how each build's mix compared with the row
above it.

| gcn-recomp | Clicks (a minute) | On joins | Gaps | Clipped runs | Mix |
|---|---|---|---|---|---|
| `caf12a2` | 131 (24.6) | 34 | 3 | 203 | |
| `8fabc65`, `6616d55` | 131 (24.6) | 34 | 3 | 203 | Identical |
| `3bde515` (layouts) | 130 (24.4) | 34 | 3 | 211 | Changed |
| `bf31b7b` (compressor) | 130 (24.4) | 34 | 3 | 25 | Changed |
| `fd1f6a8` (source type 2) | 135 (25.3) | 34 | 8 | 25 | Changed |
| `b839cf6`, `b848158` | 135 (25.3) | 34 | 8 | 25 | Same as `fd1f6a8` |
| `b848158`, `GCN_AX_LAYOUT=2001` | 136 (25.5) | 34 | 8 | 29 | |

Pass 3 agrees with the bisect. Cut to 30.176, 34.176, 114.08, 69.184 and 72.16 s, current's
unpaced recordings have 10, 14, 45, 23 and 43 clicks, 135 in all. At the routes' own seconds
four players has 44, which makes pass 3's 136.

The bisect traced what the work changed in the mixer stage.

- The compressor, `bf31b7b`, took the clipped runs from 211 to 25.
- `fd1f6a8` adds 5 clicks and 5 gaps, all in the intro stream. The work nets 4 clicks, since
  `3bde515` took one away. From 6.3 s to 15.74 s two type 2 voices play a stereo stream that
  was digital silence before `fd1f6a8`. Its click at 10.139 s is in the music itself, not on a
  join. Its gap at 15.740 s is the game stopping the stream at the frame 900 press, which
  steps straight to zero.
- The game's AX library depops stopped voices. `fn_803EDBA4`, called from `SortVoices`, sums PB
  words 41 to 49 into nine accumulators that the setup command fades out. `b848158` never
  writes those words. gcn-recomp `e6ce0a5` (PR #11) does, and its author found that no hash
  moved, because in stereo mode command `07` replaces the main buses after setup, as the fork
  has it. So the stop still steps to zero. Whether the console's `07` replaces the buses or
  adds to them is open.

## Why the real-time mixer clicks rose

Passes 1 and 2 scored the mixer stage from their real-time runs.

| Five routes, real-time mixer stage | Baseline, pass 1 | Baseline, pass 2 | Current, pass 1 | Current, pass 2 |
|---|---|---|---|---|
| Mixer seconds | 319.78 | 319.87 | 319.87 | 319.87 |
| Mixer clicks | 119 | 130 | 141 | 161 |
| Mixer clicks a minute | 22.3 | 24.4 | 26.4 | 30.2 |
| Mixer clicks within 2 samples of a block join (by chance) | 35 (3.7) | 42 (4.1) | 43 (4.4) | 52 (5.0) |
| Mixer gaps | 3 | 4 | 9 | 9 |
| Mixer clipped runs (samples) | 525 (5,942) | 207 (2,206) | 34 (378) | 31 (415) |
| Highest main L peak before the clamp | 82,740 | 86,191 | 66,056 | 63,229 |
| Samples the clamp changed | Not logged | Not logged | 633 | 657 |

| Real-time mixer clicks a minute, pass 1, then pass 2 | Baseline | Current |
|---|---|---|
| Title | 20.0, 17.9 | 23.9, 23.9 |
| Mode select | 26.3, 22.8 | 28.1, 29.8 |
| Air Ride race | 20.5, 25.2 | 24.7, 28.4 |
| City Trial | 19.9, 18.2 | 23.4, 27.8 |
| City Trial, four players | 26.6, 32.4 | 32.4, 38.2 |

Current clicked more on every route in both passes. Unpaced, the bisect found the work took
the clicks only from 131 to 135, and passes 4 and 3 found them go from 132 to 136. The bisect
found current's real-time runs made 26 more clicks than its unpaced ones while the baseline's
made one fewer, which matches pass 2's 161 and 130 against 135 and 131. It put the 26 down to
four things.

- 7 clicks (2 in the baseline), all on joins, sit on blocks the DMA played twice while the clock
  caught up. The code that replays them is unchanged since upstream. Three more real-time menu
  runs a build had 2, 0 and 6 such clicks in current against 0, 0 and 6 in the baseline.
- 6 clicks are two extra menu confirms, from presses landing after dropped frames.
- In one real-time menu run the music became full-scale noise, independent on each channel,
  from 17.59 s to the end. That's pass 2's mode select peak of 32,768. It didn't come back in 3
  more runs a build.
- The rest are the game's own sounds shifted in time.

Pass 3 checked this with the new tools. Its real-time recordings of the mixer stage have 158
clicks over 319.81 s, where its unpaced ones have 135 over the bisect's 319.78 s. Of those 158,
`block_clicks.py` puts 17 on the 27 blocks the DMA replayed, where chance gives 0.1. Each of
them sits at one of its block's joins. It puts 17 on the 308 blocks played while the clock
caught up, where chance gives 0.9, though some of those are the game's own, such as the clicks
at about 2.33 s that the unpaced runs have too. 21 clicks sit on blocks of either kind, since
some blocks are both. The unpaced runs replay no block and catch none up. On the bisect's three
real-time menu runs of current, `block_clicks.py` counts 2, 0 and 6 clicks on replays, as the
bisect did.

`noise_blocks.py` finds 44 noise-like blocks in pass 3's real-time recordings of the mixer
stage, in stretches of one block up to 18 (the race from 71.340 s to 71.605 s). The unpaced runs
have them too. In the race's first 115 s the unpaced run has 49 in 11 stretches, the longest from
71.285 s to 71.615 s. In mode select's first 35 s it has 4 single blocks, the first at 18.175 s,
where the real-time run has its one at 18.200 s. So short stretches like these come with the
game's own sounds, and pass 3 had no stretch like the bisect's full-scale noise.

## The device stage, real-time

All five routes together. Clicks a minute is over the summed seconds.

| Five routes, real-time | Baseline, pass 1 | Baseline, pass 2 | Current, pass 1 | Current, pass 2 | Current, pass 3 |
|---|---|---|---|---|---|
| Device seconds | 296.45 | 296.80 | 322.60 | 322.56 | 322.58 |
| Device clicks | 286 | 223 | 195 | 178 | 173 |
| Device clicks a minute | 57.9 | 45.1 | 36.3 | 33.1 | 32.2 |
| Device gaps | 2 | 4 | 9 | 9 | 11 |
| Device clipped runs (samples) | 475 (7,984) | 190 (2,977) | 27 (510) | 27 (573) | 14 (454) |
| Ring cuts | Not logged | Not logged | 0 | 0 | 0 |
| Ring underruns | 0 | 0 | 0 | 0 | 0 |

Each baseline cell is pass 1, then pass 2. Each current cell is passes 1, 2 and 3 in order.

| Device clicks a minute | Baseline | Current |
|---|---|---|
| Title | 23.3, 14.8 | 21.5, 19.5, 15.6 |
| Mode select | 46.9, 43.2 | 27.6, 19.0, 24.2 |
| Air Ride race | 73.0, 50.6 | 40.3, 32.4, 37.1 |
| City Trial | 53.3, 46.8 | 29.3, 35.3, 20.7 |
| City Trial, four players | 58.4, 48.5 | 47.0, 44.6, 46.2 |

| Device clipped runs (samples) | Baseline | Current |
|---|---|---|
| Title | 325 (5,379), 52 (626) | 0 (0), 4 (16), 0 (0) |
| Mode select | 0 (0), 0 (0) | 0 (0), 0 (0), 0 (0) |
| Air Ride race | 140 (2,482), 132 (2,272) | 27 (510), 23 (557), 14 (454) |
| City Trial | 0 (0), 0 (0) | 0 (0), 0 (0), 0 (0) |
| City Trial, four players | 10 (123), 6 (79) | 0 (0), 0 (0), 0 (0) |

| Device gaps and seconds | Gaps, baseline | Gaps, current | Seconds, baseline | Seconds, current |
|---|---|---|---|---|
| Title | 0, 0 | 1, 1, 1 | 28.37, 28.33 | 30.69, 30.72, 30.68 |
| Mode select | 0, 0 | 2, 1, 2 | 31.97, 31.98 | 34.72, 34.71, 34.73 |
| Air Ride race | 0, 1 | 2, 3, 2 | 105.17, 105.49 | 114.72, 114.72, 114.72 |
| City Trial | 1, 1 | 2, 2, 3 | 64.18, 64.15 | 69.73, 69.72, 69.71 |
| City Trial, four players | 1, 2 | 2, 2, 3 | 66.75, 66.85 | 72.75, 72.69, 72.75 |

Neither build had an underrun in any run, and current made no ring cut in any run.

## The title route at 91 s

`status.md`'s source type 2 counts come from 90-second title runs, and the five-route pass
plays the title for 31 s. `--routes title --margin 75` plays the same route for 91 s. It ran
twice on each build, with the tool at `13acaf4`, before the tool scored the mixer stage
unpaced, so both stages here are real-time. The second pass printed `13acaf4-dirty`, because
`docs/dev/audio.md` had been edited after the first pass and wasn't committed until `9d87d96`,
the commit that added this doc. No file under `tools/` differs between `13acaf4` and
`9d87d96`, and rescoring the second pass's recordings from a clean tree gives the same
numbers.

| Title route, 91 s, real-time | Baseline | Current |
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

## What the numbers don't show

- The mixer stage's before and after is one unpaced run of each build, pass 4 and pass 3, made
  a day apart. Pass 4's tool was at `3698f16` and pass 3's at `5ff734e`, which score the same.
  The bisect, cut at passes 1 and 2's lengths rather than the routes' seconds, agrees with
  both, but its notes aren't in this repository.
- Real-time runs move from pass to pass. The baseline's title route clipped 4,009 samples in the
  mixer stage in one pass and 485 in the other. Current's City Trial made 29.3, 35.3 and 20.7
  device clicks a minute in passes 1 to 3. Every device stage total moved the same way from
  baseline to current in passes 1 and 2.
- Pass 3's real-time runs overlapped a run of the tools' test suite on the same host, and a
  loaded host is what makes the clock catch up. Its 27 replayed blocks, 308 caught-up blocks,
  158 mixer clicks and 32.2 device clicks a minute weren't measured on a quiet host. That the 17
  clicks on replayed blocks all sit at a block's joins doesn't depend on how many were replayed.
- An unpaced run has no catch-up and no late presses. The mixer stage scores the engine, not
  what a player hears on a host that falls behind. The device stage still has both.
- The baseline's device stage is what SDL's dummy driver took, not what a sound card would. Over
  the five routes it took 296.45 s and 296.80 s of sound while the DMA delivered 319.78 s and
  319.87 s, 92.7% and 92.8%. It had no underruns. It doesn't log its ring's cuts, so its log
  doesn't say where the rest went. In passes 1 and 2 its device stage had 167 and 93 more clicks
  than its real-time mixer stage. Current's had 54 and 17 more, with no cuts.
- A device stage's seconds include the silence the device plays from when it opens until the
  ring first holds its cushion.
- The peak and the clamp count come from `[ax]` lines, which come every 400 command lists, 2 s
  of sound. Up to the last 2 s before the cut isn't in them.
- A click here is any sharp edge, the game's own sounds included. The counts say where to look,
  not what a listener hears.
- `audio_clicks.py` counts a clipped run at 32,767 or -32,768. The mixer's clamp stops at
  -32,767, so the mixer stage's negative clipping isn't in its clipped runs. The device stage
  plays those samples through the ring, which never makes one larger, so the mixer's negative
  clipping isn't in the device stage's clipped runs either. The music stream is added after the
  ring and clamps at -32,768, so clipping there does show in the device stage. The clamp count
  from `[ax] bus` has both signs and counts the mixer only.
- Underruns are as of each run's last `[ring] fill` line, which comes every 400 pulls of the
  device.
- Nobody listened to any of it, and nothing was compared with a real console. One machine, an
  M4 Max on macOS 26.6.2 with Python 3.14.7.

## Running it again

The baseline is a second clone at Dragoon `6b81b6e`, whose gcn-recomp is `caf12a2`, built
the same way as current. Pass 4 used that clone's existing build at that commit.

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk -DDRAGOON_WARMUP=OFF
ninja -C build
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --routes title --margin 75
```

The numbers past the cut in the summary come from these two commands, run on the unpaced
recordings of pass 4 and pass 3. They play no game.

```sh
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --routes title --margin 75 --no-run
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --routes menu --margin 150 --no-run
```

With `--no-run` the margin picks how much of each unpaced recording the mixer stage scores. That's
91 s for the title and 170 s for the mode select. Read the mixer rows.
The device rows come from the real-time run, which the margin doesn't cut. A margin that
reaches past a recording exits 2. At `--routes title --margin 400` the tool said the baseline's
recording held 203.01 s, short of the 416 s asked for.

A later engine goes in a clone of its own and gets a label of its own, as in
`next=/path/to/that/build`. The tool reads each clone's Dragoon and gcn-recomp commits before
the first route plays, prints them and leaves them in each run's `commits.json`, which
`--no-run` reads back. The recordings stay in each clone's `build/probe/scorecard-ROUTE/` for
the real-time run and `build/probe/scorecard-unpaced-ROUTE/` for the unpaced one, and are never
committed. With `--no-run`, a build with no unpaced run shows its mixer stage as not recorded.

| | Commit |
|---|---|
| Baseline Dragoon | `6b81b6e` |
| Baseline gcn-recomp | `caf12a2`, upstream `9b0a2fe` plus 13 |
| Current Dragoon | `788571c` in passes 1 and 2, `5ff734e` in pass 3 |
| Current gcn-recomp | `b848158` |
| The tool, passes 1 and 2 | `43ceba4` |
| The tool, title at 91 s | `13acaf4`, then `13acaf4-dirty` |
| The tool, pass 3 | `5ff734e` |
| The tool, pass 4 | `3698f16` |
| The tool, past the cut | `8aaae9a` |
