# Tools

Each tool answers one question. Start with probe.sh, which makes the runs the others read. Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`.

## Conventions

Every tool takes `--help`, which prints its usage and what it reads. Results go to stdout, including the failures a tool checks for. Errors go to stderr as one line naming the file and what's wrong, and so do warnings that leave the exit code alone. A traceback means a bug in the tool.

| Exit | Means |
|---|---|
| 0 | The tool ran and nothing failed |
| 1 | It ran and found what it checks for, such as a changed frame or a frame over budget |
| 2 | It couldn't run: a bad argument, or an input it can't read or doesn't understand |

frametime.py and shader_cache.py only report, so they never exit 1.

## probe.sh

How does the game behave when nobody is playing it? It runs the game in a hidden window for a number of seconds, feeds it a route of button presses and dumps every Nth frame as a PNG. A run leaves its frames (`frame_NNNNN.png`), its log (`stdout.txt`), its memory card (`saves/memcard_a.raw`), its shader cache (`saves/shaders.bin`) and, after a crash, `panic.txt` in `build/probe/NAME/`. Audio goes through SDL's dummy driver, so a run is silent. Audio never paces the guest, so the dummy driver doesn't change timing. A new NAME starts from a blank memory card, and a NAME that's run again keeps the card its last run left behind.

After the NAME and seconds come an input script or a route file from `tests/routes/`, the dump interval and any settings. A setting is `GCN_*=value` (the list is in `gcn-recomp/docs/diagnostics.md`), `--pads=N`, `--real-time`, `--renderer=gl`, `--scale=N` or `--bench`. GL is the engine's only renderer. `tools/probe.sh --help` prints the settings. Route files are described in `tests/routes/README.md`.

```
tools/probe.sh demo 20 tests/routes/title.txt 60 GCN_FRAMETIME=1
```

That prints the run's directory as an absolute path, then `140 frames`. Run it again with a different NAME to get a second run to compare.

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

framediff takes a tolerance and works across renderers. frame_hashes is an exact check against committed goldens. Two runs of a change need two builds and two NAMEs. Frames only one directory has are counted on stderr and don't fail the diff, which is normal when runs end at different frames.

```
tools/framediff.py build/probe/gl-run build/probe/metal-run --tolerance 3 --budget 0.001
```

## shader_cache.py

How many shaders does a cache or key list hold, and how many are new? It reads `saves/shaders.bin` (magic `WRSC`) and key lists (magic `GCSK`). The key size comes from the format word, and a magic or key size it doesn't know is refused. `count` prints the format, the record count and the distinct key count, and says how many trailing bytes it ignored (a record a kill cut off). `diff` prints how many distinct keys in NEW aren't in OLD and their share of NEW, and refuses two files in different formats. It counts and never lists keys.

```
tools/shader_cache.py count build/probe/gl-run/saves/shaders.bin
tools/shader_cache.py diff build/old-keys.bin build/probe/gl-run/saves/shaders.bin
```

## frame_hashes.py

Did a change alter what the renderer draws? It runs each route in `tests/hashes/manifest.txt` through probe.sh and compares the SHA-1 of every dumped frame with the golden in `tests/hashes/<backend>/<route>.txt`. `check` reports each frame that changed or wasn't reached. `record` rewrites the goldens, so use it only when a change to the output is on purpose. The frames are moved to the Trash once hashed and are never committed.

The manifest has one route per line. A line gives the name, the seconds to run, the dump interval, the frames the route must reach and any extra probe settings. Pass route names to run only those. `--backend` picks the goldens' directory, and probe.sh accepts only gl. A `check` of all five routes takes about two minutes.

```
tools/frame_hashes.py check title
```

## warm_shaders.py

Will a player's first session stall on shader compiles? It plays the game once so the cache is already warm. The build runs it as the `dragoon_warmup` target, unless it's configured with `-DDRAGOON_WARMUP=OFF` or has no disc. It runs the game hidden and fast, with SDL's dummy audio driver, in a scratch directory with its own blank memory card. One pass sits at the title with nobody at the controls, then one pass plays each route in `tests/hashes/manifest.txt`. The scratch `shaders.bin` starts as a copy of the player's own and grows pass by pass.

Only when every pass has succeeded is it copied over `saves/shaders.bin`, through a temp file and an `os.replace`. The cache only gains keys, and no other file in `saves/` is touched, so the player's memory card is never read or written. A failed pass exits 1 and leaves `saves/` as it was. `saves/.shader-warmup` holds the gcn-recomp commit and a SHA-1 of the manifest. If both match, the next run does nothing, so a relink doesn't replay the game. `--force` plays it anyway, and `--no-routes` plays only the attract pass and leaves the stamp alone, to see how far the attract demos get by themselves. `--attract-frames` sets the length of the attract pass.

```
tools/warm_shaders.py --force
tools/shader_cache.py count saves/shaders.bin
```

## check_no_game_data.py

Is anything from a disc tracked by git? It flags tracked paths that look like game data:

- Disc images and executables by suffix, `.raw` memory cards and `.bin` shader caches and key lists.
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
