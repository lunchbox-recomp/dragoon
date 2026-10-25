// Which cameras widen at a wider output and by how much, the pure part. src/cameras.cpp
// applies it.
#pragma once
#include <cstdint>

namespace dragoon {

// The console's own shape, which the game sets every camera up for.
constexpr float kConsoleAspect = 4.0f / 3.0f;

// The camera module sets the world cameras' aspect through two calls to HSD_CObjSetAspect,
// which return to 0x800C2884 in kar_cmreplay__near_800c24e8 and to 0x800C9820 in
// kar_cmreplay__near_800c9790. The HUD, the minimap and the menus set theirs through the
// camera library instead, so a call from anywhere else isn't a world camera's. In the race
// at gcn-recomp 3a8d154, from frame 8,183 after the finish to 13,062, the full-screen world
// cameras store 1.25538 with DRAGOON_WIDEN=1, and neither call sets them.
inline bool sets_world_aspect(uint32_t return_address) {
    return return_address == 0x800C2884 || return_address == 0x800C9820;
}

// A world camera's aspect at output aspect `output`: its 4:3 aspect times the output aspect
// over 4:3. At 4:3 it's the aspect unchanged, to the bit.
inline float widened_aspect(float aspect, float output) { return aspect * (output / kConsoleAspect); }

}  // namespace dragoon
