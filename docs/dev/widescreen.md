# Widescreen

This page covers which cameras Kirby Air Ride draws through, how Dragoon widens the world
cameras for a wider output and what a 16:9 picture still gets wrong. Every number here comes
from runs of the routes in `tests/routes/` through `tools/probe.sh`, read with
`tools/drawlog.py`.

The numbers were taken against gcn-recomp `deac351` with `--aspect` and `--dump-output`
added, the change `6575c67` makes on the fork's `dragoon` branch. At `3a8d154`, the
race's census at 4:3 and the kept widening's aspects and draws in the race, City Trial, 2P
and 4P came out the same. The section "Measured on Dragoon `b1f0ae0`" has them again at
gcn-recomp `5e49451`, with the race's cameras after the finish and Top Ride's camera widened
too.

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

The census also logs each call to `HSD_CObjSetAspect`, and each perspective camera
`HSD_CObjLoadDesc` loads, as an `[aspect]` line. Each gives the camera, where the call returns
to and where its caller returns to. `drawlog.py setters` lists them by camera and caller.

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
module scales the camera library's 2.86081 by 0.78, a factor that comes from
`kar_grlib2__near_800bbc8c`.

During play the camera module sets the world cameras' aspect every frame through two calls to
`HSD_CObjSetAspect` that return to `0x800C2884` in `kar_cmreplay__near_800c24e8` and to
`0x800C9820` in `kar_cmreplay__near_800c9790`. Each camera is first set up through the camera
library, which sets up the HUD, minimap and menu cameras as well. Those calls are a world
camera's only when the library was called from one of four places.

| The library's call, returning to | Called from, returning to | Aspect given |
|---|---|---|
| `kar_lbcamera_load_desc_update_aspect`, `0x80066E4C` | `kar_camera__800b3944`, `0x800B3990` | 1.25538 |
| `kar_lbcamera_apply_viewport_preset0`, `0x80066ECC` | `kar_grlib2__near_800babd0`, `0x800BAC38` | 1.25538 |
| `kar_lbcamera_apply_split_viewport_preset0`, `0x80066FF0` | `kar_grlib2__near_800bac5c`, `0x800BACD0` | 2.86081 in 2P |
| `kar_lbcamera_apply_quad_viewport_preset0`, `0x80067148` | `kar_grlib2__near_800bacf4`, `0x800BAD68` | 1.39419 in 4P |

The HUD's calls to the library come from `fn_801158C0`, `fn_801159C0`, `fn_80115A64`,
`fn_80115AF4` and `fn_801166B4`. The rest come from functions from `fn_8013941C` to
`fn_8013A6AC`, beside the menus' `fn_801394B0`. The two calls of the camera module and the
four of the library are the rule `src/cameras.h` keys on.

After the race's finish line the world camera that's drawn gets its aspect from the library
alone. At gcn-recomp `3a8d154`, from frame 8,183 to 13,062, the full-screen world cameras
stored 1.25538 at 16:9. On Dragoon `b1f0ae0` at a load of about 4.5, `drawlog.py setters`
showed the camera drawn at frame 8,400 getting its aspect only at frame 8,092 from the first
two calls in the table, never from the module.

A camera's address won't do as a rule, because one address can hold different cameras over a
run. In the race, the address of a HUD 3D camera at frame 4200 belonged to a world camera at
frame 8202.

### Top Ride

Top Ride draws its world through one full-screen camera at fov 30, which stores 1.18 at 4:3.
On Dragoon `a2ff7fd` at a load of about 3, at frame 3,600 of `top-ride-grass.txt`, it makes
198 of the frame's 236 draws at 4:3 and at 16:9, and fov 25 cameras make the other 38.
`drawlog.py setters` lists no call to `HSD_CObjSetAspect` for it.

A watch build of Dragoon `c4bba2b`, run at a load of about 20 just after its build, logged each
store to the camera's aspect up to frame 3,700. After `_HSD_MemClearDefaultCB` clears the
camera's memory, the only store is at `0x80403150` in `CObjLoad` (`0x80402FC0`), which copies
the aspect from the camera's description. `HSD_CObjLoadDesc` (`0x804031EC`) calls it and
returns the camera.

`kar_a2d_kurakko__near_80371968` loads the world camera, its call returning to `0x803719A0`,
when `TopRide_GameSessionInit` calls it (returning to `0x8028C0E0`). The HUD's, the effects'
and the menus' cameras come from other calls, among them `fn_802CA894`'s,
`kar_a2d_game_effect__80379f94`'s and the camera library's. That pair is the rule
`src/cameras.h` keys on for a load.

## Widening the world cameras

Three places were tried at `--aspect=16:9 --output`, each behind its own switch. The bars
were these four.

1. Every world camera's projection reads 4/3 times its 4:3 aspect in one player, 2P and 4P,
   and no HUD or menu camera changes. Before Dragoon `c62cdad` widened the library's four
   calls as well, the kept widening met this only until the race's finish. Top Ride's camera
   met it only once `2845e85` widened it as it loads.
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

`HSD_CObjSetAspect` is the one kept. It met the last three bars in one line, and the first
until the race's finish. Since the game stores the wider aspect, whatever reads it sees the
wider view.

Top Ride's world camera never goes through `HSD_CObjSetAspect`, so `HSD_CObjLoadDesc` is an HLE
function as well. It widens the camera it returns when the pair under "Top Ride" above matches,
and the census logs each perspective camera it loads.

On Dragoon `b1f0ae0` at 16:9, at loads of 4.3 to 6.3, Top Ride's camera stored 1.57333 from
its load at frame 3,234 to frame 3,833. At frame 3,600 it made 198 draws as at 4:3, and the fov
25 cameras kept 1.25538. In the output dump the player's and the CPUs' markers sit over their
karts.

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
where the world cameras were back at 4:3 then, so they only show that the race ended the same
way.

```sh
tools/probe.sh wide 30 tests/routes/air-ride-race.txt 4200 --aspect=16:9 --output
```

`src/cameras.cpp` holds the two hooks and `src/cameras.h` the rules, which
`tests/src/test_cameras.cpp` checks. The widening is always on. At 4:3 it's the identity to
the bit, so the game runs there as it did.

### A change of output aspect

Under `--aspect=window` the output aspect follows the window. The module's two calls run every
frame, so the cameras they set follow it, but the library's four calls and Top Ride's load set
a camera once. `src/cameras.cpp` keeps each camera those widen, with its 4:3 aspect and the
factor it was widened by.

At each `HSD_CObjSetCurrent`, before the projection is built, a kept camera widened for another
output aspect is widened again for the new one if it still holds what it was given. One holding
anything else has been set again or freed since, so it's left alone and forgotten. While the
output aspect holds steady nothing is written.

A hidden probe window is never resized, so the output aspect can't change during a probe run
and no run measures this. `tests/src/test_cameras.cpp` covers a resize, a camera the game set
again since and a return to 4:3, where the aspect is the 4:3 one to the bit.

## World to screen and culling

World to screen reads the world camera's stored aspect, so it needed no change of its own. A
watch build of gcn-recomp lists every load from a range of guest memory. On Dragoon `c4bba2b`
at loads of 3.2 to 3.4, in the race at 16:9, these were all the loads of the full-screen world
camera's field of view and aspect over frames 4,199 and 4,200.

| Function | Field of view loaded at | Aspect loaded at |
|---|---|---|
| `kar_lbvector_project_world_to_screen` (`0x800644AC`) | `0x80064580` | `0x80064588` |
| `kar_lbvector__near_80064770` | `0x800647EC` | `0x800647F4` |
| `fn_8027AAFC` | `0x8027AB74` | `0x8027AB98` |
| `HSD_CObjSetCurrent` | `0x8040149C` | `0x804014A4` |
| `HSD_CObjSetViewportScale` | `0x8040079C` | `0x804007B4` |
| `HSD_CObjGetFov` | `0x80402C48` | |
| `HSD_CObjGetAspect` | | `0x80402C8C` |

The world-to-screen helper reads both off the camera, so the markers it places follow the
wider view. `kar_grcoll__near_800d7e78` loads neither itself. Every load of the aspect reads the
widened value.

The test that decides which objects the world draws wasn't identified. One that takes only the
field of view wouldn't show up in this table, and neither would one in another mode or frame.
So the table doesn't show that culling follows the wider view.

The draws and the output dumps are what show it. At 16:9 the world drew at least as much as at
4:3 at every checkpoint measured here, and no dump shows an object cut off at a side edge. Five
of the ten world views drew the same number at both, which are the race after its finish, 2P's
second view, 4P's second and fourth and Top Ride.

```sh
cmake -S . -B build -DCMAKE_C_FLAGS=-DGCN_WATCH -DCMAKE_CXX_FLAGS=-DGCN_WATCH
ninja -C build
tools/probe.sh readers 300 tests/routes/air-ride-race.txt 100000 --aspect=16:9 GCN_STORE_HIST=4199-4200 GCN_READERS=/path/to/ranges.txt --exit-after=4210
```

`ranges.txt` holds the range of the camera's field of view and aspect, its address from the
`[census]` line plus `0x40` to plus `0x47`. The run's directory is its working directory, so
the path is absolute. Configure again with `-DCMAKE_C_FLAGS=` and `-DCMAKE_CXX_FLAGS=` for the
usual build.

## Measured on Dragoon `b1f0ae0`

These runs are from Dragoon `b1f0ae0` at gcn-recomp `5e49451`, two at a time, at 1-minute loads
of 2.7 to 6.3. Each checkpoint ran at 4:3 and at 16:9 on the same build.

| Checkpoint | World draws at 4:3 | At 16:9 | World aspect at 16:9 | Steady over frames |
|---|---|---|---|---|
| Race, 4200 | 204 | 217 | 1.67383 | 3,600 to 4,199 |
| Race after the finish, 8400 | 124 | 124 | 1.67383 | 8,183 to 13,062 |
| City Trial, 3300 | 371 | 376 | 1.67383 | 2,733 to 3,332 |
| 2P, 3480 | 103 and 211 | 106 and 211 | 2.97524 | 2,880 to 3,479 |
| 4P, 3480 | 104, 207, 291 and 205 | 107, 207, 304 and 205 | 1.85892 | 2,880 to 3,479 |
| Top Ride on Grass, 3600 | 198 | 198 | 1.57333 | 3,234 to 3,833 |

City Trial's world camera is made at frame 2,733 and Top Ride's is loaded at 3,234, so their
windows start there. Each runs 600 frames, past the checkpoint, in runs at 16:9 to frames
3,340 and 3,900.

Each world camera's aspect is its 4:3 one times 4/3 to five figures. Every HUD 3D, minimap
and menu camera kept its 4:3 aspect. Every call of the six that widen was given its 4:3 aspect,
as was Top Ride's load, so none widened an aspect twice.

The race's results frame at 25,800 is the same at 16:9 as at 4:3, so the race still finishes
in 1:14.68. Of the frames dumped every 600 from 8,400, only those up to 12,600 differ, while
the world camera after the finish is drawn. From frame 13,063 on, no world camera is in the
census.

## What 16:9 still gets wrong

These come from the output dumps at 16:9 of the race at 4200 and 8400, City Trial at 3300, 2P
and 4P at 3480, Top Ride on Grass at 3600 and, before `c62cdad`, the mode select at 1200.

- Every HUD element is 4/3 too wide. In the race that's the position badge, the timer, the
  minimap box, the lap count, the speedometer, the "ff" bubble and the CPU markers. In 4P
  it's the players' name labels, the speedometers and the gauges beside them, the icons for
  players past a view's edge and the clock.
- After the finish the replay's banner and buttons are 4/3 too wide as well.
- In Top Ride the clock, the lap count and the four players' counters are 4/3 too wide.
- The title and menus stretch with everything else. The mode select's frame dump at 16:9
  matches its 4:3 golden, so only presentation changes it.
- No object is cut off at a side edge in these dumps, and the world drew at least as much at
  16:9 at every checkpoint. The test that culls the world wasn't found, so pop-in while moving
  still needs a person to watch.

The markers sit where they should. The CPU markers sit over their karts in the race at 4200
and in City Trial at 3300. In 4P at 3480 each marker sits over the same scenery as at 4:3,
and player 4's marker shows in player 3's view at 16:9 where at 4:3 it's an icon at the view's
edge.
