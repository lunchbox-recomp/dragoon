# Riivolution packages

The game starts in the folder that holds `settings.txt`. This page calls that folder `DIR`.

A release unzips into `DIR/mods/` as its readme directs for Dolphin's `Load/Riivolution` folder. Its XML files go in `DIR/mods/riivolution/`, with data folders beside `riivolution/`.

```text
DIR/
  settings.txt
  mods.txt
  mods/
    riivolution/
      pack.xml
    pack/
    .out/
```

Run these commands from the repository root. `--data DIR` defaults to the current folder.

```sh
python3 tools/mod_choices.py list --data DIR
python3 tools/mod_choices.py set --data DIR pack.xml opt 1
python3 tools/mod_choices.py set --data DIR pack.xml opt off
python3 tools/mod_choices.py apply --data DIR --disc IMAGE
```

`list` prints one JSON object with `packages`. Each option has a `choice` number from `mods.txt` or its XML default. A missing `mods/riivolution/` gives an empty package list.

`set` saves one choice in `DIR/mods.txt` and prints its XML name, option ID and choice number as JSON. The file holds one `XML:OPTION=CHOICE` entry per line. Choice 0 means off.

Names that have disappeared are dropped when `set` writes the file.

Each write of `mods.txt` goes through a temp file in `DIR` named `.mods-` and eight characters from a-z, 0-9 and `_`. A kill can leave one, so `apply` first removes those over a minute old. It keeps any other `.mods-` name, such as `.mods-backup.txt`.

`apply` reads those choices and writes output under `DIR/mods/.out/`. Its JSON has `overlay`, `ram_patches`, `failed` and `ms`. Each path is relative to `DIR`, or null when there's no output.

`ms` is the tool's elapsed time in milliseconds.

If one package fails, `apply` turns all its options off for that run and tries the others. Both packages are turned off when they conflict. A package with a choice on that Riivolution doesn't turn on, because the choices picked change nothing on this disc or the package is for another game, is left off too. So is every package it turns on in a run that writes no overlay and no RAM patch list, since none of their patches changes anything on this disc.

`apply` saves each option of a package it left off as off in `mods.txt`, so `list` shows what runs. `failed` gives each affected XML name and its error. A package that `list` reports with an error is also left off and reported.

`--disc` defaults to `GAME_ISO` in `build/CMakeCache.txt`. Pass `--disc IMAGE` when the cache has no image path. Put the overlay path that `apply` prints in the `disc_overlay` line of `settings.txt`.

The overlay path is relative to the folder holding `settings.txt`. When `apply` prints null for `overlay`, empty the line by writing `disc_overlay` with no value. The game stops at start if that line still names a manifest that `apply` removed.

```text
disc_overlay mods/.out/disc-overlay.txt
```

Put the RAM patch path that `apply` prints in the `ram_patches` line of `settings.txt`. Like the overlay path, it's relative to the folder holding `settings.txt`.

```text
ram_patches mods/.out/ram-patches.txt
```

When `apply` prints null for `ram_patches`, empty the line by writing `ram_patches` with no value. The game stops at start if that line still names a list that `apply` removed.

For one run, `--ram-patches=PATH` beats `GCN_RAM_PATCHES`, which beats the key. An empty value at any of the three means no patches. A relative path in the flag or the variable is relative to the game's working directory.

`gcn-recomp/runtime/main.cpp:466-485` selects the paths, and `gcn-recomp/runtime/settings.cpp:139-142` reads both keys. `gcn-recomp/runtime/ram_patches.cpp:66-86` opens the RAM patch list, and `gcn-recomp/runtime/hw/di.cpp:68-74` stops when an overlay manifest can't open.

The tool exits 0 when the command succeeds, including an apply that leaves a failed package off. It exits 1 for:

- `list` or `apply` refusing a linked or nonregular `mods.txt`
- `set` being refused
- Riivolution refusing a disc or package after the retry

It exits 2 on a bad argument, such as a data folder it can't read, or a file operation that fails. Riivolution failing to run or list the packages exits 2 too, as do an `apply` with no disc image and a `mods.txt` that isn't UTF-8.

## The Mods page

The overlay has a Mods page after Display. The first time it's shown, it runs `list` and shows each package's options with their choices and Off. A package that `list` reports with an error shows Off with that error.

Apply and restart becomes active once a choice differs from what `list` said. Nothing applies mods at boot, so when the game started with no disc overlay loaded and no RAM patch list while `list` says an option is on, Apply and restart is active at once. Until a pick changes, the page says the game started without these mods. That covers a fresh install with a package on by default, and a start after an apply that failed or was cut short. A game that started with some mods and then gains a package that's on by default still shows that package as running. Telling it apart needs `apply` to write every option to `mods.txt`. A `--disc-overlay=` or `--ram-patches=` flag given by hand, or `GCN_DISC_OVERLAY` or `GCN_RAM_PATCHES` set empty, wins over `settings.txt` and survives the restart. An empty one means Apply and restart can't take effect in a game started that way. A `--disc-overlay=mods/.out/disc-overlay.txt` given by hand does take effect, but an apply that writes no overlay removes that file, and the restart then stops at `gcn-recomp/runtime/hw/di.cpp:74`. Only games started by hand are affected.

Apply and restart first empties the `disc_overlay` and `ram_patches` lines of `settings.txt`, since an `apply` cut short can remove a file they name, and a start would then stop on it.

Then it runs `set` for each changed option and then `apply`, on a thread of its own, so the menu keeps drawing. Each run is `/usr/bin/python3 -B tools/mod_choices.py` with `--data .` in the folder the game started in. It gets only the environment that `tools/tool_env.py` describes, and 30 s. The script gives each Riivolution run 10 s, and `apply` makes one `list` run, then an `apply` run for each try, so an `apply` that retries can run past 30 s and be stopped. A quit, Restart game, the game's reset or Ctrl-C during a run kills its process group too, so no script writes `mods.txt` or `mods/.out` under the next start. A crash of the game skips that kill with the rest of its exit hooks (`gcn-recomp/runtime/platform.cpp:33`), so a script still running then keeps writing.

The page passes no `--disc`, so `apply` reads `GAME_ISO` from `build/CMakeCache.txt`. A game started outside the repository root finds no `tools/mod_choices.py`, and the page says so.

When `apply` exits 0, the page names its paths in the two lines. A key with no path gets no value, and every other line stays as it was. Then the game restarts as the overlay's Restart game does.

The game restarts by itself only when the page was on screen from Apply and restart to the result. If the menu was closed or showed another page, the page waits for Restart game, which asks first. It says so while the run goes on and again once the mods are saved.

If `apply` left off a package that the page offered choices for, the page shows that package with its error and waits for Restart game too. `apply` saved the package as off, so it shows Off after the restart. The running game keeps its overlay files open, so it plays on unchanged until then. If `settings.txt` can't be written after `apply`, the page shows the package Off at once, with the write's error.

| What happens | What the page does |
|---|---|
| A run takes over 30 s | Kills its process group and says the script was stopped |
| A nonzero exit with an `error` line | Shows that error |
| A nonzero exit without one | Shows the exit code, and the script's stderr is in the game's output |
| A signal ends the run | Shows the signal |
| Exit 0 with output that isn't the command's JSON | Says the result can't be read |
| `settings.txt` can't be read or written | Shows the reason |

In each of these nothing restarts and the picks stay. Once the keys are emptied, `settings.txt` names no mods until an apply works. Apply and restart stays active after a failure, so the player can try again. While an option is on, the message ends by saying the next start has no mods until then. If the first write, which empties the keys, fails with nothing due, the keys stay as they were and the message doesn't say that.

A `set` that ran before the failure has saved its choice in `mods.txt`, and the page counts that choice as running. Undoing it takes a `set` of its own.

A replay has no Apply and restart, since a restart ends a replay. A result that comes in while the menu is closed is taken the next time the page is shown.

`src/mods_overlay.cpp:126-134` starts an apply, `src/mods_overlay.cpp:142-174` takes each result and `src/mods_overlay.cpp:221-272` draws the page. `src/mods_page.cpp:28-56` turns a run into JSON or a message, `src/mods_page.cpp:163-169` decides whether an apply is due at the start and whether the page says so, `src/mods_page.cpp:210-238` rewrites the two lines and `src/mods_page.cpp:272-294` decides what follows a run. `src/child_run.cpp:78-153` runs the script, and `gcn-recomp/runtime/main.cpp:419-422` is the restart.
