# Dragoon

Kirby Air Ride (USA, `GKYE01`) static recompilation on gcn-recomp. Design:
`docs/specs/2026-10-20-dragoon-design.md`.

## Commits

- One first-person line, no type prefix, no AI trailers.
- Commits on the gcn-recomp fork follow upstream's style instead. A title line, then a short
  body saying what changed and why, and how it was checked. Still no AI trailers.
- A submodule bump reads `gcn-recomp <sha>: <reason>`.
- AI use is disclosed with specifics in the README, CONTRIBUTING and release notes, not in
  commits.

## Prose for people

AI drafts the README, CONTRIBUTING, PR descriptions, issues, announcements and replies to
people. The user approves or rewrites every line before it goes out.

## Voice

Lead with the fact and use numbers instead of adjectives. Say what's broken as plainly as
what works. State what's true now, with no promises about releases or dates. Short
paragraphs, tables for anything comparable, no emoji or exclamation marks.

## Never commit or publish

The disc image, its DOL, C generated from it, extracted assets, saves, or replays that embed
game data.

## gcn-recomp

`gcn-recomp/` is upstream code. Nothing Kirby-specific goes in it; its `check_generic.py`
hook enforces that.
