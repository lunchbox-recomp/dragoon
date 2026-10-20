# Contributing

Bug reports from people who know this game are the most useful thing right now. For anything bigger than a small fix, open an issue before you start.

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

Run these before opening a PR.

```sh
python3 tools/check_no_game_data.py
python3 -m unittest discover -s tools -p 'test_*.py'
```

## AI

AI help is fine. Say which tools you used in the PR description. Leave AI co-author lines out of commits, since the README's AI section covers the project. Only send what you've run on your own disc.
