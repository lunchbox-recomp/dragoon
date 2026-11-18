# Hashes

## Frame hashes

Each golden in `gl/` holds the SHA-1 of every frame a scripted route dumps, up to the route's last checkpoint. A matching golden shows the renderer drew the same pixels in every dumped frame, on the machine that recorded it, so a renderer refactor that leaves the output alone shows up as all `OK`.

`manifest.txt` lists the routes, how long to run them and which frames they must reach. The routes themselves are in `tests/routes/`. `warm=` and `warm-from=` are `tools/warm_shaders.py`'s, explained at the top of `manifest.txt`.

```sh
python3 tools/frame_hashes.py check
python3 tools/frame_hashes.py record
```

Both take an optional list of route names. `check` runs each route through `tools/probe.sh` and reports every frame that changed or wasn't reached. `record` rewrites the goldens, so only use it when a change to the output is on purpose.

`--aspect=16:9` runs each route with `tools/probe.sh --aspect=16:9` and checks or records the goldens in `gl-16x9/` instead of `gl/`. The frames hashed are still the game's own 640x480 dumps, not the window's picture. At 16:9 a dump holds the picture before the window stretches it, so the widened world is squeezed into 640 pixels, the anchored HUD keeps its 4:3 shape once stretched, and a menu or the memory card prompt fills the middle 480 pixels between bars of 80. So no 16:9 frame hashes as its 4:3 one does. With no `--aspect`, or `--aspect=4:3`, probe.sh gets no `--aspect`, as the 4:3 goldens were recorded.

```sh
python3 tools/frame_hashes.py check --aspect=16:9
```

The hashes depend on the renderer, the scale (always 1), the macOS version and the GPU, so goldens are per machine. The committed ones were recorded on an M4 Max under macOS 26, so a mismatch on another Mac is expected. After a macOS or GPU change, look at a route's frames from `tools/probe.sh` before running `record`.

Frames come from the player's own disc, so they're never committed. The tool deletes them once they're hashed, and only the hashes stay.

## Audio hashes

Each golden in `audio/` holds a few rows for one route. A row is a count of the AX command lists the game has processed and the running hash of every output block the mixer has written since boot, as `GCN_AXSTATS=1` prints it (`[ax] hash list=N fnv=X`), so a match shows that nothing the mixer wrote before that list changed. Rows carry no frame number, since the number of lists per presented frame varies, and each lies past the list where the route's audio first differs from every other route's, so none is boot audio they all share.

```sh
python3 tools/audio_hashes.py check
python3 tools/audio_hashes.py record title --lists 7200,20000
```

`check` takes an optional list of route names. It plays each as a bench run of `tools/probe.sh` and reports every row that changed. A run that stops short of a row's list count fails.

`record` rewrites a route's golden at the `--lists` counts or at the ones it already has, and writes nothing for a route that misses any of them. Use it only when a change to the sound is on purpose. For a new route, pick multiples of 400 past the list where its hash first differs from every other route's, at counts where two bench runs give the same hash.

The goldens hold only for unpaced runs, which `--bench` is, since a paced run makes catch-up jumps. The committed ones were recorded on an M4 Max under macOS 26 and held across repeated runs there, and no other machine has been checked. No audio is captured or committed, only the counts and hashes.

## State goldens

Each golden in `state/` holds the game's own state at a route's checkpoints, which are its required frames in `manifest.txt`. It's read from guest RAM by the names in `tools/kar_ram.json`. A line is the checkpoint, the frame it was read at and then each value. They're the scene's major and minor and how many play, with how many of them are people. Then come who plays each port and each player's speed and position. The lap, the place and the race timer aren't mapped in `kar_ram.json`, so no golden holds them. A route whose frames match but whose state doesn't played differently, and one whose state matches but whose frames don't drew differently.

```sh
python3 tools/state_goldens.py check
python3 tools/state_goldens.py check --aspect=16:9
python3 tools/state_goldens.py record
```

`--aspect=16:9` plays at 16:9 and keeps its goldens in `state-16x9/`, as the frame goldens do. Twenty-four routes read the same state at both aspects. `air-ride-courses-2` doesn't, since its third race, Beanstalk Park, plays out differently at 16:9. Its checkpoint at frame 19,400 has every rider's speed and position off by up to about 1 unit, while 15,600 matches, and both aspects gave the same values when run again. The values are numbers the game computed and nothing read from the disc, with each float written to nine figures.
