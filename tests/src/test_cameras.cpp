// Which cameras widen and by how much (src/cameras.h).
#include "cameras.h"
#include <cmath>
#include <gtest/gtest.h>

namespace {

constexpr float kWide = 16.0f / 9.0f;

TEST(WidenedAspect, AtTheConsoleShapeTheAspectIsUnchangedToTheBit) {
    EXPECT_EQ(dragoon::widened_aspect(1.25538f, 4.0f / 3.0f), 1.25538f);
    EXPECT_EQ(dragoon::widened_aspect(2.23143f, 4.0f / 3.0f), 2.23143f);
}

TEST(WidenedAspect, At16By9TheViewIsAThirdWider) {
    EXPECT_FLOAT_EQ(dragoon::widened_aspect(1.25538f, kWide), 1.25538f * 4 / 3);
}

TEST(WidenedAspect, SplitScreenViewsWidenByTheSameFactor) {
    EXPECT_FLOAT_EQ(dragoon::widened_aspect(2.23143f, kWide), 2.23143f * 4 / 3);
    EXPECT_FLOAT_EQ(dragoon::widened_aspect(1.39419f, kWide), 1.39419f * 4 / 3);
}

TEST(WidenedAspect, At21By9TheViewIsSevenQuartersAsWide) {
    EXPECT_FLOAT_EQ(dragoon::widened_aspect(1.25538f, 21.0f / 9.0f), 1.25538f * 7 / 4);
}

TEST(WidenedAspect, AnOutputOfNoWidthLeavesTheAspectAlone) {
    EXPECT_EQ(dragoon::widened_aspect(1.25538f, 0.0f), 1.25538f);
    EXPECT_EQ(dragoon::widened_aspect(1.25538f, std::nanf("")), 1.25538f);
}

TEST(SetsWorldAspect, TheCameraModulesTwoCallsCountFromAnyCaller) {
    EXPECT_TRUE(dragoon::sets_world_aspect(0x800C2884, 0x800B35D4));
    EXPECT_TRUE(dragoon::sets_world_aspect(0x800C9820, 0x800B2FAC));
    EXPECT_TRUE(dragoon::sets_world_aspect(0x800C9820, 0));
    EXPECT_FALSE(dragoon::sets_world_aspect(0x800C2880, 0x800B35D4));  // the call, not its return
    EXPECT_FALSE(dragoon::sets_world_aspect(0, 0));
}

TEST(SetsWorldAspect, TheCameraLibraryCountsWhenTheCameraModuleOrAViewPresetCalledIt) {
    EXPECT_TRUE(dragoon::sets_world_aspect(0x80066E4C, 0x800B3990));  // kar_camera__800b3944
    EXPECT_TRUE(dragoon::sets_world_aspect(0x80066ECC, 0x800BAC38));  // one view
    EXPECT_TRUE(dragoon::sets_world_aspect(0x80066FF0, 0x800BACD0));  // two views
    EXPECT_TRUE(dragoon::sets_world_aspect(0x80067148, 0x800BAD68));  // four views
}

// Callers seen in the census setting up HUD, minimap and menu cameras.
TEST(SetsWorldAspect, TheCameraLibraryDoesNotCountForTheHudOrTheMenus) {
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066E4C, 0x8011590C));  // fn_801158C0
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066E4C, 0x80115B44));  // fn_80115AF4
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066E4C, 0x8013945C));  // fn_8013941C
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066F48, 0x80115950));  // preset 1, fn_801158C0
    EXPECT_FALSE(dragoon::sets_world_aspect(0x8006709C, 0x80115BC8));  // split preset 1
    EXPECT_FALSE(dragoon::sets_world_aspect(0x800671F4, 0x80115BE0));  // quad preset 1
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80067324, 0x801167D0));  // preset 2, fn_801166B4
}

// Each library call counts only with its own caller, not another world call's.
TEST(SetsWorldAspect, ALibraryCallWithAnotherWorldCallsCallerDoesNotCount) {
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066E4C, 0x800BAC38));
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066ECC, 0x800B3990));
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066FF0, 0x800BAD68));
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80067148, 0x800BACD0));
    EXPECT_FALSE(dragoon::sets_world_aspect(0x800B3990, 0x80066E4C));  // the pair the wrong way round
}

TEST(LoadsWorldCamera, TopRidesWorldCameraCounts) {
    EXPECT_TRUE(dragoon::loads_world_camera(0x803719A0, 0x8028C0E0));
}

// Callers seen in the census loading Top Ride's HUD, effect and menu cameras.
TEST(LoadsWorldCamera, NoOtherLoadCounts) {
    EXPECT_FALSE(dragoon::loads_world_camera(0x802CAD8C, 0x8028C37C));  // fn_802CA894, fov 25
    EXPECT_FALSE(dragoon::loads_world_camera(0x8037A100, 0x8037A928));  // the game's effects
    EXPECT_FALSE(dragoon::loads_world_camera(0x80382510, 0x8028C2E0));  // the slide blur
    EXPECT_FALSE(dragoon::loads_world_camera(0x80066E0C, 0x8013945C));  // the camera library
    EXPECT_FALSE(dragoon::loads_world_camera(0x803719A0, 0x8028C37C));  // another caller
    EXPECT_FALSE(dragoon::loads_world_camera(0x803719A0, 0));
    EXPECT_FALSE(dragoon::loads_world_camera(0x8028C0E0, 0x803719A0));  // the wrong way round
}

}  // namespace
