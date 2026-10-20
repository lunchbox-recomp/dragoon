# Dragoon

Kirby Air Ride (USA, `GKYE01`) static recompilation on gcn-recomp. Design:
`docs/specs/2026-10-20-dragoon-design.md`.

## Commits

- One first-person line, no type prefix, no AI trailers.
- AI use is disclosed with specifics in the README, CONTRIBUTING and release notes, not in
  commits.

## Human-written prose

The README, CONTRIBUTING, PR descriptions, issues, announcements and replies to people are
written by the user. Claude writes technical docs and drafts facts and outlines for the rest.

## Never commit or publish

The disc image, its DOL, C generated from it, extracted assets, saves, or replays that embed
game data.

## gcn-recomp

`gcn-recomp/` is upstream code. Nothing Kirby-specific goes in it; its `check_generic.py`
hook enforces that.
