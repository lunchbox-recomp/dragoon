// HUD anchors at a wider output (docs/dev/widescreen.md): the table of the HUD's render
// callbacks and the hooks that mark their draws. src/hud_anchors.h has the pure parts.
//
// recomp/patches.txt calls dragoon_hud_enter and dragoon_hud_leave from GObj_SetTextureCamera
// (0x8042A0B4) around each object's render callback. recomp/hle.txt lists HSD_JObjDispAll
// (0x8040A7B8), so its calls come here, and a HUD callback's joint tree is placed as it's
// displayed. An Edge tree goes by where its joints drew their shapes on screen last frame,
// through the current camera, and an Own tree by where its root sits. src/cameras.cpp passes
// each world camera as the game sets its aspect, and a split view's HUD anchors in the
// viewport of the one it sits in. At 4:3 every anchor is the identity and nothing moves.
//
// Addresses are this disc's (GKYE01), from analysis/symbols.txt. The HSD_CObj and HSD_JObj
// layouts are the decomp's (sysdolphin's cobj.h and jobj.h).
#include "hud_anchors.h"
#include "draw_marks.h"
#include "guest_memory.h"
#include "gx/render.h"

extern "C" void orig_HSD_JObjDispAll(CPU* c);

namespace {

using dragoon::f32_at;
using dragoon::in_ram;
using dragoon::Placement;

// The HUD's render callbacks. One not here draws Stretch.
struct Entry {
    uint32_t cb;
    Placement placement;
};
constexpr Entry kTable[] = {
    // fn_80114F1C: the race's position, lap count and speedometer, and a split view's player
    // name. It scissors to its player's view.
    {0x80114F1C, Placement::Edge},
    // fn_8011500C: the clock, the lap number and the minimap.
    {0x8011500C, Placement::Edge},
    // fn_8011F114: City Trial's gauge beside the speedometer.
    {0x8011F114, Placement::Edge},
    // kar_ifround_display_mmapply_player_marker_world_projected and
    // kar_ifround_display_mmapstart_marker_projected_midpoint: the karts and the start on the
    // minimap, which sit in its corner with it.
    {0x8011DCF8, Placement::Edge},
    {0x8011E404, Placement::Edge},
    // fn_8011F8F4, fn_801206A0, fn_80121278, fn_80121CA4 and fn_80122380: the markers over
    // karts and items, which follow them across the wider world.
    {0x8011F8F4, Placement::Own},
    {0x801206A0, Placement::Own},
    {0x80121278, Placement::Own},
    {0x80121CA4, Placement::Own},
    {0x80122380, Placement::Own},
};

Placement placement_of(uint32_t cb) {
    for (const Entry& e : kTable)
        if (e.cb == cb) return e.placement;
    return Placement::Stretch;
}

constexpr uint32_t kCObjCurrent = 0x805DE22C;  // CObjCurrent, the camera drawing
constexpr uint32_t kCObjViewport = 0x0C;       // HSD_CObj: left, right, top, bottom
constexpr uint32_t kCObjNear = 0x38;
constexpr uint32_t kCObjProjection = 0x40;     // fov and aspect, or top, bottom, left, right
constexpr uint32_t kCObjProjectionType = 0x50; // u8
constexpr uint32_t kCObjViewMtx = 0x54;        // three rows of four
constexpr uint32_t kJObjParent = 0x0C;         // HSD_JObj
constexpr uint32_t kJObjTranslate = 0x38;
constexpr uint32_t kJObjMtx = 0x44;            // its place in the world, three rows of four

dragoon::HudCallbacks g_hud;
dragoon::WorldViews g_views;
dragoon::Mark g_sent;   // the mark last put in the command stream
uint32_t g_displaying;  // HSD_JObjDispAll calls under way, the joint tree's own among them

// The frame being drawn, one more than the frames the game had submitted.
uint32_t this_frame() { return gx::g_frames_submitted.load(std::memory_order_relaxed) + 1; }

dragoon::Rect viewport_of(uint32_t cobj) {
    return {f32_at(cobj + kCObjViewport), f32_at(cobj + kCObjViewport + 4),
            f32_at(cobj + kCObjViewport + 8), f32_at(cobj + kCObjViewport + 12)};
}

dragoon::Lens lens_of(uint32_t cobj) {
    dragoon::Lens l;
    l.type = mem_r8(cobj + kCObjProjectionType);
    l.near = f32_at(cobj + kCObjNear);
    const dragoon::Rect vp = viewport_of(cobj);
    l.viewport[0] = vp.x0;
    l.viewport[1] = vp.x1;
    l.viewport[2] = vp.y0;
    l.viewport[3] = vp.y1;
    for (int i = 0; i < 4; i++) l.proj[i] = f32_at(cobj + kCObjProjection + 4 * i);
    for (int i = 0; i < 12; i++) l.view[i] = f32_at(cobj + kCObjViewMtx + 4 * i);
    return l;
}

// Where a joint sits in the world: a root's own translation, which the game has set by the
// time it draws, or the translation of a child's matrix.
void joint_origin(uint32_t jobj, float p[3]) {
    const bool root = mem_r32(jobj + kJObjParent) == 0;
    for (int i = 0; i < 3; i++)
        p[i] = root ? f32_at(jobj + kJObjTranslate + 4 * i) : f32_at(jobj + kJObjMtx + 16 * i + 12);
}

// Where a joint drew its shapes last, its matrix's translation, or false for a matrix the game
// hasn't made yet.
bool joint_last_place(uint32_t jobj, float p[3]) {
    float m[12];
    for (int i = 0; i < 12; i++) m[i] = f32_at(jobj + kJObjMtx + 4 * i);
    for (int r = 0; r < 3; r++) p[r] = m[4 * r + 3];
    return dragoon::matrix_made(m);
}

// The marks the joints of the tree at `jobj` that draw shapes call for, from where each drew
// them last, depth first and at most kMaxJoints. HSD_JObjDispAll draws a joint's shapes when it
// has some and isn't hidden, particles and splines being something else, then its children's.
constexpr uint32_t kJObjNext = 0x08, kJObjChild = 0x10, kJObjFlags = 0x14, kJObjShapes = 0x18;
constexpr uint32_t kHidden = 1u << 4, kNotShapes = (1u << 5) | (1u << 14);
constexpr size_t kMaxJoints = 256;
constexpr int kMaxDepth = 32;

void joint_marks(uint32_t jobj, const dragoon::Lens& lens, const std::vector<dragoon::Rect>& views,
                 std::vector<dragoon::Mark>& out, int depth) {
    if (!in_ram(jobj) || depth > kMaxDepth || out.size() >= kMaxJoints) return;
    const uint32_t flags = mem_r32(jobj + kJObjFlags);
    float p[3], x, y;
    if (!(flags & (kHidden | kNotShapes)) && mem_r32(jobj + kJObjShapes) != 0 &&
        joint_last_place(jobj, p) && dragoon::to_screen(lens, p, &x, &y))
        out.push_back(dragoon::edge_mark(x, y, views));
    for (uint32_t c = mem_r32(jobj + kJObjChild); in_ram(c) && out.size() < kMaxJoints; c = mem_r32(c + kJObjNext))
        joint_marks(c, lens, views, out, depth + 1);
}

void send(const dragoon::Mark& m) {
    if (m == g_sent) return;
    g_sent = m;
    dragoon::mark_anchor(m.a, m.x0, m.x1);
}

// A HUD callback displays the joint tree at `jobj`. An Edge element goes by where most of its
// joints drew their shapes last frame, or by its root's place when none has drawn yet. An Own
// element is centered on its root, which the game has just put over what it follows.
void place_tree(uint32_t jobj) {
    const uint32_t cobj = mem_r32(kCObjCurrent);
    if (!in_ram(cobj) || !in_ram(jobj)) return;
    const dragoon::Lens lens = lens_of(cobj);
    const std::vector<dragoon::Rect>& views = g_views.at(this_frame());
    static std::vector<dragoon::Mark> marks;
    marks.clear();
    if (g_hud.placement() == Placement::Edge) joint_marks(jobj, lens, views, marks, 0);
    dragoon::Mark m = dragoon::most_called(marks);
    if (marks.empty()) {
        float p[3], x, y;
        joint_origin(jobj, p);
        if (!dragoon::to_screen(lens, p, &x, &y)) return;
        m = dragoon::mark_for(g_hud.placement(), x, y, views);
    }
    g_hud.set_mark(m);
    send(m);
}

}  // namespace

// GObj_SetTextureCamera, about to call an object's render callback.
extern "C" void dragoon_hud_enter(uint32_t cb) {
    g_hud.enter(placement_of(cb));
    send(g_hud.mark());
}

// GObj_SetTextureCamera, as the render callback returns.
extern "C" void dragoon_hud_leave(void) {
    g_hud.leave();
    send(g_hud.mark());
}

// HSD_JObjDispAll(jobj in r3, ...) displays a joint and its children, calling itself for each
// child. The outermost call within a HUD callback places the tree.
extern "C" void hle_HSD_JObjDispAll(CPU* c) {
    if (g_displaying == 0 && g_hud.placement() != Placement::Stretch) place_tree(c->r[3]);
    g_displaying++;
    orig_HSD_JObjDispAll(c);
    g_displaying--;
}

// HSD_CObjSetAspect for a world camera, from src/cameras.cpp: its viewport is one of the
// frame's views.
void dragoon::hud_world_view(uint32_t cam) {
    if (in_ram(cam)) g_views.add(this_frame(), viewport_of(cam));
}
