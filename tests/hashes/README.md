# Frame hashes

Each golden in `gl/` holds the SHA-1 of every frame a scripted route dumps, up to the route's last checkpoint. A matching golden shows the renderer drew the same pixels in every dumped frame, on the machine that recorded it, so a renderer refactor that leaves the output alone shows up as all `OK`.

`manifest.txt` lists the routes, how long to run them and which frames they must reach. The routes themselves are in `tests/routes/`. A route's `warm=N` setting is for `tools/warm_shaders.py` alone, which then plays that route to frame N.

```sh
python3 tools/frame_hashes.py check
python3 tools/frame_hashes.py record
```

Both take an optional list of route names. `check` runs each route through `tools/probe.sh` and reports every frame that changed or wasn't reached. `record` rewrites the goldens, so only use it when a change to the output is on purpose.

The hashes depend on the renderer, the scale (always 1), the macOS version and the GPU, so goldens are per machine. The committed ones were recorded on an M4 Max under macOS 26, so a mismatch on another Mac is expected. After a macOS or GPU change, look at a route's frames from `tools/probe.sh` before running `record`.

Frames come from the player's own disc, so they are never committed. The tool deletes them once they're hashed, and only the hashes stay.

## Audio hashes

Each golden in `audio/` holds a few rows for one route. A row has a count of the AX command lists the game has processed and the running hash of every output block the mixer has written since boot, as `GCN_AXSTATS=1` prints it (`[ax] hash list=N fnv=X`). The hash covers all audio from boot, so a row shows that nothing the mixer wrote before that list changed. Rows carry no frame number, because the number of lists per presented frame varies. Each route's rows lie past the list where its audio first differs from the other routes', so none is boot audio they all share.

```sh
python3 tools/audio_hashes.py check
python3 tools/audio_hashes.py record title --lists 7200,20000
```

`check` takes an optional list of route names. It plays each as a bench run of `tools/probe.sh` and reports every row that changed. A run that stops short of a row's list count fails.

`record` rewrites a route's golden at the list counts given with `--lists`, or at the ones the golden already has. It writes nothing for a route that didn't reach one. Use it only when a change to the sound is on purpose. For a new route, pick counts past the list where its hashes first differ from every other route's, and that two bench runs reach with the same hash.

The goldens hold for unpaced runs only, which `--bench` is. A paced run makes catch-up jumps, so they don't apply to it. The committed ones were recorded on an M4 Max under macOS 26 and held across repeated runs there. Whether they hold on another machine hasn't been checked. No audio is captured or committed, only the counts and hashes.
