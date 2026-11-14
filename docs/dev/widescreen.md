# Widescreen

Every number here comes from runs of the routes in `tests/routes/` through `tools/probe.sh`,
read with `tools/drawlog.py`. The census and the three candidates were measured on gcn-recomp
`deac351` with `6575c67`'s `--aspect` and `--dump-output` on top. At `3a8d154` the race's
census at 4:3 and the kept widening's aspects and draws in the race, City Trial, 2P and 4P came
out the same.

## Taking the census

```sh
tools/probe.sh race 30 tests/routes/air-ride-race.txt 4200 DRAGOON_CENSUS=1 GCN_DRAWLOG=4200 GCN_DRAWLOG_VERBOSE=1
tools/drawlog.py cameras build/probe/race/stdout.txt --frame 4200 --symbols analysis/symbols.txt
```

`DRAGOON_CENSUS=1` turns on the census in `src/census.cpp`, which three hooks in
`recomp/patches.txt` call. One sits at the entry of `HSD_CObjSetCurrent` (`0x80401150`) and logs
the camera it's about to make current. Another sits where `GObj_SetTextureCamera`
(`0x8042A0B4`) calls each object's render callback, and logs the callback with the camera it
draws through.

Each pair is logged once a frame as a `[census]` line. drawlog.py matches those cameras to the
projections in the frame's `[draw]` lines and counts the draws through each.

The third hook sits where the callback returns (`0x8042A144`). In between, the callback's draws
carry a draw tag, which the draw log shows as `tag=N`. A `[cbtag]` line names the callback the
first time it's called, and `drawlog.py hud` names it beside each HUD draw.

The census also logs each call to `HSD_CObjSetAspect`, and each perspective camera
`HSD_CObjLoadDesc` loads, as an `[aspect]` line. Each gives the camera, where the call returns
to and where its caller returns to. `drawlog.py setters` lists them by camera and caller.

Each camera the game releases gets a `[release]` line, and each time it forgets the memory its
cameras were in gets an `[amnesia]` line. Both are under "A change of output aspect" below.

## The cameras

Five kinds of camera draw at the six checkpoints.

| Kind | Projection | Viewport | Made current by | Drawn through by, among others |
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

Some cameras drew nothing at every checkpoint. A fov 60 camera made current by
`GObj_SetCamera` holds an aspect of 1.33333, and a 680x520 orthographic frame is drawn through
only by `kar_dbmapgravity__near_800ab15c`. In 2P and 4P each view also has a fov 25 camera of
its own, made current by `fn_8011586C`, that drew nothing at frame 3480.

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
alone. On Dragoon `45c52c5` at a load of about 4.5, `drawlog.py setters` showed the camera
drawn at frame 8,400 getting its aspect only at frame 8,092 from the first two calls in the
table, never from the module.

A camera's address won't do as a rule, because one address can hold different cameras over a
run. In the race, the address of a HUD 3D camera at frame 4200 belonged to a world camera at
frame 8202.

### Top Ride

Top Ride draws its world through one full-screen camera at fov 30, which stores 1.18 at 4:3.
On Dragoon `a2ff7fd` at a load of about 3, at frame 3,600 of `top-ride-grass.txt`, it makes
198 of the frame's 236 draws at 4:3 and at 16:9, and fov 25 cameras make the other 38.
`drawlog.py setters` lists no call to `HSD_CObjSetAspect` for it.

A watch build of Dragoon `0159b5e`, run at a load of about 20 just after its build, logged each
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
   and no HUD or menu camera changes.
2. The stored aspect holds steady over 600 frames, so nothing widens twice.
3. The race finishes in the same time as at 4:3, 1:14.68, with the CPUs at 1:15.40, 1:15.57
   and 1:16.36.
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

`HSD_CObjSetAspect` is the one kept. It met the last three bars in one line, and it meets the
first with the library's four calls and Top Ride's load widened as well. Since the game stores
the wider aspect, whatever reads it sees the wider view.

Top Ride's world camera never goes through `HSD_CObjSetAspect`, so `HSD_CObjLoadDesc` is an HLE
function as well. It widens the camera it returns when the pair under "Top Ride" above matches,
and the census logs each perspective camera it loads. On Dragoon `45c52c5` at 16:9, Top Ride's
output dump shows the player's and the CPUs' markers over their karts.

With `HSD_CObjSetAspect` the world drew more at 16:9 than at 4:3 at all four checkpoints in the
table. In the output dumps on Dragoon `e52dce1` each CPU marker sits over its kart, in the race
at 4200 and in City Trial at 3300. The projection patch leaves the stored aspect at 4:3, so
draws stay at their 4:3 count and the markers drift outward from the karts, while the constant
loads widen the HUD and the menus along with the world.

The widened aspect doesn't compound, because the camera module works it out from the
viewport before each call to the setter.

The two calls set the aspect of cameras that aren't drawn as well, and those widen too. The
race result didn't change.

```sh
tools/probe.sh wide 30 tests/routes/air-ride-race.txt 4200 --aspect=16:9 --output
```

`src/cameras.cpp` holds the hooks and `src/cameras.h` the rules, which
`tests/src/test_cameras.cpp` checks. The widening is always on. At 4:3 it's the identity to
the bit, so the game runs there as it did.

### A change of output aspect

Under `--aspect=window` the output aspect follows the window. The module's two calls run every
frame, so the cameras they set follow it, but the library's four calls and Top Ride's load set
a camera once. `src/cameras.cpp` keeps each camera those widen, with its 4:3 aspect and the
factor it was widened by.

At each `HSD_CObjSetCurrent`, before the projection is built, a kept camera widened for another
output aspect is widened again for the new one if it still holds what it was given. One holding
anything else has been set again since, so it's left alone and forgotten. While the output
aspect holds steady nothing is written.

Freeing a camera leaves its aspect in memory, so a camera made later at a kept one's address,
holding the same aspect, would pass for it. A camera is forgotten as `CObjRelease`
(`0x80403324`) releases it, and every camera as `CObjAmnesia` (`0x804034A8`) forgets the
memory they're in at a change of scene. At most 32 are kept, the oldest forgotten first.

On Dragoon `a2ff7fd` at 16:9 and loads of 2.8 to 4.3, the census showed both. The race's world
cameras were never released one by one, and an `[amnesia]` line came before each scene's
cameras were set up, at frames 3,122, 8,092 and 13,063 among others. In `top-ride-courses.txt`
each session's camera was released a frame before the amnesia that ends the session.

A hidden probe window is never resized, so the output aspect can't change during a probe run
and no run measures a resize. `tests/src/test_cameras.cpp` covers a resize, a camera the game
set again since and a return to 4:3, where the aspect is the 4:3 one to the bit. It also covers
a released camera, one made later at its address, forgetting every camera and the bound.

## World to screen and culling

World to screen reads the world camera's stored aspect, so it needed no change of its own. A
watch build of gcn-recomp lists every load from a range of guest memory. On Dragoon `0159b5e`
at loads of 3.2 to 3.4, in the race at 16:9, these were all the loads of the full-screen world
camera's field of view and aspect between frames 4,199 and 4,200.

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

The test that decides which objects the world draws wasn't identified. The table names the code
that loads the two fields, not its callers, so a cull test that reads them through
`HSD_CObjGetFov` or `HSD_CObjGetAspect`, or runs in another mode or frame, wouldn't show. So the
table doesn't show that culling follows the wider view.

The draws and the output dumps are what show it. At 16:9 the world drew at least as much as at
4:3 at every checkpoint measured here, and no dump shows an object cut off at a side edge. Five
of the ten world views drew the same number at both, which are the race after its finish, 2P's
second view, 4P's second and fourth and Top Ride.

```sh
cmake -S . -B build -DCMAKE_C_FLAGS=-DGCN_WATCH -DCMAKE_CXX_FLAGS=-DGCN_WATCH
ninja -C build dragoon
tools/probe.sh readers 300 tests/routes/air-ride-race.txt 100000 --aspect=16:9 GCN_STORE_HIST=4199-4200 GCN_READERS=/path/to/ranges.txt --exit-after=4210
```

`ranges.txt` holds the range of the camera's field of view and aspect, its address from the
`[census]` line plus `0x40` to plus `0x47`. The game runs in `build/probe/readers/`, so the
path has to be absolute. Configure again with `-DCMAKE_C_FLAGS=` and `-DCMAKE_CXX_FLAGS=` for
the usual build.

## Measured on Dragoon `45c52c5`

These runs are from Dragoon `45c52c5` at gcn-recomp `5e49451`, two at a time, at 1-minute loads
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
windows start there. Both windows run 600 frames, past their checkpoints, so those 16:9 runs
went on to frames 3,340 and 3,900.

Each world camera's aspect is its 4:3 one times 4/3 to five figures. Every HUD 3D, minimap
and menu camera kept its 4:3 aspect. Every call of the six that widen was given its 4:3 aspect,
as was Top Ride's load, so none widened an aspect twice.

The race's results frame at 25,800 is the same at 16:9 as at 4:3, so the race still finishes
in 1:14.68. Of the frames dumped every 600 from 8,400, only those up to 12,600 differ, while
the world camera after the finish is drawn. From frame 13,063 on, no world camera is in the
census.

## Anchoring the HUD

The game draws its HUD through cameras that keep the 4:3 shape, so a stretched picture widens
the HUD with the world. Dragoon marks each HUD draw with an anchor, gcn-recomp's
`gx::set_draw_anchor`, which squeezes it back toward the left edge, the right edge or the middle
of a rect. The draw keeps its 4:3 size and its 4:3 distance to that edge. At 4:3 every anchor is
the identity.

`src/hud_anchors.cpp` keys on the render callback. `recomp/patches.txt` calls it where
`GObj_SetTextureCamera` calls each callback and where the callback returns, the census's two
sites. A callback that isn't in its table draws stretched.

| Callback | Draws | Placed by |
|---|---|---|
| `fn_80114F1C` | The speedometer, and the race's lap count and position or the players' names in split views | Its edge |
| `fn_8011500C` | The clock and the minimap | Its edge |
| `fn_8011F114` | City Trial's gauge beside the speedometer | Its edge |
| `kar_ifround_display_mmapply_player_marker_world_projected`, `kar_ifround_display_mmapstart_marker_projected_midpoint` | The karts and the start on the minimap | Its edge |
| `fn_8011F8F4`, `fn_801206A0`, `fn_80121278`, `fn_80121CA4`, `fn_80122380` | The markers over karts and items | Its own place |

One callback draws at both sides of the screen. `fn_80114F1C` puts the position at the left and
the speedometer at the right through the same HUD 3D camera, so its projection can't tell them
apart. Each is a joint tree of its own, though, drawn by its own call to `HSD_JObjDispAll`.

`recomp/hle.txt` lists `HSD_JObjDispAll`, so the hook places each tree as it's drawn, by where
it sits on screen. A tree's root, and some of its joints, sit at the middle of the screen while
its shapes are drawn at a side. So a tree goes by where most of its joints drew their shapes last
frame, each joint's matrix put through the current camera.

A tree's mark ends when its outermost `HSD_JObjDispAll` call returns. What the callback draws
itself after it, such as a stripe straight through GX, stretches as a callback outside the table
does.

A joint has no place until the game first draws it and while it's scaled to zero, since its
matrix's 3 by 3 part is all zero then. A tree with no joint placed holds the mark it had the
frame before, or goes by its root when it had none. That can happen on the frame it first shows,
each frame after while it stays scaled to nothing and a frame it shows scaled to nothing after
missing one.

A tree in a rect's left third anchors to its left edge, one in its right third to its right
edge and one between to its middle. It holds the edge it had the frame before until it's a
quarter of a third past one of that edge's lines, and then takes the other edge. Without that,
an element moving 2 pixels across a line would jump about 109 display pixels at 16:9, and a tree
whose joints straddle a line in near-equal numbers would turn each time one of them hid.

The edge holds only while the tree moves. Once the same joints have drawn in the same places
for 30 frames in a row, it takes its nearest edge. A joint that moves, shows or hides starts the
count again.

Without that, an element that stopped inside the band would keep the edge it came from, then
show at the other once it missed a frame.

A tie in a tree's vote goes to the edge it held while it moves. Once it has rested, the tie goes
to the first of those tied in the order the tree draws its joints.

A tree that misses a frame chooses afresh when it next shows, and holds nothing from that
showing, since its joints sit where they last drew, before the frame it missed. One shown for the
first time does the same, as its joints sit where the game made them, which for every tree
`fn_80114F1C` draws in the race and City Trial is the screen's middle.

The rect is the screen in one player. In 2P and 4P it's the view the tree sits in, from the
viewports of the frame's world cameras, which `src/cameras.cpp` passes as the game sets their
aspect.

A split view drawn through a camera the game sets only once would drop out of the views after a
frame. In a 4P race on Dragoon `701a2dd` every player's camera was set every frame through all
four finishes, so no run has shown one.

A tree outside every view sits on the bars between them and anchors to the screen, as the 4P
clock does at the left. In the bars' middle third it's the bars themselves, which span the
screen and stretch with it.

A marker is centered on its root, which the game has just put over the kart or item it follows.
Its rect has no width, so the marker keeps its 4:3 size and sits where the wider world puts
what it follows.

A mark takes its place where the front end has got to in the command stream. Up to 31 bytes of
what the game wrote can still wait in the write-gather pipe, so the draw they end would take
the next mark. `src/draw_marks.cpp` first pads the pipe's line with zero bytes, the GPU's no-op,
as the SDK's `GXFlush` does, and the census's draw tags go through it too.

```sh
tools/probe.sh hud 60 tests/routes/air-ride-race.txt 4200 DRAGOON_CENSUS=1 GCN_DRAWLOG=4200 GCN_DRAWLOG_VERBOSE=1
tools/probe.sh hud-wide 60 tests/routes/air-ride-race.txt 4200 --aspect=16:9 --output DRAGOON_CENSUS=1 GCN_DRAWLOG=4200 GCN_DRAWLOG_VERBOSE=1
tools/drawlog.py hud build/probe/hud/stdout.txt build/probe/hud-wide/stdout.txt --aspect 16:9
```

`drawlog.py hud` pairs the two runs' HUD draws and checks each anchored one's box against its
4:3 box, as the docstring of `tools/hud_boxes.py` says. On Dragoon `e52dce1` at gcn-recomp
`5e49451`, one run at a time at loads of 1.5 to 3.1, every checkpoint passed. `e52dce1`, here
and below, is on the `hud-anchors` branch, with the same `src/`, `recomp/` and
`tools/drawlog.py` as `fe88e8a`.

| Checkpoint | Anchored | Failed | Stretched |
|---|---|---|---|
| Race, 4200 | 41 | 0 | 0 |
| Race with `GCN_GX_SYNC=1`, 4200 | 41 | 0 | 0 |
| City Trial, 3300 | 33 | 0 | 0 |
| 2P, 3480 | 54 | 0 | 1, the bar between the views |
| 4P, 3480 | 76 | 0 | 1, an untextured full-screen draw |

Two of 4P's anchored draws are markers with no match, both in player 3's view. At 4:3 player 4
is past that view's left edge and shows as an icon there, and at 16:9 player 4 is in view and
shows as a marker over their kart. In the 4P dump each of the other markers sits over the same
scenery as at 4:3.

On Dragoon `8e6bc30` and `1ff85c8` at gcn-recomp `b11ebc6`, with `drawlog.py hud` also failing
a draw anchored to the edge across its rect and a centered draw past the band at a side, all
four checkpoints gave the same counts, one run at a time. These four callbacks' trees took these
anchors on both.

| Callback | Race, 4200 | City Trial, 3300 | 2P, 3480 | 4P, 3480 |
|---|---|---|---|---|
| `fn_80114F1C` | L for the position. R for the lap count, the speedometer and its frame | R for the speedometer and its frame | In each view, L for the name and R for the speedometer and its frame | As in 2P |
| `kar_ifround_display_mmapply_player_marker_world_projected`, the minimap's karts | R | L | L | None drawn |
| `kar_ifround_display_mmapstart_marker_projected_midpoint`, the minimap's start | R | None drawn | None drawn | None drawn |
| `fn_8011F114` | None drawn | R | R in each view | R in each view |

In the output dumps at 16:9 the race's position sits at the left and the timer in the middle.
The minimap, the lap count and the speedometer sit at the right, and each CPU marker sits over
its kart. In 2P and 4P each player's name sits at the left of their view and the speedometer at
its right, with the clock at the left of the bars.

`tests/src/test_hud_anchors.cpp` checks the thirds, the views, the vote, the held edges and the
cameras' maths.
`tests/src/test_draw_marks.cpp` checks the padding.

## Menus, text and the movie

The census of the race route at 16:9, at the first text box (60), the opening movie (600), the
title (960), the mode select (1200) and the course select (2100), found these cameras outside
play.

| Camera | Viewport | What it draws |
|---|---|---|
| Perspective at an aspect of 1.25538, `p` 25 or 30 | 640x480 | The menus |
| Ortho, `p=0,-480,0,640` | 640x480 | Text boxes and menu text, through `HSD_SisLib_803A84BC` |
| Ortho, `p=0,480,0,640` | 640x480 | The opening movie, through `kar_gmautodemo__near_8000cde0` once `kar_gmautodemo_start_opening_movie` (0x8000D26C) has started it |
| Ortho, 256 by 192 | 256x192 | A render to texture, set by no object |
| Perspective at 1.33333, `p` 60 | | Nothing |
| Ortho, 680 by 520 | | Nothing |

`recomp/patches.txt` calls `dragoon_hud_camera` at 80401150, after the world cameras follow.
While the frame has no world view, it centers every draw under one of the first three cameras
in its 640x480 frame, and the HUD table's callbacks under it take the same mark unless the table
places them. The render to texture keeps no anchor, and no run logs an `[anchor]` copy line.
`tests/src/test_hud_anchors.cpp` checks which cameras take the mark.

At 4:3 no camera takes it. A mark pads the write-gather pipe, and on the menus the game sees
that. With the marks set at 4:3 the frame check failed on every route. The opening movie's
frames differed from 360 to 900, or 400 to 900 on the `-courses` routes. The mode movies
differed from 1620 to 1860 in Air Ride, 1860 to 2100 in City Trial and 1740 to 1980 in Top
Ride, and the stadium routes at 3600. At 600 the movie showed another frame, with 89% of its
pixels changed. With no mark at 4:3, all 24 routes and their 1,906 frames matched on Dragoon
`2d68a1e` in 14 min 36 s, at loads of 2.9 to 4.4.

On Dragoon `2d68a1e` at gcn-recomp `5e54665`, `tools/picture_box.py --dark 128` measured the
output dumps at 4:3 (2560x1920) and at 16:9 (3414x1920), before and after. A centered 4:3
picture leaves bars of 427 at each side.

| Checkpoint | 4:3 | 16:9 before | 16:9 after |
|---|---|---|---|
| Text box, 60 | 2560x1920, 1.3333 | 3414x1920, 1.7781 | 2560x1920 at 427, 1.3333, bars 427 and 427 |
| Opening movie, 600 | 2560x1920, 1.3333 | 3414x1920, 1.7781 | 2560x1920 at 427, 1.3333, bars 427 and 427 |
| Title, 960 | 2560x1565, 1.6358 | 3414x1565, 2.1815 | 2559x1565 at 428, 1.6351, bars 428 and 427 |
| Mode select, 1200 | 2560x1788, 1.4318 | 3414x1788, 1.9094 | 2559x1788 at 427, 1.4312, bars 427 and 428 |
| Course select, 2100 | 2560x1920, 1.3333 | 3414x1920, 1.7781 | 2560x1920 at 427, 1.3333, bars 427 and 427 |

Two elements were measured by color. The text box's orange button (`--color FF8000 --within
24`) is 764x167 at 434 at 4:3, 1020x167 at 578 before and 764x167 at 861 after, 434 plus 427.
The course select's cursor (`--color FFF070 --within 12`) is 401x377 at 302 at 4:3, 535x377 at
403 before and 397x377 at 732 after, 4 output pixels narrower, about 1 at 480 high.

The after runs centered 83 draws at 60, 1 at 600, 156 at 960, 214 at 1200 and 83 at 2100. The
mode select's render to texture is the one draw left stretched. `drawlog.py hud` gave the same
counts as before for the race at 4200 and 4P at 3480. `tools/ram_peek.py` read the scene,
player 1's speed and place at 2400, 3600, 4200 and 6000 of the race at 4:3 and at 16:9, and all
20 values matched.

Play has narrow cameras over the screen too, so the menus' mark could reach a HUD drawn while
the frame has no view. On Dragoon `e79f475` and `ec0004a`, one run at a time at loads of 8 to 10,
`drawlog.py hud` gave the same lines at both for these four, and the 16:9 output dumps of Top
Ride and the race at 8400 were the same files.

| Checkpoint | Anchored | Failed | Stretched | 16:9 dump, `picture_box.py` |
|---|---|---|---|---|
| Top Ride on Grass, 3600 | 0 | 0 | 38 | 3414x1920, bars 0 and 0 |
| Race after the finish, 8400 | 11 | 3 | 0 | 3414x1627 from row 158, bars 0 and 0 |
| City Trial, 3300 | 33 | 0 | 0 | 3414x1920, bars 0 and 0 |
| 2P, 3480 | 54 | 0 | 1 | 3376x1764 at 19, bars 19 and 19 |

Top Ride's 38 HUD draws go through fov 25 cameras at 1.25538 over the screen, which
`fn_802CA894` and `kar_a2d_game_effect__80379f94` set up, and no world camera gives its frames
a view, so those cameras' mark is the 4:3 frame. But Top Ride makes them current and draws its
HUD outside every render callback. Their `[census]` lines name no callback, and none of the
frame's 233 draws carries a callback's tag. A camera's mark goes only to a callback's draws, so
the HUD stretches. This page once said Top Ride's census on Dragoon `701a2dd` had all 38 drawn
by `HSD_GObjJObjDisp`, read off `drawlog.py cameras`, which names the callbacks of every census
camera with the draws' field of view and viewport rather than the callback each draw was made
in. The frame's 233 draws here are the HUD's 38 and the world's 195, where `a2ff7fd` above had
236 with the world's 198.

After the race's finish the world camera that's drawn is set once, at 8,092. The module's call
returning to `0x800C2884` still sets eight cameras that aren't drawn each frame to 13,061, and
`ram_peek.py` read all eight with a 640x480 viewport at 8400, so every frame has the screen as
its view. The table places the 11 HUD draws, all `fn_8011500C`'s. The three that fail are the
banner's pieces under "What 16:9 still gets wrong".

The views are forgotten as `CObjAmnesia` forgets the scene's cameras. Before that, the results'
first frame at 13,062 read 13,061's view, and its 92 draws stretched while 91 of 13,063's were
centered. On Dragoon `7a0e1c6` 91 of 13,062's are centered.

At an output narrower than 4:3, as with `--aspect=1:1` or a tall window, no camera takes the
mark. Centered, the frame would be wider than the window and lose 80 of its 640 at each side at
1:1, showing only x 80 to 560. So the menus stretch there, squeezed but whole. No run measured it.

## What 16:9 still gets wrong

These come from the output dumps at 16:9 of the race at 4200 and 8400, City Trial at 3300, 2P
and 4P at 3480, Top Ride on Grass at 3600 and, before `b307f49`, the mode select at 1200. All
but the mode select's are from Dragoon `e52dce1`, with the race at 8400 and Top Ride run at
loads of 4.2 to 5.0.

- After the finish `fn_8011500C` draws the replay's banner and buttons, and they keep their 4:3
  shape in the middle of the screen. Since `ab50305` added the check of a centered draw past the
  band, `drawlog.py hud` fails three of their 11 draws at 8400, the banner's pieces at the sides.
  The banner's dark stripe spans the screen at 4:3 but is drawn within one of the callback's
  joint trees, so at 16:9 it takes the tree's middle anchor and stops short of both sides.
- In Top Ride the clock, the lap count and the four players' counters are 4/3 too wide. At
  3600 on Dragoon `ec0004a` `drawlog.py hud` listed all 38 of its HUD draws as stretched. Top
  Ride draws them outside every render callback, none of them carrying a callback's tag, so the
  table, which keys on the callback, can't place them.
- A HUD element that first shows goes by its root's place, or by joints still where the game made
  them, until its joints have drawn. That can anchor it to the wrong edge for a frame, as it can
  one that shows scaled to nothing after missing a frame. In the draw logs every tree
  `fn_80114F1C` draws shows in the middle for its first frame in the race at 3241 and City Trial
  at 2852, 107 display pixels from where it sits from the next, and in 2P at 2852 they stretch
  for theirs.
- An element that slides across a third's line jumps to the other edge once it's a quarter of a
  third past it. One that stops less than a quarter of a third past the line shows the edge it
  came from for 29 frames and takes its nearest edge on the 30th, and a still element with a
  blinking joint never rests, so it keeps the edge it came with. No dump caught any of these.
- A menu drawn over a world view, such as the pause menu, stretches, since the menu cameras are
  only centered while the frame has none. No dump checked one.
- At 16:9 the marks still pad the pipe, so a movie may show other frames than at 4:3. No run
  compared them.
- The test that culls the world wasn't found, so pop-in at the sides while moving needs a person
  to watch.
