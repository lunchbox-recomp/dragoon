# Widescreen

This page covers which cameras Kirby Air Ride draws through, how Dragoon widens the world
cameras for a wider output and what a 16:9 picture still gets wrong. Every number here comes
from runs of the routes in `tests/routes/` through `tools/probe.sh`, read with
`tools/drawlog.py`.

The numbers were taken against gcn-recomp `deac351` with `--aspect` and `--dump-output`
added, the change `6575c67` makes on the fork's `dragoon` branch. At the pin, `3a8d154`, the
race's census at 4:3 and the kept widening's aspects and draws in the race, City Trial, 2P
and 4P came out the same.

## Taking the census

```sh
tools/probe.sh race 30 tests/routes/air-ride-race.txt 4200 DRAGOON_CENSUS=1 GCN_DRAWLOG=4200 GCN_DRAWLOG_VERBOSE=1
tools/drawlog.py cameras build/probe/race/stdout.txt --frame 4200 --symbols analysis/symbols.txt
```

`DRAGOON_CENSUS=1` turns on two hooks in `src/census.cpp`. One sits at the entry of
`HSD_CObjSetCurrent` (`0x80401150`) and logs the camera it's about to make current. The
other sits where `GObj_SetTextureCamera` (`0x8042A0B4`) calls each object's render callback,
and logs the callback with the camera it draws through.

Each pair is logged once a frame as a `[census]` line. drawlog.py matches those cameras to the
projections in the frame's `[draw]` lines and counts the draws through each.

## The cameras

Five kinds of camera draw at the six checkpoints.

| Kind | Projection | Viewport | Set by | Drawn through by, among others |
|---|---|---|---|---|
| World | Perspective, fov 78 in one player, 68 in 2P and 80 in 4P | The player's view | `kar_objalloc__near_800b04a8` | `fn_801C6E84`, `kar_grcoll__near_800d81e4`, `kar_itdata_display_item_gobj`, `kar_efrequest2__near_8023dc8c` |
| HUD 3D | Perspective, fov 25 | The whole screen | `fn_8011586C`, `GObj_SetCamera` | `fn_80114F1C`, `fn_8011500C`, `fn_8011F114` |
| Minimap | Perspective, fov 25 | 107x80 in the race, 160x120 in City Trial and 2P | `fn_8011586C` | `fn_8011500C` |
| 2D frame | Orthographic, 64x48 | The whole screen | `fn_8011596C` | `fn_8011F8F4`, `fn_801206A0`, `kar_ifround_display_mmapply_player_marker_world_projected` |
| Menu | Perspective at fov 25 and 30, orthographic at 640x480 and 256x192 | The whole screen, or 256x192 for the render to texture | `fn_801394B0` and `GObj_SetCamera`, while nothing is drawing for the 256x192 one | `fn_80138AE0`, and `HSD_SisLib_803A84BC` (sysdolphin's text library) in the 640x480 frame |

This table counts the draws through each kind at 4:3, at each checkpoint's frame.

| Checkpoint | Route, frame | World | HUD 3D | Minimap | 2D frame | Menu | All |
|---|---|---|---|---|---|---|---|
| Title | `title.txt`, 960 | | | | | 164 | 164 |
| Mode select | `menu.txt`, 1200 | | | | | 218 | 218 |
| Air Ride race | `air-ride-race.txt`, 4200 | 204 | 30 | 2 | 9 | | 245 |
| City Trial | `city-trial.txt`, 3300 | 371 | 25 | 1 | 7 | | 404 |
| City Trial, 2P | `city-trial-2p.txt`, 3480 | 314 (103 and 211) | 46 | 1 | 8 | | 369 |
| City Trial, 4P | `city-trial-4p.txt`, 3480 | 807 (104, 207, 291 and 205) | 64 | | 12 | | 883 |

The title's 164 menu draws are 153 through fov 25 and 11 through fov 30. The mode select's
218 are 176 through fov 25, 41 through the 640x480 frame and 1 through the 256x192 render to
texture.

Some cameras drew nothing at every checkpoint. A fov 60 camera set by `GObj_SetCamera` holds
an aspect of 1.33333, and a 680x520 orthographic frame is drawn through only by
`kar_dbmapgravity__near_800ab15c`. In 2P and 4P each view also has a fov 25 camera of its
own, set by `fn_8011586C`, that drew nothing at frame 3480.

### Aspects

Every perspective camera that draws has a projection 1.062 times narrower than its
viewport, except the world cameras in 2P. The world camera stores 1.25538 at 640x480 and
1.39419 in a 308x208 4P view, and the HUD 3D camera stores 1.25538. The 2P world cameras
store 2.23143 for a 632x208 view, 1.362 times narrower than the view, because the camera
module scales the camera library's 2.86082 by 0.78, a factor that comes from
`kar_grlib2__near_800bbc8c`.

During play the camera module sets the world cameras' aspect through two calls to
`HSD_CObjSetAspect` that return to `0x800C2884` in `kar_cmreplay__near_800c24e8` and to
`0x800C9820` in `kar_cmreplay__near_800c9790`. The HUD, minimap and menu cameras get theirs
from calls elsewhere, and that's the rule `src/cameras.h` keys on. After the race's finish
the world cameras keep the aspect `CObjLoad` (`0x80402FC0`) copies from their description,
and neither call runs for them.

A camera's address won't do as a rule, because one address can hold different cameras over a
run. In the race, the address of a HUD 3D camera at frame 4200 belonged to a world camera at
frame 8202.

## Widening the world cameras

Three places were tried at `--aspect=16:9 --output`, each behind its own switch. The bars
were these four.

1. Every world camera's projection reads 4/3 times its 4:3 aspect in one player, 2P and 4P,
   and no HUD or menu camera changes. The kept widening meets this only until the race's
   finish.
2. The stored aspect holds steady over 600 frames, so nothing widens twice.
3. The race finishes in the same time as at 4:3.
4. It takes the fewest patch lines.

The candidates were `HSD_CObjSetAspect` (`0x80402C94`) as an HLE function that widens only
the camera module's two calls, the projection `HSD_CObjSetCurrent` builds (its two loads of
a perspective camera's aspect, widened when the object drawing is
`kar_objalloc__near_800b04a8`) and the camera library's 15 loads of its aspect constant.

| | `HSD_CObjSetAspect` | `HSD_CObjSetCurrent`'s projection | The 15 constant loads |
|---|---|---|---|
| Race world camera | 1.6739, stored 1.67383 | 1.6739, stored 1.25538 | 1.6739 |
| City Trial world camera | 1.6738, stored 1.67383 | Not run | Not run |
| 2P world cameras | 2.9753 | 2.9753 | 2.9753 |
| 4P world cameras | 1.8590 | 1.8590 | 1.8590 |
| HUD and menu cameras | Unchanged | Unchanged | HUD 3D 1.67383, minimap 1.6791, the mode select's fov 25 1.6739 |
| Steady over 600 frames | Yes | Yes, the stored aspect never moves | Yes |
| World draws, race 4200 | 217 | 204 | 217 |
| World draws, City Trial 3300 | 376 | Not run | Not run |
| World draws, 4P 3480 | 107, 207, 304 and 205 | 104, 207, 291 and 205 | 107, 207, 304 and 205 |
| World draws, 2P 3480 | 106 and 211 | 103 and 211 | 106 and 211 |
| Race time | 1:14.68, results frame identical to 4:3 | 1:14.68, results frame identical to 4:3 | Not run |
| Patch lines | 1 in `hle.txt` | 2 in `patches.txt` | 15 in `patches.txt` |

`HSD_CObjSetAspect` is the one kept. It meets the last three bars in one line, and the first
until the race's finish. Since the game stores the wider aspect, whatever reads it sees the
wider view.

The world drew more at 16:9 than at 4:3 at all four checkpoints that have one, and in the
race's output dump the CPU marker sits over its kart. The projection patch leaves the stored
aspect at 4:3, so draws stay at their 4:3 count and the markers drift outward from the karts.
The constant loads widen the HUD and the menus along with the world.

The widened aspect doesn't compound, because the camera module works it out from the
viewport before each call to the setter. `drawlog.py aspects` showed 1.67383 for every frame
from 3600 to 4199 of the race and from 3300 to 3899 of City Trial, and 1.85892 and 2.97524
for frames 2880 to 3479 in 4P and 2P.

The two calls set the aspect of cameras that aren't drawn as well, and those widen too. The
race result didn't change.

The race time bar was written as 1:12.60, which `docs/dev/status.md` recorded at gcn-recomp
`7d30377`. At `deac351` with the aspect change the race finished in 1:14.68 at 4:3 too, with
the CPUs at 1:15.40, 1:15.57 and 1:16.36, so the bar here is the 4:3 time.

At `3a8d154` every frame dump from 8,400 to 66,900 was the same at 4:3 and at 16:9 with the
widening. Those frames, the results screen's at 25,800 among them, all come after the finish,
where the world cameras are back at 4:3, so they only show that the race ended the same way.

```sh
tools/probe.sh wide 30 tests/routes/air-ride-race.txt 4200 --aspect=16:9 --output DRAGOON_WIDEN=1
```

`src/cameras.cpp` holds the hook and `src/cameras.h` the rule, which
`tests/src/test_cameras.cpp` checks. Without `DRAGOON_WIDEN=1` the game runs as it did, and
at 4:3 the widening is the identity to the bit.

## What 16:9 still gets wrong

These come from the output dumps of the race at 4200, 4P at 3480 and the mode select at 1200,
with `DRAGOON_WIDEN=1`, and from the race's census after its finish.

- Every HUD element is 4/3 too wide. In the race that's the position badge, the timer, the
  minimap box, the lap count, the speedometer, the "ff" bubble and the CPU markers. In 4P
  it's the P1 to P4 labels, the speedometers and the gauges beside them, the icons for
  players past a view's edge and the clock.
- The title and menus stretch with everything else. The mode select's frame dump at 16:9
  matches its 4:3 golden, so only presentation changes it.
- The CPU marker sits over its kart in the race at 4200. The 4P markers at 3480 are too far
  off to judge, so the world-to-screen check still needs doing there.
- No object is cut off at a side edge in these dumps, and the world drew more at 16:9 in
  both. Pop-in while moving still needs a person to watch.
- After the race's finish line the world cameras are back at 4:3. From frame 8,183 to 13,062
  the full-screen world cameras store 1.25538 with `DRAGOON_WIDEN=1`, because `CObjLoad` sets
  their aspect straight from their description and neither hooked call runs for them.
- The widening stays behind `DRAGOON_WIDEN=1`.
