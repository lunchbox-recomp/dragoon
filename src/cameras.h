// Which cameras widen at a wider output and by how much, the pure part. src/cameras.cpp
// applies it.
#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace dragoon {

// The console's own shape, which the game sets every camera up for.
constexpr float kConsoleAspect = 4.0f / 3.0f;

// Whether a call to HSD_CObjSetAspect is the camera library setting up a world camera, from
// where it returns to and where its caller returns to.
//
// Each camera is first set up through the camera library, whose calls set up the HUD, minimap
// and menu cameras too. Those calls are a world camera's when the library was called from one
// of four places. kar_lbcamera_load_desc_update_aspect returns to 0x80066E4C, called from
// kar_camera__800b3944 (0x800B3990). The viewport presets for one, two and four views return
// to 0x80066ECC, 0x80066FF0 and 0x80067148, called from kar_grlib2__near_800babd0 (0x800BAC38),
// kar_grlib2__near_800bac5c (0x800BACD0) and kar_grlib2__near_800bacf4 (0x800BAD68). The race's
// cameras after the finish line get their aspect from these alone.
inline bool sets_up_world_camera(uint32_t return_address, uint32_t callers_return_address) {
    switch (return_address) {
    case 0x80066E4C: return callers_return_address == 0x800B3990;
    case 0x80066ECC: return callers_return_address == 0x800BAC38;
    case 0x80066FF0: return callers_return_address == 0x800BACD0;
    case 0x80067148: return callers_return_address == 0x800BAD68;
    default: return false;
    }
}

// Whether a call to HSD_CObjSetAspect sets a world camera's aspect. During play the camera
// module sets the world cameras' aspect every frame through two calls, which return to
// 0x800C2884 in kar_cmreplay__near_800c24e8 and to 0x800C9820 in kar_cmreplay__near_800c9790.
// The library's calls that set one up count too.
inline bool sets_world_aspect(uint32_t return_address, uint32_t callers_return_address) {
    return return_address == 0x800C2884 || return_address == 0x800C9820 ||
           sets_up_world_camera(return_address, callers_return_address);
}

// Whether a call to HSD_CObjLoadDesc loads a world camera, from where it returns to and where
// its caller returns to. Top Ride's world camera takes its aspect from its description and
// never goes through HSD_CObjSetAspect. kar_a2d_kurakko__near_80371968 loads it, its call
// returning to 0x803719A0, when TopRide_GameSessionInit calls it (returning to 0x8028C0E0).
// The HUD's and menus' cameras are loaded from elsewhere.
inline bool loads_world_camera(uint32_t return_address, uint32_t callers_return_address) {
    return return_address == 0x803719A0 && callers_return_address == 0x8028C0E0;
}

// The factor a world camera's aspect is widened by at output aspect `output`: the output aspect
// over 4:3. It's 1 at 4:3, to the bit, and at an output of no width, such as a window shrunk
// to nothing under --aspect=window.
inline float widening(float output) { return output > 0.0f ? output / kConsoleAspect : 1.0f; }

// A world camera's aspect at output aspect `output`, its 4:3 aspect times the widening.
inline float widened_aspect(float aspect, float output) { return aspect * widening(output); }

// The world cameras widened once, as they're set up or loaded, which the game doesn't set
// again each frame. Each is kept with its 4:3 aspect and the factor it was widened by. When the
// output aspect changes, a camera that still holds the aspect it was given here is widened
// again for the new output. One holding anything else has been set again since, so it's left
// alone and forgotten.
//
// The game frees a camera by releasing it within a scene, or at a change of scene by forgetting
// the memory all its objects were in. Neither changes the camera's memory, so a camera made
// later at its address holding the same aspect would pass for the kept one. src/cameras.cpp
// forgets a camera as it's released, and every camera as their memory is forgotten. At most
// kMaxKept are kept, the oldest forgotten first, so the list can't grow without end.
//
// read(cam) gives a camera's stored aspect, or NaN when it isn't a perspective camera in RAM.
// write(cam, aspect) stores one.
class SetOnceCameras {
public:
    static constexpr size_t kMaxKept = 32;

    // Keeps `cam`, widened from `aspect` at output aspect `output` and holding that now. Forgets
    // its older entry, every camera that no longer holds what it was given and, at kMaxKept,
    // the oldest.
    template <class Read>
    void add(uint32_t cam, float aspect, float output, Read read) {
        std::erase_if(kept_, [&](const Kept& k) { return k.cam == cam || !holds_its_own(k, read); });
        if (kept_.size() == kMaxKept) kept_.erase(kept_.begin());
        kept_.push_back({cam, aspect, widening(output)});
    }

    // Forgets `cam`, which the game is releasing.
    void forget(uint32_t cam) {
        std::erase_if(kept_, [&](const Kept& k) { return k.cam == cam; });
    }

    // Forgets every camera, when the game forgets the memory they're in.
    void forget_all() { kept_.clear(); }

    // At output aspect `output`, widens each camera kept at another factor again, when it still
    // holds what it was given, and forgets the rest of those.
    template <class Read, class Write>
    void follow(float output, Read read, Write write) {
        const float factor = widening(output);
        std::erase_if(kept_, [&](Kept& k) {
            if (k.factor == factor) return false;
            if (!holds_its_own(k, read)) return true;
            k.factor = factor;
            write(k.cam, k.aspect * factor);
            return false;
        });
    }

    size_t size() const { return kept_.size(); }

private:
    struct Kept {
        uint32_t cam;
        float aspect;  // its 4:3 aspect
        float factor;  // the widening it was given
    };

    template <class Read>
    static bool holds_its_own(const Kept& k, Read read) {
        return read(k.cam) == k.aspect * k.factor;
    }

    std::vector<Kept> kept_;
};

}  // namespace dragoon
