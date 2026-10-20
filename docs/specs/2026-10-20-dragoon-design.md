# Dragoon design

Dragoon is a native PC/Mac port of Kirby Air Ride (GameCube, USA `GKYE01`) built by static
recompilation. The game's PowerPC code is translated to C from the player's own disc,
then compiled against a runtime that stands in for the GameCube. It lives in the
**Lunchbox** GitHub org (`lunchbox-recomp`), a home for GameCube recompilations.

The design was approved on 2026-10-20 and amended the same day after a review of the
recompiler, distribution, community norms and risks. The repo is public from the start.

## Goals

- Kirby Air Ride plays natively on Apple Silicon Macs, with Windows and Linux builds too.
- Couch multiplayer comes first, with four controllers and four-player split-screen at full
  speed, in widescreen.
- Every mode works. That means all nine Air Ride courses, Top Ride and City Trial with its
  stadiums, plus memory card saves.
- People who aren't developers can play it, because a signed launcher builds the game from
  their disc on their own machine.
- Real community traction, earned by a port that works and is honest about how it was made.

## Why a port when Dolphin runs it

Dolphin already plays Kirby Air Ride well. Dragoon has to offer what an emulator can't.

- High frame rates. gcn-recomp can scale per-frame constants (`steps.txt`), so the game can
  run above 60 fps.
- True widescreen, including the split-screen views.
- One app, with no emulator setup or per-game configuration, and native controller support.
- A base for online City Trial and mod support, which are hard to do inside an emulator.

## Non-goals (v1)

- Online play. The architecture leaves room for an input-sync layer; it ships later.
- hoshi / KAR-Deluxe mod support. The architecture leaves room for a mod-code fallback;
  it ships later.
- HD texture packs. They need new texture hashing in the recompiler; they come after v1.0.
- Writing our own recompiler. We build on gcn-recomp.
- Shipping any game code, assets or disc images, ever.

## Decisions

| Decision | Choice |
|---|---|
| Game | Kirby Air Ride, USA `GKYE01`, main.dol SHA-1 `977533bb96e6a16e127946396489be1b4164ac42` |
| Method | Static recompilation on gcn-recomp |
| Org / repo | `lunchbox-recomp` ("Lunchbox") / `dragoon`. The app is always called Dragoon |
| License | MIT, matching gcn-recomp |
| Visibility | Public from the first commits |
| First priority | Couch multiplayer; online and mods later, designed for |
| Platforms | macOS (Apple Silicon) first. Windows and Linux build in CI; they're supported once they have named testers |
| Distribution | Testers build from source through M3. From M4, a signed launcher with no game code recompiles the game locally from the player's disc |
| AI use | Open. The README states what AI did and how changes are verified |
| Commit attribution | Commits are written as the user in one-line style, with no AI trailers. AI use is disclosed with specifics in the README, CONTRIBUTING and release notes instead |
| Human-written prose | README, CONTRIBUTING, PR descriptions, issues, announcements and replies are written by the user. Claude writes technical docs and drafts facts and outlines for the rest |
| Voice | Every doc follows the house voice and passes the voice scan |
| Art | No AI-generated art or audio. Wordmark, self-made or commissioned logo; no Nintendo art |
| Money | No donations or paid features |

## Architecture

Dragoon follows the per-game shape of the gcn-recomp author's own game repos.

- `gcn-recomp/`: git submodule, pinned to an exact commit on the `dragoon` branch of our
  fork (`lunchbox-recomp/gcn-recomp`). That branch is an upstream commit plus our generic
  changes that haven't merged upstream yet. Upstream changes arrive only when we bump the pin.
- `analysis/symbols.txt`: function names and sizes in decomp-toolkit format, copied from
  wowjinxy/KAR (`config/GKYE01/symbols.txt`, CC0). gcn-recomp reads this format directly.
- `recomp/`: the tables `gcn_add_game()` consumes.
  - `hle.txt`: `OSSaveContext`, `OSLoadContext`, `OSReport`, `OSPanic`, `OSResetSystem`
  - `special_calls.txt`: `803D45D8 OSSaveContext`
  - `idle.txt`: the idle branch inside `SelectThread` (803D9E78), found from the disc's DOL
  - `names.txt`, `patches.txt`: empty until needed
  - `steps.txt`: per-frame constants, for high frame rates
- `src/`: Kirby Air Ride hooks for settings and controller setup, plus the game side of
  widescreen and split-screen.
- The build takes `-DGAME_ISO=<path>`, the player's image (`.iso`/`.gcm` or `.ciso`). The
  recompiler checks the disc ID and DOL hash, then generates C locally and compiles the app.
- Two extension points are reserved but not built yet. One is a mod-code fallback for
  injected PowerPC (hoshi); the other is an input-sync layer for online play.

### Engine work and upstream

Several things Dragoon needs are engine features, not game code.

- the newer AX audio ucode (Kirby Air Ride runs a 2003 build; the runtime decodes every build as the 2001 one, which misroutes effect sends)
- four connected controllers (the runtime connects only the first)
- an output-aspect setting for the desktop renderer, for widescreen
- a replay runner that stops at a frame and hashes state
- texture replacement, later

We write these generically and offer them upstream. Until they merge, each one is a commit
on our fork's `dragoon` branch, rebased whenever we bump. Nothing Kirby-specific goes into
gcn-recomp; its `check_generic.py` enforces that. Pin bumps are deliberate and get one
commit each, checked against our replays.

### Name provenance

wowjinxy/KAR is CC0. It imported 133 names, mostly SDK and sysdolphin, from doldecomp/kar,
which has no license; those are function names at fixed addresses. Its GPL loader tools are
never copied into Dragoon.

## Verification

The disc never enters CI, so verification has two tiers.

**CI, every push, no disc.** The macOS build of gcn-recomp's no-disc target, a stub target
that compiles Dragoon's own `src/` against the runtime headers, and unit tests for our own
code. Windows and Linux jobs come later.

**Local, against the user's disc.**

1. Replay hashes. Recorded controller sessions run headless through gcn-recomp's `--replay`
   to a fixed frame, and game state is hashed into golden files, one set per platform. A
   change that moves a hash is flagged. The stop-and-hash runner is ours to build and a good
   fit for upstream.
2. Screenshot diffs at the same checkpoints, with tolerance.
3. A human playtest checklist for each release, covering every Air Ride course, Top Ride,
   City Trial with its stadiums and four-player split-screen.

Dolphin is a manual reference for debugging, never linked and never a gate.

Replay results are the evidence behind the AI disclosure.

## Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Spike (go/no-go) | On the Mac it builds from the disc, with build time and size recorded. It reaches title, menus and a race. The audio gap is understood. Four-player City Trial runs at full speed with controllers 2 to 4 connected (in our fork) and fed from a replay. The distribution approach is confirmed. Stretch goal is a widescreen probe |
| M1 | First race | A single-player Air Ride race is playable and the replay hash runner works |
| M2 | All modes | Nine Air Ride courses, Top Ride, City Trial with stadiums, memory card saves, audio |
| M3 | Couch | Four controllers, four-player split-screen at full speed, widescreen including split views, controller setup screen |
| M4 | Launcher | A signed macOS launcher that recompiles locally from the player's disc, with a CI check that no game-derived bytes ship |
| M5 | Launch (v1.0) | Finished README and docs, playtest checklist passed, launch video |
| Later | | HD packs, online City Trial, hoshi mod support, Windows and Linux launchers |

**Go/no-go at M0.** No-go if the game dies before the title screen for reasons that need
deep recompiler work, or if four-player City Trial can't hold full speed with no clear fix.
A no-go stops the project or changes the approach; it doesn't drift.

Implementation plans are written one milestone at a time.

## Measures of success

- Launcher downloads and completed playtests, more than stars.
- Bugs found by replays before players find them.
- Upstream changes accepted into gcn-recomp.

## Safety and legal

- Nothing runs before it's audited, including gcn-recomp's source, its CMake fetches and
  anything it downloads at build time. On macOS the build downloads nothing. Its `.githooks`
  stay disabled and `tools/fetch_dtk.sh` is never run. `--telemetry` and `--record` stay off.
- The disc, the DOL, the C generated from it, extracted assets, saves and replays that embed
  game data are never committed or published.
- Players bring their own disc. We use no Nintendo trademarks or art, license our code MIT
  and state that we're not affiliated.
