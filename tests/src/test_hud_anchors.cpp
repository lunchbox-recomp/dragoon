// HUD anchors' pure parts (src/hud_anchors.h).
#include "hud_anchors.h"
#include <gtest/gtest.h>

namespace {

using dragoon::Lens;
using dragoon::Mark;
using dragoon::Rect;
using gx::Anchor;

// The four views of a four-player screen, as the game sets them.
const std::vector<Rect> kFourViews = {
    {10, 318, 16, 224}, {322, 630, 16, 224}, {10, 318, 256, 464}, {322, 630, 256, 464}};

Lens lens(uint8_t type, float a, float b, float c, float d) {
    Lens l;
    l.type = type;
    l.proj[0] = a;
    l.proj[1] = b;
    l.proj[2] = c;
    l.proj[3] = d;
    l.viewport[1] = 640;
    l.viewport[3] = 480;
    l.view[0] = l.view[5] = l.view[10] = 1;
    return l;
}

Lens perspective() { return lens(dragoon::kPerspective, 90, 1, 0, 0); }

// The HUD's 2D frame, 64 by 48 with y up from -48.
Lens hud_frame() { return lens(dragoon::kOrtho, 0, -48, 0, 64); }

TEST(NearestEdge, ThirdsOfTheRect) {
    EXPECT_EQ(dragoon::nearest_edge(213, dragoon::kScreen), Anchor::Left);
    EXPECT_EQ(dragoon::nearest_edge(214, dragoon::kScreen), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(426, dragoon::kScreen), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(427, dragoon::kScreen), Anchor::Right);
}

TEST(NearestEdge, ThirdsOfAViewAwayFromTheScreensEdge) {
    const Rect v{322, 630, 16, 224};
    EXPECT_EQ(dragoon::nearest_edge(424, v), Anchor::Left);
    EXPECT_EQ(dragoon::nearest_edge(426, v), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(526, v), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(528, v), Anchor::Right);
}

TEST(ViewHolding, TheSmallestViewHoldingThePoint) {
    const std::vector<Rect> views = {dragoon::kScreen, {322, 630, 16, 224}};
    EXPECT_EQ(dragoon::view_holding(400, 100, views), &views[1]);
    EXPECT_EQ(dragoon::view_holding(100, 100, views), &views[0]);
}

TEST(ViewHolding, EdgesBelongToTheView) {
    EXPECT_EQ(dragoon::view_holding(10, 16, kFourViews), &kFourViews[0]);
    EXPECT_EQ(dragoon::view_holding(318, 224, kFourViews), &kFourViews[0]);
}

TEST(ViewHolding, NoneOnTheBarsBetween) {
    EXPECT_EQ(dragoon::view_holding(320, 100, kFourViews), nullptr);
    EXPECT_EQ(dragoon::view_holding(100, 240, kFourViews), nullptr);
    EXPECT_EQ(dragoon::view_holding(100, 100, {}), nullptr);
}

TEST(EdgeMark, AnchorsToItsOwnView) {
    EXPECT_EQ(dragoon::edge_mark(600, 200, kFourViews), (Mark{Anchor::Right, 322, 630}));
    EXPECT_EQ(dragoon::edge_mark(30, 440, kFourViews), (Mark{Anchor::Left, 10, 318}));
    EXPECT_EQ(dragoon::edge_mark(164, 120, kFourViews), (Mark{Anchor::Center, 10, 318}));
}

TEST(EdgeMark, OnTheBarsItBelongsToTheScreen) {
    EXPECT_EQ(dragoon::edge_mark(108, 240, kFourViews), (Mark{Anchor::Left, 0, 640}));
    EXPECT_EQ(dragoon::edge_mark(600, 240, kFourViews), (Mark{Anchor::Right, 0, 640}));
}

TEST(EdgeMark, TheBarsThemselvesStretch) {
    EXPECT_EQ(dragoon::edge_mark(320, 240, kFourViews), Mark{});
}

TEST(EdgeMark, WithNoViewsTheMiddleIsCentered) {
    EXPECT_EQ(dragoon::edge_mark(320, 240, {}), (Mark{Anchor::Center, 0, 640}));
}

TEST(MarkFor, EachPlacement) {
    EXPECT_EQ(dragoon::mark_for(dragoon::Placement::Edge, 600, 200, kFourViews), (Mark{Anchor::Right, 322, 630}));
    EXPECT_EQ(dragoon::mark_for(dragoon::Placement::Own, 600, 200, kFourViews), (Mark{Anchor::Center, 600, 600}));
    EXPECT_EQ(dragoon::mark_for(dragoon::Placement::Stretch, 600, 200, kFourViews), Mark{});
}

TEST(MostCalled, TheMarkMostJointsCallFor) {
    const Mark right{Anchor::Right, 0, 640}, middle{Anchor::Center, 0, 640};
    EXPECT_EQ(dragoon::most_called({middle, right, right, middle, right}), right);
}

TEST(MostCalled, ATieGoesToTheFirst) {
    const Mark left{Anchor::Left, 0, 640}, right{Anchor::Right, 0, 640};
    EXPECT_EQ(dragoon::most_called({right, left, right, left}), right);
}

TEST(MostCalled, NoneIsStretch) { EXPECT_EQ(dragoon::most_called({}), Mark{}); }

TEST(MatrixMade, AnyOfItsThreeByThreePart) {
    for (int i : {0, 5, 10}) {
        float m[12] = {};
        m[i] = 1;
        EXPECT_TRUE(dragoon::matrix_made(m)) << i;
    }
}

TEST(MatrixMade, NotByItsTranslationAlone) {
    float m[12] = {};
    EXPECT_FALSE(dragoon::matrix_made(m));
    m[3] = m[7] = m[11] = 5;
    EXPECT_FALSE(dragoon::matrix_made(m));
}

TEST(ToScreen, PerspectiveCentersThePointAhead) {
    const float p[3] = {0, 0, -10};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(perspective(), p, &x, &y));
    EXPECT_FLOAT_EQ(x, 320);
    EXPECT_FLOAT_EQ(y, 240);
}

TEST(ToScreen, PerspectiveRightAndUp) {
    const float right[3] = {5, 0, -10}, up[3] = {0, 5, -10};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(perspective(), right, &x, &y));
    EXPECT_FLOAT_EQ(x, 480);
    ASSERT_TRUE(dragoon::to_screen(perspective(), up, &x, &y));
    EXPECT_FLOAT_EQ(y, 120);
}

TEST(ToScreen, PerspectiveTakesTheAspect) {
    Lens l = perspective();
    l.proj[1] = 2;
    const float p[3] = {5, 0, -10};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(l, p, &x, &y));
    EXPECT_FLOAT_EQ(x, 400);
}

TEST(ToScreen, ThePointGoesThroughTheViewingMatrix) {
    Lens l = perspective();
    l.view[3] = -5;
    l.view[11] = -10;
    const float p[3] = {5, 0, 0};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(l, p, &x, &y));
    EXPECT_FLOAT_EQ(x, 320);
    EXPECT_FLOAT_EQ(y, 240);
}

TEST(ToScreen, NothingAtOrBehindTheEye) {
    const float behind[3] = {0, 0, 10}, at[3] = {1, 1, 0};
    float x, y;
    EXPECT_FALSE(dragoon::to_screen(perspective(), behind, &x, &y));
    EXPECT_FALSE(dragoon::to_screen(perspective(), at, &x, &y));
}

TEST(ToScreen, IntoAView) {
    Lens l = perspective();
    l.viewport[0] = 10;
    l.viewport[1] = 318;
    l.viewport[2] = 16;
    l.viewport[3] = 224;
    const float p[3] = {0, 0, -10};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(l, p, &x, &y));
    EXPECT_FLOAT_EQ(x, 164);
    EXPECT_FLOAT_EQ(y, 120);
}

TEST(ToScreen, TheHudFrame) {
    const float middle[3] = {32, -24, 0}, quarter[3] = {16, -12, 0};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(hud_frame(), middle, &x, &y));
    EXPECT_FLOAT_EQ(x, 320);
    EXPECT_FLOAT_EQ(y, 240);
    ASSERT_TRUE(dragoon::to_screen(hud_frame(), quarter, &x, &y));
    EXPECT_FLOAT_EQ(x, 160);
    EXPECT_FLOAT_EQ(y, 120);
}

TEST(ToScreen, Frustum) {
    Lens l = lens(dragoon::kFrustum, 1, -1, -1, 1);
    l.near = 1;
    const float p[3] = {0.5f, 0.5f, -1};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(l, p, &x, &y));
    EXPECT_FLOAT_EQ(x, 480);
    EXPECT_FLOAT_EQ(y, 120);
}

TEST(ToScreen, ShiftedFrustum) {
    Lens l = lens(dragoon::kFrustum, 2, 0, 0, 2);
    l.near = 1;
    const float p[3] = {0, 0, -1};
    float x, y;
    ASSERT_TRUE(dragoon::to_screen(l, p, &x, &y));
    EXPECT_FLOAT_EQ(x, 0);
    EXPECT_FLOAT_EQ(y, 480);
}

TEST(ToScreen, NoKnownProjectionOrAFlatOne) {
    const float p[3] = {0, 0, -10};
    float x, y;
    EXPECT_FALSE(dragoon::to_screen(lens(0, 90, 1, 0, 0), p, &x, &y));
    EXPECT_FALSE(dragoon::to_screen(lens(dragoon::kOrtho, 0, 0, 0, 64), p, &x, &y));
    EXPECT_FALSE(dragoon::to_screen(lens(dragoon::kOrtho, 0, -48, 64, 64), p, &x, &y));
    EXPECT_FALSE(dragoon::to_screen(lens(dragoon::kPerspective, 90, 0, 0, 0), p, &x, &y));
}

TEST(WorldViews, AFrameReadsItsOwnViewsAndTheLastFramesOnes) {
    dragoon::WorldViews w;
    w.add(10, kFourViews[0]);
    w.add(10, kFourViews[1]);
    w.add(10, kFourViews[0]);
    EXPECT_EQ(w.at(10).size(), 2u);
    EXPECT_EQ(w.at(11).size(), 2u);
    EXPECT_TRUE(w.at(12).empty());
    EXPECT_TRUE(w.at(9).empty());
}

TEST(WorldViews, ANewFrameStartsOver) {
    dragoon::WorldViews w;
    w.add(10, kFourViews[0]);
    w.add(10, kFourViews[1]);
    w.add(11, dragoon::kScreen);
    ASSERT_EQ(w.at(11).size(), 1u);
    EXPECT_EQ(w.at(11)[0], dragoon::kScreen);
}

TEST(HudCallbacks, OutsideEveryCallbackNothingIsPlaced) {
    dragoon::HudCallbacks h;
    EXPECT_EQ(h.placement(), dragoon::Placement::Stretch);
    EXPECT_EQ(h.mark(), Mark{});
    h.leave();
    EXPECT_EQ(h.placement(), dragoon::Placement::Stretch);
}

TEST(HudCallbacks, ACallbackStartsUnmarked) {
    dragoon::HudCallbacks h;
    h.enter(dragoon::Placement::Edge);
    EXPECT_EQ(h.placement(), dragoon::Placement::Edge);
    EXPECT_EQ(h.mark(), Mark{});
}

TEST(HudCallbacks, ANestedCallbackGivesItsCallerBack) {
    dragoon::HudCallbacks h;
    const Mark right{Anchor::Right, 0, 640};
    h.enter(dragoon::Placement::Edge);
    h.set_mark(right);
    h.enter(dragoon::Placement::Own);
    EXPECT_EQ(h.mark(), Mark{});
    h.set_mark({Anchor::Center, 30, 30});
    h.leave();
    EXPECT_EQ(h.placement(), dragoon::Placement::Edge);
    EXPECT_EQ(h.mark(), right);
    h.leave();
    EXPECT_EQ(h.placement(), dragoon::Placement::Stretch);
    EXPECT_EQ(h.mark(), Mark{});
}

}  // namespace
