// Guest memory for src/'s hooks, read and written only where it's RAM.
#pragma once
#include "runtime.h"
#include <cstdint>
#include <cstring>

namespace dragoon {

inline bool in_ram(uint32_t a) { return a >= 0x80000000u && a - 0x80000000u < RAM_SIZE; }

inline float f32_at(uint32_t a) {
    const uint32_t u = mem_r32(a);
    float f;
    memcpy(&f, &u, sizeof(f));
    return f;
}

inline void set_f32(uint32_t a, float f) {
    uint32_t u;
    memcpy(&u, &f, sizeof(u));
    mem_w32(a, u);
}

}  // namespace dragoon
