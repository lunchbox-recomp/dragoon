# Architecture

Dragoon is the Kirby Air Ride side of a static recompilation. gcn-recomp, the submodule in
`gcn-recomp/`, reads the DOL from the player's disc at build time, translates each function
to C and links it with a runtime that stands in for the GameCube. Everything that knows
about Kirby Air Ride lives in this repository. Everything that would help any game goes to
the fork.

## Where things live

| Path | Holds |
|---|---|
| `analysis/symbols.txt` | Function names and sizes in decomp-toolkit's format, from wowjinxy/KAR |
| `recomp/` | The tables the recompiler reads, such as `hle.txt` for functions whose body is ours and `patches.txt` for single instructions we replace |
| `src/` | C++ compiled into the game, mostly the hooks the tables call |
| `tests/routes/` | Input scripts from a blank memory card to a checkpoint |
| `tests/hashes/` | Frame and audio goldens for those routes |
| `tests/src/` | GoogleTest tests of the parts of `src/` that don't need the game |
| `tools/` | Python tools that run the game hidden and read what it leaves behind |
| `gcn-recomp/` | The engine, pinned to our fork's `dragoon` branch |

## The boundary

- Addresses, function names, struct layouts and any other knowledge of the game go in
  `src/` and `recomp/`. The fork stays generic, and its `check_generic.py` refuses Kirby
  names, strings and addresses.
- Every hook names its guest function and address in a comment.
- A `patches.txt` line has to restate the instruction it replaces, since the line takes its
  place. Its comment says which function and why, and never pastes generated C.
- Comments describe the code as it is, not how it got there.

## How a hook reaches the game

The generated code is C and includes only the fork's `recomp.h`, so a `patches.txt` line
declares the function it calls inside its own braces. A function listed in `hle.txt` is
called as `hle_<name>(CPU*)`, and its original body stays callable as `orig_<name>`.
`gcn_add_game`'s `SOURCES` compiles `src/` into every game target, the benchmark included.

The hooks read guest memory through the runtime's `mem_r32` and friends, and the output
aspect through `gx::output_aspect()`. Each one does nothing unless its `DRAGOON_*`
environment variable is set, so the game runs as it always has without them. `tools/probe.sh` passes
`DRAGOON_*=value` settings through to the game. `docs/dev/widescreen.md` covers the two that
exist, `DRAGOON_CENSUS` and `DRAGOON_WIDEN`.

## Nothing from the disc

The disc, its DOL, the generated C, frames, logs and memory cards never get committed.
`.gitignore` keeps them out of `git add`, and `tools/check_no_game_data.py` fails CI if one
is tracked anyway.
