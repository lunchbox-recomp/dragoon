# Audio scorecard

`tools/audio_scorecard.py --routes title,menu,air-ride-race,city-trial,city-trial-4p` plays
five routes and scores their sound before the audio ring and after it, with nobody listening.
The baseline is gcn-recomp `caf12a2`, with none of the audio work. Passes 1 to 5 call `b848158`
current and `b97c019` next, and pass 6 names `3a8d154` and `dac449e` by commit.

The newest numbers are pass 6's at `dac449e`. The pin is `782d7fa`, and on the way `bad7160`
and `b5ec329` changed every route's audio hashes (Dragoon `3243778` and `fd439aa`), so no
number here is the pin's.

The mixer stage, every block the DMA delivered, is scored from an unpaced run, whose game time
doesn't wait on the host. The device stage, what the ring handed the device, is scored from a
real-time run, since the ring's pace is part of what it measures. Passes 1 and 2 scored both
stages from real-time runs, and the later passes scored them this way.

| Five routes | `caf12a2` | `b848158` | `b97c019` | `3a8d154` | `dac449e` |
|---|---|---|---|---|---|
| Pass | 4 | 3 | 5 | 6 | 6 |
| Mixer clicks (a minute) | 132 (24.4) | 136 (25.2) | 94 (17.4) | 94 (17.4) | 94 (17.4) |
| On a block join (by chance) | 35 (4.1) | 35 (4.2) | 7 (2.9) | 7 (2.9) | 7 (2.9) |
| Mixer gaps | 3 | 8 | 8 | 8 | 8 |
| Mixer clipped runs (samples) | 208 (2,200) | 25 (371) | 28 (564) | 28 (564) | 28 (564) |
| Device clicks a minute, real-time | 57.9, 45.1 | 36.3, 33.1, 32.2, 35.5 | 13.0 | 13.6 to 17.7 | 11.6 to 14.9 |

The device row is passes 1 and 2 for `caf12a2` and passes 1, 2, 3 and 5 for `b848158`.
Pass 6's device cells span its four plays. `b97c019`'s clipped runs include negative clipping
that `b848158`'s clamp at -32,767 kept out of the count (Pass 5).

Up to `b848158` the audio work cut clipping but not clicks in the scored seconds. Past them, in
the same unpaced recordings rescored with `--no-run`, the title's first 91 s went from 1,085
clicks to 19 and the mode select's first 170 s from 118 to 16. `b97c019` took the clicks on
block joins from 35 to 7, and between `3a8d154` and `dac449e` the real-time blocks delivered
while the clock caught up fell from 247 to 255 a play to 51 to 67.

## The audio work, `caf12a2..b848158`

`caf12a2` is upstream `9b0a2fe` plus 13 commits. Two are runtime fixes and two are tooling,
and the other nine bring in controllers and SDL3. Of the audio files only
`runtime/audio_sdl.cpp` changed, when `d9ee73d` moved it onto SDL3's audio stream.

The audio work is the commits below. The others in `caf12a2..b848158` are gamepad ports and
line wrapping.

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

Passes 1 and 2 each played both builds in one run of the tool. Pass 3 played current alone and
pass 4 the baseline alone, and the tool's method is under `audio_scorecard.py` in
`tools/README.md`.

A run lasts the route's last checkpoint at 60 frames a second plus 15 s, which is 31 s for the
title, 35 s for mode select, 115 s for the race, 70 s for City Trial and 73 s for four players.
Every run reached its last checkpoint, and pass 3's unpaced runs recorded 4.8 to 15.9 times
their routes' seconds. Passes 1 and 2 took 675 s and 674 s and pass 3 about 11.5 minutes.

A `--real-time` run's clock jumps to catch up wherever the host falls behind (gcn-recomp
`docs/diagnostics.md`, The clock) and presses can land after dropped frames, so two real-time
runs of a route needn't make the same sound. Up to `b848158` the DMA also played some blocks
twice while the clock caught up, and from `b97c019` on, with `a87ab06`, none of the runs here
has a replayed block (`audio.md`, What was done and what is left). The bisect found two
unpaced title runs at `caf12a2` identical over 120 s, and in pass 3 `click_diff.py` found
current's five unpaced recordings the same as the bisect's `b848158` ones over 1,250 s.

The baseline prints `[ax] frames` lines but no `[ax] bus` lines, and its `[ring]` lines carry
underruns but no cuts. So its clamp counts and cuts read Not logged.

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

No route differs by more than one click, and both builds have 35 on a block join. The race's
clipped runs fell from 150 to 25, and the title's 48 and four players' 10 fell to none. Every
route gained one gap.

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

The bisect ran unpaced at passes 1 and 2's lengths, 319.8 s in all. Its Mix column compares
each build's mix with the row above's.

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
- `fd1f6a8` adds 5 clicks and 5 gaps, all in the intro stream. From 6.3 s to 15.74 s two type
  2 voices play a stereo stream that was digital silence before `fd1f6a8`.

  Its click at 10.139 s is in the music itself, not on a join. Its gap at 15.740 s is the game
  stopping the stream at the frame 900 press, which steps straight to zero.
- Stopping a voice still steps to zero on the main buses. The game's AX library fades a
  stopped voice through the PB's depop words 41 to 49 (`fn_803EDBA4`, called from
  `SortVoices`), which `b848158` never writes and gcn-recomp `3b025ac`, in `b97c019`, does. No
  audio hash moved, because in stereo mode command `07` replaces the main buses after setup,
  though whether the console's `07` replaces them or adds to them is open.

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
the clicks only from 131 to 135, and passes 4 and 3 found them go from 132 to 136.

The bisect found current's real-time runs made 26 more clicks than its unpaced ones while the
baseline's made one fewer, which matches pass 2's 161 and 130 against 135 and 131. It put the
26 down to four things.

- 7 clicks (2 in the baseline), all on joins, sit on blocks the DMA played twice while the clock
  caught up. The code that replays them is unchanged since upstream. Three more real-time menu
  runs a build had 2, 0 and 6 such clicks in current against 0, 0 and 6 in the baseline.
- 6 clicks are two extra menu confirms, from presses landing after dropped frames.
- In pass 2's real-time mode select run of current the music became full-scale noise,
  independent on each channel, from 17.59 s to the end, with a peak of 32,768. It didn't come
  back in 3 more runs a build.
- The rest are the game's own sounds shifted in time.

Pass 3 checked this with the new tools. Its real-time recordings of the mixer stage have 158
clicks over 319.81 s, where its unpaced ones have 135 over the bisect's 319.78 s. Of those 158,
`block_clicks.py` puts 17 on the 27 blocks the DMA replayed, where chance gives 0.1, each at
one of its block's joins.

It puts 17 on the 308 blocks played while the clock caught up, where chance gives 0.9, though
some of those are the game's own, such as the clicks at about 2.33 s that the unpaced runs have
too. 21 clicks sit on blocks of either kind, since some blocks are both. On the bisect's three
real-time menu runs of current, `block_clicks.py` counts 2, 0 and 6 clicks on replays, as the
bisect did.

`noise_blocks.py` finds 44 noise-like blocks in pass 3's real-time recordings of the mixer
stage, in stretches of one block up to 18 (the race from 71.340 s to 71.605 s). The unpaced runs
have them too.

In the race's first 115 s the unpaced run has 49 in 11 stretches, the longest from 71.285 s to
71.615 s. In mode select's first 35 s it has 4 single blocks, the first at 18.175 s, where the
real-time run has its one at 18.200 s. So short stretches like these come with the game's own
sounds, and pass 3 had no stretch like the bisect's full-scale noise.

## The device stage, real-time

All five routes together. Clicks a minute is over the summed seconds. Pass 4's real-time device
stage isn't tabulated here.

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

## The title route at 91 s

The source type 2 counts under Clicks in `status.md` come from 90-second title runs, and the
five-route pass plays the title for 31 s. `--routes title --margin 75` plays the same route for
91 s. It ran twice on each build in real time, with the tool at `13acaf4`, before the tool
scored the mixer stage unpaced.

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

The clicks come after the five-route run's 31 s. In the baseline's second run, 970 of the 979
came later than that, the first of them at 41.71 s.

Of those 970, 586 fell on a block join, where chance gives 30.3. In current's second run, 10 of
its 22 came after 31 s.

## Pass 5, current against next

Pass 5 ran on 2026-10-23 and took about 22 minutes, one run of the tool over both builds a
route at a time. Current was a second clone's existing build at Dragoon `28fdb9b`, and next was
this clone at gcn-recomp `b97c019` with `2b98e17`'s tools and routes. `b97c019` adds `3056588`,
`cce9fbc`, `795ccc4`, `3b025ac`, `84471cc`, `2b7ae75`, `3d4fe9b`, `6def94c`, `a87ab06` and
`3c55458` to the mixer and the AI DMA, and `audio.md`'s What was done and what is left says
what each does.

| Five routes, unpaced | Current | Next |
|---|---|---|
| Mixer seconds | 324.00 | 324.00 |
| Mixer clicks | 136 | 94 |
| Mixer clicks a minute | 25.2 | 17.4 |
| Mixer clicks within 2 samples of a block join (by chance) | 35 (4.2) | 7 (2.9) |
| Mixer gaps | 8 | 8 |
| Mixer clipped runs (samples) | 25 (371) | 28 (564) |
| Highest main L peak before the clamp | 64,999 | 63,634 |
| Samples the clamp changed | 587 | 574 |

Each cell below is current, then next.

| Pass 5, unpaced | Clicks (a minute) | On a block join (by chance) | Gaps | Clipped runs (samples) | Main L peak | Clamped samples |
|---|---|---|---|---|---|---|
| Title, 31 s | 10 (19.4), 7 (13.5) | 3 (0.3), 0 (0.2) | 1, 1 | 0 (0), 0 (0) | 33,741, 33,117 | 2, 2 |
| Mode select, 35 s | 14 (24.0), 9 (15.4) | 4 (0.4), 0 (0.3) | 1, 1 | 0 (0), 0 (0) | 17,628, 17,099 | 0, 0 |
| Air Ride race, 115 s | 45 (23.5), 28 (14.6) | 13 (1.4), 5 (0.9) | 2, 2 | 25 (371), 28 (564) | 64,999, 63,634 | 585, 572 |
| City Trial, 70 s | 23 (19.7), 15 (12.9) | 7 (0.7), 1 (0.5) | 2, 2 | 0 (0), 0 (0) | 26,762, 23,117 | 0, 0 |
| City Trial, four players, 73 s | 44 (36.2), 35 (28.8) | 8 (1.4), 1 (1.1) | 2, 2 | 0 (0), 0 (0) | 28,982, 28,843 | 0, 0 |

Current's unpaced runs scored as pass 3's did on every cell, a day later and with a newer tool.
The clicks away from joins fell from 101 to 87, and this pass doesn't say which of those
commits took them away. Next's mixer clamps at -32,768, so the race's clipped runs compare only
split by sign (below).

Past the cut, rescored with `--no-run` from the same unpaced recordings:

| Past the cut, unpaced | Current | Next |
|---|---|---|
| Title, first 91 s, clicks | 19 | 16 |
| Title, clicks on a block join (by chance) | 5 (0.6) | 2 (0.5) |
| Title, clipped runs (samples) | 4 (26) | 4 (26) |
| Mode select, first 170 s, clicks | 16 | 11 |
| Mode select, clicks on a block join (by chance) | 6 (0.5) | 2 (0.3) |
| Mode select, clipped runs (samples) | 6 (19) | 9 (31) |

Current's 19 and 16 are the counts the rescoring of pass 3's recordings gave.

| Five routes, real-time | Current | Next |
|---|---|---|
| Device seconds | 322.83 | 322.86 |
| Device clicks | 191 | 70 |
| Device clicks a minute | 35.5 | 13.0 |
| Device gaps | 8 | 9 |
| Device clipped runs (samples) | 0 (0) | 35 (852) |
| Ring cuts | 0 | 0 |
| Ring underruns | 0 | 0 |

| Device clicks a minute | Current | Next |
|---|---|---|
| Title | 11.7 | 9.7 |
| Mode select | 22.4 | 6.9 |
| Air Ride race | 48.6 | 15.2 |
| City Trial | 30.1 | 9.5 |
| City Trial, four players | 36.3 | 17.3 |

Each build is one real-time run here. Current's 35.5 clicks a minute sits with its 36.3, 33.1
and 32.2 in passes 1 to 3. The race went differently in the two runs (below), and on the other
four routes the device clicks fell from 98 to 41.

`tools/clip_signs.py` splits the clipped runs of the same recordings by sign. The mixer rows
are the unpaced run's recording cut as the scorecard cuts it. The device rows are the
real-time run's whole recording.

| Clipped runs, by sign | Runs at +32,767 (samples) | Runs at -32,768 (samples) | Samples at -32,767 | Lowest, highest sample |
|---|---|---|---|---|
| Race mixer, 115 s, current | 25 (371) | 0 (0) | 199 | -32,767, 32,767 |
| Race mixer, 115 s, next | 22 (367) | 6 (197) | 0 | -32,768, 32,767 |
| Mode select mixer, 170 s, current | 6 (19) | 0 (0) | 15 | -32,767, 32,767 |
| Mode select mixer, 170 s, next | 6 (19) | 3 (12) | 0 | -32,768, 32,767 |
| Race device, current | 0 (0) | 0 (0) | 0 | -32,734, 32,564 |
| Race device, next | 20 (546) | 15 (306) | 0 | -32,768, 32,767 |

Unpaced, both builds play the same race, so the mixer rows compare. Next's 6 runs at -32,768
are negative clipping that current held at -32,767, where no clipped run counts it.

The device rows don't compare. Current's real-time race never reached the loud stretch, with no
sample at full scale and a log peak of 33,396 against next's 61,359. The race's frame 6000 dump
differs between the two real-time runs, while the two unpaced runs' dumps match.

Current's device stage clipped 27, 23 and 14 runs on the race in passes 1 to 3, and pass 5's is
the only one of its real-time races with none. Why current's race went differently wasn't
checked.

`tools/block_clicks.py` over the real-time runs' mixer recordings finds 13 blocks the DMA
played twice at current with 2 clicks on them. It finds none at next.

gcn-recomp `a87ab06` keeps a catch-up jump from ending a block the guest hasn't queued after,
and its message gives that as the cause of such replays. Both builds still caught up on the
clock, over 197 blocks at current and 165 at next, with 2 clicks on them at current and none at
next.

## Pass 6, 3a8d154 against dac449e

Pass 6 ran on 2026-10-25 in four plays of about 22 minutes, each over the five routes
real-time and unpaced. Plays 1, 3 and 4 played `3a8d154` first on each route and play 2 played
`dac449e` first.

`3a8d154` was the pin before Dragoon `8ef3887`, and `dac449e` the pin it set. The 27 commits
between change the pacer's wait to sleep in steps and then spin (gcn-recomp `2867e04` and
`0131e4c`). Among the rest are user-interactive QoS for the guest threads, a memory card write
after a quiet period, port memory and DVD music held through a pause.

Both builds ran from one clone, at Dragoon `3f0f8c3` in plays 1 to 3 and `0b34199` in play 4,
which adds the stretch count to `block_clicks.py` and a bounded read to `click_diff.py`. Each
play deletes the last one's recordings, so the stretch counts and the byte comparison are from
play 4 alone.

The `3a8d154` build is in `build/current/` (Running it again), and its generated C and DOL
match `build/`'s file for file. Its runs' `commits.json` name the clone's commit, since
`build/current/` isn't a clone. Dragoon `3f0f8c3` differs from `5d01033`, the last commit on
the `3a8d154` pin, only in the pin and two docs, `status.md` and `widescreen.md`.

The unpaced mixer stage scored the same at both builds in every play. It also matches pass 5's
next on every cell below, which pass 5 scored on gcn-recomp `b97c019` with its own tool.

| Five routes, unpaced | `3a8d154` | `dac449e` |
|---|---|---|
| Mixer seconds | 324.00 | 324.00 |
| Mixer clicks | 94 | 94 |
| Mixer clicks a minute | 17.4 | 17.4 |
| Mixer clicks within 2 samples of a block join (by chance) | 7 (2.9) | 7 (2.9) |
| Mixer gaps | 8 | 8 |
| Mixer clipped runs (samples) | 28 (564) | 28 (564) |
| Highest main L peak before the clamp | 63,634 | 63,634 |
| Samples the clamp changed | 574 | 574 |

| Pass 6, unpaced, both builds, every play | Clicks (a minute) | On a block join (by chance) | Gaps | Clipped runs (samples) | Main L peak | Clamped samples |
|---|---|---|---|---|---|---|
| Title, 31 s | 7 (13.5) | 0 (0.2) | 1 | 0 (0) | 33,117 | 2 |
| Mode select, 35 s | 9 (15.4) | 0 (0.3) | 1 | 0 (0) | 17,099 | 0 |
| Air Ride race, 115 s | 28 (14.6) | 5 (0.9) | 2 | 28 (564) | 63,634 | 572 |
| City Trial, 70 s | 15 (12.9) | 1 (0.5) | 2 | 0 (0) | 23,117 | 0 |
| City Trial, four players, 73 s | 35 (28.8) | 1 (1.1) | 2 | 0 (0) | 28,843 | 0 |

The last frame each unpaced run dumped hashes the same at both builds, on all five routes in
all four plays. `click_diff.py` compared play 4's unpaced recordings of the two builds over the
shorter of each pair, with the result below. The scored seconds and the 91 s and 170 s read
below all fall inside those lengths.

| Play 4, unpaced, `click_diff.py` | Seconds compared | Samples the same | Clicks at each build | Clicks only one build has |
|---|---|---|---|---|
| Title | 214.75 | every one | 36 | 0 |
| Mode select | 207.14 | every one | 18 | 0 |
| Air Ride race | 2,545.18 | every one | 36 | 0 |
| City Trial | 804.58 | every one | 24 | 0 |
| City Trial, four players | 681.66 | every one | 40 | 0 |

Past the cut, rescored with `--no-run` from each play's unpaced recordings, the two builds read
the same in every play too.

| Past the cut, unpaced | `3a8d154` | `dac449e` |
|---|---|---|
| Title, first 91 s, clicks | 16 | 16 |
| Title, clicks on a block join (by chance) | 2 (0.5) | 2 (0.5) |
| Title, clipped runs (samples) | 4 (26) | 4 (26) |
| Mode select, first 170 s, clicks | 11 | 11 |
| Mode select, clicks on a block join (by chance) | 2 (0.3) | 2 (0.3) |
| Mode select, clipped runs (samples) | 9 (31) | 9 (31) |

These are pass 5's next rows as well. `clip_signs.py` splits the mixer's clipped runs by sign, and
it reads the same at both builds in every play.

| Mixer clipped runs, by sign | Runs at +32,767 (samples) | Runs at -32,768 (samples) | Samples at -32,767 | Lowest, highest sample |
|---|---|---|---|---|
| Title, 91 s | 4 (26) | 0 (0) | 0 | -32,768, 32,767 |
| Mode select, 170 s | 6 (19) | 3 (12) | 0 | -32,768, 32,767 |
| Air Ride race, 115 s | 22 (367) | 6 (197) | 0 | -32,768, 32,767 |

The device stage is one real-time run a route, so each cell below is plays 1 to 4 in order.

| Five routes, real-time | `3a8d154` | `dac449e` |
|---|---|---|
| Device seconds | 325.72, 326.31, 326.39, 326.33 | 326.11, 326.05, 326.13, 326.09 |
| Device clicks | 77, 96, 74, 77 | 63, 72, 81, 72 |
| Device clicks a minute | 14.2, 17.7, 13.6, 14.2 | 11.6, 13.2, 14.9, 13.2 |
| Device gaps | 8, 8, 9, 8 | 8, 8, 8, 8 |
| Device clipped runs (samples) | 35 (899), 33 (843), 38 (893), 38 (936) | 27 (792), 30 (867), 27 (833), 32 (898) |
| Ring cuts | 0, 0, 0, 0 | 0, 0, 0, 0 |
| Ring underruns | 0, 0, 0, 0 | 0, 0, 0, 0 |

| Device clicks a minute | `3a8d154` | `dac449e` |
|---|---|---|
| Title | 7.8, 11.6, 5.8, 5.8 | 9.7, 5.8, 5.8, 7.7 |
| Mode select | 17.1, 15.4, 11.9, 15.4 | 10.3, 6.8, 13.7, 10.3 |
| Air Ride race | 13.4, 19.1, 15.0, 14.0 | 11.9, 16.6, 16.6, 16.0 |
| City Trial | 5.1, 7.7, 7.7, 13.6 | 9.4, 7.7, 16.2, 7.7 |
| City Trial, four players | 25.3, 28.6, 21.2, 17.9 | 14.7, 19.6, 15.5, 18.0 |

The device totals overlap. `dac449e` made fewer clicks than `3a8d154` in plays 1, 2 and 4 and
more in play 3. Every route but four players changed order between plays, and four players made
fewer clicks at `dac449e` in plays 1 to 3 and 22 at both in play 4.

The real-time mixer stage is each real-time run's whole `GCN_AIDWAV` recording, read with
`block_clicks.py`, which also counts the blocks the DMA played twice and the blocks delivered
while the clock caught up. Passes 1 and 2 scored the mixer stage from real-time runs the same
way. The recordings aren't cut to the route's seconds.

| Five routes, real-time mixer stage | `3a8d154` | `dac449e` |
|---|---|---|
| Mixer seconds | 323.04, 323.59, 323.67, 323.62 | 323.39, 323.33, 323.42, 323.39 |
| Mixer clicks | 94, 87, 86, 81 | 83, 81, 81, 82 |
| Mixer clicks a minute | 17.5, 16.1, 15.9, 15.0 | 15.4, 15.0, 15.0, 15.2 |
| Blocks played twice | 0, 0, 0, 0 | 0, 0, 0, 0 |
| Blocks delivered catching up | 247, 254, 255, 247 | 51, 67, 61, 65 |
| Clicks on blocks delivered catching up | 0, 0, 0, 0 | 0, 0, 0, 0 |

| Real-time mixer clicks (blocks caught up) | `3a8d154` | `dac449e` |
|---|---|---|
| Title | 7 (14), 8 (20), 7 (11), 8 (15) | 7 (4), 7 (2), 7 (1), 7 (4) |
| Mode select | 9 (1), 9 (4), 9 (3), 9 (1) | 9 (0), 9 (0), 9 (0), 9 (0) |
| Air Ride race | 31 (175), 26 (178), 28 (177), 28 (172) | 30 (5), 26 (13), 26 (11), 28 (15) |
| City Trial | 15 (28), 15 (31), 15 (30), 17 (34) | 15 (20), 15 (26), 15 (23), 15 (24) |
| City Trial, four players | 32 (29), 29 (21), 27 (34), 19 (25) | 22 (22), 24 (26), 24 (26), 23 (22) |

None of the 40 recordings has a block played twice or a click on a block delivered catching up,
where pass 5's current had 13 replayed blocks with 2 clicks on them.

The blocks delivered while the clock caught up fell from 247 to 255 a play at `3a8d154` to 51 to
67 at `dac449e`, and the race went from 172 to 178 to 5 to 15. Counted with `block_clicks.py` as
stretches of consecutive blocks in play 4's logs, `3a8d154` caught up in 181 stretches over the
five routes (153 on the race) and `dac449e` in 15 (7 on the race). The race recording holds
23,093 blocks at `3a8d154` in each play and 22,979 at `dac449e`.

| Play 4, blocks delivered catching up (stretches) | `3a8d154` | `dac449e` |
|---|---|---|
| Title | 15 (11) | 4 (2) |
| Mode select | 1 (1) | 0 (0) |
| Air Ride race | 172 (153) | 15 (7) |
| City Trial | 34 (12) | 24 (3) |
| City Trial, four players | 25 (4) | 22 (3) |
| Five routes | 247 (181) | 65 (15) |

The last dumped frame of a real-time run is the route's last checkpoint, and it didn't always
match the unpaced run's frame there.

| Real-time last frame equals the unpaced run's | `3a8d154` | `dac449e` |
|---|---|---|
| Title | 2 of 4 plays | 4 of 4 |
| Mode select | 1 of 4 | 4 of 4 |
| Air Ride race | 0 of 4 | 0 of 4 |
| City Trial | 1 of 4 | 2 of 4 |
| City Trial, four players | 0 of 4 | 0 of 4 |

`clip_signs.py` over each play's real-time recording gives the race's device stage by sign.

| Race device, by sign | Runs at +32,767 (samples) | Runs at -32,768 (samples) | Samples at -32,767 | Highest main L peak in the log |
|---|---|---|---|---|
| `3a8d154`, play 1 | 20 (564) | 13 (327) | 0 | 62,445 |
| `3a8d154`, play 2 | 25 (547) | 6 (290) | 0 | 62,363 |
| `3a8d154`, play 3 | 17 (538) | 14 (312) | 1 | 62,834 |
| `3a8d154`, play 4 | 22 (583) | 16 (353) | 0 | 61,800 |
| `dac449e`, play 1 | 20 (516) | 6 (274) | 1 | 60,871 |
| `dac449e`, play 2 | 17 (567) | 13 (300) | 2 | 60,432 |
| `dac449e`, play 3 | 16 (531) | 11 (302) | 0 | 61,165 |
| `dac449e`, play 4 | 19 (588) | 12 (308) | 0 | 61,780 |

All eight real-time races reached the loud stretch, so pass 5's mismatch between its two races
didn't recur. Outside the race the device stage clipped at `3a8d154` on the title in plays 1 to
3 and on four players in play 3 (6 runs, 38 samples, at +32,767), and at `dac449e` on the title
in plays 1 and 4, 1 run of 2 samples each.

What pass 6 doesn't explain:

- Why `3a8d154` caught up on 172 to 178 blocks of the race, in 153 stretches in play 4, and
  `dac449e` on 5 to 15, in 7. The 27 commits include the pacer's wait, QoS for the guest threads,
  the card write, port memory and the held music. No run here played an engine between the two,
  so the runs don't say which of them did it.
- Why the device stage's clicks moved as much between plays as between builds. City Trial at
  `dac449e` made 11, 9, 19 and 9.
- Why four players' real-time mixer clicks are fewer than its unpaced 35 at both builds (22 to 24
  at `dac449e`, 19 to 32 at `3a8d154`). The last frame of its real-time runs differs from the
  unpaced run's at both builds in every play.
- Why the race's highest main L peak in the log is lower at `dac449e` in every play (60,432 to
  61,780 against 61,800 to 62,834), when the unpaced run's is 63,634 at both. The title's
  real-time peaks at `3a8d154` were above its unpaced 33,117 in plays 1 to 3 (35,708, 36,401 and
  34,418) and below it in play 4 (32,194), and at `dac449e` they were 33,599, 33,117, 33,117
  and 33,599.
- Why 3 of the 8 race device recordings hold 1 or 2 samples at -32,767, where the mixer stage has
  none.

## What the numbers don't show

- Every pass ran on an engine where music streams often ended after their first 1.79 s slot.
  gcn-recomp `04c025f`, in `bad7160`, times disc reads as a console's drive does, which fixed
  that (`audio.md`, Stream music and disc timing).
- The mixer stage's before and after is one unpaced run of each build, pass 4 and pass 3, made
  a day apart. Pass 4's tool was at `3698f16` and pass 3's at `5ff734e`, which score the same.
  The bisect, cut at passes 1 and 2's lengths rather than the routes' seconds, agrees with
  both, but its notes aren't in this repository.
- Pass 5 played each build once. Current's unpaced runs scored the same as pass 3's, but the
  tool didn't play next twice. At `b97c019`, `tools/audio_hashes.py` gave the same audio rows on
  all twelve routes in three runs, a record between two checks.
- Real-time runs move from pass to pass. The baseline's title route clipped 4,009 samples in the
  mixer stage in one pass and 485 in the other.

  Current's City Trial made 29.3, 35.3 and 20.7 device clicks a minute in passes 1 to 3. Every
  device stage total moved the same way from baseline to current in passes 1 and 2.
- Pass 3's real-time runs overlapped a run of the tools' test suite on the same host, and a
  loaded host is what makes the clock catch up. Its 27 replayed blocks, 308 caught-up blocks,
  158 mixer clicks and 32.2 device clicks a minute weren't measured on a quiet host. That the 17
  clicks on replayed blocks all sit at a block's joins doesn't depend on how many were replayed.
- The baseline's device stage is what SDL's dummy driver took, not what a sound card would. Over
  the five routes it took 296.45 s and 296.80 s of sound while the DMA delivered 319.78 s and
  319.87 s, 92.7% and 92.8%.

  It doesn't log its ring's cuts, so its log doesn't say where the rest went. In passes 1 and 2
  its device stage had 167 and 93 more clicks than its real-time mixer stage. Current's had 54
  and 17 more, with no cuts.
- A device stage's seconds include the silence the device plays from when it opens until the
  ring first holds its cushion.
- The peak and the clamp count come from `[ax]` lines, which come every 400 command lists, 2 s
  of sound. Up to the last 2 s before the cut isn't in them.
- A click here is any sharp edge, the game's own sounds included. The counts say where to look,
  not what a listener hears.
- `audio_clicks.py` counts a clipped run at 32,767 or -32,768. The mixer's clamp stops at
  -32,767, so the mixer stage's negative clipping isn't in its clipped runs.

  The device stage plays those samples through the ring, which never makes one larger, so the
  mixer's negative clipping isn't in the device stage's clipped runs either. The music stream is
  added after the ring and clamps at -32,768, so clipping there does show in the device stage.
  The clamp count from `[ax] bus` has both signs and counts the mixer only.
- Next clamps at -32,768 in the mixer (`2b7ae75`) and in command `0E`'s output (`3d4fe9b`), so
  its negative clipping is in both stages' clipped runs, and its clamp count takes the samples
  below -32,768 where current's takes those below -32,767.
- Pass 6 played each build four times, and the device stage's totals overlap at 74 to 96 clicks
  for `3a8d154` and 63 to 81 for `dac449e`. The real-time mixer stage's totals overlap too, at 81
  to 94 and 81 to 83, though its caught-up blocks don't, at 247 to 255 and 51 to 67. Four plays
  on one machine can't say how often a fifth would fall outside those ranges.
- Pass 6's plays ran on a machine with other work on it, plays 1 to 3 back to back and play 4
  later, with a one-minute load average of 4.0, 2.9 and 2.6 as plays 1 to 3 began and 1.4 a
  minute or two before play 4. No tests or builds ran during a play, and the rescoring between
  plays played no game.
- Pass 6's tool differs from pass 5's in `audio_clicks.py`, `audio_scorecard.py`,
  `frame_dumps.py`, `probe.sh`, `probe_dirs.py` and `scorecard_runs.py`. Pass 6 didn't rescore
  pass 5's recordings with it, so its unpaced cells matching pass 5's next is the one check
  across the two versions.
- Underruns are as of each run's last `[ring] fill` line, which comes every 400 pulls of the
  device.
- Nobody listened to any of it, and nothing was compared with a real console. One machine, an
  M4 Max on macOS 26.6.2 with Python 3.14.7.

## Running it again

The baseline is a second clone at Dragoon `6b81b6e`, whose gcn-recomp is `caf12a2`, built
the same way as current. Pass 4 used that clone's existing build at that commit.

```sh
cmake -S . -B build -G Ninja -DDRAGOON_WARMUP=OFF
ninja -C build
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --routes title --margin 75
```

The numbers past the cut come from these two commands, run on pass 4's and pass 3's unpaced
recordings.

```sh
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --routes title --margin 75 --no-run
tools/audio_scorecard.py base=/path/to/dragoon-base/build current=build --routes menu --margin 150 --no-run
```

With `--no-run` the margin sets how much of each unpaced recording the mixer stage scores, 91 s
of the title and 170 s of the mode select here. Read the mixer rows, since the device rows come
from the real-time run, which the margin doesn't cut.

A later engine goes in a clone of its own with a label of its own, as in
`next=/path/to/that/build`.

Pass 5 ran from this clone built at the later engine, with current in a second clone. The
second command rescores pass 5's recordings, and so do the last two with their margins.

```sh
tools/audio_scorecard.py current=/path/to/dragoon-current/build next=build \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p
tools/audio_scorecard.py current=/path/to/dragoon-current/build next=build \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p --no-run --json
tools/audio_scorecard.py current=/path/to/dragoon-current/build next=build --routes title --margin 75 --no-run
tools/audio_scorecard.py current=/path/to/dragoon-current/build next=build --routes menu --margin 150 --no-run
```

The split by sign reads the same recordings and plays no game, and the second and third
commands give the title's 91 s and the mode select's 170 s. The `md5` command hashes the race's
frame 6000 dump from each run. Only the two unpaced runs' hashes match.

```sh
tools/clip_signs.py current=/path/to/dragoon-current/build next=build \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p
tools/clip_signs.py current=/path/to/dragoon-current/build next=build --routes title --margin 75
tools/clip_signs.py current=/path/to/dragoon-current/build next=build --routes menu --margin 150
md5 /path/to/dragoon-current/build/probe/scorecard-air-ride-race/frame_06000.png \
  build/probe/scorecard-air-ride-race/frame_06000.png \
  /path/to/dragoon-current/build/probe/scorecard-unpaced-air-ride-race/frame_06000.png \
  build/probe/scorecard-unpaced-air-ride-race/frame_06000.png
```

Pass 6 ran from this clone checked out at Dragoon `3f0f8c3` (whose pin, and so its `build/`, is
`dac449e`) and kept the `3a8d154` build inside it. The `3a8d154` build is a copy of the sources
in `build/current/` with the engine checked out there as a worktree, and the tool takes it as
`current=build/current/build`. Removing `build/current/` and running
`git -C gcn-recomp worktree prune` puts the clone back as it was.

```sh
mkdir build/current
git archive 3f0f8c3 CMakeLists.txt src analysis recomp tools | tar -x -C build/current
git -C gcn-recomp worktree add --detach "$PWD/build/current/gcn-recomp" 3a8d154
cmake -S build/current -B build/current/build -G Ninja -DDRAGOON_WARMUP=OFF \
  -DFETCHCONTENT_SOURCE_DIR_SDL3="$PWD/build/_deps/sdl3-src" -DGAME_ISO=/path/to/game.iso
ninja -C build/current/build
tools/audio_scorecard.py current=build/current/build next=build \
  --routes title,menu,air-ride-race,city-trial,city-trial-4p
```

Playing a build again deletes its earlier recordings, so pass 6 read each play before the next
began. It used the rescoring and the split by sign above with `current=build/current/build`, and
ran `block_clicks.py` on each real-time run's `mixer.raw`. The `md5` command took each route's
last dumped frame (`frame_00960.png` for the title, then 1200, 6000, 3300 and 3480) from the
route's four runs.

```sh
tools/block_clicks.py build/current/build/probe/scorecard-air-ride-race/mixer.raw
tools/block_clicks.py build/probe/scorecard-air-ride-race/mixer.raw
md5 build/current/build/probe/scorecard-air-ride-race/frame_06000.png \
  build/probe/scorecard-air-ride-race/frame_06000.png \
  build/current/build/probe/scorecard-unpaced-air-ride-race/frame_06000.png \
  build/probe/scorecard-unpaced-air-ride-race/frame_06000.png
tools/click_diff.py build/current/build/probe/scorecard-unpaced-air-ride-race/mixer.raw \
  build/probe/scorecard-unpaced-air-ride-race/mixer.raw
```

The `caught up` line of each `block_clicks.py` run gives the blocks and the stretches they come
in.

| Pass | Date | gcn-recomp | Dragoon clone | Tool |
|---|---|---|---|---|
| 1 and 2 | 2026-10-22 | `caf12a2`, `b848158` | `6b81b6e`, `43ceba4` (`788571c` plus `tools/`) | `43ceba4` |
| Title at 91 s | 2026-10-22 | `caf12a2`, `b848158` | `6b81b6e`, `13acaf4` | `13acaf4` |
| Bisect | 2026-10-22 | `caf12a2` and `b848158`, with six of the audio commits between | Notes not in this repository | Prototypes |
| 3 | 2026-10-22 | `b848158` | `5ff734e`'s code, the game code of `788571c` | `5ff734e` |
| 4 | 2026-10-23 | `caf12a2` | `6b81b6e` | `3698f16` |
| Past the cut, passes 3 and 4 | 2026-10-23 | `caf12a2`, `b848158`, from passes 4 and 3 | No game played | `8aaae9a` |
| 5 and its rescoring | 2026-10-23 | `b848158`, `b97c019` | `28fdb9b`, `2b98e17`'s tools and routes | `2b98e17`, `clip_signs.py` at `0268d8a` |
| 6 and its readings | 2026-10-25 | `3a8d154`, `dac449e` | `3f0f8c3` in plays 1 to 3, `0b34199` in play 4 | The clone's |
