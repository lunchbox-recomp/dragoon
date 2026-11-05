# Hashes

## Frame hashes

Each golden in `gl/` holds the SHA-1 of every frame a scripted route dumps, up to the route's last checkpoint. A matching golden shows the renderer drew the same pixels in every dumped frame, on the machine that recorded it, so a renderer refactor that leaves the output alone shows up as all `OK`.

`manifest.txt` lists the routes, how long to run them and which frames they must reach. The routes themselves are in `tests/routes/`. `warm=` and `warm-from=` are `tools/warm_shaders.py`'s, explained at the top of `manifest.txt`.

```sh
python3 tools/frame_hashes.py check
python3 tools/frame_hashes.py record
```

Both take an optional list of route names. `check` runs each route through `tools/probe.sh` and reports every frame that changed or wasn't reached. `record` rewrites the goldens, so only use it when a change to the output is on purpose.

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
