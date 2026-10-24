# Tools

Each tool answers one question. Start with probe.sh, which makes the runs the others read. Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`. The launcher's own helpers live in `launcher/tools/` with their tests beside them, so run those with `python3 -m unittest discover -s launcher/tools -p 'test_*.py'` too. Both run under the Command Line Tools' Python 3.9 and under a newer one.

## Conventions

Every tool takes `--help`, which prints its usage and what it reads. Results go to stdout, including the failures a tool checks for. Errors go to stderr as one line naming the file and what's wrong, and so do warnings that leave the exit code alone. A traceback means a bug in the tool.

| Exit | Means |
|---|---|
| 0 | The tool ran and nothing failed |
| 1 | It ran and found what it checks for, such as a changed frame or a frame over budget |
| 2 | It couldn't run: a bad argument, or an input it can't read or doesn't understand |

frametime.py, shader_cache.py, audio_clicks.py, audio_scorecard.py, block_clicks.py, click_diff.py, noise_blocks.py, clip_signs.py and ax_stats.py only report, so they never exit 1.

## probe.sh

How does the game behave when nobody is playing it? It runs the game in a hidden window for a number of seconds, feeds it a route of button presses and dumps every Nth frame as a PNG. A run leaves its frames (`frame_NNNNN.png`), its log (`stdout.txt`), its memory card (`saves/memcard_a.raw`), its shader cache (`saves/shaders.bin`) and, after a crash, `panic.txt` in `build/probe/NAME/`. A windowed run uses SDL's dummy audio driver, so it's silent. A `--bench` run leaves the driver to SDL and plays through the real device unless `SDL_AUDIO_DRIVER=dummy` is set, which audio_hashes.py does. Audio never paces the guest, so the dummy driver doesn't change timing. A new NAME starts from a blank memory card, and a NAME that's run again keeps the card its last run left behind.

After the NAME and seconds come an input script or a route file from `tests/routes/`, the dump interval and any settings. A setting is `GCN_*=value` (the list is in `gcn-recomp/docs/diagnostics.md`), `--pads=N`, `--real-time`, `--scale=N`, `--bench` or `--log=LIST`. `--log=dsp,ai` turns on those log categories in the game. It works in windowed runs only, because `dragoon_bench` takes no `--log`, so probe.sh refuses it with `--bench`. An unknown category stops the game at once, and `stdout.txt` names it. `tools/probe.sh --help` prints the settings. Route files are described in `tests/routes/README.md`.

```
tools/probe.sh demo 20 tests/routes/title.txt 60 GCN_FRAMETIME=1
```

That prints the run's directory as an absolute path, then a frame count (140 on an M4 Max). It exits 2 when the game isn't built. Run it again with a different NAME to get a second run to compare. Runs pile up in `build/probe/`, and prune_runs.py clears the old ones.

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

How many shaders does a cache or key list hold, and how many are new? It reads `saves/shaders.bin` (magic `WRSC`) and key lists (magic `GCSK`). The key size comes from the format word, and a magic or key size it doesn't know is refused. `count` prints the format and how many records and distinct keys the file holds. For a cache it also prints the distinct programs, which are the distinct `src_hash` values, since two keys can generate one source. It says how many trailing bytes it ignored, which is a record a kill cut off. `diff` prints how many distinct keys in NEW aren't in OLD and their share of NEW, and refuses two files in different formats. It counts and never lists keys.

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

The mixer stage is the unpaced run's `GCN_AIDWAV`, the DMA's blocks before the audio ring, cut to the route's last checkpoint plus the margin and read with audio_clicks.py's `--raw 32000 --period 160`. An unpaced run's game time doesn't follow the host's, so two unpaced runs of one build should give the same blocks. The pairs compared so far did, byte for byte, as `scorecard.md` says. A real-time run's clock catches up when the host falls behind, the DMA then plays a block twice, presses land on other frames and sounds move. So a real-time run's blocks say as much about the host's timing as about the build. An unpaced run gets more of the game's time than the cut in its wall-clock seconds, and a recording shorter than the cut stops the tool with exit 2. The unpaced run's log gives the highest `[ax] frames` peak (main L before the output clamp) and the sum of the `[ax] bus` lines' `clipped`, from the lines whose list count is within the cut. A list is a 160-sample block.

The device stage is the real-time run's `GCN_WAV`, which is what went to the device. That run's log gives the ring's cuts and underruns. The device stage also counts the clicks within 2 samples of a `[ring] cut` line's output frame, when the build logs cuts. Underruns are the last `[ring] fill` line's, which comes every 400 pulls of the device. The real-time run records `GCN_AIDWAV` too, for block_clicks.py.

Each stage gets clicks a minute, gaps and clipped runs as audio_clicks.py counts them. An older build that doesn't print a log value reads `not logged`, and a missing recording reads `not recorded`. When `--no-run` finds no unpaced run, as for runs made before the scorecard played one, the mixer stage and its log values read `not recorded`. `--no-run` cuts the mixer stage at `--margin`, as a run would. A table per route prints as the route finishes, then the totals, where clicks a minute is over the summed seconds. `--json` prints it all at the end, with each clone's commit and its gcn-recomp commit. The tool reads those two before the first route plays and leaves them in each run's `commits.json`. `--no-run` prints what its runs recorded, or `not recorded` for a run made before that file existed. When a build's runs recorded different commits, it joins them with `and` (`a1b2c3d and e4f5a6b`), in the header and in the JSON. It only reports, so it never exits 1.

scorecard_runs.py plays a route on a build and scorecard_measure.py scores a route's two runs. Neither has a command line.

## block_clicks.py

Do a run's mixer-stage clicks sit on the blocks the DMA played twice or delivered catching up? It reads a `GCN_AIDWAV` recording and the block log gcn-recomp writes beside it (`<file>.txt`). A replayed block has the same address as the block before, because the guest hadn't queued the next buffer. A caught-up block came while the clock caught up with the host, which only a `--real-time` run does. For each kind and for the two together it prints the blocks, the clicks in them or within 2 samples of either end, and the count chance would put there. A block log whose last block ends more than a second from the recording's end can't be that recording's, and stops it with exit 2. That check tells logs apart by length only. A log from another run of the same route ends about where this recording does, so it passes. The baseline's real-time title recording paired with current's title log printed counts and exited 0.

```
tools/block_clicks.py build/probe/scorecard-menu/mixer.raw
```

## click_diff.py

Which clicks does one build's unpaced recording of a route have that another's doesn't? Unpaced, the two recordings line up sample for sample, so B minus A is what the builds did differently. For each click only one has, it prints the largest B minus A within 5 ms, B minus A's second difference at the click, whether each build is silent there and whether B minus A steps at the nearest block join. A second difference of 0 means both builds have the same edge, and only the sound around it differs. `--seconds S` cuts both to S.

```
tools/click_diff.py /path/to/old-clone/build/probe/scorecard-unpaced-title/mixer.raw build/probe/scorecard-unpaced-title/mixer.raw
```

## noise_blocks.py

Where do the DMA's blocks turn to loud noise? It weighs each 160-sample block of a `GCN_AIDWAV` recording, setting its high-frequency energy against its total as the RMS of its first difference over its RMS. White noise gives about 1.41, and music and effects give far less. A block is noise-like over 1 on a channel whose peak is over 8,000, and it prints the stretches such blocks form. The game's own bright sounds, a crash for one, make short stretches too, so a stretch is a place to look rather than a fault. It reads the DMA's 32 kHz only. The ring interpolates to 48 kHz for the device, and `test_noise_blocks.py` shows that noise which flags every block at 32 kHz flags far fewer after a linear interpolation to 48 kHz, so a `GCN_WAV` recording isn't a fair input.

```
tools/noise_blocks.py build/probe/scorecard-menu/mixer.raw
```

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

Will a player's first session stall on shader compiles? It plays the game once so the cache is already warm. The build runs it as the `dragoon_warmup` target, unless it's configured with `-DDRAGOON_WARMUP=OFF`, has no disc or is a cross build. It runs the game hidden and fast, with SDL's dummy audio driver, with one pass per route in `tests/hashes/manifest.txt`. Each pass has a scratch directory of its own and starts from a blank memory card, as a fresh install does, because a route that finds an earlier pass's card takes other menus and builds other keys. Its `shaders.bin` starts as a copy of the player's own and gains the keys its route builds. Passes don't share a cache, so several play at once. `--jobs N` sets how many, and the default is a third of the cores, at most six. The longest start first. When they are done their caches are merged, each key once and in the manifest's order. The game doesn't inherit `GCN_INPUT`, `GCN_WAV`, `GCN_PROFILE`, `GCN_FEED_DUMP` or `GCN_SESSION`, since each names a file or route that the passes would otherwise share.

The merged cache is copied over `saves/shaders.bin` only once every pass has succeeded, and it only gains keys. No other file in `saves/` is touched, so the player's memory card stays as it is. A failed pass stops the ones still playing, exits 1 and leaves `saves/` as it was. `saves/.shader-warmup` holds the gcn-recomp commit and a SHA-1 each of the manifest (with the route files' text) and of warm_shaders.py. If all three match, the next run does nothing. A relink doesn't replay the game, but an edited route or tool does. A checkout asks git for the gcn-recomp commit. A source snapshot has no history, so it takes the commit from its `source-info.json`. A copy with neither exits 2. `--force` plays it anyway. A pass that outlasts twice its length at 60 fps plus 30 s is killed and counts as failed.

`--report DIR` keeps each pass's output as `NAME.log` and the cache it left as `NAME.bin` in DIR, and prints `report.txt`. A row says how many programs the game built from the starting cache before its first frame and how long that took, and how many keys the pass built itself. It also gives the keys and programs the pass added that the starting cache and the passes before it in the manifest lacked, and the merged cache's size so far. With `GCN_FRAMETIME=1` in the environment it gives the frame the pass built its last program in.

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

## source_info.py

What does a source snapshot hold? Its `source-info.json` names the Dragoon and gcn-recomp commits and the disc they build, as `disc_id` and `dol_sha1`. source_info.py reads and writes that file, and refuses one with a field missing or malformed, naming the file. export_source.py writes it, and warm_shaders.py reads the engine commit through it. It has no command line.

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

## launcher_build.py

How does the launcher build the game? launcher_build.py is its recipe, and a developer can run it from a shell. Given a snapshot from export_source.py, the player's disc and every tool by full path, it builds `<data>/game/<id>/Dragoon.app` and points `<data>/game/current` at it. It prints one JSON event per line on stdout (the format is in `--help`) and writes every line the tools print to `--log`, with each command and each step's time.

| Step | What it does |
|---|---|
| sdl | Checks the SDL tarball against gcn-recomp's pin and extracts it to `<cache>/sdl` |
| source | Copies the snapshot to `<data>/source/<commit>` and checks the copy against its manifest |
| configure | Runs CMake into an empty `<cache>/build`, which recompiles the disc |
| compile | Runs Ninja for `dragoon`, whose `[done/total]` lines become progress events |
| warmup | Runs the copy's warm_shaders.py on a copy of the player's shader cache, one progress event per pass |
| package | Wraps the game in an app sealed ad hoc, with a `stamp.json` naming both commits and the SDK |
| swap | Points `game/current` at the new build, then installs the warmed cache in `<data>/saves` |

The tools run with `PATH=/usr/bin:/bin:/usr/sbin:/sbin` and five other variables, listed in `--help`. CMake ignores `/opt/homebrew`, `/usr/local` and `/opt/local`, so Homebrew's Python, SDL or libusb can't reach the build. `FETCHCONTENT_FULLY_DISCONNECTED` makes any download an error.

Before the swap nothing in `<data>` changes but the new `source/<commit>` and `game/<id>`. A rebuild of a commit replaces its `source/<commit>`, which the installed game never reads. A failed or killed build leaves the old game current and `saves/` as it was, and a package step that fails removes its `game/<id>`. Earlier builds stay in `<data>/game` for the launcher to delete. A second build while one runs exits 3 at `<cache>/build.lock` without touching anything, its `--log` included.

```
tools/launcher_build.py --source /tmp/dragoon-source --disc "$HOME/Kirby Air Ride (USA).gcm" \
  --data /tmp/dragoon-data --cache /tmp/dragoon-cache --log /tmp/dragoon-build.log \
  --cmake /opt/homebrew/bin/cmake --ninja /opt/homebrew/bin/ninja \
  --cc /Library/Developer/CommandLineTools/usr/bin/clang \
  --cxx /Library/Developer/CommandLineTools/usr/bin/clang++ \
  --python /Library/Developer/CommandLineTools/usr/bin/python3 \
  --sdk /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk --sdl-tarball /tmp/SDL3-3.4.18.tar.gz
```

A first build on an M4 Max took 112 s, with 24 s to configure, 33 s to compile (SDL's source included) and 55 s to warm up. A second build of the same commit took 57 s, because the warm-up found its stamp current.

`--no-disc` builds `runtime_check` and stops, which proves the tools and SDL's source configure and compile with no disc. `--no-warmup` skips the warm-up. `--keep-build` keeps `<cache>/build` and the SDL source it points at, which are deleted after a good build otherwise.

## sdl_source.py

Where does SDL's source come from when nothing downloads? gcn-recomp's `CMakeLists.txt` pins SDL's release tarball by URL and SHA-256 in its `sdl3` `FetchContent_Declare`. sdl_source.py reads that pin, so the hash has one home. The launcher reads the tarball once, so what it extracts is what it hashed. Its extraction checks every member before it writes anything, and refuses absolute paths, `..` and anything but plain files and directories, since the tools' Python 3.9 has no tarfile filter. It has no command line.

## check_bundle.py

Does the launcher ship anything game-derived? The disc never reaches CI, so nothing can compare bytes with the game. check_bundle.py looks for the shapes game data takes in `Dragoon.app`, or in a DMG that it attaches read-only and detaches again. Run it on the unsigned app and again on the signed DMG, since the manifest allows the `_CodeSignature` that signing adds.

| Check | What fails |
|---|---|
| paths | A file, link or empty directory outside the source snapshot that `launcher/bundle-manifest.txt` doesn't list. Anywhere, a path that `check_no_game_data.py` flags or that a build leaves behind (`gen/`, `rels/`, `inputs/`, `main.dol`, `CMakeCache.txt`, `build.ninja`, `memcard_*`, `.shader-warmup`, in any letter case) |
| executables | A file that starts with a Mach-O magic at a path the manifest doesn't list for one, such as a built `dragoon` |
| content | The GameCube disc magic at offset 0x1C, a `CISO` header, or the disc ID anywhere outside the snapshot |
| source | A snapshot that differs from `export_source.py`'s output for the commit, file by file by SHA-256. A dev tree's `rom/game.iso` link or empty `build/` shows up here |
| size | An app or a DMG over its budget in the manifest |
| DMG | Anything besides `Dragoon.app` and an `Applications` link to `/Applications` |

```
tools/check_bundle.py launcher/dist/Dragoon.app --commit SHA
tools/check_bundle.py launcher/dist/Dragoon.dmg --commit SHA
```

It prints one `kind: path (detail)` line per finding and nothing when the bundle is clean. Paths are relative to the app. It exits 0 when clean, 1 with findings and 2 when it couldn't check. A checkout that isn't at `--commit`, a manifest it can't read and a DMG that won't attach all exit 2. `--repo` names the Dragoon checkout the reference snapshot is exported from. It defaults to the one holding the tool. `--manifest` names another manifest.

A path that no manifest line allows is a finding, so a new file in the app starts as a line in the manifest. The app's budget in the manifest is a placeholder until the dev app has been measured.

## bundle_manifest.py

What may the app hold? It reads `launcher/bundle-manifest.txt`. That file names the source snapshot's directory and the two size budgets. It also lists what's allowed outside the snapshot, as plain files, directory prefixes, Mach-O executables and symlinks with their targets. The format is at the top of the module. It has no command line.

## bundle_checks.py

What does each check look at? bundle_checks.py holds the six checks above as functions that return findings, and the `Finding` they print as. It has no command line.

## bundle_tree.py

What does an app tree hold? It lists the regular files with their sizes, the symlinks with their targets, the empty directories and any odd entries such as pipes, and never follows a link. It has no command line.

## bundle_dmg.py

How does check_bundle.py look inside a DMG? It attaches the image with `hdiutil attach -readonly -nobrowse -mountpoint` at a fresh temporary directory and always detaches it, forcing the detach if the volume is busy or the plain one hangs. An attach gets two minutes and a detach one, so a stuck hdiutil can't hold a CI job until its own timeout. A detach that fails after the checks ran still prints their findings, with the error on stderr. The tests fake hdiutil. It has no command line.

## sign_and_package.py

Can one command sign the launcher, put it in a DMG and notarize it? It lives in `launcher/tools/`, with the commands it runs in `sign_plan.py` beside it. It copies the app to `OUT/dmg-root/Dragoon.app` next to an `Applications` link and signs the copy inside out, so the app you pass stays as it was. With a Developer ID identity every item gets `codesign -f -s IDENTITY -o runtime --timestamp`, as notarization requires. None gets `--deep`. `Contents/MacOS/cmake` and `ninja` go first with `-i` identifiers made from the app's bundle ID. Sparkle's `Autoupdate`, `Updater.app` and framework follow when the app has them, without the XPC services a launcher that isn't sandboxed doesn't ship. An app that still has them is refused. The app goes last, and the launcher claims no entitlements.

`codesign --verify --strict --deep` then checks the signed app before the DMG is made, so a broken signature costs no notarization round trip. `hdiutil create -format UDZO` makes `OUT/Dragoon.dmg`, tried up to three times because it sometimes fails with Resource busy, and `codesign -i` signs it with `--timestamp` for a Developer ID identity and `--timestamp=none` for ad hoc. With a Team API key, `xcrun notarytool submit --wait` notarizes the DMG and `xcrun stapler staple` staples it. A notarized DMG then gets `xcrun stapler validate` and the `spctl` assessments for an app and for a disk image.

```
launcher/tools/sign_and_package.py --app launcher/dist/Dragoon.app --identity - --out /tmp/dragoon-release
launcher/tools/sign_and_package.py --app launcher/dist/Dragoon.app --identity "Developer ID Application: NAME (TEAM)" \
  --out dist --notary-key AuthKey.p8 --notary-key-id KEYID --notary-issuer ISSUER --dry-run
```

`--identity -` signs ad hoc, with `--timestamp=none` and without `-o runtime`. Apple's timestamp server wants an Apple identity and the internet, and the runtime's library validation would stop an ad hoc launcher loading an ad hoc Sparkle, since neither has a team ID. With no notary key the run stops after signing and says the DMG isn't notarized. Apple rejects an ad hoc signature, so `--identity -` with a notary option is refused. `--dry-run` prints every command and runs none. Each command prints as a `+` line as it runs, and the DMG's path is the last line of a finished run. The key file is only named to notarytool and never read. A rejected notarization stops the run and prints the submission ID with the `notarytool log` command that shows why. A notarization still running after `--notary-timeout MINUTES` (30 unless you give it) is cut off, and the run prints the `notarytool history` command that finds the submission. The timeout takes up to 1440 minutes, a day. A re-run needs an empty `OUT` and uploads again, so give a slow submission a longer timeout instead. `OUT` can't be inside the app, where `ditto` would copy the app into itself. It exits 0 when the DMG is made, 1 when a command failed and 2 on a bad argument.

The tests fake codesign, ditto, hdiutil, xcrun and spctl with scripts that record their calls, so they sign nothing.

## fetch_third_party.py

Where do CMake and Ninja come from? `launcher/third_party.txt` pins each by version, URL and SHA-256, one `name version url sha256` line apiece, with a comment saying where the hash came from. fetch_third_party.py is the only tool that downloads anything. It refuses a file whose SHA-256 differs from its pin and extracts the rest. SDL isn't in that file. The tool reads its pin from gcn-recomp's `CMakeLists.txt` with `sdl_source.py` and keeps the tarball whole. It lives in `launcher/tools/`.

```
launcher/tools/fetch_third_party.py --dest launcher/.third_party
launcher/tools/fetch_third_party.py --dest launcher/.third_party cmake ninja
```

`--dest` gets each download and a `<name>-<version>/` tree made afresh on every run. A download stays, so a rerun that finds it intact downloads nothing. Names after the options fetch only those items, and SDL's pin is read only when `sdl3` is one of them. Extraction checks every member before it writes anything. It allows files, directories and symlinks. It refuses an absolute path, a `..`, a hard link and a device. It also refuses any symlink that doesn't resolve to a place inside the tree, once all of them exist. The tree is made beside its final name and renamed into place. It exits 0 when everything is fetched and 2 on a bad argument or pins file. A download, a hash or an extraction that fails stops the run with exit 1. The tests serve fixture archives over `file:` URLs with right and wrong hashes.

## make_app.py

Can one command build the dev app? make_app.py assembles `Dragoon.app` from the launcher binary that SwiftPM built, the pieces fetch_third_party.py fetched and a snapshot from `export_source.py`. It builds nothing. `--launcher` defaults to `launcher/.build/release/Dragoon`, and the snapshot comes from the committed state of `--repo`. The layout is in `--help`. CMake and Ninja are thinned to arm64 with `lipo`, and CMake's modules sit under `Contents/Resources/cmake/share` with a `bin/cmake` link back to the copy in `Contents/MacOS`, since CMake finds its modules from where it was started. The SDL tarball is checked against the pin in the snapshot's own gcn-recomp before it's copied. Each piece's license goes in `Contents/Resources/licenses`, and [launcher/README.md](../launcher/README.md) says where each comes from. The app is signed ad hoc with no hardened runtime by the commands `sign_and_package.py` uses. Then it's verified.

```
launcher/tools/make_app.py --out launcher/dist --version 0.1.0
```

It exits 0 when the app is made, 1 when a step failed and 2 when an input is missing or an argument is wrong. A failure removes what it wrote. The tests build from fake pieces, a fake `lipo` and `codesign` and a fixture repository, so they need no Swift.

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
