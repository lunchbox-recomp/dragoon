// Which cameras widen and by how much (src/cameras.h).
#include "cameras.h"
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

TEST(SetsWorldAspect, OnlyTheCameraModulesTwoCallsCount) {
    EXPECT_TRUE(dragoon::sets_world_aspect(0x800C2884));
    EXPECT_TRUE(dragoon::sets_world_aspect(0x800C9820));
    EXPECT_FALSE(dragoon::sets_world_aspect(0x80066E4C));  // the camera library, for a HUD camera
    EXPECT_FALSE(dragoon::sets_world_aspect(0x800C2880));  // the call itself, not where it returns
    EXPECT_FALSE(dragoon::sets_world_aspect(0));
}

}  // namespace
