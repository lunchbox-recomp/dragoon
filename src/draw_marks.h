// Marks on the game's draws (gx::set_draw_tag, gx::set_draw_anchor) that land after every draw
// the game has written so far. A mark takes its place where the front end has got to in the
// command stream, and the last 31 bytes or less of what the game wrote can still wait in the
// write-gather pipe, so the draw they end would take the next mark. Each mark here first pads
// the pipe to the end of its line with zero bytes, the GPU's no-op, as the SDK's GXFlush does,
// and the line goes out ahead of the mark. src/draw_marks.cpp sets them.
#pragma once
#include "gx/anchor.h"
#include <cstdint>

namespace dragoon {

// The pipe sends 32 bytes at a time.
constexpr uint32_t kPipeLine = 32;

// The zero bytes that finish the pipe's line when `pending` bytes wait in it, none when it's
// empty.
inline uint32_t padding_for(uint32_t pending) {
    const uint32_t used = pending % kPipeLine;
    return used == 0 ? 0 : kPipeLine - used;
}

void mark_tag(uint8_t tag);
void mark_anchor(gx::Anchor a, float x0, float x1);

}  // namespace dragoon
