// The pipe's padding before a mark (src/draw_marks.h).
#include "draw_marks.h"
#include <gtest/gtest.h>

namespace {

TEST(PaddingFor, FinishesThePipesLine) {
    EXPECT_EQ(dragoon::padding_for(1), 31u);
    EXPECT_EQ(dragoon::padding_for(31), 1u);
    EXPECT_EQ(dragoon::padding_for(45), 19u);
}

TEST(PaddingFor, NoneForAnEmptyOrFullLine) {
    EXPECT_EQ(dragoon::padding_for(0), 0u);
    EXPECT_EQ(dragoon::padding_for(32), 0u);
    EXPECT_EQ(dragoon::padding_for(64), 0u);
}

}  // namespace
