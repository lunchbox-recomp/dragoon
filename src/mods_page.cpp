// See mods_page.h.
#include "mods_page.h"
#include "json_read.h"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <utility>

namespace dragoon {

namespace {

const char* const kUnreadable =
    "tools/mod_choices.py printed a result this build can't read. Build the game again from the same checkout.";
const char* const kInTerminal = "The reason is in the game's Terminal output.";

bool unreadable(std::string& error) {
    error = kUnreadable;
    return false;
}

std::vector<std::string> script(const char* command) { return {kModsPython, "-B", kModsScript, command, "--data", "."}; }

// The run's JSON object. False, with the player's message, for anything else.
bool result(const ChildResult& run, Json& json, std::string& error) {
    const std::string script_name = kModsScript;
    switch (run.end) {
    case ChildResult::End::not_started:
        // It's always there, as the stub that finds the Command Line Tools, so the reason is a
        // limit such as open files or processes.
        error = std::string(kModsPython) + " didn't start: " + strerror(run.code) +
                ". Quit other programs or restart the game, then try again.";
        return false;
    case ChildResult::End::timed_out:
        error = script_name + " ran for " + std::to_string(kModsTimeoutMs / 1000) +
                " s without finishing, so it was stopped. Check the mods folder and try again.";
        return false;
    case ChildResult::End::signaled:
        error = script_name + " was stopped by signal " + std::to_string(run.code) + ". " + kInTerminal;
        return false;
    case ChildResult::End::exited:
        break;
    }
    // A failed read can leave `json` half filled, so it's only looked at after a whole one.
    const bool parsed = json_read(run.out, json) && json.type == Json::Type::object;
    if (run.code != 0) {
        const Json* why = parsed ? json.get("error") : nullptr;
        if (why && why->type == Json::Type::string && !why->string.empty()) error = why->string;
        else error = script_name + " exited with code " + std::to_string(run.code) + " and gave no reason. " + kInTerminal;
        return false;
    }
    return parsed || unreadable(error);
}

bool text(const Json& object, const char* key, std::string& out) {
    const Json* v = object.get(key);
    if (!v || v->type != Json::Type::string) return false;
    out = v->string;
    return true;
}

bool whole(const Json& object, const char* key, long long& out) {
    const Json* v = object.get(key);
    if (!v || v->type != Json::Type::number || std::trunc(v->number) != v->number || std::fabs(v->number) > 1e15)
        return false;
    out = (long long)v->number;
    return true;
}

// A path or null, which is none. One with a line break would make a line of its own in
// settings.txt, so it's refused.
bool path_or_none(const Json& object, const char* key, std::string& out) {
    const Json* v = object.get(key);
    if (v && v->type == Json::Type::null) {
        out.clear();
        return true;
    }
    return text(object, key, out) && out.find_first_of("\r\n") == std::string::npos;
}

bool options(const Json& package, std::vector<ModOption>& out) {
    const Json* list = package.get("options");
    if (!list || list->type != Json::Type::array) return false;
    for (const Json& o : list->array) {
        ModOption option;
        long long choice;
        const Json* names = o.get("choices");
        if (!text(o, "id", option.id) || !text(o, "name", option.name) || !text(o, "section", option.section) ||
            !whole(o, "choice", choice) || !names || names->type != Json::Type::array)
            return false;
        for (const Json& name : names->array) {
            if (name.type != Json::Type::string) return false;
            option.choices.push_back(name.string);
        }
        // riivolution.py runs a choice outside the list as off (Package.active).
        const bool listed = choice >= 1 && choice <= (long long)option.choices.size();
        option.running = option.chosen = listed ? (int)choice : 0;
        out.push_back(std::move(option));
    }
    return true;
}

constexpr const char* kByteOrderMark = "\xEF\xBB\xBF";

// A line's key as settings.cpp splits it, past the spaces, tabs and CRs around the line and up
// to the first space or tab. A comment's starts with #, so it's never one of the two.
std::string key_of(const std::string& line) {
    const size_t first = line.find_first_not_of(" \t\r");
    if (first == std::string::npos) return "";
    const std::string t = line.substr(first, line.find_last_not_of(" \t\r") - first + 1);
    return t.substr(0, t.find_first_of(" \t"));
}

std::string key_line(const char* key, const std::string& path) { return path.empty() ? key : key + (" " + path); }

// Whether `list` or a run left any option on in mods.txt or by its XML's default.
bool any_on(const std::vector<ModPackage>& packages) {
    return std::any_of(packages.begin(), packages.end(), [](const ModPackage& package) {
        return std::any_of(package.options.begin(), package.options.end(),
                           [](const ModOption& option) { return option.running != 0; });
    });
}

}  // namespace

std::vector<std::string> mods_env(const char* home, const char* tmpdir) {
    std::vector<std::string> env = {"PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=en_US.UTF-8",
                                    "PYTHONDONTWRITEBYTECODE=1", "PYTHONNOUSERSITE=1"};
    if (home) env.push_back(std::string("HOME=") + home);
    if (tmpdir) env.push_back(std::string("TMPDIR=") + tmpdir);
    return env;
}

std::vector<std::string> mods_list_argv() { return script("list"); }

std::vector<std::vector<std::string>> mods_set_argvs(const std::vector<ModPackage>& packages) {
    std::vector<std::vector<std::string>> out;
    for (const ModPackage& package : packages) {
        for (const ModOption& option : package.options) {
            if (option.chosen == option.running) continue;
            // After --, a name that starts with a dash is still the XML or the option.
            std::vector<std::string> argv = script("set");
            argv.insert(argv.end(), {"--", package.xml, option.id,
                                     option.chosen ? std::to_string(option.chosen) : "off"});
            out.push_back(std::move(argv));
        }
    }
    return out;
}

std::vector<std::string> mods_apply_argv() { return script("apply"); }

bool mods_changed(const std::vector<ModPackage>& packages) {
    return std::any_of(packages.begin(), packages.end(), [](const ModPackage& package) {
        return std::any_of(package.options.begin(), package.options.end(),
                           [](const ModOption& option) { return option.chosen != option.running; });
    });
}

bool mods_due_at_start(const std::vector<ModPackage>& packages, bool overlay_loaded, const std::string& ram_patches) {
    return !overlay_loaded && ram_patches.empty() && any_on(packages);
}

bool mods_not_started_shown(const std::vector<ModPackage>& packages, bool apply_due) {
    return apply_due && !mods_changed(packages);
}

bool mods_list_from(const ChildResult& run, std::vector<ModPackage>& packages, std::string& error) {
    Json json;
    if (!result(run, json, error)) return false;
    const Json* list = json.get("packages");
    if (!list || list->type != Json::Type::array) return unreadable(error);
    std::vector<ModPackage> read;
    for (const Json& p : list->array) {
        ModPackage package;
        if (!text(p, "xml", package.xml)) return unreadable(error);
        const bool ok = p.get("error") ? text(p, "error", package.error) : options(p, package.options);
        if (!ok) return unreadable(error);
        read.push_back(std::move(package));
    }
    packages = std::move(read);
    return true;
}

bool mods_set_from(const ChildResult& run, std::string& error) {
    Json json;
    return result(run, json, error);
}

bool mods_apply_from(const ChildResult& run, ModsApplied& applied, std::string& error) {
    Json json;
    if (!result(run, json, error)) return false;
    ModsApplied read;
    const Json* failed = json.get("failed");
    if (!path_or_none(json, "overlay", read.overlay) || !path_or_none(json, "ram_patches", read.ram_patches) ||
        !whole(json, "ms", read.ms) || !failed || failed->type != Json::Type::array)
        return unreadable(error);
    for (const Json& f : failed->array) {
        ModPackage package;
        if (!text(f, "xml", package.xml) || !text(f, "error", package.error)) return unreadable(error);
        read.left_off.push_back(std::move(package));
    }
    applied = std::move(read);
    return true;
}

std::string mods_settings_text(const std::string& text, const std::string& overlay, const std::string& ram_patches) {
    const bool bom = text.compare(0, 3, kByteOrderMark) == 0;
    const std::string body = bom ? text.substr(3) : text;
    // An added line, and a last line the file left open, end as the file's first newline does.
    const size_t first = body.find('\n');
    const char* newline = first != std::string::npos && first > 0 && body[first - 1] == '\r' ? "\r\n" : "\n";
    const std::pair<const char*, const std::string*> keys[] = {{"disc_overlay", &overlay},
                                                               {"ram_patches", &ram_patches}};
    bool written[2] = {};
    std::string out = bom ? kByteOrderMark : "";
    for (size_t start = 0; start < body.size();) {
        size_t end = body.find('\n', start);
        const bool ended = end != std::string::npos;
        if (!ended) end = body.size();
        std::string line = body.substr(start, end - start);
        const bool cr = !line.empty() && line.back() == '\r';
        const std::string key = key_of(line);
        for (int i = 0; i < 2; i++) {
            if (key != keys[i].first) continue;
            line = key_line(keys[i].first, *keys[i].second) + (cr ? "\r" : "");
            written[i] = true;
        }
        out += line + (ended || cr ? "\n" : newline);
        start = end + 1;
    }
    for (int i = 0; i < 2; i++)
        if (!written[i]) out += key_line(keys[i].first, *keys[i].second) + newline;
    return out;
}

bool mods_save_settings(const std::string& path, const std::string& overlay, const std::string& ram_patches,
                        std::string& error) {
    std::string text;
    int failure = 0;
    if (FILE* f = fopen(path.c_str(), "rb")) {
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof(buf), f)) > 0) text.append(buf, n);
        if (ferror(f)) failure = errno;
        fclose(f);
    } else if (errno != ENOENT) {
        failure = errno;
    }
    if (!failure) {
        const std::string tmp = path + ".tmp";
        const std::string next = mods_settings_text(text, overlay, ram_patches);
        if (FILE* f = fopen(tmp.c_str(), "wb")) {
            if (fwrite(next.data(), 1, next.size(), f) != next.size()) failure = errno;
            if (fclose(f) != 0 && !failure) failure = errno;
            if (!failure && rename(tmp.c_str(), path.c_str()) != 0) failure = errno;
            if (failure) remove(tmp.c_str());
        } else {
            failure = errno;
        }
    }
    if (!failure) return true;
    error = std::filesystem::path(path).filename().string() + " couldn't be updated (" + strerror(failure) +
            "), so the game didn't restart. Check that the file and its folder are writable, then press Apply and "
            "restart again.";
    return false;
}

ModsAfterApply mods_after_apply(std::vector<ModPackage>& packages, bool& apply_due, const ModsApplyEnd& end) {
    // The `set`s ran in mods_set_argvs's order.
    int moved = 0;
    for (ModPackage& package : packages)
        for (ModOption& option : package.options)
            if (option.chosen != option.running && moved < end.sets) {
                option.running = option.chosen;
                moved++;
            }
    ModsAfterApply after;
    for (const ModPackage& off : end.left_off) {
        for (ModPackage& package : packages) {
            if (package.xml != off.xml || package.options.empty()) continue;
            for (ModOption& option : package.options) option.running = option.chosen = 0;
            after.left_off.push_back(off);
        }
    }
    // settings.txt names no mods until a run saves, which leaves something to apply only while an
    // option is on.
    apply_due = !end.saved && any_on(packages);
    if (end.saved) after.next = after.left_off.empty() && end.watched ? ModsNext::restart : ModsNext::restart_due;
    return after;
}

bool mods_drawn_since(int last_frame, long long last_ms, int frame, long long now_ms) {
    return frame == last_frame + 1 && now_ms - last_ms <= kModsGapMs;
}

}  // namespace dragoon
