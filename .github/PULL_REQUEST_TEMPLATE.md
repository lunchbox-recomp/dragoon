## Summary

<!-- What does this change do? -->

## Related issue

<!-- Closes #NNN, or N/A -->

## Test plan

<!-- What you ran or played to check it, and on which Mac -->

- [ ] Ran `python3 tools/ci.py`.
- [ ] Ran `cmake -S . -B build-tests -G Ninja -DDRAGOON_TESTS=ON -DGAME_ISO=` and `ninja -C build-tests unit` for changes in `src/`.
- [ ] Added a route in `tests/routes/` or a test that fails without this change.
- [ ] Ran the change on my own disc.

## AI tools

<!-- Which tools helped with this change? -->

## Game data

- [ ] This change contains nothing from the game.
