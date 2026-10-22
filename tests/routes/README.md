# Routes

Each file here is one input script in gcn-recomp's `input_script.h` syntax
(`frame:BUTTON[+BUTTON]:duration,...`), from a blank memory card to a checkpoint. Frames
are the game's submitted frames, not wall-clock time, so a route lands in the same place on
any machine. A press for another controller puts its port first, as in `2/2100:A:5`, and
that port has to be plugged in with `--pads=N`. Lines starting with `#` are comments, and
the rest is joined into one script.

| File | Reaches | Proof frame |
|---|---|---|
| `title.txt` | The title screen | 960 |
| `menu.txt` | The mode select menu | 1200 |
| `air-ride-race.txt` | An Air Ride race on Fantasy Meadows, past the countdown | 4200 |
| `air-ride-celestial-valley.txt` | An Air Ride race on Celestial Valley, past the countdown | 4200 |
| `air-ride-sky-sands.txt` | An Air Ride race on Sky Sands, past the countdown | 4200 |
| `air-ride-frozen-hillside.txt` | An Air Ride race on Frozen Hillside, past the countdown | 4200 |
| `air-ride-magma-flows.txt` | An Air Ride race on Magma Flows, past the countdown | 4200 |
| `air-ride-beanstalk-park.txt` | An Air Ride race on Beanstalk Park, past the countdown | 4200 |
| `air-ride-machine-passage.txt` | An Air Ride race on Machine Passage, past the countdown | 4200 |
| `air-ride-checker-knights.txt` | An Air Ride race on Checker Knights, past the countdown | 4200 |
| `city-trial.txt` | City Trial, one player, the clock running | 3300 |
| `city-trial-4p.txt` | City Trial, four players on ports 1 to 4, each steering its own way | 3480 |

Each Air Ride course route is `air-ride-race.txt` with up to four presses on the course
select, between frames 2000 and 2120, where the cursor starts on Fantasy Meadows. The grid
has two rows of five.

| Row | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Top | Fantasy Meadows | Celestial Valley | Sky Sands | Frozen Hillside | Magma Flows |
| Bottom | Beanstalk Park | Machine Passage | Checker Knights | Locked | Random |

The locked slot is Nebula Belt, the ninth course. A blank memory card can't pick it, so it
has no route. `docs/dev/status.md` says what the game checks before it opens.

Run one with `tools/probe.sh`, which takes a route file in place of a script.

```sh
tools/probe.sh race 20 tests/routes/air-ride-race.txt 600
tools/probe.sh city4 25 tests/routes/city-trial-4p.txt 60 --pads=4
```

The first runs the game in a hidden window as fast as it goes, stops it after 20 seconds and
writes every 600th frame, its output and any `panic.txt` to `build/probe/race/`. The second
plugs in four controllers, which `city-trial-4p.txt` needs. The game
runs inside that directory, so a new name starts from a blank memory card. Run a route under
a name that's been used before and the card already holds a save, which skips the card
prompts and puts every later press in the wrong place.

A route gives byte-identical frames from run to run on the same build, because gcn-recomp
applies each press where the game reads the controller, at the frame the game has reached.
Frames 4200 and 6000 of `air-ride-race.txt` matched across three runs in a row. Frames 3300
and 4500 of `city-trial.txt` matched across two runs nine minutes apart, and frames 2700 and
3300 of `city-trial-4p.txt` across two runs.

Before gcn-recomp fda6926 they didn't. Each press landed wherever the game was when the
frontend's loop next looked, and two runs of `city-trial.txt` showed 4:54:10 and 4:54:11
on the clock at frame 3300, from different spots. The RTC starts at the host's time on
every run that isn't a replay, but it doesn't move the start. The two runs nine minutes
apart start in the same place.

Each of the seven other course routes drew the same 70 frames, every 60th up to 4200, in a
`tools/frame_hashes.py record` run and in the `check` run straight after it.
