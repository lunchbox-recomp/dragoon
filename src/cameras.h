// Which cameras widen at a wider output and by how much, the pure part. src/cameras.cpp
// applies it.
#pragma once
#include <cstdint>

namespace dragoon {

// The console's own shape, which the game sets every camera up for.
constexpr float kConsoleAspect = 4.0f / 3.0f;

// Whether a call to HSD_CObjSetAspect sets a world camera's aspect, from where it returns to
// and where its caller returns to.
//
// During play the camera module sets the world cameras' aspect every frame through two calls,
// which return to 0x800C2884 in kar_cmreplay__near_800c24e8 and to 0x800C9820 in
// kar_cmreplay__near_800c9790.
//
// Each camera is first set up through the camera library, whose calls set up the HUD, minimap
// and menu cameras too. Those calls are a world camera's when the library was called from one
// of four places. kar_lbcamera_load_desc_update_aspect returns to 0x80066E4C, called from
// kar_camera__800b3944 (0x800B3990). The viewport presets for one, two and four views return
// to 0x80066ECC, 0x80066FF0 and 0x80067148, called from kar_grlib2__near_800babd0 (0x800BAC38),
// kar_grlib2__near_800bac5c (0x800BACD0) and kar_grlib2__near_800bacf4 (0x800BAD68). The race's
// cameras after the finish line get their aspect from these alone.
inline bool sets_world_aspect(uint32_t return_address, uint32_t callers_return_address) {
    switch (return_address) {
    case 0x800C2884:
    case 0x800C9820: return true;
    case 0x80066E4C: return callers_return_address == 0x800B3990;
    case 0x80066ECC: return callers_return_address == 0x800BAC38;
    case 0x80066FF0: return callers_return_address == 0x800BACD0;
    case 0x80067148: return callers_return_address == 0x800BAD68;
    default: return false;
    }
}

// Whether a call to HSD_CObjLoadDesc loads a world camera, from where it returns to and where
// its caller returns to. Top Ride's world camera takes its aspect from its description and
// never goes through HSD_CObjSetAspect. kar_a2d_kurakko__near_80371968 loads it, its call
// returning to 0x803719A0, when TopRide_GameSessionInit calls it (returning to 0x8028C0E0).
// The HUD's and menus' cameras are loaded from elsewhere.
inline bool loads_world_camera(uint32_t return_address, uint32_t callers_return_address) {
    return return_address == 0x803719A0 && callers_return_address == 0x8028C0E0;
}

// A world camera's aspect at output aspect `output`: its 4:3 aspect times the output aspect
// over 4:3. At 4:3 it's the aspect unchanged, to the bit, and so is it at an output of no
// width, such as a window shrunk to nothing under --aspect=window.
inline float widened_aspect(float aspect, float output) {
    if (!(output > 0.0f)) return aspect;
    return aspect * (output / kConsoleAspect);
}

}  // namespace dragoon
