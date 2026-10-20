# Routes

Each file here is one input script in gcn-recomp's `input_script.h` syntax
(`frame:BUTTON[+BUTTON]:duration,...`), from a blank memory card to a checkpoint. Frames
are the game's submitted frames, not wall-clock time, so a route lands in the same place on
any machine. Lines starting with `#` are comments, and the rest is joined into one script.

| File | Reaches | Proof frame |
|---|---|---|
| `title.txt` | The title screen | 960 |
| `menu.txt` | The mode select menu | 1200 |
| `air-ride-race.txt` | An Air Ride race on Fantasy Meadows, past the countdown | 4200 |
| `city-trial.txt` | City Trial, one player, the clock running | 3300 |

Run one with `tools/probe.sh`, which takes a route file in place of a script.

```sh
tools/probe.sh race 20 tests/routes/air-ride-race.txt 600
```

That runs the game in a hidden window as fast as it goes, stops it after 20 seconds and
writes every 600th frame, its output and any `panic.txt` to `build/probe/race/`. The game
runs inside that directory, so a new name starts from a blank memory card. Run a route under
a name that's been used before and the card already holds a save, which skips the card
prompts and puts every later press in the wrong place.

The same route gives byte-identical frames from run to run on the same build. Frames 4200
and 6000 of `air-ride-race.txt` matched across two runs.
