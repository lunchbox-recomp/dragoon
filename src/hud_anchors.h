// HUD anchors' pure parts: where a HUD element sits on screen and the anchor that keeps it there
// at a wider output (docs/dev/widescreen.md). src/hud_anchors.cpp reads the guest and marks the
// draws with these.
//
// The game draws its HUD through cameras that keep the 4:3 shape, and the picture is stretched
// to the output, so a HUD element widens with the world. Anchoring it squeezes it back toward an
// edge of a rect, which keeps its 4:3 shape at its 4:3 distance from that edge (gx/anchor.h).
// One render callback draws elements at both sides of the screen, so an element's anchor comes
// from where it sits, not from the callback alone.
#pragma once
#include "census.h"
#include "gx/anchor.h"
#include <cmath>
#include <cstdint>
#include <optional>
#include <vector>

namespace dragoon {

// How a HUD render callback's elements are placed at a wider output. Stretch leaves them to
// widen with the world. Edge anchors each element to the edge of its rect nearest it, and Own
// centers each on its own position, for markers that follow something in the world.
enum class Placement : uint8_t { Stretch, Edge, Own };

// A rect in the game's 640 by 480: left, right, top and bottom.
struct Rect {
    float x0 = 0.0f, x1 = 0.0f, y0 = 0.0f, y1 = 0.0f;
    bool holds(float x, float y) const { return x >= x0 && x <= x1 && y >= y0 && y <= y1; }
    float area() const { return (x1 - x0) * (y1 - y0); }
    bool operator==(const Rect& o) const { return x0 == o.x0 && x1 == o.x1 && y0 == o.y0 && y1 == o.y1; }
};
constexpr Rect kScreen{0.0f, 640.0f, 0.0f, 480.0f};

// An anchor and its rect, as gx::set_draw_anchor takes them. Stretch has a zero rect.
struct Mark {
    gx::Anchor a = gx::Anchor::Stretch;
    float x0 = 0.0f, x1 = 0.0f;
    bool operator==(const Mark& o) const { return a == o.a && x0 == o.x0 && x1 == o.x1; }
    bool operator!=(const Mark& o) const { return !(*this == o); }
};

// The edge of `r` an element at x is anchored to: left in its left third, right in its right
// third and the middle between.
inline gx::Anchor nearest_edge(float x, const Rect& r) {
    const float third = (r.x1 - r.x0) / 3.0f;
    if (x < r.x0 + third) return gx::Anchor::Left;
    if (x > r.x1 - third) return gx::Anchor::Right;
    return gx::Anchor::Center;
}

// How far past its lines an element's last edge still holds, in thirds of the rect.
constexpr float kHeldBand = 0.25f;

// The edge of `r` an element at x is anchored to when it had edge `held` of r the frame
// before: that edge's part of the rect reaches a quarter of a third past each of its lines.
// So an element moving a little across a line keeps its edge, and one sitting well past it
// takes the other. Stretch holds nothing.
inline gx::Anchor nearest_edge(float x, const Rect& r, gx::Anchor held) {
    const float third = (r.x1 - r.x0) / 3.0f, band = kHeldBand * third;
    const float left = r.x0 + third, right = r.x1 - third;
    switch (held) {
    case gx::Anchor::Left:
        if (x < left + band) return held;
        break;
    case gx::Anchor::Center:
        if (x >= left - band && x <= right + band) return held;
        break;
    case gx::Anchor::Right:
        if (x > right - band) return held;
        break;
    default: break;
    }
    return nearest_edge(x, r);
}

// The smallest of `views` holding the point, or null when none does.
inline const Rect* view_holding(float x, float y, const std::vector<Rect>& views) {
    const Rect* best = nullptr;
    for (const Rect& v : views)
        if (v.holds(x, y) && (!best || v.area() < best->area())) best = &v;
    return best;
}

// An Edge element's mark from its position on screen and the world's views, a split view's
// HUD sitting in its player's view. One in a view anchors to that view's edges. One outside
// every view sits on the bars between them and belongs to the screen, as the 4-player clock
// does, except in the middle third: there it's the bars themselves, which span the screen and
// stretch with it. An element whose mark was `last` the frame before holds last's edge in
// last's rect, as nearest_edge says.
inline Mark edge_mark(float x, float y, const std::vector<Rect>& views, const Mark& last = {}) {
    const auto edge = [&](const Rect& r) {
        return last.x0 == r.x0 && last.x1 == r.x1 ? nearest_edge(x, r, last.a) : nearest_edge(x, r);
    };
    if (const Rect* v = view_holding(x, y, views)) return {edge(*v), v->x0, v->x1};
    const gx::Anchor a = edge(kScreen);
    if (a == gx::Anchor::Center && !views.empty()) return {};
    return {a, kScreen.x0, kScreen.x1};
}

// An Own element's mark: centered on its own position, a rect of no width there.
inline Mark own_mark(float x) { return {gx::Anchor::Center, x, x}; }

inline Mark mark_for(Placement p, float x, float y, const std::vector<Rect>& views) {
    switch (p) {
    case Placement::Edge: return edge_mark(x, y, views);
    case Placement::Own: return own_mark(x);
    case Placement::Stretch: break;
    }
    return {};
}

// The mark most of an element's joints call for, or Stretch for none. A tie goes to `held`, the
// element's mark from the frame before, when it's one of those tied, and else to the first. A
// joint's own place can sit at the middle of the screen while its shapes are drawn at a side, so
// an element goes by its joints together.
inline Mark most_called(const std::vector<Mark>& marks, const std::optional<Mark>& held = std::nullopt) {
    Mark best;
    size_t best_n = 0;
    for (size_t i = 0; i < marks.size(); i++) {
        size_t n = 0;
        for (const Mark& m : marks) n += m == marks[i];
        if (n > best_n || (n == best_n && marks[i] == held)) {
            best = marks[i];
            best_n = n;
        }
    }
    return best;
}

// A point on screen, in the game's 640 by 480.
struct Point {
    float x = 0.0f, y = 0.0f;
    bool operator==(const Point& o) const { return x == o.x && y == o.y; }
};

// How many frames in a row a tree's joints sit in the same place before it has rested there.
constexpr uint32_t kRestFrames = 30;

// The marks Edge trees had the frame before, which their joints near a third's line keep
// calling for (edge_mark). Without them an element moving 2 pixels across a line would jump to
// another edge, as would a tree whose joints straddle a line in near-equal numbers when one of
// them hides. Once a tree has rested, its joints' mean place the same for kRestFrames frames in
// a row, it holds nothing: its joints call for their nearest edges and a tie goes to the first
// of those tied. So one that stopped inside the band moves to its edge then rather than when it
// next misses a frame, and one that first showed in the middle doesn't keep the middle through
// a tie at a side, as the race's speedometer frame would at 4200. A tree that misses a frame
// chooses afresh when it shows. A tree whose joints have no place yet has nothing to keep, so it
// chooses from them once they have one. Trees are told apart by their root, and a root shown
// more than once in a frame by which time it is.
class KeptMarks {
public:
    // The mark of the tree at `root`, shown in `frame` with its joints at `joints` on screen
    // among `views`: the one most of them call for, holding the tree's mark from the frame
    // before until the tree has rested. With no joint placed, the mark from the frame before,
    // or none.
    std::optional<Mark> place(uint32_t frame, uint32_t root, const std::vector<Point>& joints,
                              const std::vector<Rect>& views) {
        if (frame != frame_) {
            if (frame == frame_ + 1)
                last_.swap(now_);
            else
                last_.clear();
            now_.clear();
            frame_ = frame;
        }
        Kept k{root, 0, std::nullopt, {}, 0};
        for (const Kept& n : now_) k.time += n.root == root;
        const Kept* before = nullptr;
        for (const Kept& l : last_)
            if (l.root == root && l.time == k.time) before = &l;
        if (before) k.mark = before->mark;
        if (!joints.empty()) {
            for (const Point& p : joints) {
                k.at.x += p.x / joints.size();
                k.at.y += p.y / joints.size();
            }
            k.still = before && before->at == k.at ? before->still + 1 : 1;
            const std::optional<Mark> held = k.still < kRestFrames ? k.mark : std::nullopt;
            marks_.clear();
            for (const Point& p : joints) marks_.push_back(edge_mark(p.x, p.y, views, held.value_or(Mark{})));
            k.mark = most_called(marks_, held);
        }
        now_.push_back(k);
        return k.mark;
    }

private:
    struct Kept {
        uint32_t root;
        uint32_t time;  // which time in its frame the root showed, from 0
        std::optional<Mark> mark;
        Point at;        // its joints' mean place, when it had any
        uint32_t still;  // how many frames in a row, to this one, its joints were at `at`, or 0
    };
    uint32_t frame_ = 0;
    std::vector<Kept> last_, now_;  // the trees shown in the frame before and in this one
    std::vector<Mark> marks_;       // the marks the joints call for
};

// Whether a joint's matrix, three rows of four, has been made: the game leaves a new joint's
// all zero until it first draws it, so one with nothing in its 3 by 3 part has no place yet.
inline bool matrix_made(const float m[12]) {
    for (int r = 0; r < 3; r++)
        for (int k = 0; k < 3; k++)
            if (m[4 * r + k] != 0.0f) return true;
    return false;
}

// What a camera puts a point through, read from an HSD_CObj: its projection type (census.h's
// kPerspective, kFrustum or kOrtho), the projection's four values (fov in degrees and aspect,
// or top, bottom, left and right), its near plane, its viewport (left, right, top, bottom) and
// its viewing matrix, three rows of four.
struct Lens {
    uint8_t type = 0;
    float proj[4] = {};
    float near = 0.0f;
    float viewport[4] = {};
    float view[12] = {};
};

// Where a camera puts the point v, already in its view space, on screen, as GX does: the
// projection sysdolphin builds from the camera (C_MTXPerspective, C_MTXFrustum, C_MTXOrtho),
// then the viewport. False for a point at or behind the eye, or a camera of no known
// projection.
inline bool view_to_screen(const Lens& l, const float v[3], float* sx, float* sy) {
    float nx, ny;
    switch (l.type) {
    case kPerspective: {
        if (!(v[2] < 0.0f) || !(l.proj[1] > 0.0f)) return false;
        const float cot = 1.0f / std::tan(l.proj[0] * 0.5f * 3.14159265f / 180.0f);
        nx = cot / l.proj[1] * v[0] / -v[2];
        ny = cot * v[1] / -v[2];
        break;
    }
    case kFrustum: {
        const float t = l.proj[0], b = l.proj[1], lf = l.proj[2], rt = l.proj[3];
        if (!(v[2] < 0.0f) || rt == lf || t == b) return false;
        nx = (2.0f * l.near / (rt - lf) * v[0] + (rt + lf) / (rt - lf) * v[2]) / -v[2];
        ny = (2.0f * l.near / (t - b) * v[1] + (t + b) / (t - b) * v[2]) / -v[2];
        break;
    }
    case kOrtho: {
        const float t = l.proj[0], b = l.proj[1], lf = l.proj[2], rt = l.proj[3];
        if (rt == lf || t == b) return false;
        nx = 2.0f / (rt - lf) * v[0] - (rt + lf) / (rt - lf);
        ny = 2.0f / (t - b) * v[1] - (t + b) / (t - b);
        break;
    }
    default: return false;
    }
    *sx = l.viewport[0] + (nx + 1.0f) * 0.5f * (l.viewport[1] - l.viewport[0]);
    *sy = l.viewport[2] + (1.0f - ny) * 0.5f * (l.viewport[3] - l.viewport[2]);
    return std::isfinite(*sx) && std::isfinite(*sy);
}

// Where a camera puts the point p of the world on screen: its viewing matrix, then
// view_to_screen.
inline bool to_screen(const Lens& l, const float p[3], float* sx, float* sy) {
    float v[3];
    for (int r = 0; r < 3; r++)
        v[r] = l.view[4 * r] * p[0] + l.view[4 * r + 1] * p[1] + l.view[4 * r + 2] * p[2] + l.view[4 * r + 3];
    return view_to_screen(l, v, sx, sy);
}

// The world's views, the viewports of the world cameras the game set up in the latest frame
// that set any. A frame's HUD reads those of its own frame, or of the one before when the game
// hasn't set its cameras yet. Older ones are gone, so a menu after a race has none.
class WorldViews {
public:
    void add(uint32_t frame, const Rect& r) {
        if (frame != frame_) {
            views_.clear();
            frame_ = frame;
        }
        for (const Rect& v : views_)
            if (v == r) return;
        views_.push_back(r);
    }
    const std::vector<Rect>& at(uint32_t frame) const {
        static const std::vector<Rect> kNone;
        return frame == frame_ || frame == frame_ + 1 ? views_ : kNone;
    }

private:
    uint32_t frame_ = 0;
    std::vector<Rect> views_;
};

// The HUD callbacks being drawn, nested as render callbacks can be, each with its placement and
// the mark its draws carry. Outside every callback nothing is placed and the mark is Stretch.
class HudCallbacks {
public:
    // A callback is called. Its draws are unmarked until it displays something.
    void enter(Placement p) {
        outer_.push_back(top_);
        top_ = {p, {}};
    }
    // It returns, and its caller's mark is back.
    void leave() {
        top_ = {};
        if (!outer_.empty()) {
            top_ = outer_.back();
            outer_.pop_back();
        }
    }
    Placement placement() const { return top_.placement; }
    const Mark& mark() const { return top_.mark; }
    void set_mark(const Mark& m) { top_.mark = m; }
    // HSD_JObjDispAll is called, as it is again for each child. True for the outermost call in
    // a placed callback, whose joint tree the hook places.
    bool tree_begin() { return trees_++ == 0 && top_.placement != Placement::Stretch; }
    // It returns. After the outermost call the callback's own mark, Stretch, is back for what
    // it draws itself, as a callback outside the table draws.
    void tree_end() {
        if (--trees_ == 0) top_.mark = {};
    }

private:
    struct Level {
        Placement placement = Placement::Stretch;
        Mark mark;
    };
    std::vector<Level> outer_;
    Level top_;
    uint32_t trees_ = 0;  // HSD_JObjDispAll calls under way
};

// Notes a world camera the game has set the aspect of, whose viewport is one of the frame's
// views (src/hud_anchors.cpp).
void hud_world_view(uint32_t cam);

}  // namespace dragoon
