# Tools

Each tool answers one question. Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`.

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
