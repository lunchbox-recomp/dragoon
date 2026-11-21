# Quality

<!-- tools/quality_page.py writes this page from the files it links. Run it again after any of them
changes. `tools/quality_page.py --check` says whether it's current. -->

How well each feature in [status.md](status.md)'s table is checked today, going by the files that
check it. Each one is marked as one of these:

- **Dolphin**: Dragoon is compared with Dolphin at matched game frames, and each checkpoint in the
  triage file is counted by its class. `within` is under the budget with the state matching,
  `timing` the same pictures in another order or a few frames apart, `unclear` a difference whose
  cause isn't known and `bug` a Dragoon bug. A row names its checkpoints' frames, and splits a
  mode's at the START that begins its race or city.
- **Goldens**: our own frame, state or audio hashes cover it. No Dolphin compare does, and a golden
  only says the output hasn't changed, not that it's right.
- **Unchecked**: no Dolphin compare or golden covers it.

The golden files name no commit, so their rows say they're held to the gcn-recomp pin.
`tools/nightly.py` plays the goldens and the triaged checkpoints on the real game each night. Its
reports stay in `build/nightly/`, so none of its numbers are here.

Of 18 features, 6 are checked against Dolphin, 4 against our goldens only and 8 are unchecked. The
Dolphin compare has 41 checkpoints on 3 routes, 31 `within`, 3 `timing` and 7 `unclear`.

| Feature | Checked | status.md | Latest numbers | Measured at | Files |
|---|---|---|---|---|---|
| Boot and memory card | Dolphin | Works | Frame 60 on each of air-ride-race, city-trial and top-ride-grass, which play the same presses up to those frames: 1 `within` on each. Goldens of 1 route: 16 frames at 4:3, 16 frames at 16:9, 2 state checkpoints and 2 audio rows. | Dolphin on gcn-recomp `9358d34`, the goldens held to that pin | [dolphin-triage.txt](../../tests/hashes/dolphin-triage.txt), [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| Opening movie | Dolphin | Plays | Frames 304 and 314 on each of air-ride-race, city-trial and top-ride-grass, which play the same presses up to those frames: 2 `within` on each. Goldens of 1 route: 16 frames at 4:3, 16 frames at 16:9, 2 state checkpoints and 2 audio rows. | Dolphin on gcn-recomp `9358d34`, the goldens held to that pin | [dolphin-triage.txt](../../tests/hashes/dolphin-triage.txt), [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| Title screen | Goldens | Works | Goldens of 1 route: 16 frames at 4:3, 16 frames at 16:9, 2 state checkpoints and 2 audio rows. | Held to the pin, gcn-recomp `9358d34` | [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| Mode select | Dolphin | Works | Frames 1003 and 1013 on each of air-ride-race, city-trial and top-ride-grass, which play the same presses up to those frames: 2 `within` on each. Goldens of 1 route: 20 frames at 4:3, 20 frames at 16:9, 1 state checkpoint and 2 audio rows. | Dolphin on gcn-recomp `9358d34`, the goldens held to that pin | [dolphin-triage.txt](../../tests/hashes/dolphin-triage.txt), [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| Air Ride race | Dolphin | Runs | Before START at 3100, frames 1604, 1614, 1904, 1914, 2209 and 2219 on air-ride-race: 4 `within`, 1 `timing` at 1904 and 1 `unclear` at 1914. From START at 3100, frames 3123, 3133, 4200 and 6000 on air-ride-race: 3 `within` and 1 `unclear` at 6000. On air-ride-race the race first differs from Dolphin's at pass 807. Goldens of 10 routes: 1,018 frames at 4:3, 1,018 frames at 16:9, 16 state checkpoints and 20 audio rows. | Dolphin on gcn-recomp `9358d34`, the goldens held to that pin | [dolphin-triage.txt](../../tests/hashes/dolphin-triage.txt), [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| City Trial | Dolphin | Runs | Before START at 2700, frames 1804, 1814, 2105 and 2115 on city-trial: 3 `within` and 1 `timing` at 2105. From START at 2700, frames 2734, 2744 and 3300 on city-trial: 1 `within` and 2 `unclear` at 2744 and 3300. On city-trial the race matches Dolphin's through pass 1033. Goldens of 5 routes: 309 frames at 4:3, 309 frames at 16:9, 14 state checkpoints and 10 audio rows. | Dolphin on gcn-recomp `9358d34`, the goldens held to that pin | [dolphin-triage.txt](../../tests/hashes/dolphin-triage.txt), [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| Top Ride | Dolphin | Runs | Before START at 3200, frames 1704, 1714, 2004, 2014, 2609 and 2619 on top-ride-grass: 4 `within`, 1 `timing` at 2004 and 1 `unclear` at 2014. From START at 3200, frames 3235, 3245 and 3600 on top-ride-grass: 1 `within` and 2 `unclear` at 3245 and 3600. On top-ride-grass the race matches Dolphin's through pass 564. Goldens of 8 routes: 606 frames at 4:3, 606 frames at 16:9, 14 state checkpoints and 16 audio rows. | Dolphin on gcn-recomp `9358d34`, the goldens held to that pin | [dolphin-triage.txt](../../tests/hashes/dolphin-triage.txt), [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| Audio | Goldens | Partial | Goldens of 25 routes: 50 audio rows. The click and clipping counts, scored with nobody listening, are in the audio scorecard. | Held to the pin, gcn-recomp `9358d34` | [audio/](../../tests/hashes/audio/), [scorecard.md](scorecard.md) |
| Controllers | Goldens | Four ports, live | Goldens of 3 routes: 186 frames at 4:3, 186 frames at 16:9, 9 state checkpoints and 6 audio rows. The routes play scripted presses with no gamepad open, so gamepads and the Controllers page aren't hashed. | Held to the pin, gcn-recomp `9358d34` | [gl/](../../tests/hashes/gl/), [gl-16x9/](../../tests/hashes/gl-16x9/), [state/](../../tests/hashes/state/), [audio/](../../tests/hashes/audio/) |
| Picture | Goldens | 4:3, or wider with Air Ride's and City Trial's HUD anchored and the menus centered | Goldens of 25 routes: 1,969 frames at 16:9. | Held to the pin, gcn-recomp `9358d34` | [gl-16x9/](../../tests/hashes/gl-16x9/) |
| Speed | Unchecked | Holds 60 fps | No golden or Dolphin compare covers it. The nightly's timed step measures it against the bars in `tools/timed_bars.py`, but its results stay in `build/nightly/`, so status.md is the only source in the repo. | Not measured here | [status.md](status.md) |
| Build from the disc | Unchecked | Works | No golden or Dolphin compare covers it. status.md is the only source. | Not measured here | [status.md](status.md) |
| Disc check | Unchecked | Works | No golden or Dolphin compare covers it. status.md is the only source. | Not measured here | [status.md](status.md) |
| `.gcm` dumps | Unchecked | Work | No golden or Dolphin compare covers it. status.md is the only source. | Not measured here | [status.md](status.md) |
| Disc path with spaces | Unchecked | Works | No golden or Dolphin compare covers it. status.md is the only source. | Not measured here | [status.md](status.md) |
| Running from another directory | Unchecked | Works | No golden or Dolphin compare covers it. status.md is the only source. | Not measured here | [status.md](status.md) |
| Network during the build | Unchecked | SDL and Dear ImGui | No golden or Dolphin compare covers it. status.md is the only source. | Not measured here | [status.md](status.md) |
| Idle loop | Unchecked | Works | No golden or Dolphin compare covers it. status.md is the only source. | Not measured here | [status.md](status.md) |
