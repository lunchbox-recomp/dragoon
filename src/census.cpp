// The camera census, on with DRAGOON_CENSUS=1: which camera each render callback draws
// through, as the [census] lines census.h makes. docs/dev/widescreen.md has what it found.
//
// Two hooks in recomp/patches.txt call in. One is HSD_CObjSetCurrent (0x80401150) on entry,
// with the camera it's about to make current. The other is GObj_SetTextureCamera
// (0x8042A0B4) at its call of each object's render callback, which walks every object drawn
// through the current camera. src/cameras.cpp also calls in after each HSD_CObjSetAspect,
// with the camera, where the call returns to, the caller's stack frame and the aspect it was
// given. Off, each hook returns at once.
//
// Addresses are this disc's (GKYE01), from analysis/symbols.txt. The HSD_CObj and HSD_GObj
// layouts are the decomp's (sysdolphin's cobj.h and gobj.h).
#include "census.h"
#include "gx/render.h"
#include "runtime.h"
#include <cstdlib>
#include <cstring>

namespace {

constexpr uint32_t kCObjCurrent = 0x805DE22C;    // CObjCurrent, what HSD_CObjSetCurrent set last
constexpr uint32_t kCurrentRender = 0x805DE31C;  // hsdGObj_current_render, the object drawing
constexpr uint32_t kCurrentGx = 0x805DE320;      // hsdGObj_current_gx, the camera object drawing
constexpr uint32_t kGObjRenderCb = 0x1C;         // HSD_GObj::render_cb
constexpr uint32_t kCObjViewport = 0x0C;         // HSD_CObj: left, right, top, bottom
constexpr uint32_t kCObjProjection = 0x40;       // fov and aspect, or top, bottom, left, right
constexpr uint32_t kCObjProjectionType = 0x50;   // u8

const bool g_on = [] {
    const char* e = getenv("DRAGOON_CENSUS");
    return e && *e && strcmp(e, "0") != 0;
}();
dragoon::OncePerFrame g_once;

bool in_ram(uint32_t a) { return a >= 0x80000000u && a - 0x80000000u < RAM_SIZE; }

float f32_at(uint32_t a) {
    const uint32_t u = mem_r32(a);
    float f;
    memcpy(&f, &u, sizeof(f));
    return f;
}

dragoon::Camera read_camera(uint32_t cobj) {
    dragoon::Camera c;
    c.type = mem_r8(cobj + kCObjProjectionType);
    for (int i = 0; i < 4; i++) {
        c.proj[i] = f32_at(cobj + kCObjProjection + 4 * i);
        c.viewport[i] = f32_at(cobj + kCObjViewport + 4 * i);
    }
    return c;
}

void log_pair(uint32_t cobj, uint32_t gobj, uint32_t cb, const char* via) {
    if (!in_ram(cobj)) return;
    const uint32_t frame = gx::g_frames_submitted.load(std::memory_order_relaxed) + 1;
    const uint32_t cls = in_ram(gobj) ? mem_r16(gobj) : 0;
    const std::string line = dragoon::census_line(frame, cobj, read_camera(cobj), cb, cls, via);
    if (g_once.first(frame, line)) fprintf(stderr, "%s\n", line.c_str());
}

}  // namespace

// HSD_CObjSetCurrent on entry: the camera, and the callback of whichever object is drawing.
extern "C" void dragoon_census_camera(uint32_t cobj) {
    if (!g_on) return;
    uint32_t gobj = mem_r32(kCurrentRender);
    if (!in_ram(gobj)) gobj = mem_r32(kCurrentGx);
    log_pair(cobj, gobj, in_ram(gobj) ? mem_r32(gobj + kGObjRenderCb) : 0, "set");
}

// GObj_SetTextureCamera, about to call an object's render callback through the current camera.
extern "C" void dragoon_census_draw(uint32_t gobj, uint32_t cb) {
    if (!g_on) return;
    log_pair(mem_r32(kCObjCurrent), gobj, cb, "draw");
}

// HSD_CObjSetAspect (0x80402C94), once it has stored the aspect, from src/cameras.cpp. The
// caller saved its own return address in the word after its back chain, as the EABI's
// prologue does.
void dragoon::census_aspect(uint32_t cam, uint32_t lr, uint32_t sp, float given) {
    if (!g_on || !in_ram(cam)) return;
    const uint32_t back = in_ram(sp) ? mem_r32(sp) : 0;
    const uint32_t lr2 = in_ram(back) ? mem_r32(back + 4) : 0;
    const uint32_t frame = gx::g_frames_submitted.load(std::memory_order_relaxed) + 1;
    const std::string line = aspect_line(frame, cam, lr, lr2, given, f32_at(cam + kCObjProjection + 4));
    if (g_once.first(frame, line)) fprintf(stderr, "%s\n", line.c_str());
}
