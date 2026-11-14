// What the engine writes and sizes for the launcher's Settings fixtures, built by
// settings_fixtures.py against gcn-recomp's runtime/settings.cpp, runtime/platform.cpp and
// runtime/gx/aspect.h. It reads one command a line from stdin and prints one line for each:
//
//   save ASPECT FULLSCREEN SCALE DISC SOUNDS PATH   settings_save over PATH: "saved" or "failed"
//   window ASPECT USABLE_W USABLE_H                 the window main.cpp opens: "W H"
//   fit ASPECT DISPLAY_W DISPLAY_H                  the fullscreen picture: "X Y W H"
//   scale N                                         the picture the renderer draws at N: "W H"
//
// A usable area of 0 by 0 is none, as SDL gives where it can't say. The window's and the
// output aspect's choices are main.cpp's, and the 640, the fit and the scale's cap are the
// renderer's, copied since they can't be included; settings_fixtures.py checks the engine still
// holds each line they come from (its COPIED).
#include "gx/aspect.h"
#include "gx/render_gl.h"
#include "settings.h"
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>

namespace {

// The shape main.cpp opens the window at: the aspect's, or 4:3 for "window".
void shape(const std::string& aspect, int& w, int& h) {
    w = 4;
    h = 3;
    if (aspect != "window") gx::parse_aspect(aspect.c_str(), &w, &h);
}

// main.cpp's window: aspect_window_size with no limit where SDL gives no usable area, and
// aspect_window_rect with a kTitleBar of 40 where it does, as on macOS, whose SDL can't say
// the frame's size before the window shows.
gx::WindowSize window(const std::string& aspect, int usable_w, int usable_h) {
    int w, h;
    shape(aspect, w, h);
    if (usable_w <= 0 || usable_h <= 0) return gx::aspect_window_size(960, w, h, 0, 0);
    const gx::OutputRect r = gx::aspect_window_rect(960, w, h, {0, 0, usable_w, usable_h}, 40, 0, 0, 0);
    return {r.w, r.h};
}

// The picture on a fullscreen display: fit to the aspect, or to the display's own shape for
// "window", which main.cpp sets as the output aspect from the drawable's size.
gx::OutputRect fit(const std::string& aspect, int display_w, int display_h) {
    float ratio = 0;
    settings_parse_aspect(aspect, ratio);
    if (ratio == 0.0f) ratio = (float)display_w / (float)display_h;
    return gx::fit_aspect(display_w, display_h, ratio);
}

}  // namespace

int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        std::string command, aspect;
        in >> command;
        if (command == "save") {
            Settings s;
            int fullscreen;
            std::string disc, sounds, path;
            in >> s.aspect >> fullscreen >> s.scale >> disc >> sounds;
            std::getline(in >> std::ws, path);
            s.fullscreen = fullscreen == 1;
            s.fast_disc = disc == "fast";
            s.menu_sounds = sounds == "on";
            printf("%s\n", settings_save(path, s) ? "saved" : "failed");
        } else if (command == "window") {
            int w, h;
            in >> aspect >> w >> h;
            const gx::WindowSize size = window(aspect, w, h);
            printf("%d %d\n", size.w, size.h);
        } else if (command == "fit") {
            int w, h;
            in >> aspect >> w >> h;
            const gx::OutputRect r = fit(aspect, w, h);
            printf("%d %d %d %d\n", r.x, r.y, r.w, r.h);
        } else if (command == "scale") {
            int n;
            in >> n;
            const int capped = n > gx::kMaxInternalScale ? gx::kMaxInternalScale : n;
            printf("%d %d\n", 640 * capped, 480 * capped);
        } else {
            fprintf(stderr, "settings_fixtures: unknown command \"%s\"\n", line.c_str());
            return 2;
        }
        fflush(stdout);
    }
    return 0;
}
