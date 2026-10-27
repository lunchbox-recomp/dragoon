// The world cameras at a wider output (docs/dev/widescreen.md). A world camera's aspect is
// widened by the output aspect over 4:3 as the game stores it. Whatever reads it then sees the
// wider view, kar_lbvector_project_world_to_screen (0x800644AC) placing the markers among them.
// Every other camera keeps the aspect the game gives it. At 4:3 the widening is the identity,
// so the game runs as it always has.
#include "cameras.h"
#include "census.h"
#include "gx/render.h"
#include "runtime.h"

// recomp/hle.txt lists HSD_CObjSetAspect (0x80402C94), so its calls come here and its own
// body is orig_HSD_CObjSetAspect.
extern "C" void orig_HSD_CObjSetAspect(CPU* c);

namespace {

bool in_ram(uint32_t a) { return a >= 0x80000000u && a - 0x80000000u < RAM_SIZE; }

// Where the caller returns to, given its stack frame. Its prologue saved its return address
// in the word after its back chain, as the EABI's does. 0 when the frame isn't in RAM.
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
    const float given = (float)c->f[1].d;
    if (dragoon::sets_world_aspect(lr, lr2))
        c->f[1].d = dragoon::widened_aspect(given, gx::output_aspect());
    orig_HSD_CObjSetAspect(c);
    dragoon::census_aspect(cobj, lr, lr2, given);
}
