// The camera census's pure parts: the line logged for a camera and the render callback that
// draws through it, which of a frame's lines are new and the tag each callback's draws carry.
// src/census.cpp reads the cameras out of the guest and calls these. tools/drawlog.py reads
// the lines.
#pragma once
#include <cstdint>
#include <cstdio>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace dragoon {

// An HSD_CObj's projection type, as sysdolphin numbers them.
enum : uint8_t { kPerspective = 1, kFrustum = 2, kOrtho = 3 };

// What the census reads of a camera. A perspective camera's projection is its field of view
// in degrees and its stored aspect. A frustum or orthographic camera's is its top, bottom,
// left and right. The viewport is left, right, top and bottom in the game's 640 by 480.
struct Camera {
    uint8_t type = 0;
    float proj[4] = {};
    float viewport[4] = {};
};

inline const char* projection_name(uint8_t type) {
    switch (type) {
    case kPerspective: return "persp";
    case kFrustum: return "frustum";
    case kOrtho: return "ortho";
    default: return "none";
    }
}

// One line, such as
//   [census] f=4200 cam=8123A0C0 type=persp p=30,1.2554 vp=0,640,0,480 cb=800F1234 cls=12 via=draw
// f is the frame being drawn, one more than the frames the game had submitted, which is the
// number its frame dump and GCN_DRAWLOG give it in a probe.sh run. cam is the camera's guest
// address, cb the render callback and cls the classifier of the object it draws. via says
// which hook saw the pair: "draw" when GObj_SetTextureCamera calls the callback with this
// camera current, "set" when the callback sets the camera itself.
inline std::string census_line(uint32_t frame, uint32_t cam, const Camera& c, uint32_t cb,
                               uint32_t cls, const char* via) {
    char p[96];
    if (c.type == kPerspective)
        snprintf(p, sizeof(p), "%.6g,%.6g", c.proj[0], c.proj[1]);
    else if (c.type == kFrustum || c.type == kOrtho)
        snprintf(p, sizeof(p), "%.6g,%.6g,%.6g,%.6g", c.proj[0], c.proj[1], c.proj[2], c.proj[3]);
    else
        p[0] = '\0';
    char line[256];
    snprintf(line, sizeof(line),
             "[census] f=%u cam=%08X type=%s p=%s vp=%.6g,%.6g,%.6g,%.6g cb=%08X cls=%u via=%s",
             frame, cam, projection_name(c.type), p, c.viewport[0], c.viewport[1], c.viewport[2],
             c.viewport[3], cb, cls, via);
    return line;
}

// One line for a call to HSD_CObjSetAspect, or to HSD_CObjLoadDesc for a perspective camera,
// such as
//   [aspect] f=4200 cam=8123A0C0 lr=800C2884 lr2=800C1F00 given=1.25538 stored=1.67383
// lr is where the call returns to and lr2 where its caller returns to, so a call the camera
// library makes for someone else names them too. given is the aspect the caller passed, or
// the one the camera was loaded with, and stored the aspect the camera holds once the call is
// done, which src/cameras.cpp may have widened. A camera that isn't a perspective one holds
// no aspect, so its stored is "none".
inline std::string aspect_line(uint32_t frame, uint32_t cam, uint32_t lr, uint32_t lr2, float given,
                               const Camera& c) {
    char stored[32] = "none";
    if (c.type == kPerspective) snprintf(stored, sizeof(stored), "%.6g", c.proj[1]);
    char line[128];
    snprintf(line, sizeof(line), "[aspect] f=%u cam=%08X lr=%08X lr2=%08X given=%.6g stored=%s", frame,
             cam, lr, lr2, given, stored);
    return line;
}

// One line for a camera the game releases, such as
//   [release] f=13063 cam=814338E0
inline std::string release_line(uint32_t frame, uint32_t cam) {
    char line[48];
    snprintf(line, sizeof(line), "[release] f=%u cam=%08X", frame, cam);
    return line;
}

// Logs a call to HSD_CObjSetAspect as an aspect_line, with DRAGOON_CENSUS=1 (src/census.cpp).
void census_aspect(uint32_t cam, uint32_t lr, uint32_t lr2, float given);

// One line for the game forgetting the memory its cameras were in, such as
//   [amnesia] f=13063
inline std::string amnesia_line(uint32_t frame) {
    char line[32];
    snprintf(line, sizeof(line), "[amnesia] f=%u", frame);
    return line;
}

// Logs a camera's release as a release_line, with DRAGOON_CENSUS=1 (src/census.cpp).
void census_release(uint32_t cam);

// Logs the camera class's amnesia as an amnesia_line, with DRAGOON_CENSUS=1 (src/census.cpp).
void census_amnesia();

// One line for a render callback's draw tag, such as
//   [cbtag] f=4200 n=3 cb=8011F8F4
// n is the tag the draw log shows on the callback's draws (gx::set_draw_tag). It's logged once,
// in the frame the callback is first called.
inline std::string tag_line(uint32_t frame, uint8_t tag, uint32_t cb) {
    char line[48];
    snprintf(line, sizeof(line), "[cbtag] f=%u n=%u cb=%08X", frame, tag, cb);
    return line;
}

// A draw tag for each render callback, so the draw log says which callback made each draw. The
// tags are given out from 1 in the order the callbacks are first called, and after 255 a
// callback gets none. A callback can draw a camera's objects through GObj_SetTextureCamera
// itself, so the tag of the callback that called it is kept and given back as it returns.
class CallbackTags {
public:
    static constexpr uint8_t kNone = 0;

    // The tag for `cb` as it's called. `*fresh` is set when it's the callback's first.
    uint8_t enter(uint32_t cb, bool* fresh) {
        outer_.push_back(current_);
        auto it = tags_.find(cb);
        *fresh = it == tags_.end() && tags_.size() < 255;
        if (*fresh) it = tags_.emplace(cb, (uint8_t)(tags_.size() + 1)).first;
        current_ = it == tags_.end() ? kNone : it->second;
        return current_;
    }

    // The tag of the callback that called the one returning, or kNone.
    uint8_t leave() {
        current_ = kNone;
        if (!outer_.empty()) {
            current_ = outer_.back();
            outer_.pop_back();
        }
        return current_;
    }

private:
    std::unordered_map<uint32_t, uint8_t> tags_;
    std::vector<uint8_t> outer_;
    uint8_t current_ = kNone;
};

// Lets each distinct line through once a frame.
class OncePerFrame {
public:
    bool first(uint32_t frame, const std::string& line) {
        if (frame != frame_) {
            frame_ = frame;
            seen_.clear();
        }
        return seen_.insert(line).second;
    }

private:
    uint32_t frame_ = UINT32_MAX;
    std::unordered_set<std::string> seen_;
};

}  // namespace dragoon
