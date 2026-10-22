# Tools

Each tool answers one question. Start with probe.sh, which makes the runs the others read. Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`.

## Conventions

Every tool takes `--help`, which prints its usage and what it reads. Results go to stdout, including the failures a tool checks for. Errors go to stderr as one line naming the file and what's wrong, and so do warnings that leave the exit code alone. A traceback means a bug in the tool.

| Exit | Means |
|---|---|
| 0 | The tool ran and nothing failed |
| 1 | It ran and found what it checks for, such as a changed frame or a frame over budget |
| 2 | It couldn't run: a bad argument, or an input it can't read or doesn't understand |

frametime.py, shader_cache.py, audio_clicks.py, audio_scorecard.py, block_clicks.py, click_diff.py and noise_blocks.py only report, so they never exit 1.

## probe.sh

How does the game behave when nobody is playing it? It runs the game in a hidden window for a number of seconds, feeds it a route of button presses and dumps every Nth frame as a PNG. A run leaves its frames (`frame_NNNNN.png`), its log (`stdout.txt`), its memory card (`saves/memcard_a.raw`), its shader cache (`saves/shaders.bin`) and, after a crash, `panic.txt` in `build/probe/NAME/`. A windowed run uses SDL's dummy audio driver, so it's silent. A `--bench` run leaves the driver to SDL and plays through the real device unless `SDL_AUDIO_DRIVER=dummy` is set, which audio_hashes.py does. Audio never paces the guest, so the dummy driver doesn't change timing. A new NAME starts from a blank memory card, and a NAME that's run again keeps the card its last run left behind.

After the NAME and seconds come an input script or a route file from `tests/routes/`, the dump interval and any settings. A setting is `GCN_*=value` (the list is in `gcn-recomp/docs/diagnostics.md`), `--pads=N`, `--real-time`, `--scale=N`, `--bench` or `--log=LIST`. `--log=dsp,ai` turns on those log categories in the game. It works in windowed runs only, because `dragoon_bench` takes no `--log`, so probe.sh refuses it with `--bench`. An unknown category stops the game at once, and `stdout.txt` names it. `tools/probe.sh --help` prints the settings. Route files are described in `tests/routes/README.md`.

```
tools/probe.sh demo 20 tests/routes/title.txt 60 GCN_FRAMETIME=1
```

That prints the run's directory as an absolute path, then a frame count (140 on an M4 Max). It exits 2 when the game isn't built. Run it again with a different NAME to get a second run to compare.

## frametime.py

How steady is the frame pacing, and what made the slow frames slow? It reads the log of a run made with `GCN_FRAMETIME=1`, prints the guest's and the renderer's mean, p95, p99 and worst times from a given frame on, and lists each frame whose render time went over a limit with its batch shape and the shaders compiled in it.

```
tools/probe.sh pace 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1
tools/frametime.py build/probe/pace/stdout.txt --from 300 --slow 16.7
```

Add `--json` for machine output. Frame numbers are the `[rt]` lines'. A frame's batch is the `[ft]` line one lower.

A dumped frame is read back, which adds to its `[rt]` time, so time a run with a dump interval past its end (the 100000 above). Under `--fast` the guest interval is how fast the game goes, not its pacing. Use `--real-time` for pacing. Shader compiles show either way.

## framediff.py

Do two runs draw the same pixels? It compares every `frame_NNNNN.png` that two directories of frame dumps have in common, prints the share of pixels whose largest RGB difference is over a tolerance and the worst difference seen, and ends with a line counting the frames compared and the ones over budget. It exits 1 if any frame is over the budget. Alpha isn't compared.

framediff takes a tolerance. frame_hashes is an exact check against committed goldens. Two runs of a change need two builds and two NAMEs. Frames only one directory has are counted on stderr and don't fail the diff, which is normal when runs end at different frames.

```
tools/framediff.py build/probe/before build/probe/after --tolerance 3 --budget 0.001
```

## shader_cache.py

How many shaders does a cache or key list hold, and how many are new? It reads `saves/shaders.bin` (magic `WRSC`) and key lists (magic `GCSK`). The key size comes from the format word, and a magic or key size it doesn't know is refused. `count` prints the format, the record count and the distinct key count, and says how many trailing bytes it ignored (a record a kill cut off). `diff` prints how many distinct keys in NEW aren't in OLD and their share of NEW, and refuses two files in different formats. It counts and never lists keys.

```
tools/shader_cache.py count build/probe/demo/saves/shaders.bin
tools/shader_cache.py diff build/old-keys.bin build/probe/demo/saves/shaders.bin
```

## frame_hashes.py

Did a change alter what the renderer draws? It runs each route in `tests/hashes/manifest.txt` through probe.sh and compares the SHA-1 of every dumped frame with the golden in `tests/hashes/gl/<route>.txt`. `check` reports each frame that changed or wasn't reached. `record` rewrites the goldens, so use it only when a change to the output is on purpose. The frames are moved to the Trash once hashed and are never committed.

The manifest has one route per line. A line gives the name, the seconds to run, the dump interval, the frames the route must reach and any extra probe settings. Pass route names to run only those. A `check` of all twelve routes took 302 s while other copies of the game ran on the same machine.

```
tools/frame_hashes.py check title
```

## audio_hashes.py

Did a change alter what the AX mixer outputs? It runs each route in `tests/hashes/manifest.txt` through probe.sh as a `--bench` run with `GCN_AXSTATS=1` and SDL's dummy audio driver, and compares the `[ax] hash list=N fnv=X` lines with the rows in `tests/hashes/audio/<route>.txt`. The hash runs from boot, so a row shows that nothing the mixer wrote before list N changed. `check` reports each row that changed, and fails a run that doesn't reach a row's list count. `record` rewrites a route's golden at `--lists`, or at the list counts it already has, so use it only when a change to the sound is on purpose. No audio is kept, only the hashes. The goldens hold for unpaced runs only, and their header says so.

```
tools/audio_hashes.py check air-ride-race
tools/audio_hashes.py record title --lists 7200,20000
```

A `check` of all twelve routes took 300 s while other copies of the game ran on the same machine. Each route runs under the NAME `audio-ROUTE` in `build/probe/`. An earlier run's directory is moved to the Trash first, so the game starts from a blank memory card. The last run's directory stays, so its `[ax]` lines can explain a changed hash. List counts are multiples of 400, the interval the game prints at. It exits 0, 1 or 2 as frame_hashes.py does.

## audio_clicks.py

Where does the sound click, drop out or clip? It reads a 16-bit PCM WAV, such as the one `GCN_WAV=<path>` records of exactly what went to the audio device, and prints how many of each it found and when. A click is a sample whose second difference is over 8 times the RMS second difference of the 5 ms either side, and at least 128. A splice, such as the audio ring skipping ahead, shows as one. Each click comes with its size, its largest second difference in dB from full scale, so a quiet tick can be told from a loud one. A gap is 5 ms or more of digital silence on every channel straight after sound. A clipped run is two or more samples at full scale on one channel.

```
tools/probe.sh title-wav 90 tests/routes/title.txt 100000 --real-time GCN_WAV=out.wav
tools/audio_clicks.py build/probe/title-wav/out.wav --from 5
```

The game runs inside the probe directory, so a relative `GCN_WAV` path lands there. Use `--real-time`, because under `--fast` the game makes sound faster than the device takes it. Under probe.sh the device is SDL's dummy driver, and gcn-recomp pulls the sound itself at a sound card's pace under it, so the recording is what a sound card would get. `GCN_AIDWAV` (below) records the game's sound before the audio ring. The recording is the game's own sound, so it stays in `build/probe/` and is never committed. `--list N` caps the times printed for each, and `--json` prints the whole result. Detections under 1 ms apart chain into one click, however long the run. The click is reported at the run's first sample. `--marks` and `--period` match that first sample.

`GCN_AIDWAV=<path>` records the DMA's own blocks instead, before the audio ring touches them, as headerless 16-bit stereo at 32 kHz. `--raw 32000` reads that. `--period 160` also counts the clicks within 2 samples of a multiple of 160 samples (the DMA's 5 ms block) and how many would land there by chance.

```
tools/probe.sh title-aid 90 tests/routes/title.txt 100000 --real-time GCN_AIDWAV=aid.raw
tools/audio_clicks.py build/probe/title-aid/aid.raw --raw 32000 --period 160
```

`--marks FILE` reads sample indices from a text file (one a line) and counts the clicks near one and the marks with a click near them. With `GCN_AXSTATS=1` the game prints a `[ring] cut N frames at output frame F` line each time the audio ring throws away what it has too much of, and F is an index into the `GCN_WAV` recording.

```
tools/probe.sh title-cuts 90 tests/routes/title.txt 100000 --real-time GCN_WAV=out.wav GCN_AXSTATS=1
sed -n -E 's/^\[ring\] cut .* frame ([0-9]+)$/\1/p' build/probe/title-cuts/stdout.txt > build/probe/title-cuts/cuts.txt
tools/audio_clicks.py build/probe/title-cuts/out.wav --marks build/probe/title-cuts/cuts.txt
```

## audio_scorecard.py

How does each build's sound measure, route by route? It plays every route in `tests/hashes/manifest.txt` on one or more Dragoon builds and counts clicks, gaps and clipping at two stages, with nobody listening. Each build is a clone's `build/` directory with a label. A route plays on each build in turn before the next route starts, through that clone's own probe.sh, hidden, with SDL's dummy audio driver and `GCN_AXSTATS=1`. It plays twice on each build, once `--real-time` and once unpaced. The route files come from this clone, so every build plays the same presses.

```
tools/audio_scorecard.py base=/path/to/old-clone/build current=build
tools/audio_scorecard.py base=/path/to/old-clone/build current=build --routes title --json
```

Each run lasts the route's last checkpoint at 60 frames a second plus 15 s of wall-clock time (`--margin` changes the 15). It dumps that one frame (`GCN_DUMP_RANGE`). A run that doesn't reach it stops the tool with exit 2. The real-time runs go to `build/probe/scorecard-ROUTE/` in each clone and the unpaced ones to `build/probe/scorecard-unpaced-ROUTE/`. An earlier run in that directory goes to the Trash first, so every run starts from a blank memory card and an empty shader cache. `--no-run` measures the runs already there. The five routes `scorecard.md` scores (`--routes title,menu,air-ride-race,city-trial,city-trial-4p`) take about 11 minutes a build.

The mixer stage is the unpaced run's `GCN_AIDWAV`, the DMA's blocks before the audio ring, cut to the route's last checkpoint plus the margin and read with audio_clicks.py's `--raw 32000 --period 160`. An unpaced run's game time doesn't follow the host's, so two unpaced runs of one build give the same blocks byte for byte. A real-time run's clock catches up when the host falls behind, the DMA then plays a block twice, presses land on other frames and sounds move. So a real-time run's blocks say as much about the host's timing as about the build. An unpaced run gets more of the game's time than the cut in its wall-clock seconds, and a recording shorter than the cut stops the tool with exit 2. The unpaced run's log gives the highest `[ax] frames` peak (main L before the output clamp) and the sum of the `[ax] bus` lines' `clipped`, from the lines whose list count is within the cut. A list is a 160-sample block.

The device stage is the real-time run's `GCN_WAV`, which is what went to the device. That run's log gives the ring's cuts and underruns. The device stage also counts the clicks within 2 samples of a `[ring] cut` line's output frame, when the build logs cuts. Underruns are the last `[ring] fill` line's, which comes every 400 pulls of the device. The real-time run records `GCN_AIDWAV` too, for block_clicks.py.

Each stage gets clicks a minute, gaps and clipped runs as audio_clicks.py counts them. An older build that doesn't print a log value reads `not logged`, and a missing recording reads `not recorded`. When `--no-run` finds no unpaced run, as for runs made before the scorecard played one, the mixer stage and its log values read `not recorded`. `--no-run` cuts the mixer stage at `--margin`, as a run would. A table per route prints as the route finishes, then the totals, where clicks a minute is over the summed seconds. `--json` prints it all at the end, with each clone's commit and its gcn-recomp commit. The tool reads those two before the first route plays and leaves them in each run's `commits.json`. `--no-run` prints what its runs recorded, or `not recorded` for a run made before that file existed. When a build's runs recorded different commits, it joins them with `and` (`a1b2c3d and e4f5a6b`), in the header and in the JSON. It only reports, so it never exits 1.

scorecard_runs.py plays a route on a build and scorecard_measure.py scores a run's files. Neither has a command line.

## block_clicks.py

Do a run's mixer-stage clicks sit on the blocks the DMA played twice or delivered catching up? It reads a `GCN_AIDWAV` recording and the block log gcn-recomp writes beside it (`<file>.txt`). A replayed block has the same address as the block before, because the guest hadn't queued the next buffer. A caught-up block came while the clock caught up with the host, which only a `--real-time` run does. For each kind and for the two together it prints the blocks, the clicks in them or within 2 samples of either end, and the count chance would put there.

```
tools/block_clicks.py build/probe/scorecard-menu/mixer.raw
```

## click_diff.py

Which clicks does one build's unpaced recording of a route have that another's doesn't? Unpaced, the two recordings line up sample for sample, so B minus A is what the builds did differently. For each click only one has, it prints the largest B minus A within 5 ms, B minus A's second difference at the click, whether each build is silent there and whether B minus A steps at the nearest block join. A second difference of 0 means both builds have the same edge, and only the sound around it differs. `--seconds S` cuts both to S.

```
tools/click_diff.py /path/to/old-clone/build/probe/scorecard-unpaced-title/mixer.raw build/probe/scorecard-unpaced-title/mixer.raw
```

## noise_blocks.py

Where do the DMA's blocks turn to loud noise? It weighs each 160-sample block of a `GCN_AIDWAV` recording, setting its high-frequency energy against its total as the RMS of its first difference over its RMS. White noise gives about 1.41, and music and effects give far less. A block is noise-like over 1 on a channel whose peak is over 8,000, and it prints the stretches such blocks form. The game's own bright sounds, a crash for one, make short stretches too, so a stretch is a place to look rather than a fault. It reads the DMA's 32 kHz only, since the ring's resampling to 48 kHz lowers the ratio of any noise in a `GCN_WAV` recording.

```
tools/noise_blocks.py build/probe/scorecard-menu/mixer.raw
```

## warm_shaders.py

Will a player's first session stall on shader compiles? It plays the game once so the cache is already warm. The build runs it as the `dragoon_warmup` target, unless it's configured with `-DDRAGOON_WARMUP=OFF`, has no disc or is a cross build. It runs the game hidden and fast, with SDL's dummy audio driver, in a scratch directory, with one pass per route in `tests/hashes/manifest.txt`. Each pass starts from a blank memory card, as a fresh install does, because a route that finds an earlier pass's card takes other menus and builds other keys. The scratch `shaders.bin` starts as a copy of the player's own and grows pass by pass.

The cache is copied over `saves/shaders.bin` only once every pass has succeeded, and it only gains keys. No other file in `saves/` is touched, so the player's memory card stays as it is. A failed pass exits 1 and leaves `saves/` as it was. `saves/.shader-warmup` holds the gcn-recomp commit and a SHA-1 each of the manifest (with the route files' text) and of warm_shaders.py. If all three match, the next run does nothing. A relink doesn't replay the game, but an edited route or tool does. A checkout asks git for the gcn-recomp commit. A source snapshot has no history, so it takes the commit from its `source-info.json`. A copy with neither exits 2. `--force` plays it anyway. A pass that outlasts twice its length at 60 fps plus 30 s is killed and counts as failed.

```
tools/warm_shaders.py --force
tools/shader_cache.py count saves/shaders.bin
```

## routes.py

Which routes does the repository play? `tests/hashes/manifest.txt` lists them, and `tests/routes/` holds their files. routes.py reads the manifest into `Route` records and gives each route file's path, for frame_hashes.py, audio_hashes.py and warm_shaders.py. It also picks routes by name for the first two. It has no command line.

## source_info.py

What does a source snapshot hold? Its `source-info.json` names the Dragoon and gcn-recomp commits and the disc they build, as `disc_id` and `dol_sha1`. source_info.py reads that file and refuses one with a field missing or malformed, naming the file. warm_shaders.py reads the engine commit through it. It has no command line.

## probe_dirs.py

What happens to a probe run and its directory? It holds `trash`, which moves a directory from `build/probe/` into `~/.Trash` under a time-stamped name, and `run_probe`, which runs a probe.sh command line with its output dropped and turns a nonzero exit into an error. frame_hashes.py, audio_hashes.py and the scorecard use both. It has no command line.

## aid_blocks.py

What does `GCN_AIDWAV` write? It holds the DMA's rate, its 160-sample block and the reader for the block log beside each recording, for block_clicks.py, click_diff.py, noise_blocks.py and scorecard_measure.py. It has no command line.

## check_no_game_data.py

Is anything from a disc tracked by git? It flags tracked paths that look like game data:

- Disc images and executables by suffix, `.raw` memory cards and audio recordings, `.wav` recordings and `.bin` shader caches and key lists, wherever they sit.
- Anything under a top-level `build*/` or `rom/` (except the `rom/` README), and anything under a `saves/` at any depth.
- Frame dumps (`frame_NNNNN.png`), `stdout.txt` and `panic.txt`, wherever they sit. Other PNG files are fine.

It prints one line per path and exits 1 if it found any, so it can run in CI. It prints nothing when the tree is clean.

```
tools/check_no_game_data.py
```

## The engine's own tools

Two tools in `gcn-recomp/tools/` matter when debugging here.

`shader_keys.cpp` makes a key list from shader caches and older key lists. It keeps each key once, in the order it was first seen. The compiled binaries stay behind because they belong to one driver. Build it with the `shader_keys` target. Read its output with shader_cache.py.

```
cmake --build build --target shader_keys
build/shader_keys build/keys.bin build/probe/demo/saves/shaders.bin
```

`check_generic.py` fails if a file names a particular game, since nothing game-specific belongs in the engine. Run it before a fork commit. With no arguments it checks every tracked file. `--staged` checks only what's staged, and file names check just those files.

```
python3 gcn-recomp/tools/check_generic.py --staged
```
