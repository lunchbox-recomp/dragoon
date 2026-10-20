# Tools

Each tool answers one question. Start with probe.sh, which makes the runs the others read. Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`.

## probe.sh

How does the game behave when nobody is playing it? It runs the game in a hidden window for a number of seconds, feeds it a route of button presses and dumps every Nth frame as a PNG. Everything a run leaves goes to `build/probe/NAME/`, and the log is `build/probe/NAME/stdout.txt`. Audio goes through SDL's dummy driver, so a run is silent. A new NAME starts from a blank memory card, and a NAME that's run again keeps the card its last run left behind.

After the NAME and seconds come an input script or a route file from `tests/routes/`, the dump interval and any settings. A setting is `GCN_*=value` (the list is in `gcn-recomp/docs/diagnostics.md`), `--pads=N`, `--real-time`, `--renderer=NAME`, `--scale=N` or `--bench`. The header of `tools/probe.sh` has the details.

```
tools/probe.sh demo 20 tests/routes/title.txt 60 GCN_FRAMETIME=1
```

That prints `build/probe/demo: 140 frames`. Run it again with a different NAME to get a second run to compare.

## frametime.py

How steady is the frame pacing, and what made the slow frames slow? It reads the log of a run made with `GCN_FRAMETIME=1`, prints the guest's and the renderer's mean, p95, p99 and worst times from a given frame on, and lists each frame whose render time went over a limit with its batch shape and the shaders compiled in it.

```
tools/probe.sh pace 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1
tools/frametime.py build/probe/pace/stdout.txt --from 300 --slow 16.7
```

Add `--json` for machine output.

## framediff.py

Do two runs draw the same pixels? It compares every `frame_NNNNN.png` that two directories of frame dumps have in common, prints the share of pixels whose largest RGB difference is over a tolerance and the worst difference seen, and exits 1 if any frame is over the budget. Alpha isn't compared.

```
tools/framediff.py build/probe/gl-run build/probe/metal-run --tolerance 3 --budget 0.001
```

## shader_cache.py

What shaders does a cache or key list hold, and which are new? It reads `saves/shaders.bin` (magic `WRSC`) and key lists (magic `GCSK`). The key size comes from the format word, and a magic or key size it doesn't know is refused. `count` prints the format, the record count and the distinct key count, and says how many trailing bytes it ignored (a record a kill cut off). `diff` prints how many distinct keys in NEW aren't in OLD and their share of NEW, and refuses two files in different formats.

```
tools/shader_cache.py count build/probe/gl-run/saves/shaders.bin
tools/shader_cache.py diff old-keys.bin build/probe/gl-run/saves/shaders.bin
```

## frame_hashes.py

Did a change alter what the renderer draws? It runs each route in `tests/hashes/manifest.txt` through probe.sh and compares the SHA-1 of every dumped frame with the golden in `tests/hashes/<backend>/<route>.txt`. `check` reports each frame that changed or wasn't reached. `record` rewrites the goldens, so use it only when a change to the output is on purpose. The frames are moved to the Trash once hashed and are never committed.

The manifest has one route per line. A line gives the name, the seconds to run, the dump interval, the frames the route must reach and any extra probe settings. A `check` takes a few minutes. Pass route names to run only those, and `--backend gl|metal` to pick the goldens.

```
tools/frame_hashes.py check title
```

## check_no_game_data.py

Is anything from a disc tracked by git? It flags tracked paths that look like game data. Disc images and executables are flagged by suffix. Anything under `build*/` or `saves/` is flagged too, and so is anything under `rom/` except its README. It prints one line per path and exits 1 if it found any, so it can run in CI. It prints nothing when the tree is clean.

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
