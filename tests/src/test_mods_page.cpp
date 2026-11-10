// The Mods page's pure part (src/mods_page.h), on JSON written as tools/mod_choices.py prints
// it, for made-up packages.
#include "mods_page.h"
#include <gtest/gtest.h>
#include <cerrno>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace {

using dragoon::ChildResult;
using dragoon::ModOption;
using dragoon::ModPackage;
using dragoon::ModsAfterApply;
using dragoon::ModsApplied;
using dragoon::ModsApplyEnd;
using dragoon::ModsNext;
using End = ChildResult::End;
using Argv = std::vector<std::string>;

const char* const kList = R"({"packages": [{"options": [{"choice": 1, "choices": ["Fast", "Faster"], )"
                          R"("default": 0, "id": "speed", "name": "Speed", "section": "Racing"}, )"
                          R"({"choice": 0, "choices": ["On"], "default": 1, "id": "music", "name": "Music", )"
                          R"("section": ""}], "xml": "pack.xml"}, )"
                          R"({"error": "broken.xml has no wiidisc root. This package was left off.", )"
                          R"("xml": "broken.xml"}]})"
                          "\n";

const char* const kUnreadable =
    "tools/mod_choices.py printed a result this build can't read. Build the game again from the same checkout.";

ChildResult exited(int code, const std::string& out) {
    ChildResult r;
    r.end = End::exited;
    r.code = code;
    r.out = out;
    return r;
}

std::vector<ModPackage> listed(const std::string& json = kList) {
    std::vector<ModPackage> packages;
    std::string error;
    EXPECT_TRUE(dragoon::mods_list_from(exited(0, json), packages, error)) << error;
    return packages;
}

std::string list_error(const ChildResult& run) {
    std::vector<ModPackage> packages;
    std::string error;
    EXPECT_FALSE(dragoon::mods_list_from(run, packages, error));
    return error;
}

std::string apply_error(const std::string& json) {
    ModsApplied applied;
    std::string error;
    EXPECT_FALSE(dragoon::mods_apply_from(exited(0, json), applied, error));
    return error;
}

Argv set_argv(const std::string& xml, const std::string& option, const std::string& choice) {
    return {"/usr/bin/python3", "-B", "tools/mod_choices.py", "set", "--data", ".", "--", xml, option, choice};
}

TEST(ModsList, ReadsAPackageWithTwoOptions) {
    const std::vector<ModPackage> packages = listed();
    ASSERT_EQ(packages.size(), 2u);
    const ModPackage& pack = packages[0];
    EXPECT_EQ(pack.xml, "pack.xml");
    EXPECT_EQ(pack.error, "");
    ASSERT_EQ(pack.options.size(), 2u);
    const ModOption& speed = pack.options[0];
    EXPECT_EQ(speed.id, "speed");
    EXPECT_EQ(speed.name, "Speed");
    EXPECT_EQ(speed.section, "Racing");
    EXPECT_EQ(speed.choices, (Argv{"Fast", "Faster"}));
    EXPECT_EQ(speed.running, 1);
    EXPECT_EQ(speed.chosen, 1);
    const ModOption& music = pack.options[1];
    EXPECT_EQ(music.id, "music");
    EXPECT_EQ(music.section, "");
    EXPECT_EQ(music.choices, (Argv{"On"}));
    EXPECT_EQ(music.running, 0);
    EXPECT_EQ(music.chosen, 0);
}

TEST(ModsList, ShowsAFailedPackageOffWithItsError) {
    const std::vector<ModPackage> packages = listed();
    ASSERT_EQ(packages.size(), 2u);
    EXPECT_EQ(packages[1].xml, "broken.xml");
    EXPECT_EQ(packages[1].error, "broken.xml has no wiidisc root. This package was left off.");
    EXPECT_TRUE(packages[1].options.empty());
}

TEST(ModsList, ReadsAnEmptyFolder) {
    EXPECT_TRUE(listed("{\"packages\": []}").empty());
}

TEST(ModsList, TakesAChoiceOutsideTheListAsOff) {
    // riivolution.py runs such a default as off (Package.active).
    const std::vector<ModPackage> packages = listed(
        R"({"packages": [{"options": [{"choice": 3, "choices": ["A", "B"], "default": 3, "id": "x", )"
        R"("name": "X", "section": ""}, {"choice": -1, "choices": ["A"], "default": -1, "id": "y", )"
        R"("name": "Y", "section": ""}, {"choice": 2, "choices": ["A", "B"], "default": 0, "id": "z", )"
        R"("name": "Z", "section": ""}], "xml": "p.xml"}]})");
    ASSERT_EQ(packages.size(), 1u);
    ASSERT_EQ(packages[0].options.size(), 3u);
    EXPECT_EQ(packages[0].options[0].running, 0);
    EXPECT_EQ(packages[0].options[0].chosen, 0);
    EXPECT_EQ(packages[0].options[1].running, 0);
    EXPECT_EQ(packages[0].options[2].running, 2);
}

TEST(ModsList, RefusesJsonThatIsntAList) {
    EXPECT_EQ(list_error(exited(0, "{}")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "[]")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "{\"packages\": {}}")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "{\"packages\": [3]}")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "{\"packages\": [{\"xml\": 3, \"options\": []}]}")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "{\"packages\": [{\"xml\": \"p.xml\"}]}")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "{\"packages\": [{\"xml\": \"p.xml\", \"error\": 3}]}")), kUnreadable);
    const std::string option = R"({"packages": [{"xml": "p.xml", "options": [OPTION]}]})";
    const auto with = [&](const std::string& o) {
        std::string text = option;
        return exited(0, text.replace(text.find("OPTION"), 6, o));
    };
    EXPECT_EQ(list_error(with("3")), kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choices": [], "id": "x", "name": "X", "section": ""})")), kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": "1", "choices": [], "id": "x", "name": "X", "section": ""})")),
              kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": 1.5, "choices": ["A"], "id": "x", "name": "X", "section": ""})")),
              kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": 1e300, "choices": ["A"], "id": "x", "name": "X", "section": ""})")),
              kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": 0, "choices": [1], "id": "x", "name": "X", "section": ""})")),
              kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": 0, "choices": {}, "id": "x", "name": "X", "section": ""})")),
              kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": 0, "choices": [], "name": "X", "section": ""})")), kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": 0, "choices": [], "id": "x", "section": ""})")), kUnreadable);
    EXPECT_EQ(list_error(with(R"({"choice": 0, "choices": [], "id": "x", "name": "X"})")), kUnreadable);
}

TEST(ModsChanges, ApplyWaitsForAChoiceThatDiffers) {
    const std::vector<ModPackage> packages = listed();
    EXPECT_FALSE(dragoon::mods_changed(packages));
    EXPECT_TRUE(dragoon::mods_set_argvs(packages).empty());
}

TEST(ModsChanges, AChangeIsOneSetAndItsUndoIsNone) {
    std::vector<ModPackage> packages = listed();
    ASSERT_EQ(packages.size(), 2u);
    ASSERT_EQ(packages[0].options.size(), 2u);
    packages[0].options[0].chosen = 2;
    EXPECT_TRUE(dragoon::mods_changed(packages));
    EXPECT_EQ(dragoon::mods_set_argvs(packages), (std::vector<Argv>{set_argv("pack.xml", "speed", "2")}));
    packages[0].options[0].chosen = 1;
    EXPECT_FALSE(dragoon::mods_changed(packages));
    EXPECT_TRUE(dragoon::mods_set_argvs(packages).empty());
}

TEST(ModsChanges, TurningAnOptionOffSetsOff) {
    std::vector<ModPackage> packages = listed();
    ASSERT_EQ(packages.size(), 2u);
    ASSERT_EQ(packages[0].options.size(), 2u);
    packages[0].options[0].chosen = 0;
    packages[0].options[1].chosen = 1;
    EXPECT_EQ(dragoon::mods_set_argvs(packages),
              (std::vector<Argv>{set_argv("pack.xml", "speed", "off"), set_argv("pack.xml", "music", "1")}));
}

TEST(ModsChanges, NamesStartingWithADashStayArguments) {
    std::vector<ModPackage> packages = listed(
        R"({"packages": [{"options": [{"choice": 0, "choices": ["A"], "default": 0, "id": "-o", )"
        R"("name": "O", "section": ""}], "xml": "-p.xml"}]})");
    ASSERT_EQ(packages.size(), 1u);
    ASSERT_EQ(packages[0].options.size(), 1u);
    packages[0].options[0].chosen = 1;
    EXPECT_EQ(dragoon::mods_set_argvs(packages), (std::vector<Argv>{set_argv("-p.xml", "-o", "1")}));
}

TEST(ModsCommands, ListAndApplyRunTheScriptOnThisFolder) {
    EXPECT_EQ(dragoon::mods_list_argv(), (Argv{"/usr/bin/python3", "-B", "tools/mod_choices.py", "list", "--data", "."}));
    EXPECT_EQ(dragoon::mods_apply_argv(),
              (Argv{"/usr/bin/python3", "-B", "tools/mod_choices.py", "apply", "--data", "."}));
}

TEST(ModsCommands, TheEnvironmentIsTheToolsOwn) {
    const Argv base = {"PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=en_US.UTF-8", "PYTHONDONTWRITEBYTECODE=1",
                       "PYTHONNOUSERSITE=1"};
    EXPECT_EQ(dragoon::mods_env(nullptr, nullptr), base);
    Argv both = base;
    both.push_back("HOME=/Users/a b");
    both.push_back("TMPDIR=/tmp/t/");
    EXPECT_EQ(dragoon::mods_env("/Users/a b", "/tmp/t/"), both);
    Argv home = base;
    home.push_back("HOME=/h");
    EXPECT_EQ(dragoon::mods_env("/h", nullptr), home);
}

TEST(ModsSet, TakesAnExitZeroWithJson) {
    std::string error;
    EXPECT_TRUE(dragoon::mods_set_from(exited(0, "{\"choice\": 2, \"option\": \"speed\", \"xml\": \"pack.xml\"}\n"),
                                       error));
    EXPECT_FALSE(dragoon::mods_set_from(exited(0, "saved\n"), error));
    EXPECT_EQ(error, kUnreadable);
}

TEST(ModsApply, ReadsThePathsAndWhatWasLeftOff) {
    ModsApplied applied;
    std::string error;
    ASSERT_TRUE(dragoon::mods_apply_from(
        exited(0, R"({"failed": [{"error": "a.xml and b.xml conflict.", "xml": "b.xml"}], "ms": 41, )"
                  R"("overlay": "mods/.out/disc-overlay.txt", "ram_patches": null})"
                  "\n"),
        applied, error))
        << error;
    EXPECT_EQ(applied.overlay, "mods/.out/disc-overlay.txt");
    EXPECT_EQ(applied.ram_patches, "");
    EXPECT_EQ(applied.ms, 41);
    ASSERT_EQ(applied.left_off.size(), 1u);
    EXPECT_EQ(applied.left_off[0].xml, "b.xml");
    EXPECT_EQ(applied.left_off[0].error, "a.xml and b.xml conflict.");
}

TEST(ModsApply, ReadsNothingOn) {
    ModsApplied applied;
    std::string error;
    ASSERT_TRUE(dragoon::mods_apply_from(
        exited(0, R"({"failed": [], "ms": 3, "overlay": null, "ram_patches": "mods/.out/ram-patches.txt"})"), applied,
        error));
    EXPECT_EQ(applied.overlay, "");
    EXPECT_EQ(applied.ram_patches, "mods/.out/ram-patches.txt");
    EXPECT_TRUE(applied.left_off.empty());
}

TEST(ModsApply, RefusesJsonThatIsntAnApply) {
    EXPECT_EQ(apply_error(R"({"failed": [], "ms": 1, "overlay": null})"), kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [], "ms": 1, "ram_patches": null})"), kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [], "ms": 1, "overlay": 3, "ram_patches": null})"), kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [], "ms": 1, "overlay": null, "ram_patches": false})"), kUnreadable);
    EXPECT_EQ(apply_error(R"({"ms": 1, "overlay": null, "ram_patches": null})"), kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [3], "ms": 1, "overlay": null, "ram_patches": null})"), kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [{"xml": "a.xml"}], "ms": 1, "overlay": null, "ram_patches": null})"),
              kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [{"error": "e"}], "ms": 1, "overlay": null, "ram_patches": null})"),
              kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [], "overlay": null, "ram_patches": null})"), kUnreadable);
}

TEST(ModsApply, RefusesAPathWithALineBreak) {
    // It would end up as a line of its own in settings.txt.
    EXPECT_EQ(apply_error(R"({"failed": [], "ms": 1, "overlay": "a\nscale 9", "ram_patches": null})"), kUnreadable);
    EXPECT_EQ(apply_error(R"({"failed": [], "ms": 1, "overlay": null, "ram_patches": "a\rb"})"), kUnreadable);
}

TEST(ModsResult, ATimeoutSaysItWasStopped) {
    ChildResult r;
    r.end = End::timed_out;
    r.out = "{\"packages\": []}";
    EXPECT_EQ(list_error(r),
              "tools/mod_choices.py ran for 30 s without finishing, so it was stopped. Check the mods folder and try "
              "again.");
}

TEST(ModsResult, ANonzeroExitGivesTheScriptsError) {
    EXPECT_EQ(list_error(exited(1, "{\"error\": \"mods.txt is a link. Remove the link or move the file.\"}\n")),
              "mods.txt is a link. Remove the link or move the file.");
    ModsApplied applied;
    std::string error;
    EXPECT_FALSE(dragoon::mods_apply_from(exited(2, "{\"error\": \"The disc image isn't a file.\"}"), applied, error));
    EXPECT_EQ(error, "The disc image isn't a file.");
    EXPECT_FALSE(dragoon::mods_set_from(exited(1, "{\"error\": \"The choice is past the last one.\"}"), error));
    EXPECT_EQ(error, "The choice is past the last one.");
}

TEST(ModsResult, ANonzeroExitWithoutAnErrorGivesTheCode) {
    const std::string no_reason =
        "tools/mod_choices.py exited with code 2 and gave no reason. The reason is in the game's Terminal output.";
    EXPECT_EQ(list_error(exited(2, "")), no_reason);
    EXPECT_EQ(list_error(exited(2, "Traceback")), no_reason);
    EXPECT_EQ(list_error(exited(2, "{\"error\": 3}")), no_reason);
    EXPECT_EQ(list_error(exited(2, "{\"error\": \"\"}")), no_reason);
    EXPECT_EQ(list_error(exited(2, "[\"error\"]")), no_reason);
    EXPECT_EQ(list_error(exited(1, "{\"packages\": []}")),
              "tools/mod_choices.py exited with code 1 and gave no reason. The reason is in the game's Terminal output.");
}

TEST(ModsResult, OutputThatIsntJsonIsUnreadable) {
    EXPECT_EQ(list_error(exited(0, "")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "{\"packages\": []} trailing")), kUnreadable);
    EXPECT_EQ(list_error(exited(0, "{\"packages\": [}")), kUnreadable);
}

TEST(ModsResult, ASignalIsNamed) {
    ChildResult r;
    r.end = End::signaled;
    r.code = SIGKILL;
    EXPECT_EQ(list_error(r),
              "tools/mod_choices.py was stopped by signal 9. The reason is in the game's Terminal output.");
}

TEST(ModsResult, APythonThatDoesntStartIsNamed) {
    ChildResult r;
    r.end = End::not_started;
    // /usr/bin/python3 is always there, as the stub that finds the Command Line Tools, so this is
    // a failure such as running out of descriptors.
    r.code = EMFILE;
    EXPECT_EQ(list_error(r), "/usr/bin/python3 didn't start: Too many open files. Quit other programs or restart "
                             "the game, then try again.");
}

// kList with speed on its second choice and music on, two changes.
std::vector<ModPackage> two_changes() {
    std::vector<ModPackage> packages = listed();
    if (packages.size() != 2 || packages[0].options.size() != 2) {
        ADD_FAILURE() << "kList didn't read";
        return {};
    }
    packages[0].options[0].chosen = 2;
    packages[0].options[1].chosen = 1;
    return packages;
}

ModsApplyEnd saved_end(std::vector<ModPackage> left_off = {}) {
    ModsApplyEnd end;
    end.sets = 2;
    end.saved = true;
    end.left_off = std::move(left_off);
    return end;
}

TEST(ModsAfterApply, RestartsOnceEveryChangeIsSaved) {
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = true;
    const ModsAfterApply after = dragoon::mods_after_apply(packages, apply_due, saved_end());
    EXPECT_EQ(after.next, ModsNext::restart);
    EXPECT_TRUE(after.left_off.empty());
    EXPECT_FALSE(apply_due);
    EXPECT_EQ(packages[0].options[0].running, 2);
    EXPECT_EQ(packages[0].options[1].running, 1);
    EXPECT_FALSE(dragoon::mods_changed(packages));
}

TEST(ModsAfterApply, WaitsWhenThePageWasntOnScreen) {
    // A run that ends while the menu is closed or on another page doesn't restart by itself.
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = true;
    ModsApplyEnd end = saved_end();
    end.watched = false;
    const ModsAfterApply after = dragoon::mods_after_apply(packages, apply_due, end);
    EXPECT_EQ(after.next, ModsNext::restart_due);
    EXPECT_TRUE(after.left_off.empty());
    EXPECT_FALSE(apply_due);
}

TEST(ModsAfterApply, ShowsAPackageLeftOffAsOff) {
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = true;
    const ModsAfterApply after = dragoon::mods_after_apply(
        packages, apply_due, saved_end({{"pack.xml", "a.xml and pack.xml conflict.", {}}}));
    EXPECT_EQ(after.next, ModsNext::restart_due);
    ASSERT_EQ(after.left_off.size(), 1u);
    EXPECT_EQ(after.left_off[0].xml, "pack.xml");
    EXPECT_EQ(after.left_off[0].error, "a.xml and pack.xml conflict.");
    EXPECT_FALSE(apply_due);
    // apply saved its options off in mods.txt.
    for (const ModOption& option : packages[0].options) {
        EXPECT_EQ(option.running, 0);
        EXPECT_EQ(option.chosen, 0);
    }
}

TEST(ModsAfterApply, APackageListShowedWithAnErrorDoesntHoldTheRestart) {
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = false;
    const ModsAfterApply after = dragoon::mods_after_apply(
        packages, apply_due, saved_end({{"broken.xml", "broken.xml has no wiidisc root.", {}}}));
    EXPECT_EQ(after.next, ModsNext::restart);
    EXPECT_TRUE(after.left_off.empty());
}

TEST(ModsAfterApply, AFailedSetMovesOnlyTheSetsBeforeIt) {
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = false;
    ModsApplyEnd end;
    end.sets = 1;
    const ModsAfterApply after = dragoon::mods_after_apply(packages, apply_due, end);
    EXPECT_EQ(after.next, ModsNext::ready);
    EXPECT_TRUE(apply_due);
    EXPECT_EQ(packages[0].options[0].running, 2);
    EXPECT_EQ(packages[0].options[1].running, 0);
    // mods.txt holds speed's 2 now, so undoing it is a `set` of its own.
    packages[0].options[0].chosen = 1;
    EXPECT_EQ(dragoon::mods_set_argvs(packages),
              (std::vector<Argv>{set_argv("pack.xml", "speed", "1"), set_argv("pack.xml", "music", "1")}));
}

TEST(ModsAfterApply, AFailedApplyKeepsApplyAndRestartActive) {
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = false;
    ModsApplyEnd end;
    end.sets = 2;
    EXPECT_EQ(dragoon::mods_after_apply(packages, apply_due, end).next, ModsNext::ready);
    EXPECT_FALSE(dragoon::mods_changed(packages));
    EXPECT_TRUE(apply_due);
    // A later run with no `set` that saves clears it.
    end.sets = 0;
    end.saved = true;
    EXPECT_EQ(dragoon::mods_after_apply(packages, apply_due, end).next, ModsNext::restart);
    EXPECT_FALSE(apply_due);
}

TEST(ModsAfterApply, APackageLeftOffEndsOffWhenSettingsCantBeWritten) {
    // `apply` saved pack.xml off in mods.txt before the settings.txt write failed.
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = false;
    ModsApplyEnd end = saved_end({{"pack.xml", "a.xml and pack.xml conflict.", {}}});
    end.saved = false;
    EXPECT_EQ(dragoon::mods_after_apply(packages, apply_due, end).next, ModsNext::ready);
    for (const ModOption& option : packages[0].options) {
        EXPECT_EQ(option.running, 0);
        EXPECT_EQ(option.chosen, 0);
    }
    // Nothing is on now, so the next start's lack of mods is what the page shows.
    EXPECT_FALSE(apply_due);
}

TEST(ModsAfterApply, AFailedRunWithEveryOptionOffLeavesNothingDue) {
    // The player picked speed off. Its `set` worked and `apply` failed.
    std::vector<ModPackage> packages = listed();
    ASSERT_EQ(packages.size(), 2u);
    ASSERT_EQ(packages[0].options.size(), 2u);
    packages[0].options[0].chosen = 0;
    bool apply_due = true;
    ModsApplyEnd end;
    end.sets = 1;
    EXPECT_EQ(dragoon::mods_after_apply(packages, apply_due, end).next, ModsNext::ready);
    EXPECT_FALSE(dragoon::mods_changed(packages));
    EXPECT_FALSE(apply_due);
}

// A fresh install: mods.txt has no line, so `list` gives the option its XML's default.
const char* const kDefaultOn = R"({"packages": [{"options": [{"choice": 1, "choices": ["On"], "default": 1, )"
                               R"("id": "music", "name": "Music", "section": ""}], "xml": "pack.xml"}]})"
                               "\n";

TEST(ModsDueAtStart, AFreshInstallWithADefaultOnPackageIsDue) {
    const std::vector<ModPackage> packages = listed(kDefaultOn);
    ASSERT_EQ(packages.size(), 1u);
    EXPECT_FALSE(dragoon::mods_changed(packages));
    EXPECT_TRUE(dragoon::mods_due_at_start(packages, false, ""));
}

TEST(ModsDueAtStart, AGameThatStartedWithModsIsntDue) {
    const std::vector<ModPackage> packages = listed(kDefaultOn);
    ASSERT_EQ(packages.size(), 1u);
    EXPECT_FALSE(dragoon::mods_due_at_start(packages, true, ""));
    EXPECT_FALSE(dragoon::mods_due_at_start(packages, false, "mods/.out/ram-patches.txt"));
    EXPECT_FALSE(dragoon::mods_due_at_start(packages, true, "mods/.out/ram-patches.txt"));
}

TEST(ModsDueAtStart, EveryOptionOffIsntDue) {
    std::vector<ModPackage> packages = listed();
    ASSERT_EQ(packages.size(), 2u);
    ASSERT_EQ(packages[0].options.size(), 2u);
    EXPECT_TRUE(dragoon::mods_due_at_start(packages, false, ""));
    // With speed off too, nothing is on, and broken.xml has no options.
    packages[0].options[0].running = packages[0].options[0].chosen = 0;
    EXPECT_FALSE(dragoon::mods_due_at_start(packages, false, ""));
    EXPECT_FALSE(dragoon::mods_due_at_start({}, false, ""));
}

TEST(ModsDueAtStart, AfterAFailedApplyApplyAndRestartStaysActive) {
    // The run emptied settings.txt's keys, and its `set`s saved speed's 2 and music's 1 in mods.txt.
    std::vector<ModPackage> packages = two_changes();
    ASSERT_EQ(packages.size(), 2u);
    bool apply_due = false;
    ModsApplyEnd end;
    end.sets = 2;
    EXPECT_EQ(dragoon::mods_after_apply(packages, apply_due, end).next, ModsNext::ready);
    EXPECT_TRUE(apply_due);
    // The game starts again with no mods and a new page, and `list` reads what mods.txt holds.
    EXPECT_FALSE(dragoon::mods_changed(packages));
    EXPECT_TRUE(dragoon::mods_due_at_start(packages, false, ""));
}

TEST(ModsNotStarted, ShowsWhileAnApplyIsDueAndNothingChanged) {
    const std::vector<ModPackage> packages = listed(kDefaultOn);
    ASSERT_EQ(packages.size(), 1u);
    EXPECT_TRUE(dragoon::mods_not_started_shown(packages, true));
    EXPECT_FALSE(dragoon::mods_not_started_shown(packages, false));
}

TEST(ModsNotStarted, GoesOnceAPickChanges) {
    // The player picked music off, so Apply and restart is about that pick now.
    std::vector<ModPackage> packages = listed(kDefaultOn);
    ASSERT_EQ(packages.size(), 1u);
    ASSERT_EQ(packages[0].options.size(), 1u);
    packages[0].options[0].chosen = 0;
    EXPECT_FALSE(dragoon::mods_not_started_shown(packages, true));
}

TEST(ModsAfterApply, AnOptionStillOnAfterAFailedSetKeepsApplyDue) {
    // The player picked music off, and Apply emptied the keys before its `set` failed, so mods.txt
    // still holds music on.
    std::vector<ModPackage> packages = listed(kDefaultOn);
    ASSERT_EQ(packages.size(), 1u);
    ASSERT_EQ(packages[0].options.size(), 1u);
    packages[0].options[0].chosen = 0;
    bool apply_due = false;
    ModsApplyEnd end;
    end.sets = 0;
    EXPECT_EQ(dragoon::mods_after_apply(packages, apply_due, end).next, ModsNext::ready);
    EXPECT_EQ(packages[0].options[0].running, 1);
    EXPECT_TRUE(apply_due);
}

TEST(ModsDrawn, EachFrameInTurnIsOnScreen) {
    EXPECT_TRUE(dragoon::mods_drawn_since(41, 1000, 42, 1016));
    EXPECT_TRUE(dragoon::mods_drawn_since(41, 1000, 42, 1000 + dragoon::kModsGapMs));
}

TEST(ModsDrawn, AMissedFrameIsAnotherPage) {
    EXPECT_FALSE(dragoon::mods_drawn_since(41, 1000, 43, 1033));
    EXPECT_FALSE(dragoon::mods_drawn_since(41, 1000, 41, 1016));
}

TEST(ModsDrawn, AGapInTimeIsAClosedMenu) {
    EXPECT_FALSE(dragoon::mods_drawn_since(41, 1000, 42, 1001 + dragoon::kModsGapMs));
}

TEST(ModsSettings, EmptiesTheKeysWhenEverythingIsOff) {
    ModsApplied applied;
    std::string error;
    ASSERT_TRUE(dragoon::mods_apply_from(exited(0, R"({"failed": [], "ms": 2, "overlay": null, "ram_patches": null})"),
                                         applied, error));
    EXPECT_EQ(dragoon::mods_settings_text("aspect 16:9\ndisc_overlay mods/.out/disc-overlay.txt\n"
                                          "ram_patches mods/.out/ram-patches.txt\nscale 3\n",
                                          applied.overlay, applied.ram_patches),
              "aspect 16:9\ndisc_overlay\nram_patches\nscale 3\n");
}

TEST(ModsSettings, NamesThePathsApplyWrote) {
    EXPECT_EQ(dragoon::mods_settings_text("disc_overlay\n  ram_patches\told.txt\n", "mods/.out/disc-overlay.txt",
                                          "mods/.out/ram-patches.txt"),
              "disc_overlay mods/.out/disc-overlay.txt\nram_patches mods/.out/ram-patches.txt\n");
}

TEST(ModsSettings, AddsTheKeysAFileLacks) {
    EXPECT_EQ(dragoon::mods_settings_text("", "o.txt", ""), "disc_overlay o.txt\nram_patches\n");
    EXPECT_EQ(dragoon::mods_settings_text("scale 3\n", "", "r.txt"), "scale 3\ndisc_overlay\nram_patches r.txt\n");
    EXPECT_EQ(dragoon::mods_settings_text("ram_patches r.txt\n", "o.txt", ""), "ram_patches\ndisc_overlay o.txt\n");
}

TEST(ModsSettings, KeepsCommentsUnknownKeysAndEveryCopyInLine) {
    // A load takes the last copy of a key, so each one names the new path.
    EXPECT_EQ(dragoon::mods_settings_text("# disc_overlay old\n\ndisc_overlays x\ndisc_overlay a\ndisc_overlay b\n"
                                          "ram_patches\n",
                                          "o.txt", ""),
              "# disc_overlay old\n\ndisc_overlays x\ndisc_overlay o.txt\ndisc_overlay o.txt\nram_patches\n");
}

TEST(ModsSettings, KeepsAByteOrderMarkAndCrLf) {
    EXPECT_EQ(dragoon::mods_settings_text("\xEF\xBB\xBF"
                                          "scale 3\r\ndisc_overlay a\r\n",
                                          "o.txt", "r.txt"),
              "\xEF\xBB\xBF"
              "scale 3\r\ndisc_overlay o.txt\r\nram_patches r.txt\r\n");
    EXPECT_EQ(dragoon::mods_settings_text("\xEF\xBB\xBF"
                                          "disc_overlay a",
                                          "", ""),
              "\xEF\xBB\xBF"
              "disc_overlay\nram_patches\n");
}

TEST(ModsSettings, EndsALastLineThatHadNoNewline) {
    EXPECT_EQ(dragoon::mods_settings_text("scale 3", "o.txt", "r.txt"),
              "scale 3\ndisc_overlay o.txt\nram_patches r.txt\n");
    EXPECT_EQ(dragoon::mods_settings_text("scale 3\r\naspect 4:3", "", ""),
              "scale 3\r\naspect 4:3\r\ndisc_overlay\r\nram_patches\r\n");
    EXPECT_EQ(dragoon::mods_settings_text("scale 3\r\naspect 4:3\r", "", ""),
              "scale 3\r\naspect 4:3\r\ndisc_overlay\r\nram_patches\r\n");
    EXPECT_EQ(dragoon::mods_settings_text("scale 3\r\ndisc_overlay a\r", "o.txt", ""),
              "scale 3\r\ndisc_overlay o.txt\r\nram_patches\r\n");
}

class ModsSaveSettings : public ::testing::Test {
protected:
    void SetUp() override {
        dir_ = std::filesystem::temp_directory_path() / ("dragoon mods " + std::to_string(getpid()));
        std::filesystem::remove_all(dir_);
        std::filesystem::create_directories(dir_);
        path_ = (dir_ / "settings.txt").string();
    }
    void TearDown() override {
        chflags(path_.c_str(), 0);
        std::filesystem::permissions(dir_, std::filesystem::perms::owner_all);
        std::filesystem::remove_all(dir_);
    }
    std::string contents() const {
        std::ifstream in(path_, std::ios::binary);
        std::stringstream s;
        s << in.rdbuf();
        return s.str();
    }
    std::filesystem::path dir_;
    std::string path_;
};

TEST_F(ModsSaveSettings, MakesAMissingFile) {
    std::string error;
    ASSERT_TRUE(dragoon::mods_save_settings(path_, "mods/.out/disc-overlay.txt", "", error)) << error;
    EXPECT_EQ(contents(), "disc_overlay mods/.out/disc-overlay.txt\nram_patches\n");
    EXPECT_FALSE(std::filesystem::exists(path_ + ".tmp"));
}

TEST_F(ModsSaveSettings, RewritesTheKeysInPlace) {
    std::ofstream(path_, std::ios::binary) << "aspect 16:9\nram_patches mods/.out/ram-patches.txt\n";
    std::string error;
    ASSERT_TRUE(dragoon::mods_save_settings(path_, "", "", error)) << error;
    EXPECT_EQ(contents(), "aspect 16:9\nram_patches\ndisc_overlay\n");
}

TEST_F(ModsSaveSettings, SaysWhenItCantWrite) {
    std::ofstream(path_, std::ios::binary) << "scale 3\n";
    std::filesystem::permissions(dir_, std::filesystem::perms::owner_read | std::filesystem::perms::owner_exec);
    std::string error;
    EXPECT_FALSE(dragoon::mods_save_settings(path_, "o.txt", "", error));
    EXPECT_EQ(error,
              "settings.txt couldn't be updated (Permission denied), so the game didn't restart. Check that the file "
              "and its folder are writable, then press Apply and restart again.");
    EXPECT_EQ(contents(), "scale 3\n");
}

TEST_F(ModsSaveSettings, LeavesNoTempFileWhenTheRenameFails) {
    std::ofstream(path_, std::ios::binary) << "scale 3\n";
    // An immutable file reads, but nothing can be renamed over it.
    ASSERT_EQ(chflags(path_.c_str(), UF_IMMUTABLE), 0);
    std::string error;
    EXPECT_FALSE(dragoon::mods_save_settings(path_, "o.txt", "", error));
    EXPECT_EQ(error,
              "settings.txt couldn't be updated (Operation not permitted), so the game didn't restart. Check that the "
              "file and its folder are writable, then press Apply and restart again.");
    EXPECT_FALSE(std::filesystem::exists(path_ + ".tmp"));
    EXPECT_EQ(contents(), "scale 3\n");
}

TEST_F(ModsSaveSettings, SaysWhenItCantRead) {
    std::filesystem::create_directory(path_);
    std::string error;
    EXPECT_FALSE(dragoon::mods_save_settings(path_, "o.txt", "", error));
    EXPECT_EQ(error,
              "settings.txt couldn't be updated (Is a directory), so the game didn't restart. Check that the file "
              "and its folder are writable, then press Apply and restart again.");
}

}  // namespace
