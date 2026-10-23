// The census line and its once-a-frame filter (src/census.h).
#include "census.h"
#include <gtest/gtest.h>

namespace {

dragoon::Camera perspective(float fov, float aspect) {
    dragoon::Camera c;
    c.type = dragoon::kPerspective;
    c.proj[0] = fov;
    c.proj[1] = aspect;
    c.viewport[1] = 640;
    c.viewport[3] = 480;
    return c;
}

TEST(CensusLine, PerspectiveCameraShowsFovAndAspect) {
    EXPECT_EQ(dragoon::census_line(4200, 0x8123A0C0, perspective(30, 1.2554f), 0x800F1234, 12, "draw"),
              "[census] f=4200 cam=8123A0C0 type=persp p=30,1.2554 vp=0,640,0,480 cb=800F1234 cls=12 via=draw");
}

TEST(CensusLine, OrthographicCameraShowsItsFrame) {
    dragoon::Camera c;
    c.type = dragoon::kOrtho;
    c.proj[0] = 0;
    c.proj[1] = -480;
    c.proj[2] = 0;
    c.proj[3] = 640;
    c.viewport[1] = 640;
    c.viewport[3] = 480;
    EXPECT_EQ(dragoon::census_line(7, 0x80001000, c, 0, 0, "set"),
              "[census] f=7 cam=80001000 type=ortho p=0,-480,0,640 vp=0,640,0,480 cb=00000000 cls=0 via=set");
}

TEST(CensusLine, UnknownTypeLeavesTheProjectionEmpty) {
    dragoon::Camera c;
    c.type = 9;
    EXPECT_EQ(dragoon::census_line(1, 0x80000020, c, 0x80000040, 3, "draw"),
              "[census] f=1 cam=80000020 type=none p= vp=0,0,0,0 cb=80000040 cls=3 via=draw");
}

TEST(OncePerFrame, RepeatInAFrameIsDropped) {
    dragoon::OncePerFrame once;
    EXPECT_TRUE(once.first(5, "a"));
    EXPECT_TRUE(once.first(5, "b"));
    EXPECT_FALSE(once.first(5, "a"));
}

TEST(OncePerFrame, NewFrameLetsItThroughAgain) {
    dragoon::OncePerFrame once;
    EXPECT_TRUE(once.first(5, "a"));
    EXPECT_TRUE(once.first(6, "a"));
    EXPECT_FALSE(once.first(6, "a"));
}

}  // namespace
