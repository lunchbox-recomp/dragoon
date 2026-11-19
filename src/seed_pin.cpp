// The test seed, on with DRAGOON_SEED_PIN=1: the game's RNG gets the same seeds as Dolphin's
// reference runs, for tools/dolphin_diff.py only. Off, the game reads the clock as it always has.
//
// The game seeds HSD_Rand from the clock at five instructions, each a call of OSGetTick or
// OSGetTime. recomp/patches.txt replaces each call with an `if` on this switch: on, it loads
// the constant dolphin_ref.py's SEED_PINS has Dolphin's game INI load at the same address with
// one lis, and off, it makes the original call. The sites and why they're all of them are in
// docs/dev/status.md ("The seed").
#include <cstdlib>
#include <cstring>

namespace {

const bool g_on = [] {
    const char* e = getenv("DRAGOON_SEED_PIN");
    return e && strcmp(e, "1") == 0;
}();

}  // namespace

extern "C" int dragoon_seed_pinned(void) { return g_on; }
