// The Mods page's pure part (docs/dev/mods.md). tools/mod_choices.py's JSON becomes the page's
// packages, the player's changes become its `set` commands, and what `apply` wrote goes in
// settings.txt's disc_overlay and ram_patches lines. src/mods_overlay.cpp draws the page and
// runs the commands.
//
// Each command runs from the game's working directory, the folder holding settings.txt, which
// is the repository root for build/dragoon. That folder is the script's --data folder too.
#pragma once
#include "child_run.h"
#include <string>
#include <vector>

namespace dragoon {

// The Command Line Tools' Python, the script and how long a run of it may take. The script gives
// each Riivolution run 10 s, and `apply` makes one `list` run, then an `apply` run for each try,
// so an `apply` that retries can run past the limit and be stopped.
constexpr const char* kModsPython = "/usr/bin/python3";
constexpr const char* kModsScript = "tools/mod_choices.py";
constexpr int kModsTimeoutMs = 30000;

// One option of a package. Choice N is choices[N - 1], and 0 is off.
struct ModOption {
    std::string id, name, section;
    std::vector<std::string> choices;
    int running = 0;  // what `list` said, from mods.txt or the XML's default
    int chosen = 0;   // what the page has picked
};

// A package has options, or an error saying why it's off.
struct ModPackage {
    std::string xml;
    std::string error;
    std::vector<ModOption> options;
};

// What `apply` printed. The paths are relative to the data folder, empty for none.
struct ModsApplied {
    std::string overlay;
    std::string ram_patches;
    std::vector<ModPackage> left_off;  // each with its error and no options
    long long ms = 0;
};

// The script's whole environment: tools/tool_env.py's, with HOME and TMPDIR when they're set.
std::vector<std::string> mods_env(const char* home, const char* tmpdir);
std::vector<std::string> mods_list_argv();
// One `set` for each option whose pick differs from what's running, in the page's order.
std::vector<std::vector<std::string>> mods_set_argvs(const std::vector<ModPackage>& packages);
std::vector<std::string> mods_apply_argv();
// Whether any pick differs from what's running, which Apply and restart waits for.
bool mods_changed(const std::vector<ModPackage>& packages);
// Whether the game runs none of what `list` calls running, so Apply and restart is due before any
// change: it started with no disc overlay loaded and no RAM patch list (ram_patches_file()), and
// an option is on in mods.txt or by its XML's default.
bool mods_due_at_start(const std::vector<ModPackage>& packages, bool overlay_loaded, const std::string& ram_patches);
// Whether the page says the game started without the mods shown running: an apply is due and no
// pick has changed, since Apply and restart is then about the new picks.
bool mods_not_started_shown(const std::vector<ModPackage>& packages, bool apply_due);

// A run of each command read. False, with the player's message in `error`, for a run that timed
// out, didn't start, was killed or exited nonzero, and for output that isn't the command's JSON.
bool mods_list_from(const ChildResult& run, std::vector<ModPackage>& packages, std::string& error);
bool mods_set_from(const ChildResult& run, std::string& error);
bool mods_apply_from(const ChildResult& run, ModsApplied& applied, std::string& error);

// settings.txt's `text` with every disc_overlay and ram_patches line naming the new path, or
// holding the key alone for none, and a line added for a key it lacks. Every other line, a byte
// order mark and CR LF endings stay as settings_save keeps them (gcn-recomp/runtime/settings.h).
std::string mods_settings_text(const std::string& text, const std::string& overlay, const std::string& ram_patches);
// mods_settings_text on the file at `path`, written to `path`.tmp and renamed over it. A missing
// file is made. False, with the player's message in `error`, when it can't be read or written.
bool mods_save_settings(const std::string& path, const std::string& overlay, const std::string& ram_patches,
                        std::string& error);

// How a run of Apply and restart ended. The page empties settings.txt's two keys before the first
// `set`, so they name no file an interrupted `apply` removes, and names the new paths after it.
struct ModsApplyEnd {
    int sets = 0;                      // the `set`s that worked, in mods_set_argvs's order
    bool saved = false;                // `apply` worked and settings.txt names its paths
    std::vector<ModPackage> left_off;  // what `apply` left off, when it worked
    bool watched = true;               // the page was on screen from the run's start to its end
};

enum class ModsNext {
    restart,      // start the game again now
    restart_due,  // say what was left off, or that the mods are saved, and wait for Restart game
    ready,        // show the packages again, with the run's error
};

struct ModsAfterApply {
    ModsNext next = ModsNext::ready;
    std::vector<ModPackage> left_off;  // the packages left off that the page offered choices for
};

// What the page does after a run, with `running` moved to what mods.txt now holds: the first
// `sets` changes, and after `apply` each option of a left-off package at off, which `apply`
// saved. `apply_due` says settings.txt waits for an apply while an option is on, so Apply and
// restart stays active with nothing changed. A package `list` already showed with an error
// doesn't hold the restart.
ModsAfterApply mods_after_apply(std::vector<ModPackage>& packages, bool& apply_due, const ModsApplyEnd& end);

// Whether the page was on screen the whole time between a draw at `last_frame` and `last_ms` and
// one at `frame` and `now_ms`. The menu's frames count up by one while it shows the page and stop
// while it's closed, so a gap of more than kModsGapMs means the menu was closed.
constexpr long long kModsGapMs = 250;
bool mods_drawn_since(int last_frame, long long last_ms, int frame, long long now_ms);

}  // namespace dragoon
