# Tools

Each tool answers one question. Start with probe.sh, which makes the runs the others read. To playtest with sound, run playtest.sh. session_report.py explains the session afterwards. Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`.

## Conventions

Every tool takes `--help`, which prints its usage and what it reads. Results go to stdout, including the failures a tool checks for. Errors go to stderr as one line naming the file and what's wrong, and so do warnings that leave the exit code alone. A traceback means a bug in the tool.

| Exit | Means |
|---|---|
| 0 | The tool ran and nothing failed |
| 1 | It ran and found what it checks for, such as a changed frame or a frame over budget |
| 2 | It couldn't run: a bad argument, or an input it can't read or doesn't understand |

frametime.py, shader_cache.py, audio_clicks.py and session_report.py only report, so they never exit 1.

## probe.sh

How does the game behave when nobody is playing it? It runs the game in a hidden window for a number of seconds, feeds it a route of button presses and dumps every Nth frame as a PNG. A run leaves its frames (`frame_NNNNN.png`), its log (`stdout.txt`), its memory card (`saves/memcard_a.raw`), its shader cache (`saves/shaders.bin`) and, after a crash, `panic.txt` in `build/probe/NAME/`. A windowed run uses SDL's dummy audio driver, so it's silent. A `--bench` run leaves the driver to SDL and plays through the real device unless `SDL_AUDIO_DRIVER=dummy` is set, which audio_hashes.py does. Audio never paces the guest, so the dummy driver doesn't change timing. A new NAME starts from a blank memory card, and a NAME that's run again keeps the card its last run left behind.

After the NAME and seconds come an input script or a route file from `tests/routes/`, the dump interval and any settings. A setting is `GCN_*=value` (the list is in `gcn-recomp/docs/diagnostics.md`), `--pads=N`, `--real-time`, `--scale=N`, `--bench`, `--log=LIST`, `--replay=DIR` or `--exit-after=N`. `--log=dsp,ai` turns on those log categories in the game. An unknown category stops the game at once, and `stdout.txt` names it. `--replay=DIR` plays back the input log in DIR (an absolute path), and `--exit-after=N` quits once N frames have been shown. These three work in windowed runs only, because `dragoon_bench` takes none of them, so probe.sh refuses them with `--bench`. A run keeps no input log unless `GCN_SESSION=DIR` records a session, as playtest.sh does. A relative DIR is taken from the run's directory. A run ends early when the game exits. `tools/probe.sh --help` prints the settings. Route files are described in `tests/routes/README.md`.

```
tools/probe.sh demo 20 tests/routes/title.txt 60 GCN_FRAMETIME=1
```

That prints the run's directory as an absolute path, then a frame count (140 on an M4 Max). It exits 2 when the game isn't built. Run it again with a different NAME to get a second run to compare.

## playtest.sh

What happened while I played? It runs the game in its window with sound, as `build/dragoon` runs for a player. It sets `GCN_SESSION` to `build/playtest/<date>-<time>/` ("Playtest sessions" in gcn-recomp's `docs/diagnostics.md`). The game records into that one directory what went to the sound device (`out.wav`), the mixer's blocks before the audio ring (`aid.raw`), the input log with the memory card it started from (`inputs/`) and `session.json`. Everything it prints goes to the terminal and to `stdout.txt` there, the frame times and the sound device's timing lines among it. Quit the game as usual or press Ctrl+C in the terminal, and playtest.sh prints the directory.

```
tools/playtest.sh
```

That's all a playtester runs. It runs from the repository's root, so it plays on the card and shader cache in `saves/` as `build/dragoon` does. Nothing needs sending back. The session stays in `build/playtest/`, which git ignores. session_report.py and replay_session.py read it there. The recordings, the input log and the card snapshot are the player's own game data. They're never committed, and check_no_game_data.py fails on any of them.

`--pads=N` plugs in more controllers and `--scale=N` sets the render scale. `GCN_*=value` sets any other switch, and one the session sets itself, like `GCN_WAV`, takes the value given instead. `--dry-run` prints the directory and the command without running anything, which is how its tests check it. It exits with the game's status, or 2 when `GCN_SESSION` is already set or the game isn't built. Without `GCN_SESSION` the game records none of this.

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
- the frame pacing from frame 300 through frametime.py, with the frames over 33 ms
- the shaders compiled while it ran, and every panic, `FATAL` or `FAULT` line

A click is the mixer's when `aid.raw` clicks within 2 ms of the moment that output frame was made from. The `[audio] output frame F plays DMA frame D` lines find that moment to within about 1.3 ms. Otherwise it's the ring's when the ring cut, or a stretch of pulls it couldn't fill began or ended, within 5 ms of it. Failing that it's the device's when a callback came late within 5 ms, and if nothing explains it, it's unexplained. Music streamed from the disc is mixed in after the ring, so a click in that music is unexplained. So is a sharp onset that the click finder flags in the 48 kHz device stage and not in the 32 kHz mixer stage. A late callback can starve the device without a mark in `out.wav`, which holds what was handed over and not when, so the late callbacks are listed on their own too.

`--system-log` also counts the Core Audio overloads macOS logged from the session's start to 5 s past the end of `out.wav`. Core Audio logs one when an IO cycle misses its deadline. It runs `/usr/bin/log show --style compact` over that window with the predicate `subsystem == "com.apple.coreaudio" AND eventMessage CONTAINS[c] "overload"`, which only reads the log. It counts the lines from that subsystem whose message holds the word in any letter case, by process. The unified log doesn't keep messages long, so an old session's window can come back empty.

`--json` prints the whole result, and `--list N` caps the times printed for each list (default 10). A run-N directory, made when the game reset the console, reads its own part of the session's `stdout.txt`. A file that's missing or empty leaves its sections out and is named on stderr. It exits 2 only when the directory has no readable `session.json`.

## replay_session.py

Does a session replay faithfully? It plays a session's input log back through probe.sh in a hidden window with no sound, with `--replay`, `GCN_AIDWAV`, `GCN_AXSTATS=1` and SDL's dummy driver, as `build/probe/replay-<name>/`. Guest time is virtual, so a faithful replay hands the mixer the same blocks the session did. It compares the SHA-1 of the session's `aid.raw` with that of as much of the replay's, says where they first differ when they do and lists the mixer clicks in the replay over the session's length. It also shows each line where the game said the replay parted from its recording, and warns when the session ran on another engine commit than the one built.

```
tools/replay_session.py build/playtest/20261022-161851
```

The replay runs to 600 frames more than 60 for each second of the session's mixer audio. probe.sh gives it twice the session's length plus two minutes. The input log is copied into the replay's directory first, since a replay keeps a scratch copy of the memory card beside the log it reads, so the session stays as it was. An earlier replay's directory goes to the Trash. It exits 0 when the mixer audio matches, 1 when it differs or the replay stops short, and 2 on a bad argument, a session without `inputs/` or `aid.raw`, or a probe.sh run that failed.

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

The manifest has one route per line. A line gives the name, the seconds to run, the dump interval, the frames the route must reach and any extra probe settings. Pass route names to run only those. A `check` of all five routes takes about two minutes.

```
tools/frame_hashes.py check title
```

## audio_hashes.py

Did a change alter what the AX mixer outputs? It runs each route in `tests/hashes/manifest.txt` through probe.sh as a `--bench` run with `GCN_AXSTATS=1` and SDL's dummy audio driver, and compares the `[ax] hash list=N fnv=X` lines with the rows in `tests/hashes/audio/<route>.txt`. The hash runs from boot, so a row shows that nothing the mixer wrote before list N changed. `check` reports each row that changed, and fails a run that doesn't reach a row's list count. `record` rewrites a route's golden at `--lists`, or at the list counts it already has, so use it only when a change to the sound is on purpose. No audio is kept, only the hashes. The goldens hold for unpaced runs only, and their header says so.

```
tools/audio_hashes.py check air-ride-race
tools/audio_hashes.py record title --lists 7200,20000
```

A `check` of all five routes takes about two minutes. Each route runs under the NAME `audio-ROUTE` in `build/probe/`. An earlier run's directory is moved to the Trash first, so the game starts from a blank memory card. The last run's directory stays, so its `[ax]` lines can explain a changed hash. List counts are multiples of 400, the interval the game prints at. It exits 0, 1 or 2 as frame_hashes.py does.

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

An hour's recording is too long to hold every sample's second difference at once. `analyse_long`, which session_report.py uses, works through it 30 seconds at a time and finds what one pass would. Its tests check that it matches one pass.

`--marks FILE` reads sample indices from a text file (one a line) and counts the clicks near one and the marks with a click near them. With `GCN_AXSTATS=1` the game prints a `[ring] cut N frames at output frame F` line each time the audio ring throws away what it has too much of, and F is an index into the `GCN_WAV` recording.

```
tools/probe.sh title-cuts 90 tests/routes/title.txt 100000 --real-time GCN_WAV=out.wav GCN_AXSTATS=1
sed -n -E 's/^\[ring\] cut .* frame ([0-9]+)$/\1/p' build/probe/title-cuts/stdout.txt > build/probe/title-cuts/cuts.txt
tools/audio_clicks.py build/probe/title-cuts/out.wav --marks build/probe/title-cuts/cuts.txt
```

## warm_shaders.py

Will a player's first session stall on shader compiles? It plays the game once so the cache is already warm. The build runs it as the `dragoon_warmup` target, unless it's configured with `-DDRAGOON_WARMUP=OFF`, has no disc or is a cross build. It runs the game hidden and fast, with SDL's dummy audio driver, in a scratch directory, with one pass per route in `tests/hashes/manifest.txt`. Each pass starts from a blank memory card, as a fresh install does, because a route that finds an earlier pass's card takes other menus and builds other keys. The scratch `shaders.bin` starts as a copy of the player's own and grows pass by pass.

The cache is copied over `saves/shaders.bin` only once every pass has succeeded, and it only gains keys. No other file in `saves/` is touched, so the player's memory card stays as it is. A failed pass exits 1 and leaves `saves/` as it was. `saves/.shader-warmup` holds the gcn-recomp commit and a SHA-1 each of the manifest (with the route files' text) and of warm_shaders.py. If all three match, the next run does nothing. A relink doesn't replay the game, but an edited route or tool does. A copy with no gcn-recomp checkout exits 2. `--force` plays it anyway. A pass that outlasts twice its length at 60 fps plus 30 s is killed and counts as failed.

```
tools/warm_shaders.py --force
tools/shader_cache.py count saves/shaders.bin
```

## routes.py

Which routes does the repository play? `tests/hashes/manifest.txt` lists them, and `tests/routes/` holds their files. routes.py reads the manifest into `Route` records and gives each route file's path, for frame_hashes.py, audio_hashes.py and warm_shaders.py. It also picks routes by name for the first two. It has no command line.

## probe_dirs.py

What happens to a probe run's directory? It holds `trash`, which frame_hashes.py, audio_hashes.py and replay_session.py use to move a directory from `build/probe/` into `~/.Trash` under a time-stamped name. It has no command line.

## session_log.py

What does a session's log say about its sound device, its ring and its crashes? It reads the `[audio]`, `[ring]`, `[shaders]` and `[session]` lines of a session's `stdout.txt`, with its panic, `FATAL` and `FAULT` lines, for session_report.py. It splits the log at its `[session]` lines, so a run-N directory gets its own part. It has no command line.

## click_stages.py

Which stage made each click the sound device got? It puts each device-stage click down to the mixer, the ring, the device or nothing, by the rules under session_report.py. It has no command line.

## core_audio_log.py

How many Core Audio overloads did macOS log while a session ran? It builds the read-only `log show` command and counts the matching lines by process. Its tests read lines captured from a Mac's log, with overload lines written in their layout, never live output. It has no command line.

## session_text.py

How does session_report.py's result read as text? It has no command line.

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
