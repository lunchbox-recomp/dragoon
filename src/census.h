// The camera census's pure parts: the line logged for a camera and the render callback that
// draws through it, and which of a frame's lines are new. src/census.cpp reads the cameras
// out of the guest and calls these. tools/drawlog.py reads the lines.
#pragma once
#include <cstdint>
#include <cstdio>
#include <string>
#include <unordered_set>

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
