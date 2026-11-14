# Tools

Each tool answers one question. Start with probe.sh, which makes the runs the others read. To playtest with sound, run playtest.sh and read the session with session_report.py, and with pad_report.py for the controls.

Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`. The launcher's own helpers live in `launcher/tools/` with their tests beside them, so run those with `python3 -m unittest discover -s launcher/tools -p 'test_*.py'` too. Both run under the Command Line Tools' Python 3.9 and under a newer one.

## Conventions

Every tool with a command line takes `--help` and prints its usage and what it reads, except `swift_test.py`, which hands `--help` to swift. Results go to stdout, including the failures a tool checks for. Errors go to stderr as one line naming the file and what's wrong, and so do warnings that leave the exit code alone, while a traceback means a bug in the tool.

| Exit | Means |
|---|---|
| 0 | The tool ran and nothing failed |
| 1 | It ran and found what it checks for, such as a changed frame or a frame over budget |
| 2 | It couldn't run: a bad argument, or an input it can't read or doesn't understand |

frametime.py, shader_cache.py, audio_clicks.py, audio_scorecard.py, block_clicks.py, click_diff.py, noise_blocks.py, clip_signs.py, ax_stats.py, stream_voices.py, session_report.py, pad_report.py and picture_box.py only report, so they never exit 1.

## probe.sh

How does the game behave when nobody is playing it? It runs the game in a hidden window for a number of seconds, feeds it a route of button presses and dumps every Nth frame as a PNG. A run leaves its frames (`frame_NNNNN.png`), its log (`stdout.txt`), its memory card (`saves/memcard_a.raw`), its shader cache (`saves/shaders.bin`) and, after a crash, `panic.txt` in `build/probe/NAME/`. A windowed run uses SDL's dummy audio driver and passes `--no-gamepads`, so it's silent and never opens a controller left on beside it. A `--bench` run leaves the driver to SDL and plays through the real device unless `SDL_AUDIO_DRIVER=dummy` is set, which audio_hashes.py does. Audio never paces the guest, so the dummy driver doesn't change timing. A new NAME starts from a blank memory card, and a NAME that's run again keeps the card its last run left behind.

After the NAME and seconds come an input script or a route file from `tests/routes/` (its README describes them) and the dump interval, then any settings, which `tools/probe.sh --help` lists. `GCN_*` switches are in `gcn-recomp/docs/diagnostics.md`, and Dragoon's `DRAGOON_*` ones are in `src/`, such as `DRAGOON_CENSUS=1` in `docs/dev/widescreen.md`. `--log`, `--disc=fast|console`, `--aspect`, `--output`, `--replay`, `--exit-after` and `--no-session-audio` need a windowed run, so probe.sh refuses them with `--bench`.

A relative `--disc`, `--replay` or `--bin` path is taken from where probe.sh was run. `--bin=PATH` runs PATH in place of `build/dragoon`, or of `build/dragoon_bench` under `--bench`, so two builds can be benched in turn from one clone.

A run keeps no input log unless `GCN_SESSION=DIR` records a session. A relative DIR is taken from the run's directory, `build/probe/NAME/`, for this one. The session's `inputs/` lands in that DIR.

```
tools/probe.sh demo 20 tests/routes/title.txt 60 GCN_FRAMETIME=1
```

That prints the run's directory as an absolute path, then a frame count (140 on an M4 Max), which leaves out any `--output` dumps. It exits 2 when the game isn't built, and a different NAME gives a second run to compare. Runs pile up in `build/probe/`, and prune_runs.py clears the old ones.

## bot_link.py

Can a program play the game one frame at a time? It listens on a Unix socket first and then runs probe.sh with `GCN_BOT` set to that socket, so the game connects with nothing left to chance. The bot is called once for each frame the engine steps it at.

The bot reads guest RAM and returns the pad for each port it drives. The input log records the bot's pads, and the run is a session (`GCN_SESSION`), so every run leaves an input log that replays with no bot. The protocol is the engine's, under "Bots" in `gcn-recomp/docs/diagnostics.md`.

```
tools/bot_link.py --script tests/routes/menu.txt --watch 80000000:4 menu-bot 60 -- --exit-after=1500
```

That plays the menu route with a bot that presses nothing. It prints the four bytes at `80000000` when they change and says how the link ended. `--pads N` sets how many ports the bot drives (1 by default).

`--every N` sets the dump interval, and everything after `--` is more probe.sh settings. `--hang SECONDS` ends the run when the game sends no frame, or answers no read, for that long (30 by default, 0 for never). `--send N` makes the bot send ports 1 to N whatever `--pads` says, to see the engine refuse a port the game doesn't have or one the bot left out.

Other tools import `run(name, seconds, bot, pads=, script=, every=, settings=, hang=)`, which calls `bot(link)` once a frame. The bot reads 1 to 256 bytes of RAM at a time through `link.read(addr, length)` and returns `{port: Pad(...)}`, where a port it leaves out stops the game. `run` returns an `Outcome`, whose `reason` is one of those below and whose `input_log` is the directory `--replay=` takes.

The rules for the deadline and a hang are in the docstrings of `run` and `Link`, and `Pad` raises `ValueError` on a value the engine would refuse. ram_peek.py shows the module's argument helpers in use.

| Reason | Means | Detail |
|---|---|---|
| `time_limit` | SECONDS were up | The seconds |
| `exit_after` | The `--exit-after` frames were shown | The setting |
| `shutdown` | The game shut the console down by itself | Its `[reset]` line |
| `game_exited` | The game ended some other way and left its input log whole | The frame it ended at |
| `game_died` | The game ended and its input log has no `# end` line, or it reset the console and the new process began no session | The last line of `stdout.txt`, or the `[reset]` line |
| `hang` | No frame or no answer to a read for `hang` seconds, or no new connection that long after a reset | How long, and the last frame or the frame of the unanswered read, or after a reset the game's last line. When the game reported an assertion after its last frame, its `[OS] assertion ... failed` line and the line after it that says where |
| `engine_stop` | The engine stopped the game | Its `[bot] frame N: ...` line from `stdout.txt` |
| `connect_failed` | The engine couldn't connect | Its `--bot PATH: ...` line |
| `panic` | The game crashed | The first line of `panic.txt`, or the `FATAL` or `FAULT` line |
| `bot_raised` | The bot raised | The exception, which `error` holds too |
| `never_linked` | The game ended without connecting or saying why, or hadn't connected when SECONDS were up | What probe.sh printed, or the last line of `stdout.txt` |
| `bad_link` | The engine sent what isn't the protocol | The line |

The engine writes `# end` in its input log on the ways out it chooses, and that includes the signals that ask it to quit, such as a SIGTERM from outside. A game that left none was killed with SIGKILL or hit a signal the engine doesn't catch, such as SIGABRT. Its 2 second watchdog leaves none either, when the engine's own exit hangs.

An `exit_after` needs the end line's frame to reach the `--exit-after` count, and a `shutdown` wins over it.

The command exits 0 for `time_limit`, `exit_after` and `shutdown`. It exits 2 for `never_linked`, as it does for a socket another bot holds or a probe.sh that won't run. Every other reason exits 1, `game_exited` included, since in a bot run only a quit signal from outside, such as a SIGTERM, ends the game that way.

The socket is `build/probe/NAME/bot.sock`, or `/tmp/dragoon-bot-HASH.sock` when that path passes the 103 bytes a Unix socket takes, and a lock beside it refuses a second bot on the same socket. A run deletes the `stdout.txt`, `panic.txt` and `session/` an earlier run of NAME left but keeps its frames, so give each run a new NAME. The session the run makes records no audio unless `settings` gives `GCN_WAV` or `GCN_AIDWAV` a path, and a `GCN_SESSION` of your own records what the engine records by default.

A game that resets the console connects again and the bot goes on with it, with `Link.starts` counting the connections. The tests stand a fake probe.sh in for the game, so they need no disc.

## ram_peek.py

What does guest RAM hold at the frames I name, along a route? It plays the game through bot_link.py with a bot that presses nothing, so the route's presses are the only ones. At each frame it prints one line with every item's value.

```
tools/ram_peek.py --script tests/routes/air-ride-race.txt --at 3200,3400-3600/100 race-peek 100 scene.minor player1.speed player1.x 8053627C:f32x4 -- --exit-after=3610
```

An item is a name from kar_ram.json or a raw read at an address, and `--help` gives the syntax of both and of `--at`. NAME has to be new, since a run in an old `build/probe/NAME/` starts from that run's memory card. `--script`, `--pads`, `--hang` and the settings after `--` are bot_link.py's, and so are its outcome lines.

The tests stand a fake link in for the game, so they need no disc.

## kar_ram.py

Where does Kirby Air Ride keep what a bot needs to see? `kar_ram.json` names each value by its address and type, as stable-retro's `data.json` does. Each entry says what the value is, what the confirmed values mean and the route and frames it was watched on. A value watched on another route names that route and its frame in its meaning.

`load(path=None)` reads the table into `Entry` records by name. It raises `ValueError` naming the file and the entry for one that's malformed or reaches outside main RAM, `80000000` to `817FFFFF`. `decode(entry, data)` turns the bytes read for an entry into an int, a float or, for a run of bytes, the bytes.

`read(link, name)` reads a value through a bot's `Link` and decodes it, and `read(link, name, table)` looks the name up in a table `load` gave. ram_peek.py prints the names along a route. It has no command line.

A type is a big-endian `u8`, `s8`, `u16`, `s16`, `u32` or `s32`, an `f32` or `bytes` with a `length` from 1 to 256. A value the game keeps in an object it allocates, such as a player's position, has a `path` of hex offsets. The address then holds a pointer, and each offset is added to the pointer read before it.

`read` returns None when a pointer on the way is null or leads outside main RAM, as for a player who isn't in the race. The players are numbered by port, as the game's slots are.

`scene.major` says which mode is up and `scene.minor` which screen. A course or the city loads between two frames the link sends, so loading has no screen of its own. The menu values are only right on their own screens and the player values only in a race or the city, so a bot reads the screen first.

Top Ride's races keep their players elsewhere, so there the player values read as if nobody played.

## bot_walk.py

Where do the soak's bots steer? `Walk(seed, ports)` gives each port a pad every time `pads()` is called. A port holds the stick toward one heading for half a second to two seconds, then turns to another. It taps A for 4 frames now and then, and never presses START.

The walk reads no RAM, so a seed gives the same pads whatever the game does. Port N of seed S walks from `random.Random(S * 5 + N)`, so adding a port leaves the others as they were, and 5S is left for the menu walker's schedule. It has no command line.

## bot_menus.py

How does a bot get from the boot to a race and back to the menus? `Menus(ports, Schedule(seed, modes))` reads which screen is up and where its cursor is. It presses a button as libmelee's menu helper does, down for 5 frames and then up for 45 while the screen answers.

A menu value keeps its last value off its own screen, so `Menus` reads `scene.minor` first and a cursor only on the screen that owns it. `step(link)`, for a `bot_link.run` callback, gives the pads for the frame, or None while a race or the city plays, which is the race bots' turn (bot_walk.py). It reads the screen on every frame of a race too, so the race bots never press on City Trial's stats or the card that follows them.

The schedule picks each round's mode and the Air Ride course from the seed, and the modes come round in a shuffled order each time through. `Menus` says what it's doing to the `say` it was given. It has no command line.

The paths come from the routes in `tests/routes/` and the values in kar_ram.json.

| Path | What it presses | Still to confirm in the game |
|---|---|---|
| Boot to the mode select | A while the game boots, then A and START in turn on the opening movie and title, 100 frames apart | |
| Mode select | B on another mode's own menu to go back to the mode select, then DOWN or UP to the mode, A, then UP until `menu.item` reads 0 and A on the mode's own menu for Start Game, then A to skip its movie. A row that 3 UPs leave alone gets A | |
| Air Ride | The cursor along its row and then down or up to the course, A, then A to join, A for OK and START | |
| Top Ride | A on the course select, then A and START in turn on the machine select | |
| City Trial, 1 to 4 players | A on every port at the movie, A on each port that isn't in at the player select, START once all are in and OK | |
| Leaving a race | START, DOWN, DOWN and A on the pause menu once `round_seconds` of game time are up, or START through the results of a race that ends first | |
| Leaving the city | A through its stats and card, then the stadium, then START on every port through its results, which wait for each player's. A on the checklist when the round checked a box. B held 90 frames at the player entry goes back to City Trial's own menu (the game took 47) | |
| Leaving a stadium | After `round_seconds`, START, DOWN and A pick End Game on its two-row pause menu, where DOWN wraps. End Game goes back to City Trial's own menu. With more than one player the rows sit side by side, so RIGHT takes DOWN's place | RIGHT on a stadium's pause menu with three players, so leaving a three-player stadium is unconfirmed. A two-player soak left 12 stadiums with it. One player's and four players' menus have been watched, and the fake game in testgame.py lays out every count above one side by side |
| Most presses | 5 frames down and 45 up, so the screen is looked at again 50 frames after a press. The title waits 100 frames and a race's START 305. The pause menu waits 100 after START and 305 after its last A | The routes usually wait about 300 frames after a press that changes the screen. A press made during the change may land on the next screen |

The walker says `unconfirmed step` the first time it takes each step in the right-hand column, and `screen N isn't in kar_ram.json` for a screen the table doesn't name, which it presses A on. A screen that stays up past `stuck_seconds` of game time raises `Stuck`. So does a race that goes past `play_seconds`, 600 s by default, which the soak's `Player` raises to `round_seconds` and 60 when that's more. The menus going on for five times `stuck_seconds` with no race or city raise it too, as when two screens take turns. After a console reset the walker forgets the press under way and the screen, and starts over from the boot.

## bot_soak.py

Does the game hold up when bots play it for a long time? `bot_soak.py` plays it through bot_link.py as a new run in `build/probe/soak-sSEED-TIME/` and stops at the first fault. The menu walker (bot_menus.py) takes it from the boot to a race and back to the menus after each round, for the modes in `--modes` (`air-ride`, `top-ride` and `city-trial`, all three by default) with `--ports` controllers. In a race or the city each bot holds the stick toward wherever a walk from the seed says and taps A at random, and never presses START (bot_walk.py).

```
tools/bot_soak.py --seed 7 --minutes 60 --modes city-trial --ports 4
```

The seed is printed, and the soak adds `GCN_AXVOICES=1` to the settings after `--` and makes no frame dumps. `--minutes` is wall time (10 by default), and `--round` is the game seconds the walker lets a race or a City Trial stadium run before it leaves through the pause menu (120 by default). `--help` gives the other defaults and the limits, and `--hang` here has to be above 0.

It stops at the first of these.

- The game exits, shuts itself down, panics or is stopped by the engine.
- The game sends no frame, or no answer to a read, for `--hang` seconds of wall time.
- A music stream ends early, by stream_voices.py's rule on the run's `[axv]` lines.
- The menus or a race outlast the walker's limits, which follow `--stuck` and `--round` (bot_menus.py).

The frozen-picture check never runs, since the link gives no picture hash.

A console reset rebuilds the shader cache before the bot connects again, and that time counts against `--hang`. The soak prints the first reset's `[shaders] ... in Z ms` line and warns when Z reaches two thirds of the limit, so the next run can raise `--hang`.

A stop keeps the run's input log and writes `bot.json` beside it, with the seed, the arguments, the Dragoon and engine commits, how the run stopped and the console resets. It says whether the stop came after a reset, since a replay plays only the process after the last reset, from the card as it stood then.

When the stop's process kept no input log, `bot.json` goes to `build/probe/NAME/` instead and the stop says it has no input log to replay.

The commits are the checkout's HEAD, which may not be what was built. `engine_built` is the engine commit the game's `session.json` says it was built from, with `-dirty` for a tree with changes.

A music cut is read from the log, and the log can hold a console reset after it. The last process's replay can't show that cut, so the stop and `bot.json` say so (`before_reset`) and name the input log and replay line of the process it happened in. That replay ends with `--exit-after` at the frame of the `# end` line closing the log, and has none when the line is missing.

The stop prints the `probe.sh --replay=` line that plays the input log back as `replay-NAME`. The line carries the settings after `--`, so the replay runs the run's build and disc with the run's switches. Their `--disc` and `--bin` paths are made absolute, since probe.sh reads a relative one from where it was run, and `--pads` plugs in the ports `--ports` drove, though a replay sets every port from the input log (a four-port soak's log replayed the same with `--pads=1`).

The line leaves out what the soak sets for itself, and any `GCN_WAV` or `GCN_AIDWAV` recording, which a replay would write over. It ends at the stop's frame with `--exit-after`, except for a hang, whose last frame a replay isn't known to reach.

The soak exits 0 when the run ended with no stop, at its time limit or at an `--exit-after` given after `--`, and 1 when it stopped. A bad argument, a game that never connected or a bot that raised an error exits 2 and writes no `bot.json`.

The tests stand a fake probe.sh in for the game, so they need no disc.

## bot_watch.py

What does the soak watch for while the bots play? `Frozen` watches the picture and `LogWatch` follows the game's `stdout.txt`, and each raises `Detected` from the bot callback. That ends the run at that frame with its input log whole.

`Frozen` fires when the picture's hash has stayed the same for 10 s of game time and the race bots' pads changed on at least 2 frames of those seconds. Frames the menu walker plays don't count, because a menu or a loading screen can stand still while the walker presses. `LogWatch` reads the log every 60 frames, gives the `[axv]` lines to stream_voices.py's `Tracker` and counts the console resets. It handles every line of a read before it raises the first cut, which carries the resets and the session that came before it. A `[session]` line starts the voices over, since the old process's are gone. It has no command line.

## bot_stop.py

How did the run end, and was that a fault? `classify` turns a `bot_link.run` result into a `Stop` whose kind is `game_exit`, `panic`, `engine_stop`, `hang`, `frozen_picture`, `music_cut` or `menus_stuck`. It returns None for a run that reached its time limit, or an `--exit-after` it was given. A game that never connected, a bad link or a bot that raised an error says nothing about the game, so those are a `SoakError`.

When the first console reset's shader rebuild took two thirds of the hang limit or more, a hang with no unanswered read and no assertion from the game says in its detail that the rebuild may be the cause. It has no command line.

## bot_record.py

What does a stop keep? `new_name` gives a run a NAME no earlier run used, `commits` reads the Dragoon and engine commits through git or `source-info.json`, `built_engine` reads the engine commit a session's `session.json` names, and `record` and `write` make `bot.json`. `replay_line` is the `probe.sh` command that plays an input log back. It has no command line.

## bot_player.py

What does the soak's bot do on each frame? `Player` is the callback `bot_link.run` takes. The menu walker has the pads while a menu is up and the race bots have them while a race or the city plays, and every frame the watchers are told what was sent. It prints a line of progress every five minutes, and has no command line.

## playtest.sh

What happened while I played? It runs the game in its window with sound, as `build/dragoon` runs for a player. It sets `GCN_SESSION` to `build/playtest/<date>-<time>/` ("Playtest sessions" in gcn-recomp's `docs/diagnostics.md`).

The game records into that one directory what went to the sound device (`out.wav`), the mixer's blocks before the audio ring (`aid.raw`), the input log with the memory card it started from (`inputs/`) and `session.json`. Everything it prints goes to the terminal and to `stdout.txt` there, the frame times and the sound device's timing lines among it. Quit the game as usual or press Ctrl+C in the terminal, and playtest.sh prints the directory.

```
tools/playtest.sh
```

That's all a playtester runs. It runs from the repository's root, so it plays on the card and shader cache in `saves/` as `build/dragoon` does. Nothing needs sending back.

When the overlay menu's Display page changes the picture, it writes `settings.txt` in the current folder, which for playtest.sh is the repository's root. Later runs started there read it, and `.gitignore` ignores it.

The session stays in `build/playtest/`, and session_report.py, pad_report.py and replay_session.py read it there. The recordings, the input log and the card snapshot are the player's own game data. `.gitignore` ignores them, and check_no_game_data.py fails on any that's tracked.

`--pads=N` plugs in more controllers and `--scale=N` sets the render scale. `GCN_*=value` sets any other switch, and one the session sets itself, like `GCN_WAV`, takes the value given instead. An empty value counts as unset, so the session fills in its own. To record no audio, give `GCN_WAV` and `GCN_AIDWAV` a path that can't be opened, such as `/dev/null/none`. `--dry-run` prints the directory and the command without running anything, which is how its tests check it.

It exits with the game's status, or 2 when `GCN_SESSION` is already set or the game isn't built. Without `GCN_SESSION` the game records none of this.

## session_report.py

What did the sound and the pacing do in a playtest, and which stage made each click? It reads a session's directory and nothing else, so nobody has to listen.

```
tools/session_report.py build/playtest/20261022-161851
```

It prints these:

- the session's length, start, host and display, with the engine commit it ran on
- the sound device's driver, rate, channels and buffer, then each late callback, each stretch of pulls the ring couldn't fill and each ring cut, with its time
- clicks, gaps and clipped runs a minute in `out.wav` (the device stage) and in `aid.raw` (the mixer stage), through audio_clicks.py
- each device-stage click put down to a stage
- each stretch of `aid.raw` that turns to loud noise, with where it starts and ends, through noise_blocks.py
- the frame pacing from frame 300 through frametime.py, with the frames over 33 ms
- the shaders compiled while it ran, and every `FATAL` or `FAULT` line, which a guest panic ends in

click_stages.py puts each device-stage click down to the mixer, the ring, the device or nothing, by the rules in its docstring. A late callback can starve the device without a mark in `out.wav`, so the late callbacks are listed on their own too.

The noise check reads only `aid.raw`, as noise_blocks.py explains, 10 seconds at a time. It never changes the exit code.

In `--json` the stretches are under `noise` in noise_blocks.py's own `--json` shape, and the value is null when `aid.raw` is missing or empty. The text says `aid.raw missing` for that and `none in aid.raw` when it finds no stretch, and it gives a count with a line for each stretch otherwise.

`--system-log` also counts the Core Audio overloads macOS logged from the session's start to 5 s past the end of `out.wav`, through core_audio_log.py's read-only `log show`, by process. The unified log doesn't keep them long, so an old session's window can come back empty.

`--json` prints the whole result, and `--list N` caps the times printed for each list (default 10). A file that's missing or empty leaves its sections out and is named on stderr. It exits 2 on a bad argument or a directory with no readable `session.json`.

A run-N directory, made when the game reset the console and started again, reads its own part of the session's `stdout.txt`. The report names the run that follows a reset, and says so when the game shut the console down instead.

## replay_session.py

Does a session replay faithfully? It plays a session's input log back through probe.sh in a hidden window with no sound, with `--replay`, `GCN_AIDWAV`, `GCN_AXSTATS=1` and SDL's dummy driver, as `build/probe/replay-<name>/`. Guest time is virtual, so a faithful replay hands the mixer the same blocks the session did.

It compares the SHA-1 of the session's `aid.raw` with that of as much of the replay's, says where they first differ when they do and lists the mixer clicks in the replay over the session's length. It also shows each line where the game said the replay parted from its recording, and warns when the session ran on another engine commit than the one built.

```
tools/replay_session.py build/playtest/20261022-161851
```

The replay runs to 600 frames more than 60 for each second of the session's mixer audio. probe.sh gives it twice the session's length plus two minutes. The input log is copied into the replay's directory first, since a replay keeps a scratch copy of the memory card beside the log it reads, so the session stays as it was.

An earlier replay's directory is deleted first. It exits 0 when the mixer audio matches, 1 when it differs or the replay stops short, and 2 on a bad argument, a session without `inputs/` or with an `aid.raw` of less than one frame, or a probe.sh run that failed.

## pad_report.py

Which of the pad's controls reached the game in a playtest, and on which port? It reads a session's input log, the state of each pad every time the game polled it, so it shows what the game got from the controller rather than what the controller sent.

```
tools/pad_report.py build/playtest/20261022-161851
```

For each port the game saw plugged in, it prints the gamepads put on it and taken off, then each control's use and the controls nobody used, which `--help` details. Comparing what the pad sent with what reached the game shows whether a control was pressed and lost, or never pressed. It also reads an input log's own directory, such as one in `saves/inputs/`, without the gamepad lines.

## frametime.py

How steady is the frame pacing, and what made the slow frames slow? It reads the log of a run made with `GCN_FRAMETIME=1` and prints the guest's and the renderer's mean, population standard deviation, p95, p99 and worst times from frame 300 unless `--from` says. It lists each frame whose render time went over `--slow` (16.7 ms unless you give it) with its batch shape and the shaders compiled in it, then each frame whose guest interval went over `--late` (25 ms unless you give it).

```
tools/probe.sh pace 130 tests/routes/city-trial-4p.txt 100000 --pads=4 --real-time GCN_FRAMETIME=1
tools/frametime.py build/probe/pace/stdout.txt
tools/frametime.py build/probe/pace/stdout.txt --from 3400
```

Add `--json` for machine output. Frame numbers are the `[rt]` lines'. A frame's batch is the `[ft]` line one lower.

A dumped frame is read back, which adds to its `[rt]` time, so time a run with a dump interval past its end (the 100000 above). Under `--fast` the guest interval is how fast the game goes, not its pacing. Use `--real-time` for pacing. Shader compiles show either way.

## framediff.py

Do two runs draw the same pixels? It compares every `frame_NNNNN.png` that two directories of frame dumps have in common, prints the share of pixels whose largest RGB difference is over a tolerance and the worst difference seen, and ends with a line counting the frames compared and the ones over budget. It exits 1 if any frame is over the budget. Alpha isn't compared.

framediff takes a tolerance. frame_hashes is an exact check against committed goldens. Two runs of a change need two builds and two NAMEs. Frames only one directory has are counted on stderr and don't fail the diff, which is normal when runs end at different frames.

```
tools/framediff.py build/probe/before build/probe/after --tolerance 3 --budget 0.001
```

## picture_box.py

Where does the picture sit in an output dump, and what shape is it? For each PNG it prints the box holding every pixel brighter than `--dark`, its width over its height and the bars left and right of it. `--color RRGGBB` boxes one colour instead, such as a button's outline, to compare one element's shape and place with a 4:3 dump's. The output stretch blurs the picture's edge into the bars by a few pixels, so `--dark 128` counts a pixel only once it's half lit.

```
tools/picture_box.py --dark 128 build/probe/wide/output_01200.png
```

## drawlog.py

Which cameras does a frame draw through, and what aspect does each hold? It reads a run's `stdout.txt`. The draws come from `GCN_DRAWLOG=N` with `GCN_DRAWLOG_VERBOSE=1`, and the cameras and the render callbacks that use them come from `DRAGOON_CENSUS=1`.

`cameras` prints one line per projection and viewport the frame draws through, in draw order, with its aspect (or orthographic frame), the viewport's aspect over the projection's and the draw count. The census cameras that match follow, with their stored aspect, the callbacks that set them and the ones that drew through them, by name with `--symbols analysis/symbols.txt`.

`--frame N` reads only frame N's census. Cameras that drew nothing come last.

`aspects` lists each perspective camera's stored aspect from one frame to another, with the frames it held it. It exits 1 when one changed within its viewport, which is how a widening that compounds frame on frame would show.

`setters` lists who set each camera's aspect from one frame to another. It reads the `[aspect]` line that `DRAGOON_CENSUS=1` prints for each call to `HSD_CObjSetAspect` and each perspective camera `HSD_CObjLoadDesc` loads.

Each line names a camera and where the call returns to, then where its caller returns to. It ends with the aspect the call was given and the one the camera held after, or `none` for a camera that isn't a perspective one.

`--symbols` names the function that holds each call by the sizes in `symbols.txt`, with how far in the return address is. The call is the instruction before the return address. `--cam ADDR` keeps one camera's lines.

When no line is left, `setters` says so on stderr. A camera whose aspect the game sets some other way has none.

`hud` checks that the HUD keeps its 4:3 box at a wider output. It reads two runs of one route to one frame with `GCN_DRAWLOG=N` and `GCN_DRAWLOG_VERBOSE=1`, the first at 4:3 and the second at `--aspect` (16:9 by default). The check is in hud_boxes.py, whose docstring gives how draws pair and when a pair fails, and drawlines.py reads the draw log's lines for both tools.

```
tools/probe.sh race 30 tests/routes/air-ride-race.txt 4200 DRAGOON_CENSUS=1 GCN_DRAWLOG=4200 GCN_DRAWLOG_VERBOSE=1
tools/drawlog.py cameras build/probe/race/stdout.txt --frame 4200 --symbols analysis/symbols.txt
tools/drawlog.py aspects build/probe/race/stdout.txt --from 3600 --to 4199
tools/drawlog.py setters build/probe/race/stdout.txt --from 4200 --to 4200 --symbols analysis/symbols.txt
tools/probe.sh race-wide 30 tests/routes/air-ride-race.txt 4200 --aspect=16:9 GCN_DRAWLOG=4200 GCN_DRAWLOG_VERBOSE=1
tools/drawlog.py hud build/probe/race/stdout.txt build/probe/race-wide/stdout.txt --aspect 16:9
```

It exits 2 when the log lacks the lines a command needs, naming the setting that makes them. `hud` exits 1 when an anchored draw fails.

## shader_cache.py

How many shaders does a cache or key list hold, and how many are new? It reads `saves/shaders.bin` (magic `WRSC`) and key lists (magic `GCSK`). The key size comes from the format word, and a magic or key size it doesn't know is refused. `count` prints the format and how many records and distinct keys the file holds. For a cache it also prints the distinct programs, which are the distinct `src_hash` values, since two keys can generate one source. It says how many trailing bytes it ignored, which is a record a kill cut off. `diff` prints how many distinct keys in NEW aren't in OLD and their share of NEW, and refuses two files in different formats. It counts and never lists keys.

```
tools/shader_cache.py count build/probe/demo/saves/shaders.bin
tools/shader_cache.py diff build/old-keys.bin build/probe/demo/saves/shaders.bin
```

## frame_hashes.py

Did a change alter what the renderer draws? It runs each route in `tests/hashes/manifest.txt` through probe.sh and compares the SHA-1 of every dumped frame with the golden in `tests/hashes/gl/<route>.txt`. `check` reports each frame that changed or wasn't reached. `record` rewrites the goldens, so use it only when a change to the output is on purpose. The frames are deleted once hashed and are never committed.

The manifest holds 24 routes, one per line. A line gives the name, the seconds to run, the dump interval, the frames the route must reach, any extra probe settings and any `warm=` or `warm-from=` setting. Pass route names to run only those.

On 2026-10-22, when the manifest held twelve routes, a `check` of all twelve took 302 s while other copies of the game ran on the same machine.

`check --slow=N` gives each route N times its seconds, for a build that runs slower than the one the goldens came from. N is a whole number from 1, the default. With N above 1 the game quits one dump interval past the route's last frame (probe.sh `--exit-after`), so a fast build doesn't spend the extra seconds.

The dump interval and the frames a route must reach don't change, and `record` refuses `--slow`.

```
tools/frame_hashes.py check title
tools/frame_hashes.py check title --slow=4
```

## audio_hashes.py

Did a change alter what the AX mixer outputs? It runs each route in `tests/hashes/manifest.txt` through probe.sh as a `--bench` run with `GCN_AXSTATS=1` and SDL's dummy audio driver, and compares the `[ax] hash list=N fnv=X` lines with the rows in `tests/hashes/audio/<route>.txt`. The hash runs from boot, so a row shows that nothing the mixer wrote before list N changed. `check` reports each row that changed, and fails a run that doesn't reach a row's list count. `record` rewrites a route's golden at `--lists`, or at the list counts it already has, so use it only when a change to the sound is on purpose. No audio is kept, only the hashes. The goldens hold for unpaced runs only, and their header says so.

```
tools/audio_hashes.py check air-ride-race
tools/audio_hashes.py record title --lists 7200,20000
```

On 2026-10-22, when the manifest held twelve routes, a `check` of all twelve took 300 s while other copies of the game ran on the same machine.

Each route runs under the NAME `audio-ROUTE` in `build/probe/`. An earlier run's directory is deleted first, so the game starts from a blank memory card. The last run's directory stays, so its `[ax]` lines can explain a changed hash. List counts are multiples of 400, the interval the game prints at. It exits 0, 1 or 2 as frame_hashes.py does.

As in frame_hashes.py, `check --slow=N` gives each route N times its seconds, and `record` refuses it. The rows are list counts, not times, so a slower build is held to the same ones. A bench takes no `--exit-after`, so a fast build spends all of the seconds.

A bench that crashes prints no report, and probe.sh exits 1. That counts as a route that doesn't match, so `check` says the bench printed no report and fails the lists it didn't reach. `record` exits 2 on it without writing a golden, as it does on any other probe.sh failure.

## interp_bisect.py

Which functions change a route when the interpreter runs them? It reads every function start from `analysis/symbols.txt` and checks ROUTE with frame_hashes.py, or with audio_hashes.py under `--audio`. Each check sets `GCN_INTERPRET` to a list of starts, a file in `build/bisect/` with one hex address a line, named by absolute path.

Every check but the first passes `--slow=N` on and takes ROUTE's seconds times N. One function among the 20,003 starts in `symbols.txt` takes at most 19 checks, and each further one at most 18 more. `--help` gives the search, what goes to `build/bisect/ROUTE-KIND-found.txt` and `-smallest.txt`, the 16-function cap and the exit codes.

```
tools/interp_bisect.py title --slow=20
tools/interp_bisect.py air-ride-race --slow=20 --audio
```

A build reads `GCN_INTERPRET` from gcn-recomp `782d7fa` on. One on an older pin runs every list natively, so the bisect exits 0.

## audio_clicks.py

Where does the sound click, drop out or clip? It reads a 16-bit PCM WAV, such as the one `GCN_WAV=<path>` records of exactly what went to the audio device, and prints how many of each it found and when. A click is a sample whose second difference is over 8 times the RMS second difference of the 5 ms either side, and at least 128. A splice, such as the audio ring skipping ahead, shows as one. Each click comes with its size, its largest second difference in dB from full scale, so a quiet tick can be told from a loud one. A gap is 5 ms or more of digital silence on every channel straight after sound. A clipped run is two or more samples at full scale on one channel.

```
tools/probe.sh title-wav 90 tests/routes/title.txt 100000 --real-time GCN_WAV=out.wav
tools/audio_clicks.py build/probe/title-wav/out.wav --from 5
```

The game runs inside the probe directory, so a relative `GCN_WAV` path lands there. Use `--real-time`, because under `--fast` the game makes sound faster than the device takes it. Under probe.sh the device is SDL's dummy driver, and gcn-recomp pulls the sound itself at a sound card's pace under it, so the recording is what a sound card would get. `GCN_AIDWAV` (below) records the game's sound before the audio ring. The recording is the game's own sound, so it stays in `build/probe/` and is never committed. `--list N` caps the times printed for each, and `--json` prints the whole result. Detections under 1 ms apart chain into one click, however long the run. The click is reported at the run's first sample. `--marks` and `--period` match that first sample.

`GCN_AIDWAV=<path>` records the DMA's own blocks instead, before the audio ring touches them, as headerless 16-bit stereo at 32 kHz. `--raw 32000` reads that. `--period 160` also counts the clicks within 2 samples of a multiple of 160 samples (the DMA's 5 ms block) and how many would land there by chance.

```
tools/probe.sh title-aid 90 tests/routes/title.txt 100000 --real-time GCN_AIDWAV=aid.raw
tools/audio_clicks.py build/probe/title-aid/aid.raw --raw 32000 --period 160
```

`--marks FILE` reads sample indices from a text file (one a line) and counts the clicks near one and the marks with a click near them. With `GCN_AXSTATS=1` the game prints a `[ring] cut N frames at output frame F` line each time the audio ring throws away what it has too much of, and F is an index into the `GCN_WAV` recording.

```
tools/probe.sh title-cuts 90 tests/routes/title.txt 100000 --real-time GCN_WAV=out.wav GCN_AXSTATS=1
sed -n -E 's/^\[ring\] cut .* frame ([0-9]+)$/\1/p' build/probe/title-cuts/stdout.txt > build/probe/title-cuts/cuts.txt
tools/audio_clicks.py build/probe/title-cuts/out.wav --marks build/probe/title-cuts/cuts.txt
```

`analyse_file`, for other tools to call, reads a recording 10 seconds at a time and finds what one pass would.

## audio_scorecard.py

How does each build's sound measure, route by route? It plays every route in `tests/hashes/manifest.txt` on one or more Dragoon builds and counts clicks, gaps and clipping at two stages through audio_clicks.py, with nobody listening. Each build is a clone's `build/` directory with a label.

A route plays on each build in turn before the next route starts, through that clone's own probe.sh, hidden, with SDL's dummy audio driver and `GCN_AXSTATS=1`. It plays twice on each build, once `--real-time` and once unpaced. The route files come from this clone, so every build plays the same presses.

```
tools/audio_scorecard.py base=/path/to/old-clone/build current=build
tools/audio_scorecard.py base=/path/to/old-clone/build current=build --routes title --json
```

The five routes `docs/dev/scorecard.md` scores (`--routes title,menu,air-ride-race,city-trial,city-trial-4p`) take about 11 minutes a build. An unpaced run's game time doesn't follow the host's, so two unpaced runs of one build should give the same blocks, and the pairs compared did, byte for byte (`docs/dev/scorecard.md`). `--help` gives each stage's measures, where each run and its `commits.json` go, how `--no-run` reads them and what `not logged` and `not recorded` mean.

A real-time run's clock catches up when the host falls behind, so presses land on other frames and sounds move, and its blocks say as much about the host's timing as about the build. At gcn-recomp `b848158` a catch-up jump could end a block before the guest had queued the next buffer and make the DMA play that buffer twice, which `a87ab06` stops. A guest that fills its buffers from its main loop can still fail to refill in time when a catch-up delivers the owed blocks close together, and then the DMA plays a buffer again ("The clock" in `gcn-recomp/docs/diagnostics.md`).

The real-time run records `GCN_AIDWAV` too, for block_clicks.py. scorecard_runs.py plays a route on a build and scorecard_measure.py scores a route's two runs. Neither has a command line.

## block_clicks.py

Do a run's mixer-stage clicks sit on the blocks the DMA played twice or delivered catching up? It reads a `GCN_AIDWAV` recording and its block log (`<file>.txt`), and for each kind prints the marked blocks, their stretches, the clicks on them and the count chance would put there. A block log whose last block ends more than a second from the recording's end exits 2, and that check goes by length only, so another run's log of the same route passes.

```
tools/block_clicks.py build/probe/scorecard-menu/mixer.raw
```

The baseline's real-time title recording paired with current's title log printed counts and exited 0.

## click_diff.py

Which clicks does one build's unpaced recording of a route have that another's doesn't? Unpaced, the two recordings line up sample for sample, so B minus A is what the builds did differently. For each click only one has, it prints the largest B minus A within 5 ms, B minus A's second difference at the click, whether each build is silent there and whether B minus A steps at the nearest block join. A second difference of 0 means both builds have the same edge, and only the sound around it differs. `--seconds S` cuts both to S.

`--seconds S` also reads no more than S seconds of each recording, so a route's scored seconds can be compared without reading an unpaced run that went on for tens of minutes. The share of samples that are the same in both is rounded down, so 100.0% means every sample.

```
tools/click_diff.py /path/to/old-clone/build/probe/scorecard-unpaced-title/mixer.raw build/probe/scorecard-unpaced-title/mixer.raw
```

## noise_blocks.py

Where do the DMA's blocks turn to loud noise? It weighs each 160-sample block of a `GCN_AIDWAV` recording, setting its high-frequency energy against its total as the RMS of its first difference over its RMS. White noise gives about 1.41, and music and effects give far less. A block is noise-like over 1 on a channel whose peak is over 8,000, and it prints the stretches such blocks form. The game's own bright sounds, a crash for one, make short stretches too, so a stretch is a place to look rather than a fault. It reads the DMA's 32 kHz only. The ring interpolates to 48 kHz for the device, and `test_noise_blocks.py` shows that noise which flags every block at 32 kHz flags far fewer after a linear interpolation to 48 kHz, so a `GCN_WAV` recording isn't a fair input.

```
tools/noise_blocks.py build/probe/scorecard-menu/mixer.raw
```

session_report.py runs it on a session's `aid.raw` 10 seconds at a time, and the command above reads the whole file.

## clip_signs.py

Which side of full scale do a build's clipped runs sit on? audio_clicks.py counts a clipped run at 32,767 or at -32,768 as one number. A build whose clamp stops at -32,767 holds its negative clipping at a value that number leaves out, so two builds' counts only compare once they're split by sign. clip_signs.py takes the same `LABEL=BUILD_DIR`, `--routes` and `--margin` as audio_scorecard.py and reads the two recordings it scores from the runs already in each `build/probe/`, so it plays no game. The mixer is the unpaced run's recording cut where the scorecard cuts it. The device is the real-time run's whole recording. For each it prints the clipped runs and their samples at +32,767 and at -32,768, the samples at -32,767 and the lowest and highest sample. For the real-time run it also prints the highest main L peak in its log, which shows whether that run reached a loud stretch.

```
tools/clip_signs.py current=/path/to/old-clone/build next=build --routes air-ride-race
tools/clip_signs.py current=/path/to/old-clone/build next=build --routes menu --margin 150
```

A recording that isn't there reads `not recorded`, and a run that didn't reach its route's last checkpoint exits 2, as does an unpaced recording shorter than the cut.

## ax_stats.py

What did the game's voices ask the AX mixer for over a run? It sums the `[ax] pb` and `[ax] bus` lines of runs made with `GCN_AXSTATS=1` (their fields are in `gcn-recomp/docs/diagnostics.md`) into a row per count and a column per run. `--until N` stops at list N, so two unpaced runs that reached different lists compare over the same ones, and `--help` gives the rest.

```
tools/audio_hashes.py check
tools/ax_stats.py build/probe/audio-title/stdout.txt build/probe/audio-air-ride-race/stdout.txt
tools/ax_stats.py before/stdout.txt build/probe/audio-title/stdout.txt --until 20000
```

## stream_voices.py

Which voices did the mixer stop that the game didn't? It reads the `[axv]` lines of a run made with `GCN_AXVOICES=1` and lists each voice that ran with `stream=1` or `looping=1`, or that ended early, by parameter block address. A block that runs again after it stopped or ended, or that gets a new sample, counts as a voice for each run.

`--help` gives the columns and the rules for `ended early`. A run lists hundreds of voices, because sound effects start with the loop flag set too. The music streams start at an address in `018xxxxx`, and some scenes play a PCM16 ring at `0062A280` and `0062A780` instead, so filter the `at` column for those.

```
tools/probe.sh voices 60 tests/routes/menu.txt 100000 GCN_AXVOICES=1
tools/stream_voices.py build/probe/voices/stdout.txt | grep -E "  at (018|0062A)"
tools/stream_voices.py build/probe/voices/stdout.txt | grep "ended early"
```

It only reports, so it never exits 1. It exits 2 on a bad argument, or on a log it can't read or that has no `[axv]` lines.

## warm_shaders.py

Will a player's first session stall on shader compiles? It plays the game once so the cache is already warm. The build runs it as the `dragoon_warmup` target, unless it's configured with `-DDRAGOON_WARMUP=OFF`, has no disc or is a cross build. It runs the game hidden and fast, with SDL's dummy audio driver and `--no-gamepads` so it never opens a controller, with one pass per route in `tests/hashes/manifest.txt` that has no `warm-from=` setting. Each pass has a scratch directory of its own and starts from a blank memory card, as a fresh install does, because a route that finds an earlier pass's card takes other menus and builds other keys. Its `shaders.bin` starts as a copy of the player's own and gains the keys its route builds. Passes don't share a cache, so several play at once. `--jobs N` sets how many, and the default is a third of the cores, at most six. The longest start first. When they are done their caches are merged, each key once and in the manifest's order. The game doesn't inherit `GCN_INPUT`, `GCN_WAV`, `GCN_PROFILE`, `GCN_FEED_DUMP` or `GCN_SESSION`, since each names a file or route that the passes would otherwise share. `--disc FILE` names the disc image every pass plays, which a game built from the engine kit needs.

A pass plays to 900 frames past its route's last required frame, or to frame N when the route has a `warm=N` setting in the manifest. N has to be a whole number past that frame, and a route gets one at most, or the warm-up exits 2 naming the route and the manifest line.

A route with a `warm-from=ROUTE` setting gets no pass, because ROUTE's pass plays what the route does. The comment at the top of `tests/hashes/manifest.txt` says why some routes open a `-courses` route or keep a pass of their own, and how a change to a pass has to be checked. `test_routes.py` checks that the four courses that compile late open their passes and race past their last compiles.

`air-ride-race`, `air-ride-celestial-valley` and `air-ride-beanstalk-park` get the programs they first draw past their own stretches, at frames 5,649 to 12,068 of their own routes, from Sky Sands, which draws them by frame 14,186.

The merged cache replaces `saves/shaders.bin` only once every pass has succeeded, and nothing else in `saves/` is touched, so the memory card stays as it is. `saves/.shader-warmup` stamps what the warm-up played, and a run with a current stamp does nothing unless `--force` is given. `--help` gives what the stamp holds and the pass timeout.

`--report DIR` keeps each pass's output as `NAME.log` and the cache it left as `NAME.bin` in DIR, and prints `report.txt`. A row says how many programs the game built from the starting cache before its first frame and how long that took, how many keys the pass built itself and how many of those no other pass built. It also gives the keys and programs the pass added that the starting cache and the passes before it in the manifest lacked, and the merged cache's size so far. With `GCN_FRAMETIME=1` in the environment it gives the frame the pass built its last program in.

Four more columns split each pass's seconds into starting the game, frames up to 2,000, frames 2,001 to 3,400 and the rest. A frame's share is its `[ft]` guest interval, and starting the game is the time before the first frame and after the last. They need `GCN_FRAMETIME=1` too and read 0 without it, and a closing `all` row adds up the frames, the seconds and the four splits.

```
tools/warm_shaders.py --force
env GCN_FRAMETIME=1 tools/warm_shaders.py --force --jobs 4 --saves build/probe/warm/saves --report build/probe/warm/report
tools/shader_cache.py count saves/shaders.bin
```

## prune_runs.py

Which runs in `build/probe/` are old enough to clear? probe.sh and the hash tools leave a directory per run. For each CLONE it lists the direct children of `CLONE/build/probe/` with nothing newer than `--hours` (24 unless you give it).

Without `--delete` it prints what would go, a line each with its size and age, then the total. With `--delete` it removes those and prints the same lines and the space freed. A size is the files' lengths, not the blocks they take.

```
tools/prune_runs.py /path/to/clone
tools/prune_runs.py --hours 6 --delete /path/to/clone /path/to/old-clone
```

Names listed in `build/probe/keep`, one a line, stay, compared ignoring case. A run you mean to read later, such as the last `audio-ROUTE` directory audio_hashes.py leaves or the `scorecard-ROUTE` ones audio_scorecard.py `--no-run` reads back, needs its name there. `--help` gives the link and refusal rules and the exit codes.

## routes.py

Which routes does the repository play? `tests/hashes/manifest.txt` lists them, and routes.py reads it into `Route` records and picks routes by name. `route_file` gives a route's file in `tests/routes/`, and the module has no command line.

A route's `warm=N` setting goes in its `warm` field and its `warm-from=ROUTE` in its `warm_from` field, and both stay out of its probe.sh settings, since probe.sh refuses a setting it doesn't know. A bad N, a second `warm=` or `warm-from=`, both on one route or a setting that looks like a misspelled one, such as `WARM=` or `warm:`, raises `ValueError` naming the route and the manifest line. So does a `warm-from=` that names the route itself, a route the manifest doesn't list or one with a `warm-from=` of its own.

## source_info.py

What does a source snapshot hold? Its `source-info.json` names the Dragoon and gcn-recomp commits and the disc they build (`disc_id` and `dol_sha1`), and export_source.py writes it. source_info.py, which has no command line, reads and writes that file and refuses one with a field missing or malformed, naming the file.

## probe_dirs.py

What happens to a probe run and its directory? It holds `remove_run`, which deletes a directory from `build/probe/` for good, and `run_probe`, which runs a probe.sh command line with its output dropped and turns a nonzero exit into a `ProbeFailed` error that keeps the status. `slow_factor` reads the N of a `--slow=N` and refuses anything but a whole number from 1.

`remove_run` unlinks a link inside the directory and leaves its target alone, and it refuses a directory that's itself a link. It has no command line.

## aid_blocks.py

What does `GCN_AIDWAV` write? It holds the DMA's rate and 160-sample block, with the reader for the block log beside each recording, for the audio tools. It has no command line.

## session_log.py

What does a session's log say about its sound and its crashes? It reads the `[audio]`, `[ring]`, `[shaders]` and `[session]` lines of a session's `stdout.txt`, with its `FATAL` and `FAULT` lines.

It splits the log at its `[session]` lines, so a run-N directory gets its own part. It has no command line.

## click_stages.py

Which stage made each click the sound device got? It puts each device-stage click down to the mixer, the ring, the device or nothing, by the rules in its docstring. It has no command line.

## core_audio_log.py

How many Core Audio overloads did macOS log while a session ran? It builds the read-only `log show` command and counts the matching lines by process. Its tests read lines captured from a Mac's log, with overload lines written in their layout and never live output.

It has no command line.

## session_text.py

How does session_report.py's result read as text? It has no command line.

## check_no_game_data.py

Is anything from a disc tracked by git? It flags tracked paths that look like game data:

- Disc images and executables by suffix, `.raw` memory cards and audio recordings, `.wav` recordings and `.bin` shader caches and key lists, wherever they sit.
- A mod's game files by suffix (`.dat`, `.hps`, `.bnr`, `.elf` and `.gct`), wherever they sit.
- Anything under a top-level `build*/` or `rom/` (except the `rom/` README), and anything under a `saves/` at any depth.
- Anything under a top-level `mods/` in any letter case. A `mods/` further down, such as `tests/mods/`, is fine.
- Frame dumps (`frame_NNNNN.png` and `output_NNNNN.png`), `stdout.txt` and `panic.txt`, wherever they sit. Other PNG files are fine.
- A playtest session's `session.json`, the input log's `inputs.txt` and the `aid.raw.txt` block log, wherever `GCN_SESSION` put them. Its `.raw` and `.wav` recordings fall under the suffix rule, and a session under `build/` under the build rule.

It prints one line per path and exits 1 if it found any, so it can run in CI. It prints nothing when the tree is clean.

```
tools/check_no_game_data.py
```

## ci.py

Does the commit pass CI? ci.py runs every step of CI's four jobs, `tools`, `macos`, `kit` and `launcher`, from the repository's root. The workflow runs each job by name, so a Mac without a runner runs the same steps. It stops at the first step that fails and exits 1, and an unknown job exits 2.

The `kit` job leaves the kit in `engine kit/` and links it against stub tables in `stub game/`, with a space in each name because a player's path may have one. It deletes both first, so a second run starts from scratch there. The builds go to `build-nodisc/` and `build-kit/` and a second run reuses them, so delete those for a fresh build.

```
tools/ci.py
tools/ci.py tools launcher
```

## mutant.py

Do the tests notice when the code breaks? It runs a test directory on a changed copy of a commit and reports whether the tests failed. A changed copy is a mutant, which is killed when the tests fail and survives when they pass, so a survivor is a gap in the tests.

A spec file holds the changes. It can live anywhere, and committing it lets others run the same check.

The spec is a JSON list of mutants. Each has a `name` and a `dir` to discover tests in, relative to the repo (`tools` or `launcher/tools`). Its `replace` list holds `{file, old, new}` edits that are applied together, in order. Every `old` has to occur exactly once in its file, so a typo can't make a mutant that changes nothing. `new` may be empty. An optional `pattern` says which test files in `dir` to run. It's what `unittest discover -p` takes and it defaults to `test_*.py`. It matches file names, so it has no `/`. A `dir` and `pattern` that run no test are refused at their baseline.

```json
[
  {"name": "git() drops the exit status",
   "dir": "tools",
   "pattern": "test_export_source.py",
   "replace": [{"file": "tools/export_source.py",
                "old": "why = e.stderr.strip() or f\"exit {e.returncode}\"",
                "new": "why = e.stderr.strip()"}]}
]
```

```
tools/mutant.py build/probe/mutant/spec.json /tmp/dragoon-mutants
```

This spec sits in `build/probe/`, which git ignores, so it stays on your machine.

It prints `killed NAME`, `survived NAME` or `timeout NAME` for each mutant as it finishes, then `total N, killed K, survived S, timeout T`. A kill that isn't unittest's exit 1 says how the run ended, as in `killed NAME (exit -9)` for a signal or `(exit 5)` for no tests. A crash in the tool exits 2, so it can't read as a survivor.

Each run is `PYTHON -B -m unittest discover -s COPY/DIR -p PATTERN`, run from the copy, PYTHON being `--python` (the Python running the tool unless you give another). With the default pattern a mutant on `tools` takes about a minute. The example above runs one test file and takes seconds.

`tools/mutant.py --help` gives how each run is isolated (a fresh `git archive` copy of `--rev`, a baseline for each `dir` and `pattern` that has to pass and run a test, a bare environment and `--timeout`), what DEST keeps, how ^C and signals clean up and the exit codes. A copy has no `.git` and no gcn-recomp, so a test that needs either has to skip itself, as `RealTreeTest` in `test_launcher_build.py` does. A mutant that breaks an import counts as killed too, so read its log before you trust a kill that matters.

## export_source.py

What source does the launcher build? export_source.py writes a snapshot of Dragoon's HEAD, with gcn-recomp in `gcn-recomp/` at the commit HEAD pins, as `git archive` gives them. Untracked and ignored files such as `rom/game.iso`, `build/` and `saves/` never reach it. Nor does git history. It adds `source-info.json` (see source_info.py) and `source-manifest.txt`, which lists every other file as a `<sha256>  <path>` line sorted by path.

```
tools/export_source.py /tmp/dragoon-source
```

It writes nothing and exits 2 when:

- a tracked file in either repository has uncommitted changes. Untracked files don't count, since `git archive` leaves them out anyway
- gcn-recomp is checked out at another commit than HEAD pins, or isn't checked out
- OUT isn't empty
- git or tar fails while writing, which leaves OUT missing or empty again

`--repo` names a checkout other than the one holding the tool. A missing OUT is made. git comes from `PATH` and tar is `/usr/bin/tar`.

Its `src_digest` is the SHA-256 of `src/`'s lines in a `source-manifest.txt`. It comes out the same from a snapshot and from a clean checkout of its commit, one with nothing untracked, ignored or changed in `src/`. engine_kit.py writes it to the kit, and launcher_build.py checks it.

## launcher_build.py

How does the launcher build the game? launcher_build.py is its recipe, and a developer can run it from a shell. Given a snapshot from export_source.py, a kit from engine_kit.py, the player's disc and every tool by full path, it builds `<data>/game/<id>/Dragoon.app` and points `<data>/game/current` at it. The player's Mac runs no CMake or Ninja and never builds SDL. It prints one JSON event per line on stdout (the format is in `--help`). It writes every line the tools print to `--log`, with each command, each step's time and how much `--data` and `--cache` hold after it. That measurement never fails a step. A file removed while it's measured counts as nothing, and any other error is written to the log in its place.

| Step | What it does |
|---|---|
| recompile | Empties `<cache>/build`. There the snapshot's `extract_dol.py` takes `main.dol` from the disc, checked against the disc ID and SHA-1 in `source-info.json`, and its `recomp.py` writes the game's C to `gen/` |
| compile | Runs make on the kit's Makefile with a job per core, which compiles `gen/*.c` and links `dragoon` with the kit. Each compile line make prints becomes a progress event |
| warmup | Runs the snapshot's warm_shaders.py on the disc and a copy of the player's shader cache, one progress event per pass |
| package | Wraps the game in an app sealed ad hoc, with a `stamp.json` naming both commits and the SDK |
| swap | Points `game/current` at the new build, then installs the warmed cache in `<data>/saves`, where a failure is only a warning |

The tools run with `PATH=/usr/bin:/bin:/usr/sbin:/sbin` and five other variables, listed in `--help`, so nothing Homebrew or MacPorts installed reaches the build. The snapshot and the kit are only read, and Python runs with `-B`, so a build leaves the launcher's seal as it was.

Before the swap nothing in `<data>` changes but the new `game/<id>`. A build that fails before the swap leaves the old game current and `saves/` as it was, and a package step that fails removes its `game/<id>`. Earlier builds stay in `<data>/game` for the launcher to delete.

Once `game/current` points at the new build, the build has succeeded, so a `--log` line the recipe can't write afterward is lost and fails nothing. A shader cache file that can't be installed afterward is a `warning` event, and the run still prints `done` and exits 0 with that file left as it was. When only the stamp can't be installed, the new cache stays beside the old stamp, so the next build warms again.

A SIGTERM, which is how the launcher cancels, exits 143 once the running step has cleaned up. It leaves no half-made `game/<id>` and no temp file in `saves/`, and one that lands after the swap leaves the new game current.

The swap makes a temporary link, `.current.<pid>.partial`, in `<data>/game` and renames it over `game/current`. A SIGTERM that lands right after the link is made can leave it there, and the next swap removes it.

A second build while one runs exits 3 at `<cache>/build.lock` without touching anything, its `--log` included. A kit whose `kit.mk` names a gcn-recomp commit other than the one in the snapshot's `source-info.json` or a `src/` digest other than the snapshot's, or names none, exits 2 the same way, with an error event at step `kit`. Its `engine.o` and headers wouldn't match the generated C.

```
tools/launcher_build.py --source /tmp/dragoon-source --kit /tmp/engine-kit \
  --disc "$HOME/Kirby Air Ride (USA).gcm" \
  --data /tmp/dragoon-data --cache /tmp/dragoon-cache --log /tmp/dragoon-build.log \
  --make /Library/Developer/CommandLineTools/usr/bin/make \
  --cc /Library/Developer/CommandLineTools/usr/bin/clang \
  --cxx /Library/Developer/CommandLineTools/usr/bin/clang++ \
  --python /Library/Developer/CommandLineTools/usr/bin/python3 \
  --sdk /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk
```

A first build on an M4 Max, with the Command Line Tools' make 3.81, clang 21 and the 26.5 SDK, took 95.2 s. That's 4.2 s to recompile, 18.0 s to compile and link, 72.7 s to warm up and 0.1 s to package. `--data` and `--cache` held 482 MB at most, once the game was packaged and before `<cache>/build` was deleted, and 54 MB afterwards. A second build of the same commit took 22.2 s, because the warm-up found its stamp current.

`--no-warmup` skips the warm-up. `--keep-build` keeps `<cache>/build`, which is deleted after a good build otherwise.

## mod_choices.py

How does a player pick and apply Riivolution package options? `mod_choices.py` reads `mods/` in the folder holding `settings.txt`, and [the Riivolution package guide](../docs/dev/mods.md) says the rest.

```sh
python3 tools/mod_choices.py list --data DIR
python3 tools/mod_choices.py set --data DIR pack.xml opt 1
python3 tools/mod_choices.py apply --data DIR --disc IMAGE
```

## mods.py

Which mods does a mods folder hold, and can the game be built with them? Each folder in it whose name doesn't start with a dot is one mod. A mod's `files/` mirrors the disc's root, and its `dol.txt` is a patch list in the format of gcn-recomp's `docs/dol-patches.md`.

`mods.py` checks folder mods given as its MODS argument, while `mod_choices.py` handles Riivolution packages in `mods/`.

Either may be missing, and either name may come in any letter case. The other files beside `dol.txt` are the ones its `section` lines may name, so a section's file sits there and not under `files/`.

Dotfiles and dot folders are skipped everywhere, so a `.DS_Store` never reaches the disc. A loose file in the mods folder isn't a mod.

```
tools/mods.py check "$HOME/Library/Application Support/Dragoon/mods" --dol-sha1 SHA
```

`check` prints one JSON object. It lists each mod's name, file count and bytes in folder name order ignoring case, then gives the digest.

A mod holds the files under its `files/`, its `dol.txt` and the other files beside that. The digest is the SHA-256 over each file a mod holds, by the mod's name and its path in the mod, with its size and its SHA-256. In a mod without `dol.txt` the files beside `files/` are left alone, so they're not in it.

Adding, removing, editing or renaming a file a mod holds changes the digest, while a dotfile or a loose file in the mods folder never does. It's `none` when no mod holds a file, and a missing or empty folder has no mods.

A mod is refused for any of these. `check` then prints one object with the error, the mod and the path in it instead.

| Refused | Where |
|---|---|
| A link | Under `files/`, anywhere in a mod with a `dol.txt` or in place of the mod's own folder |
| `files` or `dol.txt` in two letter cases | At the top of a mod |
| Anything that isn't a file or a folder, or can't be read | Under `files/` or anywhere in a mod with a `dol.txt` |
| A file of 4 GiB or more | Under `files/` or anywhere in a mod with a `dol.txt` |
| A folder that can't be read | The mod's own folder |
| A name that isn't ASCII or holds a control character | Under `files/` |
| `main.dol` in any letter case, since code changes go in `dol.txt` | At the top of `files/` |
| Two files that are one disc path ignoring case | Under `files/`, in one mod or two |
| A file where another file needs a folder | Under `files/`, in one mod or two |
| Over 1 MiB, not UTF-8 or not starting with a `dol` line that names SHA | `dol.txt` |

It exits 0 when no mod is refused, 1 when one is and 2 on a bad argument or a mods folder it can't read.

`prepare`, for the build, clones every mod's files into a new folder through clone_file.py. Its `files/` holds every file under the mods' `files/` by disc path, and each `dol.txt` goes to `patches/N/` with the files beside it, N counting the mods from 1. When any mod has a `dol.txt`, gcn-recomp's `dol_patch.py` applies the lists in mod order to the game's checked DOL and writes `main.dol` and `main.dol.syms` in the folder.

Then gcn-recomp's `disc_overlay.py` builds the overlay from the clones, with that `main.dol` as the DOL it boots. `prepare` returns the DOL to recompile, the manifest and the digest of the clones. The DOL is the one the overlay boots, and the digest comes from the clones, so a mod edited during a build doesn't change it.

A refusal from either tool that names a mod's list or file comes back naming the mod. Any other failure of either tool is a `PrepareError`, and so is a file that can't be cloned or copied, such as one deleted since the scan, which it names. Both tools run under `-B` with tool_env.py's environment and nothing else, as the recipe's own tools do, so the user's site-packages stay out.

The tests make every mods folder, image and DOL, at paths with spaces. Some run `prepare` against fakes of the two tools, and the rest against the pinned gcn-recomp's own, skipping when it isn't checked out.

## clone_file.py

How does a build copy a file without copying its bytes? `clone` makes an APFS clone through `clonefile`, which shares the original's blocks until either changes, so editing a mod afterwards leaves the build's copy as it was. Where the volume can't clone, or the call fails for any other reason, it copies the bytes instead.

Neither way follows a link, so a clone of a link is a link and a copy of one fails. It has no command line.

## tool_env.py

What environment does a tool the build runs get? `tool_env()` gives only `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, `HOME`, `TMPDIR`, `LANG`, `PYTHONDONTWRITEBYTECODE` and `PYTHONNOUSERSITE`. launcher_build.py runs the recipe's tools with it and mods.py runs gcn-recomp's, so the two can't drift apart.

It has no command line.

## engine_kit.py

What does a player's Mac need to build the game without CMake or SDL's source? engine_kit.py packs `engine.o` (runtime_check's objects, Dragoon's `src/` among them), `libSDL3.a`, the two runtime headers, `kit.mk`, the Makefile from `launcher/kit/` and the licenses, from a build configured with no disc and a deployment target. launcher_build.py pairs a kit with a snapshot by `kit.mk`'s `ENGINE_COMMIT` and `SRC_SHA256`, and `--help` lists the rest of `kit.mk` and the builds it refuses.

```
cmake -S . -B build-kit -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 -DGAME_ISO=
ninja -C build-kit runtime_check SDL3-static
tools/engine_kit.py --build build-kit --out build-kit/kit --strip-debug
```

CI's `kit` job runs these, links the kit against `tests/kit/stub_tables.c`, empty tables that stand in for the recompiler's output, and uploads the kit as the `engine-kit` artifact. A framework missing from `game_libs.txt` fails that link.

On the player's side, launcher_build.py has the Command Line Tools' python3 run `extract_dol.py` and `recomp.py` into a directory, and then the kit's Makefile compiles `gen/*.c` there and links `./dragoon`. `KIT` is named on the command line, since make splits the Makefile's own path at its spaces, and the kit's path may have them:

```
make -f "$KIT/Makefile" -j16 KIT="$KIT" SDK=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  CC=/Library/Developer/CommandLineTools/usr/bin/clang CXX=/Library/Developer/CommandLineTools/usr/bin/clang++
```

The Makefile's header lists the characters that `KIT`, `SDK`, `CC` and `CXX` can't hold. A new `kit.mk` or kit header rebuilds every object. engine_kit.py exits 1 when ld or strip fails and 2 on a build it can't make a kit from.

## check_bundle.py

Does the launcher ship anything game-derived? The disc never reaches CI, so nothing can compare bytes with the game. check_bundle.py looks for the shapes game data takes in `Dragoon.app`, or in a DMG that it attaches read-only and detaches again. Run it on the unsigned app and again on the signed DMG, since the manifest allows the `_CodeSignature` that signing adds.

| Check | What fails |
|---|---|
| paths | A file, link or empty directory outside the source snapshot that `launcher/bundle-manifest.txt` doesn't list. Anywhere, a path that `check_no_game_data.py` flags or that a build leaves behind (`gen/`, `rels/`, `inputs/`, `main.dol`, `CMakeCache.txt`, `build.ninja`, `memcard_*`, `.shader-warmup`, in any letter case) |
| executables | A file that starts with a Mach-O magic at a path the manifest doesn't list for one, such as a built `dragoon`. An ar archive (`!<arch>`, or a fat file holding one) or a file named `.a` or `.o` in any letter case that has no `object` or `engine` line of its own, and an engine that isn't a thin Mach-O object ending where its string table does. Any of those or any Mach-O that can't be read whole, such as an archive member that isn't the opening symbol table or a thin Mach-O ending at its string table. One that defines `fn_` and 8 hex digits or `g_recomp_*` in any architecture, the names the recompiler gives the game's functions and tables |
| content | The GameCube disc magic at offset 0x1C, a `CISO` header, or the disc ID anywhere outside the snapshot, or more than once in the engine object. The engine carries the disc ID once, as a public constant |
| source | A snapshot that differs from `export_source.py`'s output for the commit, file by file by SHA-256. A dev tree's `rom/game.iso` link or empty `build/` shows up here |
| size | An app or a DMG over its budget in the manifest |
| DMG | Anything besides `Dragoon.app` and an `Applications` link to `/Applications` |

```
tools/check_bundle.py launcher/dist/Dragoon.app --commit SHA
tools/check_bundle.py launcher/dist/Dragoon.dmg --commit SHA
```

It prints one `kind: path (detail)` line per finding and nothing when the bundle is clean, and paths are relative to the app. It exits 0 when clean and 1 with findings. A checkout that isn't at `--commit` exits 2, and so do a manifest it can't read and a DMG that won't attach, or won't detach after a clean check.

`--repo` names the Dragoon checkout the reference snapshot is exported from, the one holding the tool unless you give another. `--manifest` names another manifest.

A path that no manifest line allows is a finding, so a new file in the app starts as a line in the manifest. The app's budget in the manifest is an estimate, with a guess for the launcher and Sparkle. The engine kit sits at `Contents/Resources/kit/`, beside the snapshot.

## bundle_manifest.py

What may the app hold? It reads `launcher/bundle-manifest.txt`. That file names the source snapshot's directory and the two size budgets. Everything allowed outside the snapshot has a line naming its kind, such as a plain file, a directory prefix, a Mach-O executable or a symlink with its target. Static libraries and objects have lines of their own, and one of them at most is the kit's engine, the only file outside the snapshot that may hold the disc ID. The format is at the top of the module. It has no command line.

## bundle_checks.py

What does each check look at? bundle_checks.py holds the six checks above as functions that return findings, and the `Finding` they print as. It has no command line.

## bundle_objects.py

How does check_bundle.py read a Mach-O file or an archive? nm skips an archive member that isn't an object without a word, so bundle_objects.py reads each member's header first, in a plain archive and in each archive slice of a fat file. Only the first member may be the symbol table, under one of its four `__.SYMDEF` names. Every other member has to be a thin Mach-O that ends where the string table its `LC_SYMTAB` names does, as clang and ld end one, with fewer than 8 newlines after it, as ar and strip pad one. Then `nm --defined-only -j -arch all` lists what the file defines in every architecture, since nm shows a fat file's host slice alone by default. The tests compile objects from one-line C with the system's `cc` and archive them with `ar` and `lipo`. They also build archives byte by byte. It has no command line.

## bundle_tree.py

What does an app tree hold? It lists the regular files with their sizes, the symlinks with their targets, the empty directories and any odd entries such as pipes, and never follows a link. It has no command line.

## bundle_dmg.py

How does check_bundle.py look inside a DMG? It attaches the image with `hdiutil attach -readonly -nobrowse -mountpoint` at a fresh temporary directory and always detaches it, forcing the detach if the volume is busy or the plain one hangs. An attach gets two minutes and a detach one, so a stuck hdiutil can't hold a CI job until its own timeout.

A detach that fails after checks that found something still prints the findings, with the error on stderr. The tests fake hdiutil, and the module has no command line.

## make_app.py

How do the pieces become `Dragoon.app`? make_app.py lives in `launcher/tools/`. It writes `OUT/Dragoon.app` around the launcher that `swift build -c release` made. It never runs SwiftPM, so the launcher has to be built first. The app also holds an engine kit, which is CI's `engine-kit` artifact or one made by hand with `engine_kit.py`, and a snapshot from `export_source.py`.

| In the app | What it holds |
|---|---|
| `Contents/MacOS/Dragoon` | The launcher, mode 0755 |
| `Contents/Resources/kit/` | The kit, byte for byte |
| `Contents/Resources/source/` | The snapshot, byte for byte |
| `Contents/Resources/licenses/Dragoon.txt` | The snapshot's `LICENSE` |
| `Contents/Info.plist` | `launcher/Info.plist` with `CFBundleShortVersionString` and `CFBundleVersion` set to `--version` |

```
launcher/tools/make_app.py --out launcher/dist --version 0.1.0 --launcher /tmp/Dragoon \
  --kit /tmp/engine-kit --source /tmp/dragoon-source
tools/check_bundle.py launcher/dist/Dragoon.app --commit SHA
```

The app is sealed with `codesign --force --sign -`, ad hoc, with no hardened runtime and no `--deep`, as a dev build is. `sign_and_package.py` signs a copy for release. `--version` is one to three numbers joined by dots. `OUT` is made if it's missing. The app is built under a temporary name in it and renamed into place. A failed run removes that directory and the directories it made for `OUT`, so it leaves nothing behind. It only removes a directory that's empty by then, so a second run sharing a new `OUT` keeps its app. The kit and the snapshot are only read, and `launcher/dist/` is git-ignored for the app to go in.

It exits 0 when the app is there and prints its path. A step that failed, such as codesign, exits 1. It exits 2 with one line saying why, having written nothing, when:

- an argument is missing or bad, or `OUT` is the kit or the snapshot or below one, however its name is spelled
- `OUT/Dragoon.app` already exists
- the kit lacks a file that `launcher/bundle-manifest.txt` lists, or holds one it doesn't
- the snapshot lacks `source-info.json`, `source-manifest.txt` or `LICENSE`, or its files aren't the ones `source-manifest.txt` lists with their hashes, because one is missing, extra or edited
- the kit is from another gcn-recomp commit or another `src/` than the snapshot's, which `kit_problem` in `launcher_build.py` decides for both tools

The tests fake codesign with a script that records its call, so they sign nothing. Every path in them has a space.

## sign_and_package.py

Can one command sign the launcher, put it in a DMG and notarize it? It lives in `launcher/tools/`, with the commands it runs in `sign_plan.py` beside it.

```
launcher/tools/sign_and_package.py --app launcher/dist/Dragoon.app --identity - --out /tmp/dragoon-release
launcher/tools/sign_and_package.py --app launcher/dist/Dragoon.app --identity "Developer ID Application: NAME (TEAM)" \
  --out dist --notary-key AuthKey.p8 --notary-key-id KEYID --notary-issuer ISSUER --dry-run
```

`--help` lists each signing step, why ad hoc signing skips the timestamp and the hardened runtime, the notarization cut-off (30 minutes unless `--notary-timeout` says, a day at most) and the exit codes. The engine kit's files are sealed with the app as resources, and none is signed on its own.

The tests fake codesign, ditto, hdiutil, xcrun and spctl with scripts that record their calls, so they sign nothing.

## swift_test.py

How do the launcher's Swift tests run on a Mac with the Command Line Tools and no Xcode? swift_test.py lives in `launcher/tools/` and runs `swift test --package-path launcher` with its own arguments passed on (`--filter NAME` works), exiting with swift's status.

```
launcher/tools/swift_test.py
launcher/tools/swift_test.py --filter FileSystemTests
```

[Why a wrapper runs the tests](../launcher/README.md#why-a-wrapper-runs-the-tests) in the launcher's README gives the flags it adds and when. It adds none when `xcode-select` fails, and it prints the swift command on stderr as a `+` line before it runs. A signal that ends swift exits 128 plus its number, and exit 2 means swift couldn't be started.

## fork_cites.py

Which gcn-recomp cites did an engine bump leave pointing at the wrong lines? fork_cites.py finds the cites of fork files by line in every tracked text file. It reads each one's lines at OLD with `git -C gcn-recomp show` and looks for the same text at NEW. Run it after moving the pin and before touching a cite.

```
tools/fork_cites.py 95e1c6b 5e54665
tools/fork_cites.py 95e1c6b 5e54665 --at 92405f1
```

These count as cites:

| Form | Example |
|---|---|
| A path under `gcn-recomp/` | `gcn-recomp/runtime/main.cpp:419-422` |
| A fork-relative path or a bare name that exactly one fork file has and no Dragoon file does | `runtime/hw/example.h:64`, `example.cpp:42` |
| A `:N` continuation, which takes the file of the cite before it on the line | `example.cpp:42`, `:53-60` |
| A list straight after a cite | `example_batch.cpp:180, 522-523` |

No fork file has the `example` names, so the tool doesn't count those cites. The first example is a real cite, and it's checked. The tool skips its own source and tests, which are full of examples.

A name Dragoon also has, such as `CMakeLists.txt`, needs the `gcn-recomp/` prefix. A name two fork files share is skipped with a warning on stderr. A `file:N:M` compiler diagnostic isn't a cite, and nor is anything in a Markdown fenced block, which holds quoted output.

It prints `ok`, `moved ... now A-B` or `gone` for each cite whose file changed, comparing lines with their surrounding whitespace stripped. `outside` marks a cite whose lines aren't in the file at OLD, changed or not, since it was stale before the bump. Then it prints `total T, ok O, moved M, gone G, outside X, unchanged U`. It exits 1 when any cite moved, is gone or is outside.

A cite that already holds NEW's lines reads as moved. So when a bump's cites were edited by hand first, `--at REV` reads Dragoon's files at the commit that moved the pin instead of the working tree. A cite that was already wrong at OLD but still sits inside its file can't be caught this way, so read the cited lines at NEW against the prose too.

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
