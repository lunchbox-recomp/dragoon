# Frame hashes

Each golden in `gl/` holds the SHA-1 of every frame a scripted route dumps, up to the route's last checkpoint. A matching golden proves the renderer drew the same pixels as when it was recorded, so a renderer refactor that leaves the output alone shows up as all `OK`.

`manifest.txt` lists the routes, how long to run them and which frames they must reach. The routes themselves are in `tests/routes/`.

```sh
python3 tools/frame_hashes.py check
python3 tools/frame_hashes.py record
```

Both take `--backend gl|metal` and an optional list of route names. `check` runs each route through `tools/probe.sh` and reports every frame that changed or wasn't reached. `record` rewrites the goldens, so only use it when a change to the output is on purpose.

The hashes depend on the renderer, the scale (always 1), the macOS version and the GPU. Goldens are per machine until CI can run the game.

Frames come from the player's own disc, so they are never committed. The tool moves them to the Trash once they're hashed, and only the hashes stay.
