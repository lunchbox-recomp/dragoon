# Dragoon

Kirby Air Ride (GameCube, USA) recompiled to run natively on Mac. You build it from your own disc. Nothing from the game is in this repo.

I loved this game as a kid, mostly playing it on my own. I'm a software engineer, and getting to work on it now as an adult still feels a little unreal. I want Dragoon to be something the people who kept Kirby Air Ride alive are glad exists, so it's built in the open and credits them below.

## Status

Tested on one Mac, an M4 Max on macOS 26.

| Part | State |
|---|---|
| Title and menus | Work. The panel on the right of the mode select stays plain gray |
| Air Ride | A full race runs on Fantasy Meadows. Other courses haven't been checked |
| City Trial | Runs with one player, or four in split screen at full speed. A new effect can stutter the first time it shows up |
| Stadium | Not reached yet |
| Top Ride | Not tried |
| Audio | Partial. Effects like reverb are misrouted ([details](docs/dev/audio.md)) |
| Controllers | Up to four gamepads, one per port. Each gets the same port next launch. The keyboard is on port 1. Tested with simulated gamepads, not with four real ones |
| Picture | 4:3 only |
| Other platforms | Not tested |

Full numbers are in [docs/dev/status.md](docs/dev/status.md).

## Building

You need:

- your own Kirby Air Ride disc (USA, `GKYE01`) as an `.iso`, `.ciso` or `.gcm`. Convert `.rvz` and `.gcz` first
- a Mac with Apple Silicon and the Xcode Command Line Tools
- CMake and Ninja (`brew install cmake ninja`)

The first configure downloads SDL 3.4.18's source (15.7 MB) and checks its hash. To use an SDL3 you already have, add `-DGCN_SYSTEM_SDL=ON`.

```sh
git clone --recursive https://github.com/lunchbox-recomp/dragoon
cd dragoon
ln -s "/path/to/Kirby Air Ride (USA).gcm" rom/game.iso
cmake -S . -B build -G Ninja
ninja -C build
build/dragoon
```

The wrong disc stops the configure step and prints the disc ID it found.

If linking fails over an unknown `arm64e.x1` architecture, your Command Line Tools are older than your default SDK. Add `-DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk` to the `cmake` line.

## How it works

[gcn-recomp](https://github.com/ethannicholas/gcn-recomp) reads the game's code from your disc and translates its 20,003 PowerPC functions to C. That C is compiled together with a runtime that stands in for the GameCube's hardware.

This repo holds the Kirby Air Ride side, like function names and the tables that tell the recompiler about the game's quirks. Engine fixes go to [our gcn-recomp fork](https://github.com/lunchbox-recomp/gcn-recomp) and are sent upstream as pull requests.

## AI

Claude, Codex or local models running in [Pi](https://github.com/earendil-works/pi) write the code. I decide what gets built and check the results by playing it on my own disc. These docs are drafted the same way, and I edit them.

Commits don't carry AI co-author lines. Almost every commit would need one and the tool changes from day to day, so this section covers all of them.

## Credits

- [gcn-recomp](https://github.com/ethannicholas/gcn-recomp) by Ethan Nicholas, the recompiler and runtime Dragoon is built on (MIT)
- [wowjinxy/KAR](https://github.com/wowjinxy/KAR), the Kirby Air Ride decompilation, for the function names in `analysis/symbols.txt` (CC0)

## Legal

Dragoon isn't affiliated with or endorsed by Nintendo or HAL Laboratory. Kirby Air Ride is a Nintendo trademark. You need your own copy of the game to build Dragoon. A build contains the game's code, so please don't share it.

Dragoon's own code is MIT licensed. See [LICENSE](LICENSE).
