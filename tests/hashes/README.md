# Frame hashes

Each golden in `gl/` holds the SHA-1 of every frame a scripted route dumps, up to the route's last checkpoint. A matching golden shows the renderer drew the same pixels in every dumped frame, on the machine that recorded it, so a renderer refactor that leaves the output alone shows up as all `OK`.

`manifest.txt` lists the routes, how long to run them and which frames they must reach. The routes themselves are in `tests/routes/`.

```sh
python3 tools/frame_hashes.py check
python3 tools/frame_hashes.py record
```

Both take an optional list of route names. `check` runs each route through `tools/probe.sh` and reports every frame that changed or wasn't reached. `record` rewrites the goldens, so only use it when a change to the output is on purpose.

The hashes depend on the renderer, the scale (always 1), the macOS version and the GPU, so goldens are per machine. The committed ones were recorded on an M4 Max under macOS 26, so a mismatch on another Mac is expected. After a macOS or GPU change, look at a route's frames from `tools/probe.sh` before running `record`.

Frames come from the player's own disc, so they are never committed. The tool moves them to the Trash once they're hashed, and only the hashes stay.
