// Tags and anchors set after every draw the game has written (src/draw_marks.h).
#include "draw_marks.h"
#include "gx/render.h"
#include "runtime.h"

// gcn-recomp/runtime/gx/fifo.cpp: the bytes waiting in the write-gather pipe.
uint32_t gp_pending();

namespace {

// Finishes the pipe's line with no-ops, so the draw it ends goes out now.
void send_pending() {
    for (uint32_t n = dragoon::padding_for(gp_pending()); n > 0; n--) gp_write8(0);
}

}  // namespace

void dragoon::mark_tag(uint8_t tag) {
    send_pending();
    gx::set_draw_tag(tag);
}

void dragoon::mark_anchor(gx::Anchor a, float x0, float x1) {
    send_pending();
    gx::set_draw_anchor(a, x0, x1);
}
