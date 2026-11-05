# Riivolution packages

The game starts in the folder that holds `settings.txt`. This page calls that folder `DIR`. A release unzips into `DIR/mods/` as its readme directs for Dolphin's `Load/Riivolution` folder. Its XML files go in `DIR/mods/riivolution/`, with data folders beside `riivolution/`.

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

`set` saves one choice in `DIR/mods.txt` and prints its XML name, option ID and choice number as JSON. The file holds one `XML:OPTION=CHOICE` entry per line. Choice 0 means off. Names that have disappeared are dropped when `set` writes the file.

`apply` reads those choices and writes output under `DIR/mods/.out/`. Its JSON has `overlay`, `ram_patches`, `failed` and `ms`. Each path is relative to `DIR`, or null when there's no output. `ms` is the tool's elapsed time in milliseconds.

If one package fails, `apply` turns all its options off for that run and tries the others. Both packages are turned off when they conflict. The saved choices stay in `mods.txt`, and `failed` gives each affected XML name and its error. A package that `list` reports with an error is also left off and reported.

`--disc` defaults to `GAME_ISO` in `build/CMakeCache.txt`. Pass `--disc IMAGE` when the cache has no image path. The game reads the output through the `disc_overlay` and `ram_patches` keys in `settings.txt`. Those paths are relative to the folder holding `settings.txt`.
