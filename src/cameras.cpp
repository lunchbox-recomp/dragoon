// The world cameras at a wider output (docs/dev/widescreen.md). With DRAGOON_WIDEN=1, a world
// camera's aspect is widened by the output aspect over 4:3 as the camera module stores it, so
// the game culls for the wider view too. Every other camera keeps the aspect the game gives
// it. Without the switch the game runs as it always has.
#include "cameras.h"
#include "gx/render.h"
#include "runtime.h"
#include <cstdlib>
#include <cstring>

// recomp/hle.txt lists HSD_CObjSetAspect (0x80402C94), so its calls come here and its own
// body is orig_HSD_CObjSetAspect.
extern "C" void orig_HSD_CObjSetAspect(CPU* c);

namespace {

const bool g_widen = [] {
    const char* e = getenv("DRAGOON_WIDEN");
    return e && *e && strcmp(e, "0") != 0;
}();

}  // namespace

// HSD_CObjSetAspect(cobj in r3, aspect in f1) stores the aspect of a perspective camera. lr is
// still the caller's return address on entry.
extern "C" void hle_HSD_CObjSetAspect(CPU* c) {
    if (g_widen && dragoon::sets_world_aspect(c->lr))
        c->f[1].d = dragoon::widened_aspect((float)c->f[1].d, gx::output_aspect());
    orig_HSD_CObjSetAspect(c);
}
