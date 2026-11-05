# Architecture

Dragoon is the Kirby Air Ride side of a static recompilation. gcn-recomp, the submodule in
`gcn-recomp/`, reads the DOL from the player's disc at build time, translates each function
to C and links it with a runtime that stands in for the GameCube.

## Where things live

| Path | Holds |
|---|---|
| `analysis/symbols.txt` | Function names and sizes in decomp-toolkit's format, from wowjinxy/KAR |
| `recomp/` | The tables the recompiler reads, such as `hle.txt` for functions whose body is ours and `patches.txt` for single instructions we replace |
| `src/` | C++ compiled into the game, mostly the hooks the tables call |
| `tests/routes/` | Input scripts from a blank memory card to a checkpoint |
| `tests/hashes/` | Frame and audio goldens for those routes |
| `tests/src/` | GoogleTest tests of the parts of `src/` that don't need the game |
| `tests/kit/` | Stub tables that CI's kit job links the engine kit against |
| `tools/` | Python and shell tools that run the game hidden and read what it leaves. Others build the engine kit and the launcher's game or run CI's steps (`tools/README.md`) |
| `launcher/` | The macOS launcher, a SwiftPM package of the `Dragoon` app and `DragoonCore`. Its `kit/Makefile` links the game from the engine kit, and the scripts in its `tools/` run its tests and assemble and sign `Dragoon.app` |
| `docs/` | This page, the design in `docs/specs/` and notes in `docs/dev/` on status, audio, the audio scorecard and widescreen |
| `build.sh` | Configures `build/` the first time and runs Ninja there. It fetches the submodule if it's missing, and on a Mac with Xcode it uses Xcode's toolchain |
| `rom/` | Where the player's disc image goes, as an `.iso` or `.ciso` such as `rom/game.iso`. Git ignores everything in it but its README |
| `gcn-recomp/` | The engine, pinned to our fork's `dragoon` branch |

## The boundary

- Addresses, function names, struct layouts and any other knowledge of the game go in
  `src/` and `recomp/`. The fork stays generic, and its `check_generic.py` refuses the
  Kirby terms in its `tools/game_terms.txt`, such as the title and the disc ID.
- Every hook names its guest function and address in a comment.
- A `patches.txt` line has to restate the instruction it replaces, since the line takes its
  place. Its comment says which function and why, and never pastes generated C.
- Comments describe the code as it is, not how it got there.

## How a hook reaches the game

The generated code is C and includes only the fork's `recomp.h`, so a `patches.txt` line
declares the function it calls inside its own braces. A function listed in `hle.txt` is
called as `hle_<name>(CPU*)`, and its original body stays callable as `orig_<name>`.

`gcn_add_game`'s `SOURCES` compiles `src/` into every game target, the benchmark included.
`runtime_check` compiles it too, so the engine kit's `engine.o` carries the hooks for a game
the launcher links from the kit. The kit's `kit.mk` names the gcn-recomp commit and the
SHA-256 of the `src/` it was built from, and the launcher takes it only for a source snapshot
with the same two.

The hooks read guest memory through the runtime's `mem_r32` and friends, and the output
aspect through `gx::output_aspect()`. The census hooks do nothing unless `DRAGOON_CENSUS` is
set. The world camera widening is always on, and at 4:3 it leaves every aspect as the game
set it, so the game runs there as it always has.

The HUD anchors in `src/hud_anchors.cpp` are always on too. Each joint tree a render callback in
its table displays keeps its 4:3 shape, held to an edge or the middle of the screen or of its
player's view, and a marker stays centered on the kart or item it follows. The bars between
split views and what a callback draws outside a joint tree stretch, and at 4:3 every anchor
leaves its draw where the game put it.

`src/draw_marks.cpp` pads the write-gather pipe to the end of its line before each mark, so the
mark lands after every draw the game has written. The HUD anchors' marks
(`src/hud_anchors.cpp:137`) and the census's draw tags (`src/census.cpp:81` and `:87`) both go
through it.

`tools/probe.sh` passes `DRAGOON_*=value` settings through to the game.
`docs/dev/widescreen.md` covers the one that exists, `DRAGOON_CENSUS`.

## Nothing from the disc

The disc, its DOL, the generated C, frames, logs and memory cards never get committed.
`.gitignore` keeps them out of `git add`, and `tools/check_no_game_data.py` fails CI if one
is tracked anyway.
