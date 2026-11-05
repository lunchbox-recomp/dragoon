/* What the recompiler's output gives the engine, with nothing in it. CI links the prebuilt
 * kit against this alone, so the kit's link runs with no disc. */
#include "recomp.h"

const RecompFunc g_recomp_funcs[1];
const uint32_t g_recomp_func_count = 0;
const uint32_t g_recomp_code_base = 0, g_recomp_code_end = 0;
const RecompModule g_recomp_modules[1];
const uint32_t g_recomp_module_count = 0;
const RecompRel g_recomp_rels[1];
const uint32_t g_recomp_rel_count = 0;
/* The interpreter's tables. The hash is 64-bit FNV-1a's of no bytes, as recomp.py writes it. */
const RecompRange g_recomp_ranges[1];
const uint32_t g_recomp_range_count = 0;
uint8_t g_code_changed_bits[1];
const RecompSite g_recomp_sites[1];
const uint32_t g_recomp_site_count = 0;
const uint32_t g_recomp_idle[1];
const uint32_t g_recomp_idle_count = 0;
const RecompSpecial g_recomp_specials[1];
const uint32_t g_recomp_special_count = 0;
const RecompText g_recomp_text[1];
const uint32_t g_recomp_text_count = 0;
const uint64_t g_recomp_text_fnv = 0xCBF29CE484222325ull;

void orig_OSSaveContext(CPU* c) { (void)c; }
/* src/cameras.cpp's camera hooks call the original bodies. */
void orig_HSD_CObjSetAspect(CPU* c) { (void)c; }
void orig_HSD_CObjLoadDesc(CPU* c) { (void)c; }
void orig_CObjRelease(CPU* c) { (void)c; }
void orig_CObjAmnesia(CPU* c) { (void)c; }
/* src/hud_anchors.cpp's joint hook calls the original body too. */
void orig_HSD_JObjDispAll(CPU* c) { (void)c; }
