// The overlay's Mods page (docs/dev/mods.md), in the desktop game, which defines GCN_OVERLAY.
// It lists each package's options with their choices and Off, and a failed package shows off
// with its error. Apply and restart empties settings.txt's disc_overlay and ram_patches lines,
// then runs tools/mod_choices.py `set` for each change and then `apply`, on a thread of its own
// so the menu keeps drawing. Then it names apply's paths in those lines and restarts the game as
// the overlay's Restart game does (frontend.h). src/mods_page.h has the pure part, which decides
// what follows a run; this file has the ImGui and the threads.
//
// The page runs nothing until it's first shown. A result that comes in while the menu is
// closed is taken the next time the page draws, and then the game waits for Restart game.
#ifdef GCN_OVERLAY
#include "mods_page.h"
#include "frontend.h"
#include "hw/disc_overlay.h"
#include "input_log.h"
#include "overlay/overlay.h"
#include "platform.h"
#include "ram_patches.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <future>
#include <utility>
#include "imgui.h"

namespace {

using namespace dragoon;

const char* const kNoScript =
    "tools/mod_choices.py isn't in the folder the game started in. Start the game from the repository root.";
const char* const kNoPackages = "mods/riivolution holds no packages. Unzip a Riivolution release into mods/ and "
                                "restart the game.";
const char* const kLeftOff = "Some packages were left off, and the choices are saved for the next start. Press "
                             "Restart game to start with them.";
const char* const kSaved = "The mods are saved for the next start. Press Restart game to start with them.";
const char* const kApplyingOnScreen =
    "Applying the mods. If this page stays open until the mods are ready, the game restarts.";
const char* const kApplyingOffScreen = "Applying the mods. Once they're saved for the next start, press Restart game "
                                       "to start with them.";
const char* const kNotStarted = "The game started without these mods. Press Apply and restart to start with them.";
const char* const kNoModsYet = "The next start has no mods until Apply and restart works.";

enum class Phase {
    unread,       // not shown yet
    reading,      // `list` is running
    unreadable,   // `list` failed, with the error
    ready,        // the packages are shown, with the last Apply's error if it failed
    applying,     // `set` and `apply` are running
    restart_due,  // applied and saved, waiting for Restart game, with what was left off
};

struct ReadDone {
    bool ok = false;
    std::string error;
    std::vector<ModPackage> packages;
};

struct ApplyDone {
    int sets = 0;  // the `set`s that worked
    bool applied = false;
    std::string error;
    ModsApplied result;
};

struct Page {
    Phase phase = Phase::unread;
    std::vector<ModPackage> packages;
    std::vector<ModPackage> left_off;
    std::string error;
    bool apply_due = false;  // the next start runs none of the mods shown running, until an apply saves
    bool watched = false;    // the page has drawn every frame since the apply started
    int frame = -1;          // the menu frame and the time of the page's last draw
    long long ms = 0;
    std::future<ReadDone> reading;
    std::future<ApplyDone> applying;
};

ChildResult run(const std::vector<std::string>& argv, const std::vector<std::string>& env) {
    // Quit, Restart game, the game's reset and Ctrl-C end a script still running.
    static const bool hooked = (plat_at_exit([] { child_run_kill_running(); }), true);
    (void)hooked;
    return child_run(argv, env, kModsTimeoutMs);
}

ReadDone read_mods(std::vector<std::string> env) {
    ReadDone done;
    done.ok = mods_list_from(run(mods_list_argv(), env), done.packages, done.error);
    return done;
}

ApplyDone apply_mods(std::vector<std::vector<std::string>> sets, std::vector<std::string> env) {
    ApplyDone done;
    for (const auto& argv : sets) {
        if (!mods_set_from(run(argv, env), done.error)) return done;
        done.sets++;
    }
    done.applied = mods_apply_from(run(mods_apply_argv(), env), done.result, done.error);
    return done;
}

bool script_here() {
    std::error_code ignored;
    return std::filesystem::is_regular_file(kModsScript, ignored);
}

std::vector<std::string> env() { return mods_env(getenv("HOME"), getenv("TMPDIR")); }

void fail(Page& page, Phase phase, std::string error) {
    page.phase = phase;
    page.error = std::move(error);
    fprintf(stderr, "[mods] %s\n", page.error.c_str());
}

void start_read(Page& page) {
    if (!script_here()) return fail(page, Phase::unreadable, kNoScript);
    page.phase = Phase::reading;
    page.error.clear();
    page.reading = std::async(std::launch::async, read_mods, env());
}

// settings.txt names no output while `set` and `apply` run, since an apply cut short can remove
// a file it names. Since gcn-recomp ed82ff0 a start skips such a line rather than stopping on it,
// which settings.h gives this menu as the reason for. The lines are still emptied first, so a
// start after a cut-short apply loads nothing that apply left in mods/.out, and the page says the
// game started without these mods (docs/dev/mods.md). Both writes are on the draw thread, as the
// Display page's are.
void start_apply(Page& page) {
    if (!script_here()) return fail(page, Phase::ready, kNoScript);
    std::string error;
    if (!mods_save_settings("settings.txt", "", "", error)) return fail(page, Phase::ready, std::move(error));
    page.phase = Phase::applying;
    page.error.clear();
    page.watched = true;
    page.applying = std::async(std::launch::async, apply_mods, mods_set_argvs(page.packages), env());
}

template <typename T> bool done(std::future<T>& f) {
    return f.valid() && f.wait_for(std::chrono::seconds(0)) == std::future_status::ready;
}

// Takes a finished read or apply. An apply that worked names its paths in settings.txt, and
// mods_after_apply says what follows.
void take_results(Page& page) {
    if (page.phase == Phase::reading && done(page.reading)) {
        ReadDone read = page.reading.get();
        if (!read.ok) return fail(page, Phase::unreadable, std::move(read.error));
        page.packages = std::move(read.packages);
        page.apply_due = mods_due_at_start(page.packages, disc_overlay_loaded(), ram_patches_file());
        page.phase = Phase::ready;
    }
    if (page.phase == Phase::applying && done(page.applying)) {
        ApplyDone run = page.applying.get();
        ModsApplyEnd end;
        end.sets = run.sets;
        end.watched = page.watched;
        if (run.applied) {
            fprintf(stderr, "[mods] tools/mod_choices.py apply took %lld ms\n", run.result.ms);
            end.saved = mods_save_settings("settings.txt", run.result.overlay, run.result.ram_patches, run.error);
            end.left_off = std::move(run.result.left_off);
        }
        ModsAfterApply after = mods_after_apply(page.packages, page.apply_due, end);
        switch (after.next) {
        case ModsNext::restart:
            return frontend_restart();
        case ModsNext::restart_due:
            for (const ModPackage& p : after.left_off)
                fprintf(stderr, "[mods] %s was left off. %s\n", p.xml.c_str(), p.error.c_str());
            page.left_off = std::move(after.left_off);
            page.phase = Phase::restart_due;
            return;
        case ModsNext::ready:
            return fail(page, Phase::ready, std::move(run.error));
        }
    }
}

std::string choice_label(const ModOption& option, int choice) {
    if (choice == 0) return "Off";
    const std::string& name = option.choices[(size_t)choice - 1];
    return name.empty() ? "Choice " + std::to_string(choice) : name;
}

void draw_option(ModOption& option) {
    ImGui::SetNextItemWidth(ImGui::GetFontSize() * 10.0f);
    if (ImGui::BeginCombo("##choice", choice_label(option, option.chosen).c_str())) {
        for (int c = 0; c <= (int)option.choices.size(); c++) {
            ImGui::PushID(c);
            const bool picked = option.chosen == c;
            if (ImGui::Selectable(choice_label(option, c).c_str(), picked)) option.chosen = c;
            if (picked) ImGui::SetItemDefaultFocus();
            ImGui::PopID();
        }
        ImGui::EndCombo();
    }
    ImGui::SameLine();
    ImGui::TextUnformatted(option.name.c_str());
}

void draw_packages(std::vector<ModPackage>& packages) {
    for (size_t i = 0; i < packages.size(); i++) {
        ModPackage& package = packages[i];
        ImGui::PushID((int)i);
        ImGui::SeparatorText(package.xml.c_str());
        if (!package.error.empty()) {
            ImGui::TextUnformatted("Off");
            ImGui::TextDisabled("%s", package.error.c_str());
        }
        const std::string* section = nullptr;
        for (size_t j = 0; j < package.options.size(); j++) {
            ModOption& option = package.options[j];
            if (!option.section.empty() && (!section || *section != option.section))
                ImGui::TextDisabled("%s", option.section.c_str());
            section = &option.section;
            ImGui::PushID((int)j);
            draw_option(option);
            ImGui::PopID();
        }
        ImGui::PopID();
    }
}

void draw_phase(Page& page) {
    switch (page.phase) {
    case Phase::unread:
    case Phase::reading:
        ImGui::TextUnformatted("Reading the mods folder.");
        return;
    case Phase::unreadable:
        ImGui::TextUnformatted(page.error.c_str());
        if (ImGui::Button("Read again")) start_read(page);
        return;
    case Phase::restart_due:
        // The overlay's Restart game is below every page, and it asks first.
        ImGui::TextUnformatted(page.left_off.empty() ? kSaved : kLeftOff);
        draw_packages(page.left_off);
        return;
    case Phase::ready:
    case Phase::applying:
        break;
    }
    if (page.packages.empty()) {
        ImGui::TextUnformatted(kNoPackages);
        return;
    }
    const bool applying = page.phase == Phase::applying;
    ImGui::BeginDisabled(applying);
    draw_packages(page.packages);
    ImGui::EndDisabled();
    ImGui::Separator();
    // A replay ends at a restart (frontend.h), so the overlay offers none there either.
    if (input_replay_loaded()) {
        ImGui::TextUnformatted("A replay can't restart the game, so mods can't change during one.");
        return;
    }
    if (applying) {
        // Once the page has left the screen, the run waits for Restart game (mods_after_apply).
        ImGui::TextUnformatted(page.watched ? kApplyingOnScreen : kApplyingOffScreen);
        return;
    }
    // The next start has no mods while an apply is due, so a failure then says so. start_apply's
    // own failures, with none due, leave settings.txt's keys as they were.
    if (!page.error.empty()) {
        const std::string shown = page.apply_due ? page.error + " " + kNoModsYet : page.error;
        ImGui::TextUnformatted(shown.c_str());
    } else if (mods_not_started_shown(page.packages, page.apply_due)) {
        ImGui::TextUnformatted(kNotStarted);
    }
    ImGui::BeginDisabled(!page.apply_due && !mods_changed(page.packages) && page.error.empty());
    if (ImGui::Button("Apply and restart")) start_apply(page);
    ImGui::EndDisabled();
    ImGui::TextDisabled("If every package applies while this page is open, the game starts again at once, and "
                        "anything it hasn't saved is lost.");
}

void draw(void* user) {
    Page& page = *static_cast<Page*>(user);
    const int frame = ImGui::GetFrameCount();
    const long long now =
        std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch())
            .count();
    if (!mods_drawn_since(page.frame, page.ms, frame, now)) page.watched = false;
    page.frame = frame;
    page.ms = now;
    if (page.phase == Phase::unread) start_read(page);
    take_results(page);
    // Long text wraps, so an error doesn't widen the menu.
    ImGui::PushTextWrapPos(ImGui::GetCursorPosX() + ImGui::GetFontSize() * 30.0f);
    draw_phase(page);
    ImGui::PopTextWrapPos();
}

Page g_page;

// Before main, which is before overlay_init stops taking pages (overlay.h).
struct Registration {
    Registration() { overlay_add_page("Mods", draw, &g_page); }
} g_registration;

}  // namespace
#endif
