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

void orig_OSSaveContext(CPU* c) { (void)c; }
/* src/cameras.cpp's camera hooks call the original bodies. */
void orig_HSD_CObjSetAspect(CPU* c) { (void)c; }
void orig_HSD_CObjLoadDesc(CPU* c) { (void)c; }
void orig_CObjRelease(CPU* c) { (void)c; }
void orig_CObjAmnesia(CPU* c) { (void)c; }
/* src/hud_anchors.cpp's joint hook calls the original body too. */
void orig_HSD_JObjDispAll(CPU* c) { (void)c; }
