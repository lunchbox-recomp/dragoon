// The world cameras at a wider output (docs/dev/widescreen.md). A world camera's aspect is
// widened by the output aspect over 4:3 as the game stores it. Whatever reads it then sees the
// wider view, kar_lbvector_project_world_to_screen (0x800644AC) placing the markers among them.
// Every other camera keeps the aspect the game gives it. At 4:3 the widening is the identity,
// so the game runs as it always has.
#include "cameras.h"
#include "census.h"
#include "guest_memory.h"
#include "gx/render.h"
#include <cmath>

// recomp/hle.txt lists HSD_CObjSetAspect (0x80402C94) and HSD_CObjLoadDesc (0x804031EC), so
// their calls come here and their own bodies are orig_HSD_CObjSetAspect and
// orig_HSD_CObjLoadDesc.
extern "C" void orig_HSD_CObjSetAspect(CPU* c);
extern "C" void orig_HSD_CObjLoadDesc(CPU* c);

namespace {

using dragoon::in_ram;

constexpr uint32_t kCObjAspect = 0x44;          // HSD_CObj: a perspective camera's aspect
constexpr uint32_t kCObjProjectionType = 0x50;  // u8

// A perspective camera's stored aspect, or NaN for anything else.
float stored_aspect(uint32_t cam) {
    if (!in_ram(cam) || mem_r8(cam + kCObjProjectionType) != dragoon::kPerspective) return NAN;
    return dragoon::f32_at(cam + kCObjAspect);
}

void store_aspect(uint32_t cam, float aspect) { dragoon::set_f32(cam + kCObjAspect, aspect); }

// The world cameras the library sets up and Top Ride's, which nothing sets again each frame,
// kept so they follow a change of output aspect. Only the guest thread holding the baton
// touches it.
dragoon::SetOnceCameras g_set_once;

// Where the caller returns to, given its stack frame `sp`. The word at sp is the back chain,
// the address of the frame of the caller's own caller. The caller's prologue saved its return
// address in that frame's LR save word, the back chain plus 4, as the EABI's prologue does, and
// that's what this reads. The word at sp plus 4 is the LR save word the hooked function would
// fill, so it's stale here. 0 when either address isn't in RAM.
uint32_t callers_return_address(uint32_t sp) {
    const uint32_t back = in_ram(sp) ? mem_r32(sp) : 0;
    return in_ram(back) ? mem_r32(back + 4) : 0;
}

}  // namespace

// HSD_CObjSetAspect(cobj in r3, aspect in f1) stores the aspect of a perspective camera. lr is
// still the caller's return address on entry, and r1 the caller's stack frame. The census
// (src/census.cpp) logs the call.
extern "C" void hle_HSD_CObjSetAspect(CPU* c) {
    const uint32_t cobj = c->r[3], lr = c->lr, lr2 = callers_return_address(c->r[1]);
    const float given = (float)c->f[1].d, output = gx::output_aspect();
    if (dragoon::sets_world_aspect(lr, lr2)) c->f[1].d = dragoon::widened_aspect(given, output);
    orig_HSD_CObjSetAspect(c);
    if (dragoon::sets_up_world_camera(lr, lr2)) g_set_once.add(cobj, given, output, stored_aspect);
    dragoon::census_aspect(cobj, lr, lr2, given);
}

// HSD_CObjLoadDesc(desc in r3) makes a camera from its description and returns it in r3.
// CObjLoad stores the description's aspect straight into the camera, with no call to
// HSD_CObjSetAspect, so a world camera loaded this way is widened here. The census logs each
// perspective camera it loads.
extern "C" void hle_HSD_CObjLoadDesc(CPU* c) {
    const uint32_t lr = c->lr, lr2 = callers_return_address(c->r[1]);
    orig_HSD_CObjLoadDesc(c);
    const uint32_t cobj = c->r[3];
    const float loaded = stored_aspect(cobj);
    if (std::isnan(loaded)) return;
    if (dragoon::loads_world_camera(lr, lr2)) {
        const float output = gx::output_aspect();
        store_aspect(cobj, dragoon::widened_aspect(loaded, output));
        g_set_once.add(cobj, loaded, output, stored_aspect);
    }
    dragoon::census_aspect(cobj, lr, lr2, loaded);
}

// HSD_CObjSetCurrent (0x80401150) on entry, from recomp/patches.txt, before the camera's
// projection is built: the kept cameras follow the output aspect, should it have changed.
extern "C" void dragoon_cameras_follow(void) {
    g_set_once.follow(gx::output_aspect(), stored_aspect, store_aspect);
}
