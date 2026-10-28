# Tools

Each tool answers one question. Start with probe.sh, which makes the runs the others read. To playtest with sound, run playtest.sh and read the session with session_report.py, and with pad_report.py for the controls.

Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`. The launcher's own helpers live in `launcher/tools/` with their tests beside them, so run those with `python3 -m unittest discover -s launcher/tools -p 'test_*.py'` too. Both run under the Command Line Tools' Python 3.9 and under a newer one.

## Conventions

Every tool but `swift_test.py`, which hands it to swift, takes `--help` and prints its usage and what it reads. Results go to stdout, including the failures a tool checks for. Errors go to stderr as one line naming the file and what's wrong, and so do warnings that leave the exit code alone. A traceback means a bug in the tool.

| Exit | Means |
|---|---|
| 0 | The tool ran and nothing failed |
| 1 | It ran and found what it checks for, such as a changed frame or a frame over budget |
| 2 | It couldn't run: a bad argument, or an input it can't read or doesn't understand |

frametime.py, shader_cache.py, audio_clicks.py, audio_scorecard.py, block_clicks.py, click_diff.py, noise_blocks.py, clip_signs.py, ax_stats.py, session_report.py and pad_report.py only report, so they never exit 1.

## probe.sh

How does the game behave when nobody is playing it? It runs the game in a hidden window for a number of seconds, feeds it a route of button presses and dumps every Nth frame as a PNG. A run leaves its frames (`frame_NNNNN.png`), its log (`stdout.txt`), its memory card (`saves/memcard_a.raw`), its shader cache (`saves/shaders.bin`) and, after a crash, `panic.txt` in `build/probe/NAME/`. A windowed run uses SDL's dummy audio driver, so it's silent. A `--bench` run leaves the driver to SDL and plays through the real device unless `SDL_AUDIO_DRIVER=dummy` is set, which audio_hashes.py does. Audio never paces the guest, so the dummy driver doesn't change timing. A new NAME starts from a blank memory card, and a NAME that's run again keeps the card its last run left behind.

After the NAME and seconds come an input script or a route file from `tests/routes/`, the dump interval and any settings. A setting is `GCN_*=value` (the list is in `gcn-recomp/docs/diagnostics.md`), `DRAGOON_*=value` (Dragoon's own switches in `src/`, such as `DRAGOON_CENSUS=1` in `docs/dev/widescreen.md`), `--pads=N`, `--real-time`, `--scale=N`, `--bench`, `--log=LIST`, `--disc=PATH`, `--aspect=W:H`, `--output`, `--replay=DIR` or `--exit-after=N`. `--log=dsp,ai` turns on those log categories in the game. It works in windowed runs only, because `dragoon_bench` takes no `--log`, so probe.sh refuses it with `--bench`. An unknown category stops the game at once, and `stdout.txt` names it. `--disc=PATH` names the disc image the game plays, which a game built from the engine kit needs, since it has no disc of its own. A relative path is taken from where probe.sh was run, and a path that isn't a file exits 2. `tools/probe.sh --help` prints the settings. Route files are described in `tests/routes/README.md`.

`--aspect=16:9` stretches the picture to 16:9, and `--output` also writes `output_NNNNN.png` beside each frame, showing what the window shows. Both need a windowed run, so probe.sh refuses either with `--bench`. The frame count it prints leaves the output dumps out.

`--replay=DIR` plays back the input log in `DIR/inputs.txt`, and `--exit-after=N` quits once N frames have been shown. A relative DIR is taken from where probe.sh was run, like a `--disc` path. A DIR with no `inputs.txt` exits 2.

Both need a windowed run, so probe.sh refuses either with `--bench`. A run ends early when the game exits.

A run keeps no input log unless `GCN_SESSION=DIR` records a session. A relative DIR is taken from the run's directory, `build/probe/NAME/`, for this one. The session's `inputs/` lands in that DIR.

```
tools/probe.sh demo 20 tests/routes/title.txt 60 GCN_FRAMETIME=1
```

That prints the run's directory as an absolute path, then a frame count (140 on an M4 Max). It exits 2 when the game isn't built. Run it again with a different NAME to get a second run to compare. Runs pile up in `build/probe/`, and prune_runs.py clears the old ones.

## playtest.sh

What happened while I played? It runs the game in its window with sound, as `build/dragoon` runs for a player. It sets `GCN_SESSION` to `build/playtest/<date>-<time>/` ("Playtest sessions" in gcn-recomp's `docs/diagnostics.md`).

The game records into that one directory what went to the sound device (`out.wav`), the mixer's blocks before the audio ring (`aid.raw`), the input log with the memory card it started from (`inputs/`) and `session.json`. Everything it prints goes to the terminal and to `stdout.txt` there, the frame times and the sound device's timing lines among it. Quit the game as usual or press Ctrl+C in the terminal, and playtest.sh prints the directory.

```
tools/playtest.sh
```

That's all a playtester runs. It runs from the repository's root, so it plays on the card and shader cache in `saves/` as `build/dragoon` does. Nothing needs sending back.

The session stays in `build/playtest/`, and session_report.py, pad_report.py and replay_session.py read it there. The recordings, the input log and the card snapshot are the player's own game data. `.gitignore` ignores them, and check_no_game_data.py fails on any that's tracked.

`--pads=N` plugs in more controllers and `--scale=N` sets the render scale. `GCN_*=value` sets any other switch, and one the session sets itself, like `GCN_WAV`, takes the value given instead. `--dry-run` prints the directory and the command without running anything, which is how its tests check it.

It exits with the game's status, or 2 when `GCN_SESSION` is already set or the game isn't built. Without `GCN_SESSION` the game records none of this.

## session_report.py

What did the sound and the pacing do in a playtest, and which stage made each click? It reads a session's directory and nothing else, so nobody has to listen.

```
tools/session_report.py build/playtest/20261022-161851
```

It prints these:

- the session's length, start, host and display, with the engine commit it ran on
- the sound device's driver, rate, channels and buffer, then each late callback, each stretch of pulls the ring couldn't fill and each ring cut, with its time
- clicks, gaps and clipped runs a minute in `out.wav` (the device stage) and in `aid.raw` (the mixer stage), through audio_clicks.py
- each device-stage click put down to a stage
- each stretch of `aid.raw` that turns to loud noise, with where it starts and ends, through noise_blocks.py
- the frame pacing from frame 300 through frametime.py, with the frames over 33 ms
- the shaders compiled while it ran, and every `FATAL` or `FAULT` line, which a guest panic ends in

A click is the mixer's when `aid.raw` clicks within 2 ms of the moment that output frame was made from. The `[audio] output frame F plays DMA frame D` lines find that moment to within about 1.3 ms. Otherwise it's the ring's when the ring cut, or a stretch of pulls it couldn't fill began or ended, within 5 ms of it.

Failing that it's the device's when a callback came late within 5 ms, and if nothing explains it, it's unexplained. Music streamed from the disc is mixed in after the ring, so a click in that music is unexplained. So is a sharp onset that the click finder flags in the 48 kHz device stage and not in the 32 kHz mixer stage.

A late callback can starve the device without a mark in `out.wav`, which holds what was handed over and not when, so the late callbacks are listed on their own too.

The noise check reads `aid.raw` only, at the DMA's 32 kHz and 10 seconds at a time. The ring interpolates to 48 kHz for the device, so `out.wav` isn't a fair input, as the noise_blocks.py section says. A stretch is a place to look, since the game's own bright sounds make short ones too, and it never changes the exit code.

In `--json` the stretches are under `noise` in noise_blocks.py's own `--json` shape, and the value is null when `aid.raw` is missing or empty. The text says `aid.raw missing` for that and `none in aid.raw` when it finds no stretch, and it gives a count with a line for each stretch otherwise.

`--system-log` also counts the Core Audio overloads macOS logged from the session's start to 5 s past the end of `out.wav`. Core Audio logs one when an IO cycle misses its deadline. It runs `/usr/bin/log show --style compact` over that window with the predicate `subsystem == "com.apple.coreaudio" AND eventMessage CONTAINS[c] "overload"`, which only reads the log.

It counts the lines from that subsystem whose message holds the word in any letter case, by process. The unified log doesn't keep messages long, so an old session's window can come back empty.

`--json` prints the whole result, and `--list N` caps the times printed for each list (default 10). A file that's missing or empty leaves its sections out and is named on stderr. It exits 2 only when the directory has no readable `session.json`.

A run-N directory, made when the game reset the console and started again, reads its own part of the session's `stdout.txt`. The report names the run that follows a reset, and says so when the game shut the console down instead.

## replay_session.py

Does a session replay faithfully? It plays a session's input log back through probe.sh in a hidden window with no sound, with `--replay`, `GCN_AIDWAV`, `GCN_AXSTATS=1` and SDL's dummy driver, as `build/probe/replay-<name>/`. Guest time is virtual, so a faithful replay hands the mixer the same blocks the session did.

It compares the SHA-1 of the session's `aid.raw` with that of as much of the replay's, says where they first differ when they do and lists the mixer clicks in the replay over the session's length. It also shows each line where the game said the replay parted from its recording, and warns when the session ran on another engine commit than the one built.

```
tools/replay_session.py build/playtest/20261022-161851
```

The replay runs to 600 frames more than 60 for each second of the session's mixer audio. probe.sh gives it twice the session's length plus two minutes. The input log is copied into the replay's directory first, since a replay keeps a scratch copy of the memory card beside the log it reads, so the session stays as it was.

An earlier replay's directory is deleted first. It exits 0 when the mixer audio matches, 1 when it differs or the replay stops short, and 2 on a bad argument, a session without `inputs/` or with an `aid.raw` of less than one frame, or a probe.sh run that failed.

## pad_report.py

Which of the pad's controls reached the game in a playtest, and on which port? It reads a session's input log, the state of each pad every time the game polled it, so it shows what the game got from the controller rather than what the controller sent.

```
tools/pad_report.py build/playtest/20261022-161851
```

For each port the game saw plugged in, it prints the gamepads put on it and taken off, from the session's `stdout.txt`. A gamepad line goes after the last frame `stdout.txt` timed before it, and times are given at 60 frames a second. Next come the buttons in the order they were first pressed, with how many times.

Each stick gets how far it went from the middle and which of its eight directions it reached, and each trigger gets its highest value and how many levels it took. A trigger that only ever read 255 was on or off. Last come the controls nobody used on that port, where a stick counts once it reaches a direction.

A run-N directory, made when the game reset the console, reads its own part of the session's `stdout.txt`.

It also reads an input log's own directory, such as one in `saves/inputs/`, without the gamepad lines. Port 1 takes the keyboard as well, so its presses may be keys. It exits 2 on a bad argument, a directory without `inputs.txt` or `inputs/inputs.txt`, a log older than version 2 or one with no pad state.

## frametime.py

How steady is the frame pacing, and what made the slow frames slow? It reads the log of a run made with `GCN_FRAMETIME=1`, prints the guest's and the renderer's mean, population standard deviation, p95, p99 and worst times from a given frame on, and lists each frame whose render time went over a limit with its batch shape and the shaders compiled in it. Then it lists each frame whose guest interval went over `--late` (25 ms unless you give it).

```
tools/probe.sh pace 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1
tools/frametime.py build/probe/pace/stdout.txt --from 300 --slow 16.7
tools/frametime.py build/probe/pace/stdout.txt --from 3400 --late 25
```

Add `--json` for machine output. Frame numbers are the `[rt]` lines'. A frame's batch is the `[ft]` line one lower.

A dumped frame is read back, which adds to its `[rt]` time, so time a run with a dump interval past its end (the 100000 above). Under `--fast` the guest interval is how fast the game goes, not its pacing. Use `--real-time` for pacing. Shader compiles show either way.

## framediff.py

Do two runs draw the same pixels? It compares every `frame_NNNNN.png` that two directories of frame dumps have in common, prints the share of pixels whose largest RGB difference is over a tolerance and the worst difference seen, and ends with a line counting the frames compared and the ones over budget. It exits 1 if any frame is over the budget. Alpha isn't compared.

framediff takes a tolerance. frame_hashes is an exact check against committed goldens. Two runs of a change need two builds and two NAMEs. Frames only one directory has are counted on stderr and don't fail the diff, which is normal when runs end at different frames.

```
tools/framediff.py build/probe/before build/probe/after --tolerance 3 --budget 0.001
```

## drawlog.py

Which cameras does a frame draw through, and what aspect does each hold? It reads a run's `stdout.txt`. The draws come from `GCN_DRAWLOG=N` with `GCN_DRAWLOG_VERBOSE=1`, and the cameras and the render callbacks that use them come from `DRAGOON_CENSUS=1`.

`cameras` prints one line per projection and viewport the frame draws through, in draw order, with its aspect (or orthographic frame), the viewport's aspect over the projection's and the draw count. The census cameras that match follow, with their stored aspect, the callbacks that set them and the ones that drew through them, by name with `--symbols analysis/symbols.txt`.

`--frame N` reads only frame N's census. Cameras that drew nothing come last.

`aspects` lists each perspective camera's stored aspect from one frame to another, with the frames it held it. It exits 1 when one changed within its viewport, which is how a widening that compounds frame on frame would show.

`setters` lists who set each camera's aspect from one frame to another. It reads the `[aspect]` line that `DRAGOON_CENSUS=1` prints for each call to `HSD_CObjSetAspect` and each perspective camera `HSD_CObjLoadDesc` loads.

Each line names a camera and where the call returns to, then where its caller returns to. It ends with the aspect the call was given and the one the camera held after, or `none` for a camera that isn't a perspective one.

`--symbols` names the function that holds each call by the sizes in `symbols.txt`, with how far in the return address is. The call is the instruction before the return address. `--cam ADDR` keeps one camera's lines.

When no line is left, `setters` says so on stderr. A camera whose aspect the game sets some other way has none.

```
tools/probe.sh race 30 tests/routes/air-ride-race.txt 4200 DRAGOON_CENSUS=1 GCN_DRAWLOG=4200 GCN_DRAWLOG_VERBOSE=1
tools/drawlog.py cameras build/probe/race/stdout.txt --frame 4200 --symbols analysis/symbols.txt
tools/drawlog.py aspects build/probe/race/stdout.txt --from 3600 --to 4199
tools/drawlog.py setters build/probe/race/stdout.txt --from 4200 --to 4200 --symbols analysis/symbols.txt
```

It exits 2 when the log lacks the lines a command needs, naming the setting that makes them.

## shader_cache.py

How many shaders does a cache or key list hold, and how many are new? It reads `saves/shaders.bin` (magic `WRSC`) and key lists (magic `GCSK`). The key size comes from the format word, and a magic or key size it doesn't know is refused. `count` prints the format and how many records and distinct keys the file holds. For a cache it also prints the distinct programs, which are the distinct `src_hash` values, since two keys can generate one source. It says how many trailing bytes it ignored, which is a record a kill cut off. `diff` prints how many distinct keys in NEW aren't in OLD and their share of NEW, and refuses two files in different formats. It counts and never lists keys.

```
tools/shader_cache.py count build/probe/demo/saves/shaders.bin
tools/shader_cache.py diff build/old-keys.bin build/probe/demo/saves/shaders.bin
```

## frame_hashes.py

Did a change alter what the renderer draws? It runs each route in `tests/hashes/manifest.txt` through probe.sh and compares the SHA-1 of every dumped frame with the golden in `tests/hashes/gl/<route>.txt`. `check` reports each frame that changed or wasn't reached. `record` rewrites the goldens, so use it only when a change to the output is on purpose. The frames are deleted once hashed and are never committed.

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

A `check` of all twelve routes took 300 s while other copies of the game ran on the same machine. Each route runs under the NAME `audio-ROUTE` in `build/probe/`. An earlier run's directory is deleted first, so the game starts from a blank memory card. The last run's directory stays, so its `[ax]` lines can explain a changed hash. List counts are multiples of 400, the interval the game prints at. It exits 0, 1 or 2 as frame_hashes.py does.

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

`analyse_file`, for other tools to call, reads a recording from disk 10 seconds at a time instead of holding every sample's second difference at once, which at 48 kHz stereo is about 5.4 MiB a second, or about 19 GiB an hour. It finds what one pass would, and its tests check that. A gap or a clipped run that goes on past a part is followed to its end, and a WAV that ends before its header says is read as far as it goes.

## audio_scorecard.py

How does each build's sound measure, route by route? It plays every route in `tests/hashes/manifest.txt` on one or more Dragoon builds and counts clicks, gaps and clipping at two stages, with nobody listening. Each build is a clone's `build/` directory with a label. A route plays on each build in turn before the next route starts, through that clone's own probe.sh, hidden, with SDL's dummy audio driver and `GCN_AXSTATS=1`. It plays twice on each build, once `--real-time` and once unpaced. The route files come from this clone, so every build plays the same presses.

```
tools/audio_scorecard.py base=/path/to/old-clone/build current=build
tools/audio_scorecard.py base=/path/to/old-clone/build current=build --routes title --json
```

Each run lasts the route's last checkpoint at 60 frames a second plus 15 s of wall-clock time (`--margin` changes the 15). It dumps that one frame (`GCN_DUMP_RANGE`). A run that doesn't reach it stops the tool with exit 2. The real-time runs go to `build/probe/scorecard-ROUTE/` in each clone and the unpaced ones to `build/probe/scorecard-unpaced-ROUTE/`. An earlier run in that directory is deleted first, so every run starts from a blank memory card and an empty shader cache. `--no-run` measures the runs already there. The five routes `scorecard.md` scores (`--routes title,menu,air-ride-race,city-trial,city-trial-4p`) take about 11 minutes a build.

The mixer stage is the unpaced run's `GCN_AIDWAV`, the DMA's blocks before the audio ring, cut to the route's last checkpoint plus the margin and read with audio_clicks.py's `--raw 32000 --period 160`. An unpaced run's game time doesn't follow the host's, so two unpaced runs of one build should give the same blocks. The pairs compared so far did, byte for byte, as `scorecard.md` says. A real-time run's clock catches up when the host falls behind, the DMA then plays a block twice, presses land on other frames and sounds move. So a real-time run's blocks say as much about the host's timing as about the build. An unpaced run gets more of the game's time than the cut in its wall-clock seconds, and a recording shorter than the cut stops the tool with exit 2. The unpaced run's log gives the highest `[ax] frames` peak (main L before the output clamp) and the sum of the `[ax] bus` lines' `clipped`, from the lines whose list count is within the cut. A list is a 160-sample block.

The device stage is the real-time run's `GCN_WAV`, which is what went to the device. That run's log gives the ring's cuts and underruns. The device stage also counts the clicks within 2 samples of a `[ring] cut` line's output frame, when the build logs cuts. Underruns are the last `[ring] fill` line's, which comes every 400 pulls of the device. The real-time run records `GCN_AIDWAV` too, for block_clicks.py.

Each stage gets clicks a minute, gaps and clipped runs as audio_clicks.py counts them. An older build that doesn't print a log value reads `not logged`, and a missing recording reads `not recorded`. When `--no-run` finds no unpaced run, as for runs made before the scorecard played one, the mixer stage and its log values read `not recorded`. `--no-run` cuts the mixer stage at `--margin`, as a run would. A table per route prints as the route finishes, then the totals, where clicks a minute is over the summed seconds. `--json` prints it all at the end, with each clone's commit and its gcn-recomp commit. The tool reads those two before the first route plays and leaves them in each run's `commits.json`. `--no-run` prints what its runs recorded, or `not recorded` for a run made before that file existed. When a build's runs recorded different commits, it joins them with `and` (`a1b2c3d and e4f5a6b`), in the header and in the JSON. It only reports, so it never exits 1.

scorecard_runs.py plays a route on a build and scorecard_measure.py scores a route's two runs. Neither has a command line.

## block_clicks.py

Do a run's mixer-stage clicks sit on the blocks the DMA played twice or delivered catching up? It reads a `GCN_AIDWAV` recording and the block log gcn-recomp writes beside it (`<file>.txt`). A replayed block has the same address as the block before, because the guest hadn't queued the next buffer. A caught-up block came while the clock caught up with the host, which only a `--real-time` run does. For each kind and for the two together it prints the blocks, the clicks in them or within 2 samples of either end, and the count chance would put there. A block log whose last block ends more than a second from the recording's end can't be that recording's, and stops it with exit 2. That check tells logs apart by length only. A log from another run of the same route ends about where this recording does, so it passes. The baseline's real-time title recording paired with current's title log printed counts and exited 0.

It also prints the stretches the marked blocks come in. A stretch is a run of marked blocks that follow one another in the log, so 5 caught-up blocks in a row are 1 stretch. A block past the recording's end is in no stretch, and a last log line a killed run cut short is skipped.

```
tools/block_clicks.py build/probe/scorecard-menu/mixer.raw
```

## click_diff.py

Which clicks does one build's unpaced recording of a route have that another's doesn't? Unpaced, the two recordings line up sample for sample, so B minus A is what the builds did differently. For each click only one has, it prints the largest B minus A within 5 ms, B minus A's second difference at the click, whether each build is silent there and whether B minus A steps at the nearest block join. A second difference of 0 means both builds have the same edge, and only the sound around it differs. `--seconds S` cuts both to S.

`--seconds S` also reads no more than S seconds of each recording, so a route's scored seconds can be compared without reading an unpaced run that went on for tens of minutes. The share of samples that are the same in both is rounded down, so 100.0% means every sample.

```
tools/click_diff.py /path/to/old-clone/build/probe/scorecard-unpaced-title/mixer.raw build/probe/scorecard-unpaced-title/mixer.raw
```

## noise_blocks.py

Where do the DMA's blocks turn to loud noise? It weighs each 160-sample block of a `GCN_AIDWAV` recording, setting its high-frequency energy against its total as the RMS of its first difference over its RMS. White noise gives about 1.41, and music and effects give far less. A block is noise-like over 1 on a channel whose peak is over 8,000, and it prints the stretches such blocks form. The game's own bright sounds, a crash for one, make short stretches too, so a stretch is a place to look rather than a fault. It reads the DMA's 32 kHz only. The ring interpolates to 48 kHz for the device, and `test_noise_blocks.py` shows that noise which flags every block at 32 kHz flags far fewer after a linear interpolation to 48 kHz, so a `GCN_WAV` recording isn't a fair input.

```
tools/noise_blocks.py build/probe/scorecard-menu/mixer.raw
```

session_report.py runs it on a playtest session's `aid.raw` through `find_source`, which reads 10 seconds at a time instead of holding the recording. It finds what one pass would, including a stretch that crosses a part's edge, and its tests check that. The command above still reads the whole file.

## clip_signs.py

Which side of full scale do a build's clipped runs sit on? audio_clicks.py counts a clipped run at 32,767 or at -32,768 as one number. A build whose clamp stops at -32,767 holds its negative clipping at a value that number leaves out, so two builds' counts only compare once they're split by sign. clip_signs.py takes the same `LABEL=BUILD_DIR`, `--routes` and `--margin` as audio_scorecard.py and reads the two recordings it scores from the runs already in each `build/probe/`, so it plays no game. The mixer is the unpaced run's recording cut where the scorecard cuts it. The device is the real-time run's whole recording. For each it prints the clipped runs and their samples at +32,767 and at -32,768, the samples at -32,767 and the lowest and highest sample. For the real-time run it also prints the highest main L peak in its log, which shows whether that run reached a loud stretch.

```
tools/clip_signs.py current=/path/to/old-clone/build next=build --routes air-ride-race
tools/clip_signs.py current=/path/to/old-clone/build next=build --routes menu --margin 150
```

A recording that isn't there reads `not recorded`, and a run that didn't reach its route's last checkpoint exits 2, as does an unpaced recording shorter than the cut.

## ax_stats.py

What did the game's voices ask the AX mixer for over a run? It reads the `[ax] pb` and `[ax] bus` lines that a run with `GCN_AXSTATS=1` prints every 400 command lists, and prints a row per count with a column per run and a total. Counts are summed over the windows, and the bus peaks take the largest window. `src0_coef=a/b/c/d` becomes four rows, and the mixer's top eight values are left out. The fields are described in `gcn-recomp/docs/diagnostics.md`. `--until N` stops at the window that ends at list N. Two unpaced runs of one route reach different lists in the same time, so it lets them be compared over the same lists. A file with no such lines up to there exits 2, and so does an `--until` of 0 or less. A column is named by its run's directory. Two runs in directories of one name, such as two clones' `audio-title`, each take the shortest trailing path that no other run shares. The same file given twice exits 2.
```
tools/audio_hashes.py check
tools/ax_stats.py build/probe/audio-title/stdout.txt build/probe/audio-air-ride-race/stdout.txt
tools/ax_stats.py before/stdout.txt build/probe/audio-title/stdout.txt --until 20000
```

## warm_shaders.py

Will a player's first session stall on shader compiles? It plays the game once so the cache is already warm. The build runs it as the `dragoon_warmup` target, unless it's configured with `-DDRAGOON_WARMUP=OFF`, has no disc or is a cross build. It runs the game hidden and fast, with SDL's dummy audio driver, with one pass per route in `tests/hashes/manifest.txt` that has no `warm-from=` setting. Each pass has a scratch directory of its own and starts from a blank memory card, as a fresh install does, because a route that finds an earlier pass's card takes other menus and builds other keys. Its `shaders.bin` starts as a copy of the player's own and gains the keys its route builds. Passes don't share a cache, so several play at once. `--jobs N` sets how many, and the default is a third of the cores, at most six. The longest start first. When they are done their caches are merged, each key once and in the manifest's order. The game doesn't inherit `GCN_INPUT`, `GCN_WAV`, `GCN_PROFILE`, `GCN_FEED_DUMP` or `GCN_SESSION`, since each names a file or route that the passes would otherwise share. `--disc FILE` names the disc image every pass plays, which a game built from the engine kit needs.

A pass plays to 900 frames past its route's last required frame, or to frame N when the route has a `warm=N` setting in the manifest. N has to be a whole number past that frame, and a route gets one at most, or the warm-up exits 2 naming the route and the manifest line.

A route with a `warm-from=ROUTE` setting gets no pass, because ROUTE's pass plays what the route does. Every program the route's own pass built still has to come from one pass or another, and only a warm-up can show that, with `shader_cache.py diff` against one that played the route.

Most courses get their programs from the three `-courses` routes, which race one course after another (`tests/routes/README.md`). A race that follows another starts from another state of the game, and there Sky Sands, Magma Flows, Frozen Hillside and Checker Knights each missed programs their own passes built late. So `air-ride-courses-1` opens with Sky Sands to frame 14,400 and `air-ride-courses-2` with Magma Flows to 12,700, while Frozen Hillside plays a pass of its own to 6,000 and Checker Knights one of 5,100 frames.

`air-ride-race`, `air-ride-celestial-valley` and `air-ride-beanstalk-park` get the programs they first draw past their own stretches, at frames 5,649 to 12,068 of their own routes, from Sky Sands, which draws them by frame 14,186. Of the keys `air-ride-race`'s own pass built, 8 come from passes other than `air-ride-courses-1`. `test_routes.py` checks that the four courses that compile late open their passes and race past those frames, but only a run can show the other routes still get their programs.

So any change to a pass or the route it plays means diffing the new warm-up's cache against the last one, both ways, with `shader_cache.py diff`. A change to what the `-courses` routes race also means running the eight `air-ride-` routes unpaced to frame 16,000 again, as under "Chained course passes" in `docs/dev/status.md`.

The merged cache is copied over `saves/shaders.bin` only once every pass has succeeded, and it only gains keys. No other file in `saves/` is touched, so the player's memory card stays as it is. A failed pass stops the ones still playing, exits 1 and leaves `saves/` as it was. `saves/.shader-warmup` holds the gcn-recomp commit and a SHA-1 each of the manifest (with the text of every route file it lists, a `warm-from=` route's too) and of warm_shaders.py. If all three match, the next run does nothing. A relink doesn't replay the game, but an edited route or tool does. A checkout asks git for the gcn-recomp commit. A source snapshot has no history, so it takes the commit from its `source-info.json`. A copy with neither exits 2. `--force` plays it anyway. A pass that outlasts twice its length at 60 fps plus 30 s is killed and counts as failed.

`--report DIR` keeps each pass's output as `NAME.log` and the cache it left as `NAME.bin` in DIR, and prints `report.txt`. A row says how many programs the game built from the starting cache before its first frame and how long that took, how many keys the pass built itself and how many of those no other pass built. It also gives the keys and programs the pass added that the starting cache and the passes before it in the manifest lacked, and the merged cache's size so far. With `GCN_FRAMETIME=1` in the environment it gives the frame the pass built its last program in.

Four more columns split each pass's seconds into starting the game, frames up to 2,000, frames 2,001 to 3,400 and the rest. A frame's share is its `[ft]` guest interval, and starting the game is the time before the first frame and after the last. They need `GCN_FRAMETIME=1` too and read 0 without it, and a closing `all` row adds up the frames, the seconds and the four splits.

```
tools/warm_shaders.py --force
env GCN_FRAMETIME=1 tools/warm_shaders.py --force --jobs 4 --saves build/probe/warm/saves --report build/probe/warm/report
tools/shader_cache.py count saves/shaders.bin
```

## prune_runs.py

Which runs in `build/probe/` are old enough to clear? probe.sh and the hash tools leave a directory per run, and their frames and recordings filled a disk once. Agents can't `rm`, so nothing else cleans them up. For each CLONE it looks at the direct children of `CLONE/build/probe/` and lists the ones with nothing newer than `--hours` (24 unless you give it). A child's age is the newest mtime of it and of anything under it, so a fresh file deep inside an old run keeps the run. A file's age is its own mtime.

Without `--delete` it prints what would go, a line each with its size and age, then the total. With `--delete` it removes those and prints the same lines and the space freed. A size is the files' lengths, not the blocks they take.

```
tools/prune_runs.py /path/to/clone
tools/prune_runs.py --hours 6 --delete /path/to/clone /path/to/old-clone
```

Names listed in `build/probe/keep`, one a line, stay. Blank lines and lines that start with `#` are skipped, and `keep` itself is never touched. Names are compared ignoring case, as the default macOS volume does, so `Keep` is never touched and a line `case` protects `Case`. A run you mean to read later, such as the last `audio-ROUTE` directory that audio_hashes.py leaves for its `[ax]` lines or the `scorecard-ROUTE` directories that audio_scorecard.py `--no-run` reads back, is prunable after 24 hours unless its name is in `keep`.

Links are never followed. A symlinked child is removed as a link and its target stays, and the age walk doesn't go through links.

A CLONE is refused when it isn't a directory, when its `build/probe` isn't `CLONE/build/probe` once links are resolved (a link to elsewhere, say) or when its `keep` isn't a readable plain file. Nothing is removed from any CLONE then, and it exits 2. A CLONE with no `build/probe` is skipped with a note on stderr. A child it can't read or remove is named on stderr and the rest still go. That exits 1, and a child that failed to remove counts as nothing freed. Otherwise it exits 0.

## routes.py

Which routes does the repository play? `tests/hashes/manifest.txt` lists them, and `tests/routes/` holds their files. routes.py reads the manifest into `Route` records and gives each route file's path, for frame_hashes.py, audio_hashes.py and warm_shaders.py. It also picks routes by name for the first two. It has no command line.

A route's `warm=N` setting goes in its `warm` field and its `warm-from=ROUTE` in its `warm_from` field, and both stay out of its probe.sh settings, since probe.sh refuses a setting it doesn't know. A bad N, a second `warm=` or `warm-from=`, both on one route or a setting that looks like a misspelled one, such as `WARM=` or `warm:`, raises `ValueError` naming the route and the manifest line. So does a `warm-from=` that names the route itself, a route the manifest doesn't list or one with a `warm-from=` of its own.

## source_info.py

What does a source snapshot hold? Its `source-info.json` names the Dragoon and gcn-recomp commits and the disc they build, as `disc_id` and `dol_sha1`. source_info.py reads and writes that file, and refuses one with a field missing or malformed, naming the file. export_source.py writes it, and warm_shaders.py reads the engine commit through it. It has no command line.

## probe_dirs.py

What happens to a probe run and its directory? It holds `remove_run`, which deletes a directory from `build/probe/` for good, and `run_probe`, which runs a probe.sh command line with its output dropped and turns a nonzero exit into an error.

`remove_run` unlinks a link inside the directory and leaves its target alone, and it refuses a directory that's itself a link. frame_hashes.py, audio_hashes.py, replay_session.py and the scorecard use both. It has no command line.

## aid_blocks.py

What does `GCN_AIDWAV` write? It holds the DMA's rate, its 160-sample block and the reader for the block log beside each recording, for block_clicks.py, click_diff.py, noise_blocks.py and scorecard_measure.py. It has no command line.

## session_log.py

What does a session's log say about its sound device, its ring and its crashes? It reads the `[audio]`, `[ring]`, `[shaders]` and `[session]` lines of a session's `stdout.txt`, with its `FATAL` and `FAULT` lines, for session_report.py. A guest panic ends in a `FATAL` line, so it counts once.

It splits the log at its `[session]` lines, so a run-N directory gets its own part. It has no command line.

## click_stages.py

Which stage made each click the sound device got? It puts each device-stage click down to the mixer, the ring, the device or nothing, by the rules under session_report.py. It has no command line.

## core_audio_log.py

How many Core Audio overloads did macOS log while a session ran? It builds the read-only `log show` command and counts the matching lines by process. Its tests read lines captured from a Mac's log, with overload lines written in their layout and never live output.

It has no command line.

## session_text.py

How does session_report.py's result read as text? It has no command line.

## check_no_game_data.py

Is anything from a disc tracked by git? It flags tracked paths that look like game data:

- Disc images and executables by suffix, `.raw` memory cards and audio recordings, `.wav` recordings and `.bin` shader caches and key lists, wherever they sit.
- A mod's game files by suffix (`.dat`, `.hps`, `.bnr`, `.elf` and `.gct`), wherever they sit.
- Anything under a top-level `build*/` or `rom/` (except the `rom/` README), and anything under a `saves/` at any depth.
- Anything under a top-level `mods/` in any letter case. A `mods/` further down, such as `tests/mods/`, is fine.
- Frame dumps (`frame_NNNNN.png` and `output_NNNNN.png`), `stdout.txt` and `panic.txt`, wherever they sit. Other PNG files are fine.
- A playtest session's `session.json`, the input log's `inputs.txt` and the `aid.raw.txt` block log, wherever `GCN_SESSION` put them. Its `.raw` and `.wav` recordings fall under the suffix rule, and a session under `build/` under the build rule.

It prints one line per path and exits 1 if it found any, so it can run in CI. It prints nothing when the tree is clean.

```
tools/check_no_game_data.py
```

## ci.py

Does the commit pass CI? ci.py runs every step of CI's four jobs, `tools`, `macos`, `kit` and `launcher`, from the repository's root. The workflow runs each job by name, so a Mac without a runner runs the same steps. It stops at the first step that fails and exits 1, and an unknown job exits 2.

The `kit` job leaves the kit in `engine kit/` and links it against stub tables in `stub game/`, with a space in each name because a player's path may have one. It deletes both first, so a second run starts from scratch there. The builds go to `build-nodisc/` and `build-kit/` and a second run reuses them, so delete those for a fresh build.

```
tools/ci.py
tools/ci.py tools launcher
```

## mutant.py

Do the tests notice when the code breaks? It changes a copy of a commit, runs a test directory there and reports whether the tests failed. A changed copy is a mutant. It's killed when the tests fail and survives when they pass, and a survivor is a gap in the tests. A spec file holds the changes, so someone checking a new test keeps it in place of a throwaway script. It can live anywhere, and it's worth committing when others should be able to run the same check.

The spec is a JSON list of mutants. Each has a `name` and a `dir` to discover tests in, relative to the repo (`tools` or `launcher/tools`). Its `replace` list holds `{file, old, new}` edits that are applied together, in order. Every `old` has to occur exactly once in its file, so a typo can't make a mutant that changes nothing. `new` may be empty. An optional `pattern` says which test files in `dir` to run. It's what `unittest discover -p` takes and it defaults to `test_*.py`. It matches file names, so it has no `/`. A `dir` and `pattern` that run no test are refused at their baseline.

```json
[
  {"name": "git() drops the exit status",
   "dir": "tools",
   "pattern": "test_export_source.py",
   "replace": [{"file": "tools/export_source.py",
                "old": "why = e.stderr.strip() or f\"exit {e.returncode}\"",
                "new": "why = e.stderr.strip()"}]}
]
```

```
tools/mutant.py build/probe/mutant/spec.json /tmp/dragoon-mutants
```

This spec sits in `build/probe/`, which git ignores, so it stays on your machine.

It prints `killed NAME`, `survived NAME` or `timeout NAME` for each mutant as it finishes, then `total N, killed K, survived S, timeout T`. A kill that isn't unittest's exit 1 says how the run ended, as in `killed NAME (exit -9)` for a signal or `(exit 5)` for no tests. Each run is `python3 -B -m unittest discover -s COPY/DIR -p PATTERN`, run from the copy. With the default pattern a mutant on `tools` takes about a minute. The example above runs one test file and takes seconds.

These keep a kill from meaning nothing.

- Every copy is a `git archive` of `--rev` (HEAD unless you say otherwise). The repo's own files are never edited or run, and uncommitted changes aren't tested. `--repo` names a checkout other than the one holding the tool.
- Each distinct `dir` and `pattern` gets a baseline on an unchanged copy first, and it has to pass and run at least one test. A selection that fails on its own would read every mutant as killed. One that runs nothing, such as a misspelled `pattern`, would read every mutant as a survivor, because Python 3.9 exits 0 for a run of no tests. The tool reads the count from unittest's `Ran N tests` line, so it doesn't depend on discover's rules or on the exit code, which is 5 on 3.12 and later.
- Each mutant runs on a fresh copy, so no stale bytecode or leftover from an earlier run is tested in its place.
- The tests get `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, as `launcher_build.py`'s tools do, your `HOME` and `TMPDIR`, `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`. The last puts what a test prints while it runs ahead of unittest's summary and not after it, so a line that looks like the summary comes before the real one. Nothing else in your environment reaches them, so no key or token in it does.
- Every copy is built and every edit applied before any test runs, so a bad edit costs no run. A `pattern` that runs no test costs its baseline.
- A run that outlasts `--timeout` (600 s unless you say otherwise, for each run) is killed along with everything it started. Whatever a run leaves running is killed when the run ends, and so is a run still going when ^C, SIGTERM or SIGHUP ends the tool.

A copy has no `.git` and, since `git archive` leaves submodules out, no gcn-recomp. A test that needs either has to skip itself, as `RealTreeTest` in `test_launcher_build.py` does. `--python FILE` picks the interpreter that runs the tests, and it defaults to the one running the tool.

DEST is a new directory outside the repo. The tool refuses one that exists or is inside the repo or, with `--repo`, inside the checkout holding the tool. The copies are built there as `baseline-N` and `mutant-N`, counting from 1 in the order the spec first uses a dir and pattern and lists a mutant. Each has the last 64 KiB of its run's output beside it as a `.log`. A mutant that breaks an import counts as killed too, so read its log before you trust a kill that matters.

When the run ends it removes the copies and keeps the logs. That holds however the run ends, even on a tool error or ^C. SIGTERM and SIGHUP are handled like ^C and end the tool with exit 143 and 129. One that was already ignored when the tool started stays ignored, so `nohup` keeps working. A signal that comes while it removes the copies is ignored, and the run ends with its usual code, so a second ^C can't leave the rest behind. DEST goes too when nothing's left in it, as when the tool stops before any test runs. It removes only what it made, so anything else that ends up in DEST stays and keeps DEST with it. The tool makes any missing parent of DEST and leaves it there, since only DEST itself is removed. A copy it can't remove is named on stderr and doesn't change the result. A signal the tool doesn't catch, such as SIGKILL or SIGQUIT, leaves the copies behind and any test still going. `--keep` keeps the copies, to read a mutant's files or run its tests by hand, and then DEST is yours to delete.

It exits 0 when every mutant was killed and 1 when any survived or timed out. It exits 2, as the other tools do, with one `mutant:` line on stderr when it couldn't decide:

- the spec or an argument is bad
- an `old` isn't found exactly once
- a file or dir isn't in the copy, or a link would take an edit outside it
- DEST exists or is inside the repo or the checkout holding the tool
- a baseline fails, times out or runs no test

A crash in the tool exits 2 as well, so it can't read as a survivor. A SIGTERM or SIGHUP ends it with 143 or 129 and prints no message of its own.

## export_source.py

What source does the launcher build? export_source.py writes a snapshot of Dragoon's HEAD, with gcn-recomp in `gcn-recomp/` at the commit HEAD pins, as `git archive` gives them. Untracked and ignored files such as `rom/game.iso`, `build/` and `saves/` never reach it. Nor does git history. It adds `source-info.json` (see source_info.py) and `source-manifest.txt`, which lists every other file as a `<sha256>  <path>` line sorted by path.

```
tools/export_source.py /tmp/dragoon-source
```

It writes nothing and exits 2 when:

- a tracked file in either repository has uncommitted changes. Untracked files don't count, since `git archive` leaves them out anyway
- gcn-recomp is checked out at another commit than HEAD pins, or isn't checked out
- OUT isn't empty
- git or tar fails while writing, which leaves OUT missing or empty again

`--repo` names a checkout other than the one holding the tool. A missing OUT is made. git comes from `PATH` and tar is `/usr/bin/tar`.

Its `src_digest` is the SHA-256 of `src/`'s lines in a `source-manifest.txt`. It comes out the same from a snapshot and from a clean checkout of its commit, one with nothing untracked, ignored or changed in `src/`. engine_kit.py writes it to the kit, and launcher_build.py checks it.

## launcher_build.py

How does the launcher build the game? launcher_build.py is its recipe, and a developer can run it from a shell. Given a snapshot from export_source.py, a kit from engine_kit.py, the player's disc and every tool by full path, it builds `<data>/game/<id>/Dragoon.app` and points `<data>/game/current` at it. The player's Mac runs no CMake or Ninja and never builds SDL. It prints one JSON event per line on stdout (the format is in `--help`). It writes every line the tools print to `--log`, with each command, each step's time and how much `--data` and `--cache` hold after it. That measurement never fails a step. A file removed while it's measured counts as nothing, and any other error is written to the log in its place.

| Step | What it does |
|---|---|
| recompile | Empties `<cache>/build`. There the snapshot's `extract_dol.py` takes `main.dol` from the disc, checked against the disc ID and SHA-1 in `source-info.json`, and its `recomp.py` writes the game's C to `gen/` |
| compile | Runs make on the kit's Makefile with a job per core, which compiles `gen/*.c` and links `dragoon` with the kit. Each compile line make prints becomes a progress event |
| warmup | Runs the snapshot's warm_shaders.py on the disc and a copy of the player's shader cache, one progress event per pass |
| package | Wraps the game in an app sealed ad hoc, with a `stamp.json` naming both commits and the SDK |
| swap | Points `game/current` at the new build, then installs the warmed cache in `<data>/saves`, where a failure is only a warning |

The tools run with `PATH=/usr/bin:/bin:/usr/sbin:/sbin` and five other variables, listed in `--help`, so nothing Homebrew or MacPorts installed reaches the build. The snapshot and the kit are only read, and Python runs with `-B`, so a build leaves the launcher's seal as it was.

Before the swap nothing in `<data>` changes but the new `game/<id>`. A build that fails before the swap leaves the old game current and `saves/` as it was, and a package step that fails removes its `game/<id>`. Earlier builds stay in `<data>/game` for the launcher to delete.

Once `game/current` points at the new build, the build has succeeded, so a `--log` line the recipe can't write afterward is lost and fails nothing. A shader cache file that can't be installed afterward is a `warning` event, and the run still prints `done` and exits 0 with that file left as it was. When only the stamp can't be installed, the new cache stays beside the old stamp, so the next build warms again.

A SIGTERM, which is how the launcher cancels, exits 143 once the running step has cleaned up. It leaves no half-made `game/<id>` and no temp file in `saves/`, and one that lands after the swap leaves the new game current.

The swap makes a temporary link, `.current.<pid>.partial`, in `<data>/game` and renames it over `game/current`. A SIGTERM that lands right after the link is made can leave it there, and the next swap removes it.

A second build while one runs exits 3 at `<cache>/build.lock` without touching anything, its `--log` included. A kit whose `kit.mk` names a gcn-recomp commit other than the one in the snapshot's `source-info.json` or a `src/` digest other than the snapshot's, or names none, exits 2 the same way, with an error event at step `kit`. Its `engine.o` and headers wouldn't match the generated C.

```
tools/launcher_build.py --source /tmp/dragoon-source --kit /tmp/engine-kit \
  --disc "$HOME/Kirby Air Ride (USA).gcm" \
  --data /tmp/dragoon-data --cache /tmp/dragoon-cache --log /tmp/dragoon-build.log \
  --make /Library/Developer/CommandLineTools/usr/bin/make \
  --cc /Library/Developer/CommandLineTools/usr/bin/clang \
  --cxx /Library/Developer/CommandLineTools/usr/bin/clang++ \
  --python /Library/Developer/CommandLineTools/usr/bin/python3 \
  --sdk /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk
```

A first build on an M4 Max, with the Command Line Tools' make 3.81, clang 21 and the 26.5 SDK, took 95.2 s. That's 4.2 s to recompile, 18.0 s to compile and link, 72.7 s to warm up and 0.1 s to package. `--data` and `--cache` held 482 MB at most, once the game was packaged and before `<cache>/build` was deleted, and 54 MB afterwards. A second build of the same commit took 22.2 s, because the warm-up found its stamp current.

`--no-warmup` skips the warm-up. `--keep-build` keeps `<cache>/build`, which is deleted after a good build otherwise.

## engine_kit.py

What does a player's Mac need to build the game without CMake, Ninja or SDL's source? engine_kit.py packs it from a build configured with no disc and a deployment target, once `runtime_check` and `SDL3-static` are built. The kit holds `engine.o` (runtime_check's objects joined by `ld -r`, so the link takes all of them), `libSDL3.a`, `recomp.h` and `compat.h`, `kit.mk`, the Makefile from `launcher/kit/` and the licenses of gcn-recomp, SDL and the hidapi inside SDL. `kit.mk` takes `GAME_CFLAGS` from the `game_cflags.txt` gcn-recomp's configure wrote to the build directory, `LINK_FLAGS` from its `game_ldflags.txt` and `GAME_LIBS`, the frameworks and libraries, from its `game_libs.txt`. It also holds `MACOSX_MIN`, the build's deployment target. Its `ENGINE_COMMIT` is the gcn-recomp commit in the `gcn_engine_sha.h` that runtime_check was compiled with. So every flag and framework the game gets comes from CMake, and launcher_build.py can tell which snapshots the kit builds.

runtime_check compiles Dragoon's `src/` too, so `engine.o` has the hooks the generated C calls, and the player's Mac never compiles `src/`. The kit's `SRC_SHA256` is export_source.py's `src_digest` of the build's `src/`. launcher_build.py pairs a kit with a snapshot by both `ENGINE_COMMIT` and `SRC_SHA256`.

That digest names what `engine.o` holds only when `src/` is a clean checkout that runtime_check compiled. So engine_kit.py refuses a `src/` where `git status --ignored` shows anything, and one with a file newer than runtime_check's objects of `src/`.

```
cmake -S . -B build-kit -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 -DGAME_ISO=
ninja -C build-kit runtime_check SDL3-static
tools/engine_kit.py --build build-kit --out build-kit/kit --strip-debug
```

CI's `kit` job runs these, links the kit against `tests/kit/stub_tables.c`, empty tables that stand in for the recompiler's output, and uploads the kit as the `engine-kit` artifact. A framework missing from `game_libs.txt` fails that link.

On the player's side, launcher_build.py has the Command Line Tools' python3 run `extract_dol.py` and `recomp.py` into a directory, and then the kit's Makefile compiles `gen/*.c` there and links `./dragoon`. `KIT` is named on the command line, since make splits the Makefile's own path at its spaces, and the kit's path may have them:

```
make -f "$KIT/Makefile" -j16 KIT="$KIT" SDK=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  CC=/Library/Developer/CommandLineTools/usr/bin/clang CXX=/Library/Developer/CommandLineTools/usr/bin/clang++
```

A `$`, `"`, `` ` ``, `:` or `;` in `KIT`, `SDK`, `CC` or `CXX` stops make with an error, since make or the shell would read it as its own. A space in any of the four is fine. Finder shows a `:` in a name as a `/`. The launcher passes paths it controls. A new `kit.mk` or kit header rebuilds every object.

A build with a `GAME_ISO` is refused, since its `main.o` would carry the disc's path. So is a build with no deployment target, or one missing any of the three files. gcn-recomp's configure writes the two link files together, and neither when it can't write every library, with a warning saying why. A `game_libs.txt` that names a path is refused too, since a player's Mac may not have it. So is a `gcn_engine_sha.h` that names no commit, or one with `-dirty` after it, since the kit's headers and `engine.o` then match no commit a snapshot can name. `ld -r` turns the objects' DWARF into a debug map naming the build's own `.o` files, which a player doesn't have. `--strip-debug` drops that map and `libSDL3.a`'s DWARF. The kit is written under a temporary name and renamed into place, so a failed run leaves no OUT. It exits 1 when ld or strip fails and 2 on a build it can't make a kit from. The tests use objects compiled from one-line C, and compilers that only record their arguments under the real `make`, with the kit, the directory holding `gen/`, the SDK and the compilers at paths with spaces.

## check_bundle.py

Does the launcher ship anything game-derived? The disc never reaches CI, so nothing can compare bytes with the game. check_bundle.py looks for the shapes game data takes in `Dragoon.app`, or in a DMG that it attaches read-only and detaches again. Run it on the unsigned app and again on the signed DMG, since the manifest allows the `_CodeSignature` that signing adds.

| Check | What fails |
|---|---|
| paths | A file, link or empty directory outside the source snapshot that `launcher/bundle-manifest.txt` doesn't list. Anywhere, a path that `check_no_game_data.py` flags or that a build leaves behind (`gen/`, `rels/`, `inputs/`, `main.dol`, `CMakeCache.txt`, `build.ninja`, `memcard_*`, `.shader-warmup`, in any letter case) |
| executables | A file that starts with a Mach-O magic at a path the manifest doesn't list for one, such as a built `dragoon`. An ar archive (`!<arch>`, or a fat file holding one) or a file named `.a` or `.o` in any letter case that has no `object` or `engine` line of its own, and an engine that isn't a thin Mach-O object ending where its string table does. Any of those or any Mach-O that can't be read whole, such as an archive member that isn't the opening symbol table or a thin Mach-O ending at its string table. One that defines `fn_` and 8 hex digits or `g_recomp_*` in any architecture, the names the recompiler gives the game's functions and tables |
| content | The GameCube disc magic at offset 0x1C, a `CISO` header, or the disc ID anywhere outside the snapshot, or more than once in the engine object. The engine carries the disc ID once, as a public constant |
| source | A snapshot that differs from `export_source.py`'s output for the commit, file by file by SHA-256. A dev tree's `rom/game.iso` link or empty `build/` shows up here |
| size | An app or a DMG over its budget in the manifest |
| DMG | Anything besides `Dragoon.app` and an `Applications` link to `/Applications` |

```
tools/check_bundle.py launcher/dist/Dragoon.app --commit SHA
tools/check_bundle.py launcher/dist/Dragoon.dmg --commit SHA
```

It prints one `kind: path (detail)` line per finding and nothing when the bundle is clean. Paths are relative to the app. It exits 0 when clean, 1 with findings and 2 when it couldn't check. A checkout that isn't at `--commit`, a manifest it can't read and a DMG that won't attach all exit 2. `--repo` names the Dragoon checkout the reference snapshot is exported from. It defaults to the one holding the tool. `--manifest` names another manifest.

A path that no manifest line allows is a finding, so a new file in the app starts as a line in the manifest. The app's budget in the manifest is a placeholder until the launcher and Sparkle are built. The engine kit sits at `Contents/Resources/kit/`, beside the snapshot.

## bundle_manifest.py

What may the app hold? It reads `launcher/bundle-manifest.txt`. That file names the source snapshot's directory and the two size budgets. Everything allowed outside the snapshot has a line naming its kind, such as a plain file, a directory prefix, a Mach-O executable or a symlink with its target. Static libraries and objects have lines of their own, and one of them at most is the kit's engine, the only file outside the snapshot that may hold the disc ID. The format is at the top of the module. It has no command line.

## bundle_checks.py

What does each check look at? bundle_checks.py holds the six checks above as functions that return findings, and the `Finding` they print as. It has no command line.

## bundle_objects.py

How does check_bundle.py read a Mach-O file or an archive? nm skips an archive member that isn't an object without a word, so bundle_objects.py reads each member's header first, in a plain archive and in each archive slice of a fat file. Only the first member may be the symbol table, under one of its four `__.SYMDEF` names. Every other member has to be a thin Mach-O that ends where the string table its `LC_SYMTAB` names does, as clang and ld end one, with fewer than 8 newlines after it, as ar and strip pad one. Then `nm --defined-only -j -arch all` lists what the file defines in every architecture, since nm shows a fat file's host slice alone by default. The tests compile objects from one-line C with the system's `cc` and archive them with `ar` and `lipo`. They also build archives byte by byte. It has no command line.

## bundle_tree.py

What does an app tree hold? It lists the regular files with their sizes, the symlinks with their targets, the empty directories and any odd entries such as pipes, and never follows a link. It has no command line.

## bundle_dmg.py

How does check_bundle.py look inside a DMG? It attaches the image with `hdiutil attach -readonly -nobrowse -mountpoint` at a fresh temporary directory and always detaches it, forcing the detach if the volume is busy or the plain one hangs. An attach gets two minutes and a detach one, so a stuck hdiutil can't hold a CI job until its own timeout. A detach that fails after the checks ran still prints their findings, with the error on stderr. The tests fake hdiutil. It has no command line.

## make_app.py

How do the pieces become `Dragoon.app`? make_app.py lives in `launcher/tools/`. It writes `OUT/Dragoon.app` around the launcher that `swift build -c release` made. It never runs SwiftPM, so the launcher has to be built first. The app also holds an engine kit, which is CI's `engine-kit` artifact or one made by hand with `engine_kit.py`, and a snapshot from `export_source.py`.

| In the app | What it holds |
|---|---|
| `Contents/MacOS/Dragoon` | The launcher, mode 0755 |
| `Contents/Resources/kit/` | The kit, byte for byte |
| `Contents/Resources/source/` | The snapshot, byte for byte |
| `Contents/Resources/licenses/Dragoon.txt` | The snapshot's `LICENSE` |
| `Contents/Info.plist` | `launcher/Info.plist` with `CFBundleShortVersionString` and `CFBundleVersion` set to `--version` |

```
launcher/tools/make_app.py --out launcher/dist --version 0.1.0 --launcher /tmp/Dragoon \
  --kit /tmp/engine-kit --source /tmp/dragoon-source
tools/check_bundle.py launcher/dist/Dragoon.app --commit SHA
```

The app is sealed with `codesign --force --sign -`, ad hoc, with no hardened runtime and no `--deep`, as a dev build is. `sign_and_package.py` signs a copy for release. `--version` is one to three numbers joined by dots. `OUT` is made if it's missing. The app is built under a temporary name in it and renamed into place. A failed run removes that directory and the directories it made for `OUT`, so it leaves nothing behind. It only removes a directory that's empty by then, so a second run sharing a new `OUT` keeps its app. The kit and the snapshot are only read, and `launcher/dist/` is git-ignored for the app to go in.

It exits 0 when the app is there and prints its path. A step that failed, such as codesign, exits 1. It exits 2 with one line saying why, having written nothing, when:

- an argument is missing or bad, or `OUT` is the kit or the snapshot or below one, however its name is spelled
- `OUT/Dragoon.app` already exists
- the kit lacks a file that `launcher/bundle-manifest.txt` lists, or holds one it doesn't
- the snapshot lacks `source-info.json`, `source-manifest.txt` or `LICENSE`, or its files aren't the ones `source-manifest.txt` lists with their hashes, because one is missing, extra or edited
- the kit is from another gcn-recomp commit or another `src/` than the snapshot's, which `kit_problem` in `launcher_build.py` decides for both tools

The tests fake codesign with a script that records its call, so they sign nothing. Every path in them has a space.

## sign_and_package.py

Can one command sign the launcher, put it in a DMG and notarize it? It lives in `launcher/tools/`, with the commands it runs in `sign_plan.py` beside it. It copies the app to `OUT/dmg-root/Dragoon.app` next to an `Applications` link and signs the copy inside out, so the app you pass stays as it was. With a Developer ID identity every item gets `codesign -f -s IDENTITY -o runtime --timestamp`, as notarization requires. None gets `--deep`. Sparkle's `Autoupdate`, `Updater.app` and framework go first when the app has them, without the XPC services a launcher that isn't sandboxed doesn't ship. An app that still has them is refused. The app goes last, and the launcher claims no entitlements. The engine kit's files are sealed with the app as resources, and none is signed on its own.

`codesign --verify --strict --deep` then checks the signed app before the DMG is made, so a broken signature costs no notarization round trip. `hdiutil create -format UDZO` makes `OUT/Dragoon.dmg`, tried up to three times because it sometimes fails with Resource busy, and `codesign -i` signs it with `--timestamp` for a Developer ID identity and `--timestamp=none` for ad hoc. With a Team API key, `xcrun notarytool submit --wait` notarizes the DMG and `xcrun stapler staple` staples it. A notarized DMG then gets `xcrun stapler validate` and the `spctl` assessments for an app and for a disk image.

```
launcher/tools/sign_and_package.py --app launcher/dist/Dragoon.app --identity - --out /tmp/dragoon-release
launcher/tools/sign_and_package.py --app launcher/dist/Dragoon.app --identity "Developer ID Application: NAME (TEAM)" \
  --out dist --notary-key AuthKey.p8 --notary-key-id KEYID --notary-issuer ISSUER --dry-run
```

`--identity -` signs ad hoc, with `--timestamp=none` and without `-o runtime`. Apple's timestamp server wants an Apple identity and the internet, and the runtime's library validation would stop an ad hoc launcher loading an ad hoc Sparkle, since neither has a team ID. With no notary key the run stops after signing and says the DMG isn't notarized. Apple rejects an ad hoc signature, so `--identity -` with a notary option is refused. `--dry-run` prints every command and runs none. Each command prints as a `+` line as it runs, and the DMG's path is the last line of a finished run. The key file is only named to notarytool and never read. A rejected notarization stops the run and prints the submission ID with the `notarytool log` command that shows why. A notarization still running after `--notary-timeout MINUTES` (30 unless you give it) is cut off, and the run prints the `notarytool history` command that finds the submission. The timeout takes up to 1440 minutes, a day. A re-run needs an empty `OUT` and uploads again, so give a slow submission a longer timeout instead. `OUT` can't be inside the app, where `ditto` would copy the app into itself. It exits 0 when the DMG is made, 1 when a command failed and 2 on a bad argument.

The tests fake codesign, ditto, hdiutil, xcrun and spctl with scripts that record their calls, so they sign nothing.

## swift_test.py

How do the launcher's Swift tests run on a Mac with the Command Line Tools and no Xcode? swift_test.py lives in `launcher/tools/` and runs `swift test --package-path launcher` with its own arguments passed on (`--filter NAME` works), exiting with swift's status. Plain `swift test` fails there with `no such module 'Testing'`, because the tools keep `Testing.framework` where neither the compiler nor the test runner looks.

When `xcode-select -p` names a directory that holds `Library/Developer/Frameworks/Testing.framework` and has no `Platforms` directory, whatever the directory is called, the tool adds `-Xswiftc -F` for that `Frameworks` directory and `-Xlinker -rpath` for it and for `Library/Developer/usr/lib`, where `lib_TestingInterop.dylib` is. Xcode's developer directory has a `Platforms` directory, so with Xcode selected, or when `xcode-select` fails, it adds nothing. The flags stay out of `Package.swift`, because `unsafeFlags` there would bake one Mac's paths into the package.

```
launcher/tools/swift_test.py
launcher/tools/swift_test.py --filter FileSystemTests
```

The swift command prints on stderr as a `+` line before it runs, and `xcode-select` prints nothing. A signal that ends swift counts as 128 plus its number, and exit 2 means swift couldn't be started. Every argument goes to swift, `--help` included, so the tool has no help of its own and `swift_test.py --help` prints swift's.

The tests fake `xcode-select` and swift with scripts that record their calls, and they build fake developer directories at paths with spaces. Two of them run the tool as a script with the fake swift found on `PATH` and the real `xcode-select` answering from `DEVELOPER_DIR`, so they see what swift prints. CI's launcher job runs the tool, and with Xcode on GitHub's runner it adds nothing there.

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
