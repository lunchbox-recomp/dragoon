# Contributing

Bug reports from people who know this game are the most useful thing. For anything bigger than a small fix, open an issue before you start.

## Bugs

Open an issue with:

- what you did, what you saw and what the game does on a console or in Dolphin
- your Mac, your macOS version and the Dragoon commit (`git rev-parse --short HEAD`)
- a screenshot or short clip if it's visual

Never attach the disc, its DOL, the generated C, saves or memory cards. They come from the game, and none of it can live here.

## Code

- Kirby Air Ride code goes in this repo. A fix that would help any game goes to [our gcn-recomp fork](https://github.com/lunchbox-recomp/gcn-recomp) so it can go upstream. Nothing Kirby-specific goes in the fork.
- Every fix comes with a route in `tests/routes/` or a test that fails without it. Routes are explained in [tests/routes/README.md](tests/routes/README.md).
- Keep PRs under about 400 hand-written lines. Split anything bigger.
- Commit messages are one short line saying what changed, with no prefix like `fix:`.

Run all four of CI's jobs before opening a PR. Naming jobs runs only those, as in `python3 tools/ci.py tools launcher`, the two that need no CMake build.

```sh
python3 tools/ci.py
```

For a change in `src/`, also run its unit tests with no disc. `ninja unit` runs them beside gcn-recomp's own, and the first configure downloads GoogleTest beside the engine's own copy of SDL and Dear ImGui.

```sh
cmake -S . -B build-tests -G Ninja -DDRAGOON_TESTS=ON -DGAME_ISO=
ninja -C build-tests unit
```

## AI

AI help is fine if the PR description says which tools you used. We'd rather commits left out AI co-author lines, since the README's AI section covers the project, but one won't hold up a PR. Only send what you've run on your own disc.
