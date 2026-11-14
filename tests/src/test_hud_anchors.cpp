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

TEST(NearestEdge, AHeldEdgeReachesAQuarterOfAThirdPastItsLines) {
    // The lines sit at 213.3 and 426.7, and a quarter of a third is 53.3.
    EXPECT_EQ(dragoon::nearest_edge(266, dragoon::kScreen, Anchor::Left), Anchor::Left);
    EXPECT_EQ(dragoon::nearest_edge(267, dragoon::kScreen, Anchor::Left), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(161, dragoon::kScreen, Anchor::Center), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(159, dragoon::kScreen, Anchor::Center), Anchor::Left);
    EXPECT_EQ(dragoon::nearest_edge(479, dragoon::kScreen, Anchor::Center), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(481, dragoon::kScreen, Anchor::Center), Anchor::Right);
    EXPECT_EQ(dragoon::nearest_edge(374, dragoon::kScreen, Anchor::Right), Anchor::Right);
    EXPECT_EQ(dragoon::nearest_edge(373, dragoon::kScreen, Anchor::Right), Anchor::Center);
}

TEST(NearestEdge, PastItsBandAHeldEdgeGoesByTheThirds) {
    EXPECT_EQ(dragoon::nearest_edge(600, dragoon::kScreen, Anchor::Left), Anchor::Right);
    EXPECT_EQ(dragoon::nearest_edge(40, dragoon::kScreen, Anchor::Right), Anchor::Left);
}

TEST(NearestEdge, StretchHoldsNothing) {
    EXPECT_EQ(dragoon::nearest_edge(214, dragoon::kScreen, Anchor::Stretch), Anchor::Center);
    EXPECT_EQ(dragoon::nearest_edge(427, dragoon::kScreen, Anchor::Stretch), Anchor::Right);
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

TEST(EdgeMark, ALastMarkHoldsItsEdgeInItsOwnRect) {
    // x 105 is in the left third of player 1's view, whose line sits at 112.7, within a
    // quarter of a third of it.
    EXPECT_EQ(dragoon::edge_mark(105, 100, kFourViews, {Anchor::Center, 10, 318}), (Mark{Anchor::Center, 10, 318}));
    EXPECT_EQ(dragoon::edge_mark(105, 100, kFourViews, {Anchor::Center, 322, 630}), (Mark{Anchor::Left, 10, 318}));
}

TEST(EdgeMark, OnTheBarsALastMarkHoldsItsEdgeInTheScreen) {
    EXPECT_EQ(dragoon::edge_mark(250, 240, kFourViews, {Anchor::Left, 0, 640}), (Mark{Anchor::Left, 0, 640}));
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

TEST(MostCalled, ATieGoesToTheHeldMark) {
    const Mark left{Anchor::Left, 0, 640}, right{Anchor::Right, 0, 640};
    EXPECT_EQ(dragoon::most_called({right, left, right, left}, left), left);
    EXPECT_EQ(dragoon::most_called({left, right, left, right}, right), right);
}

TEST(MostCalled, AHeldMarkWithFewerCallsLoses) {
    const Mark left{Anchor::Left, 0, 640}, right{Anchor::Right, 0, 640};
    EXPECT_EQ(dragoon::most_called({right, left, right}, left), right);
}

TEST(MostCalled, AHeldMarkNoJointCallsForDoesntWin) {
    const Mark left{Anchor::Left, 0, 640}, right{Anchor::Right, 0, 640}, middle{Anchor::Center, 0, 640};
    EXPECT_EQ(dragoon::most_called({right, left}, middle), right);
}

constexpr uint32_t kRoot = 0x81200000, kOtherRoot = 0x81200400;
const Mark kLeft{Anchor::Left, 0, 640}, kMiddle{Anchor::Center, 0, 640}, kRight{Anchor::Right, 0, 640};

// On the screen the thirds' lines sit at 213.3 and 426.7, and a held edge reaches 53.3 past them.
// A tree holds nothing from its first showing, so a test that holds a mark from frame 10 first
// shows its tree at frame 9.
TEST(KeptMarks, AnElementMovingAcrossAThirdsLineKeepsItsEdge) {
    // Centered at x 425 a tree is C(0..640). At 427 it would be R(0..640), drawn about 109
    // display pixels further right at 16:9.
    ASSERT_EQ(dragoon::edge_mark(427, 100, {}), kRight);
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{425, 100}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{425, 100}}, {}), kMiddle);
    EXPECT_EQ(k.place(11, kRoot, {{427, 100}}, {}), kMiddle);
    EXPECT_EQ(k.place(12, kRoot, {{427, 100}}, {}), kMiddle);
}

TEST(KeptMarks, AnElementThatFirstShowsInTheMiddleSettlesAtItsEdge) {
    // As fn_80114F1C's speedometer does in the race: its joints first drew in the middle
    // third, and it sits in the right third from then on.
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}}, {}), kMiddle);
    EXPECT_EQ(k.place(11, kRoot, {{590, 400}}, {}), kRight);
}

TEST(KeptMarks, ATreeHoldsNothingFromItsFirstShowing) {
    // The race's speedometer frame from its first drawn frame, 3241, when its joints sat where
    // the game made them, at the screen's middle. From 3242 it draws at its place, one joint in
    // the right third and a joint at the middle, a tie, so the middle it held from 3241 kept it
    // there until it had rested 29 frames later.
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(3241, kRoot, {{320, 240}, {320, 240}}, {}), kMiddle);
    for (uint32_t f = 3242; f < 3290; f++)
        EXPECT_EQ(k.place(f, kRoot, {{578.4f, 408.8f}, {320, 240}}, {}), kRight) << f;
}

TEST(KeptMarks, AFrameWithNoJointPlacedDoesntLetAFirstShowingsMarkHold) {
    // The review's input: first shown with its joints at the middle, then scaled to nothing for
    // a frame, it takes its edge as soon as its joints draw at its place.
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(9, kRoot, {{320, 240}, {320, 240}}, {}), kMiddle);
    EXPECT_EQ(k.place(10, kRoot, {}, {}), kMiddle);
    for (uint32_t f = 11; f < 41; f++)
        EXPECT_EQ(k.place(f, kRoot, {{578.4f, 408.8f}, {320, 240}}, {}), kRight) << f;
}

TEST(KeptMarks, AnElementRestingInTheBandTakesItsNearestEdge) {
    // The review's input. Coming from the middle, a tree at 470 holds C while it moves there.
    // Once it has sat there 30 frames in a row it takes R, so it doesn't jump when it shows again
    // after missing a frame.
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{320, 400}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 40; f++) EXPECT_EQ(k.place(f, kRoot, {{470, 400}}, {}), kMiddle) << f;
    EXPECT_EQ(k.place(40, kRoot, {{470, 400}}, {}), kRight);
    EXPECT_EQ(k.place(42, kRoot, {{470, 400}}, {}), kRight);
}

TEST(KeptMarks, AMoveStartsTheRestAgain) {
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{320, 400}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 40; f++) k.place(f, kRoot, {{470, 400}}, {});
    for (uint32_t f = 40; f < 69; f++) EXPECT_EQ(k.place(f, kRoot, {{471, 400}}, {}), kMiddle) << f;
    EXPECT_EQ(k.place(69, kRoot, {{471, 400}}, {}), kRight);
}

TEST(KeptMarks, AFrameWithNoJointPlacedStartsTheRestAgain) {
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{320, 400}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 31; f++) k.place(f, kRoot, {{470, 400}}, {});
    EXPECT_EQ(k.place(31, kRoot, {}, {}), kMiddle);
    for (uint32_t f = 32; f < 61; f++) EXPECT_EQ(k.place(f, kRoot, {{470, 400}}, {}), kMiddle) << f;
    EXPECT_EQ(k.place(61, kRoot, {{470, 400}}, {}), kRight);
}

TEST(KeptMarks, AnElementMovingUpOrDownHasntRested) {
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{320, 400}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 60; f++) EXPECT_EQ(k.place(f, kRoot, {{470, 300.0f + f}}, {}), kMiddle) << f;
}

TEST(KeptMarks, ATreeRestsOnlyWhenAllItsJointsDo) {
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{320, 400}, {320, 400}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}, {320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 60; f++)
        EXPECT_EQ(k.place(f, kRoot, {{470, 400}, {470.0f + f % 2, 400}}, {}), kMiddle) << f;
}

TEST(KeptMarks, ARestedTreesTieGoesToTheFirstOfThoseTied) {
    // Shown in the middle, it moves to rest with its joints split between the right and the
    // middle, the right's first. It holds the middle while it moves and takes the right once it
    // has rested.
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{320, 400}, {320, 400}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}, {320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 40; f++)
        EXPECT_EQ(k.place(f, kRoot, {{500, 400}, {300, 400}}, {}), kMiddle) << f;
    EXPECT_EQ(k.place(40, kRoot, {{500, 400}, {300, 400}}, {}), kRight);
    EXPECT_EQ(k.place(41, kRoot, {{500, 400}, {300, 400}}, {}), kRight);
}

TEST(KeptMarks, ARestedTreesTieFollowsTheOrderItDrawsItsJoints) {
    // The middle's joint draws first, so the middle wins the tie once the tree has rested.
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}, {320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 60; f++)
        EXPECT_EQ(k.place(f, kRoot, {{300, 400}, {500, 400}}, {}), kMiddle) << f;
}

TEST(KeptMarks, JointsThatPulseAboutTheirMeanHaventRested) {
    // The review's pulse: the joints move out and back while their mean stays at 320.
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{215, 100}, {425, 100}}, {});
    for (uint32_t f = 10; f < 80; f++) {
        const std::vector<dragoon::Point> joints =
            f % 2 ? std::vector<dragoon::Point>{{212, 100}, {428, 100}} : std::vector<dragoon::Point>{{215, 100}, {425, 100}};
        EXPECT_EQ(k.place(f, kRoot, joints, {}), kMiddle) << f;
    }
}

TEST(KeptMarks, JointsThatSwapPlacesHaventRested) {
    // The review's swap: rested at the right, its two joints then trade places every frame.
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}, {320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 41; f++) k.place(f, kRoot, {{500, 400}, {300, 400}}, {});
    for (uint32_t f = 41; f < 80; f++) {
        const std::vector<dragoon::Point> joints =
            f % 2 ? std::vector<dragoon::Point>{{300, 400}, {500, 400}} : std::vector<dragoon::Point>{{500, 400}, {300, 400}};
        EXPECT_EQ(k.place(f, kRoot, joints, {}), kRight) << f;
    }
}

TEST(KeptMarks, AStillElementWithAJointThatBlinksNeverRests) {
    // Which joints are placed changes every frame, so it keeps the edge it came with.
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{320, 400}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{320, 400}}, {}), kMiddle);
    for (uint32_t f = 11; f < 200; f++) {
        const std::vector<dragoon::Point> joints =
            f % 2 ? std::vector<dragoon::Point>{{470, 400}, {470, 420}} : std::vector<dragoon::Point>{{470, 400}};
        EXPECT_EQ(k.place(f, kRoot, joints, {}), kMiddle) << f;
    }
}

TEST(KeptMarks, AJointThatHidesDoesntTurnTheVote) {
    // Two joints just left of the right third's line and three just right of it, then one of
    // the three hidden: a tie, which would go to the first, in the middle.
    ASSERT_EQ(dragoon::most_called({kMiddle, kMiddle, kRight, kRight}), kMiddle);
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{415, 100}, {420, 100}, {430, 100}, {435, 100}, {440, 100}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{415, 100}, {420, 100}, {430, 100}, {435, 100}, {440, 100}}, {}), kRight);
    EXPECT_EQ(k.place(11, kRoot, {{415, 100}, {420, 100}, {435, 100}, {440, 100}}, {}), kRight);
}

TEST(KeptMarks, ATieGoesToTheHeldEdge) {
    // Two joints at 300 and three at 500 call for R, and with the three at 400 they still do,
    // as R holds there. With one of those hidden it's a tie, which the first would take to C.
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{300, 100}, {300, 100}, {500, 100}, {500, 100}, {500, 100}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{300, 100}, {300, 100}, {500, 100}, {500, 100}, {500, 100}}, {}), kRight);
    EXPECT_EQ(k.place(11, kRoot, {{300, 100}, {300, 100}, {400, 100}, {400, 100}, {400, 100}}, {}), kRight);
    EXPECT_EQ(k.place(12, kRoot, {{300, 100}, {300, 100}, {400, 100}, {400, 100}}, {}), kRight);
    EXPECT_EQ(k.place(13, kRoot, {{300, 100}, {300, 100}, {400, 100}, {400, 100}, {400, 100}}, {}), kRight);
}

TEST(KeptMarks, ATreeThatMissesAFrameChoosesAgain) {
    dragoon::KeptMarks k;
    k.place(9, kRoot, {{200, 100}}, {});
    EXPECT_EQ(k.place(10, kRoot, {{200, 100}}, {}), kLeft);
    EXPECT_EQ(k.place(11, kRoot, {{230, 100}}, {}), kLeft);
    EXPECT_EQ(k.place(13, kRoot, {{230, 100}}, {}), kMiddle);
    // Its joints showed where they drew before the frame it missed, so it holds nothing from then.
    EXPECT_EQ(k.place(14, kRoot, {{200, 100}}, {}), kLeft);
}

TEST(KeptMarks, ATreeWithNoJointPlacedYetKeepsNothing) {
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(10, kRoot, {}, {}), std::nullopt);
    EXPECT_EQ(k.place(11, kRoot, {{230, 100}}, {}), kMiddle);
}

TEST(KeptMarks, ATreeHoldsTheMarkFromItsFirstFrameWithAJointPlaced) {
    // The review's input: its joints drew in the frame it showed with none placed, so the mark
    // they give in the frame after holds.
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(10, kRoot, {}, {}), std::nullopt);
    EXPECT_EQ(k.place(11, kRoot, {{425, 100}}, {}), kMiddle);
    EXPECT_EQ(k.place(12, kRoot, {{427, 100}}, {}), kMiddle);
}

TEST(KeptMarks, ATreesMarkHoldsWhileNoJointHasAPlace) {
    // As when the element is scaled to nothing, which leaves its joints' matrices all zero.
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(10, kRoot, {{600, 100}}, {}), kRight);
    EXPECT_EQ(k.place(11, kRoot, {}, {}), kRight);
}

TEST(KeptMarks, EachTreeAndEachTimeItShowsInAFrameKeepsItsOwn) {
    dragoon::KeptMarks k;
    for (uint32_t f = 9; f < 11; f++) {
        k.place(f, kRoot, {{200, 100}}, {});
        k.place(f, kOtherRoot, {{450, 100}}, {});
        k.place(f, kRoot, {{300, 100}}, {});
    }
    EXPECT_EQ(k.place(11, kRoot, {{230, 100}}, {}), kLeft);
    EXPECT_EQ(k.place(11, kOtherRoot, {{400, 100}}, {}), kRight);
    EXPECT_EQ(k.place(11, kRoot, {{470, 100}}, {}), kMiddle);
}

TEST(KeptMarks, AShowingWithNoJointPlacedStillCountsAsOne) {
    // A root shown twice a frame, first with no joint placed and then at x 600. Its second
    // showing holds R the next frame at 400, which on its own would be C.
    dragoon::KeptMarks k;
    k.place(9, kRoot, {}, {});
    k.place(9, kRoot, {{600, 100}}, {});
    EXPECT_EQ(k.place(10, kRoot, {}, {}), std::nullopt);
    EXPECT_EQ(k.place(10, kRoot, {{600, 100}}, {}), kRight);
    EXPECT_EQ(k.place(11, kRoot, {}, {}), std::nullopt);
    EXPECT_EQ(k.place(11, kRoot, {{400, 100}}, {}), kRight);
}

TEST(KeptMarks, ATreeGoesByItsView) {
    dragoon::KeptMarks k;
    EXPECT_EQ(k.place(10, kRoot, {{300, 100}}, kFourViews), (Mark{Anchor::Right, 10, 318}));
}

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

TEST(HudCallbacks, OnlyAPlacedCallbacksOutermostTreeIsPlaced) {
    dragoon::HudCallbacks h;
    EXPECT_FALSE(h.tree_begin());
    h.tree_end();
    h.enter(dragoon::Placement::Stretch);
    EXPECT_FALSE(h.tree_begin());
    h.tree_end();
    h.leave();
    h.enter(dragoon::Placement::Edge);
    EXPECT_TRUE(h.tree_begin());
    EXPECT_FALSE(h.tree_begin());
    h.tree_end();
    h.tree_end();
    EXPECT_TRUE(h.tree_begin());
}

TEST(HudCallbacks, WhatACallbackDrawsAfterATreeIsStretched) {
    // A centered text tree, then a full-width stripe the callback draws itself, which stretches
    // as a draw outside every callback does.
    dragoon::HudCallbacks h;
    const Mark centered{Anchor::Center, 0, 640};
    h.enter(dragoon::Placement::Edge);
    ASSERT_TRUE(h.tree_begin());
    h.set_mark(centered);
    h.tree_begin();
    h.tree_end();
    EXPECT_EQ(h.mark(), centered);
    h.tree_end();
    EXPECT_EQ(h.mark(), Mark{});
}

// The menus' cameras as the census found them on the title, the mode select and the course select.
Lens narrow(float fov) { return lens(dragoon::kPerspective, fov, 1.25538f, 0, 0); }

TEST(MenuCamera, TheNarrowCameraOverTheScreen) {
    EXPECT_TRUE(dragoon::menu_camera(narrow(25)));
    EXPECT_TRUE(dragoon::menu_camera(narrow(30)));
}

TEST(MenuCamera, TheSixFortyByFourEightyFrameEitherWayUp) {
    EXPECT_TRUE(dragoon::menu_camera(lens(dragoon::kOrtho, 0, -480, 0, 640)));  // the text library's
    EXPECT_TRUE(dragoon::menu_camera(lens(dragoon::kOrtho, 0, 480, 0, 640)));   // the opening movie's
}

TEST(MenuCamera, NotAWorldCamera) {
    EXPECT_FALSE(dragoon::menu_camera(lens(dragoon::kPerspective, 78, 1.67383f, 0, 0)));  // the race's at 16:9
    EXPECT_FALSE(dragoon::menu_camera(lens(dragoon::kPerspective, 30, 1.18f, 0, 0)));     // Top Ride's at 4:3
    EXPECT_FALSE(dragoon::menu_camera(lens(dragoon::kPerspective, 30, 1.57333f, 0, 0)));  // and at 16:9
}

TEST(MenuCamera, NotTheOtherFrames) {
    EXPECT_FALSE(dragoon::menu_camera(lens(dragoon::kPerspective, 60, 1.33333f, 0, 0)));
    EXPECT_FALSE(dragoon::menu_camera(hud_frame()));
    EXPECT_FALSE(dragoon::menu_camera(lens(dragoon::kOrtho, -20, 500, -20, 660)));
    EXPECT_FALSE(dragoon::menu_camera(lens(dragoon::kFrustum, 0, -480, 0, 640)));
}

TEST(MenuCamera, NotTheRenderToTexture) {
    Lens l = lens(dragoon::kOrtho, 0, 192, 0, 256);
    l.viewport[1] = 256;
    l.viewport[3] = 192;
    EXPECT_FALSE(dragoon::menu_camera(l));
}

TEST(MenuCamera, NotOverOneView) {
    Lens l = narrow(25);
    l.viewport[0] = 10;
    l.viewport[1] = 318;
    l.viewport[2] = 16;
    l.viewport[3] = 224;
    EXPECT_FALSE(dragoon::menu_camera(l));
}

TEST(MenuCamera, EachSideOfTheViewportCounts) {
    for (int i = 0; i < 4; i++) {
        Lens p = narrow(25), o = lens(dragoon::kOrtho, 0, -480, 0, 640);
        p.viewport[i] += 1;
        o.viewport[i] += 1;
        EXPECT_FALSE(dragoon::menu_camera(p)) << "side " << i;
        EXPECT_FALSE(dragoon::menu_camera(o)) << "side " << i;
    }
}

TEST(MenuCamera, EachValueOfTheFrameCounts) {
    for (int i = 0; i < 4; i++) {
        Lens o = lens(dragoon::kOrtho, 0, -480, 0, 640);
        o.proj[i] += 1;
        EXPECT_FALSE(dragoon::menu_camera(o)) << "value " << i;
    }
}

TEST(MenuCamera, TheNarrowAspectToWithinATenThousandth) {
    Lens l = narrow(25);
    l.proj[1] = 1.25538f + 0.00005f;
    EXPECT_TRUE(dragoon::menu_camera(l));
    l.proj[1] = 1.25538f - 0.00005f;
    EXPECT_TRUE(dragoon::menu_camera(l));
    l.proj[1] = 1.25538f + 0.0002f;
    EXPECT_FALSE(dragoon::menu_camera(l));
    l.proj[1] = 1.25538f - 0.0002f;
    EXPECT_FALSE(dragoon::menu_camera(l));
}

constexpr float kWide = 16.0f / 9.0f;

TEST(CameraMark, AMenuCameraCentersTheFrameWhileNoWorldIsShown) {
    const Mark frame{Anchor::Center, 0, 640};
    EXPECT_EQ(dragoon::kMenuFrame, frame);
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {}, kWide), frame);
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {dragoon::kScreen}, kWide), Mark{});
    EXPECT_EQ(dragoon::camera_mark(narrow(25), kFourViews, kWide), Mark{});
    EXPECT_EQ(dragoon::camera_mark(hud_frame(), {}, kWide), Mark{});
}

TEST(CameraMark, NoneAtFourByThree) {
    // A mark pads the write-gather pipe, which moves the movies' frames, and at 4:3 it would
    // anchor nothing.
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {}, 4.0f / 3.0f), Mark{});
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {}, 0.0f), Mark{});
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {}, 21.0f / 9.0f), dragoon::kMenuFrame);
}

TEST(CameraMark, NoneAtANarrowerOutput) {
    // Centered at 1:1 the frame would widen by 4/3 and lose about 107 of its 640 at each side.
    // Stretched, it all shows, squeezed.
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {}, 1.0f), Mark{});
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {}, 3.0f / 4.0f), Mark{});
    EXPECT_EQ(dragoon::camera_mark(lens(dragoon::kOrtho, 0, -480, 0, 640), {}, 1.0f), Mark{});
    EXPECT_EQ(dragoon::camera_mark(narrow(25), {}, 1.34f), dragoon::kMenuFrame);
}

// After the race's finish the world camera that's drawn gets its aspect once, at frame 8,092.
// The camera module still sets eight others over the screen each frame to 13,061, so each frame
// has the screen as a view and the narrow HUD 3D camera marks nothing, as at 8,400.
TEST(CameraMark, TheRaceAfterItsFinishKeepsTheModulesView) {
    dragoon::WorldViews w;
    for (uint32_t f = 8093; f <= 8400; f++) {
        for (int cam = 0; cam < 8; cam++) w.add(f, dragoon::kScreen);
        EXPECT_EQ(dragoon::camera_mark(narrow(25), w.at(f), kWide), Mark{}) << "frame " << f;
        EXPECT_EQ(dragoon::camera_mark(narrow(25), w.at(f + 1), kWide), Mark{}) << "frame " << f + 1;
    }
}

TEST(HudCallbacks, AStretchedCallbackTakesTheCamerasMark) {
    dragoon::HudCallbacks h;
    h.set_camera(dragoon::kMenuFrame);
    EXPECT_EQ(h.mark(), Mark{});  // outside every callback
    h.enter(dragoon::Placement::Stretch);
    EXPECT_EQ(h.mark(), dragoon::kMenuFrame);
    h.leave();
    EXPECT_EQ(h.mark(), Mark{});
    h.set_camera({});
    h.enter(dragoon::Placement::Stretch);
    EXPECT_EQ(h.mark(), Mark{});
}

TEST(HudCallbacks, APlacedCallbackIgnoresTheCamerasMark) {
    dragoon::HudCallbacks h;
    h.set_camera(dragoon::kMenuFrame);
    h.enter(dragoon::Placement::Edge);
    EXPECT_EQ(h.mark(), Mark{});
    h.set_camera(dragoon::kMenuFrame);
    EXPECT_EQ(h.mark(), Mark{});
    ASSERT_TRUE(h.tree_begin());
    h.set_mark({Anchor::Right, 0, 640});
    h.tree_end();
    EXPECT_EQ(h.mark(), Mark{});
    h.enter(dragoon::Placement::Stretch);  // nested in it
    EXPECT_EQ(h.mark(), dragoon::kMenuFrame);
}

TEST(HudCallbacks, ACameraMadeCurrentInAStretchedCallbackMarksWhatFollows) {
    dragoon::HudCallbacks h;
    h.enter(dragoon::Placement::Stretch);
    h.set_camera(dragoon::kMenuFrame);
    EXPECT_EQ(h.mark(), dragoon::kMenuFrame);
    h.set_camera({});
    EXPECT_EQ(h.mark(), Mark{});
    h.leave();
    h.set_camera(dragoon::kMenuFrame);
    EXPECT_EQ(h.mark(), Mark{});
}

TEST(HudCallbacks, AStretchedCallbacksTreesKeepTheCamerasMark) {
    dragoon::HudCallbacks h;
    h.set_camera(dragoon::kMenuFrame);
    h.enter(dragoon::Placement::Stretch);
    EXPECT_FALSE(h.tree_begin());
    h.tree_end();
    EXPECT_EQ(h.mark(), dragoon::kMenuFrame);
}

// Top Ride on Grass at frame 3,600: its 38 HUD draws go through fov 25 cameras at 1.25538 over
// the screen, and no world camera gives the frame a view, so the camera's mark is the 4:3 frame.
// But Top Ride makes them current and draws its HUD outside every render callback, so nothing is
// marked and the HUD stretches, its joint trees included.
TEST(HudCallbacks, TopRidesHudOutsideEveryCallbackStretches) {
    dragoon::HudCallbacks h;
    const Mark m = dragoon::camera_mark(narrow(25), {}, kWide);
    ASSERT_EQ(m, dragoon::kMenuFrame);
    h.set_camera(m);
    EXPECT_EQ(h.mark(), Mark{});
    EXPECT_FALSE(h.tree_begin());
    EXPECT_EQ(h.mark(), Mark{});
    h.tree_end();
    EXPECT_EQ(h.mark(), Mark{});
}

}  // namespace
