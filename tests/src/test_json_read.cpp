// JSON read into a tree (src/json_read.h).
#include "json_read.h"
#include <gtest/gtest.h>

namespace {

using dragoon::Json;
using dragoon::json_read;

Json read(const std::string& text) {
    Json j;
    EXPECT_TRUE(json_read(text, j)) << text;
    return j;
}

bool refused(const std::string& text) {
    Json j;
    return !json_read(text, j);
}

TEST(JsonRead, ReadsAnObjectInOrder) {
    const Json j = read(" {\"b\": [1, true, null], \"a\": {\"c\": false}}\n");
    ASSERT_EQ(j.type, Json::Type::object);
    ASSERT_EQ(j.object.size(), 2u);
    EXPECT_EQ(j.object[0].first, "b");
    EXPECT_EQ(j.object[1].first, "a");
    const Json* b = j.get("b");
    ASSERT_NE(b, nullptr);
    ASSERT_EQ(b->array.size(), 3u);
    EXPECT_EQ(b->array[0].type, Json::Type::number);
    EXPECT_EQ(b->array[0].number, 1);
    EXPECT_EQ(b->array[1].type, Json::Type::boolean);
    EXPECT_TRUE(b->array[1].boolean);
    EXPECT_EQ(b->array[2].type, Json::Type::null);
    const Json* c = j.get("a")->get("c");
    ASSERT_NE(c, nullptr);
    EXPECT_EQ(c->type, Json::Type::boolean);
    EXPECT_FALSE(c->boolean);
    EXPECT_EQ(j.get("d"), nullptr);
    EXPECT_EQ(b->get("b"), nullptr);
}

TEST(JsonRead, ReadsEmptyContainers) {
    EXPECT_EQ(read("{}").type, Json::Type::object);
    EXPECT_EQ(read("[ ]").type, Json::Type::array);
    EXPECT_TRUE(read("[]").array.empty());
}

TEST(JsonRead, ReadsNumbers) {
    EXPECT_EQ(read("0").number, 0);
    EXPECT_EQ(read("-12").number, -12);
    EXPECT_EQ(read("41").number, 41);
    EXPECT_EQ(read("2.5").number, 2.5);
    EXPECT_EQ(read("1e3").number, 1000);
    EXPECT_EQ(read("-1.5E-1").number, -0.15);
}

TEST(JsonRead, RefusesNumbersOutsideTheGrammar) {
    EXPECT_TRUE(refused("01"));
    EXPECT_TRUE(refused("+1"));
    EXPECT_TRUE(refused("1."));
    EXPECT_TRUE(refused(".5"));
    EXPECT_TRUE(refused("1e"));
    EXPECT_TRUE(refused("-"));
    EXPECT_TRUE(refused("0x10"));
}

TEST(JsonRead, ReadsEscapes) {
    EXPECT_EQ(read("\"a\\\"b\\\\c\\/d\"").string, "a\"b\\c/d");
    EXPECT_EQ(read("\"\\b\\f\\n\\r\\t\"").string, "\b\f\n\r\t");
}

TEST(JsonRead, TurnsUnicodeEscapesIntoUtf8) {
    EXPECT_EQ(read("\"\\u0041\"").string, "A");
    EXPECT_EQ(read("\"\\u00e9\"").string, "\xC3\xA9");
    EXPECT_EQ(read("\"\\u30ab\"").string, "\xE3\x82\xAB");
    EXPECT_EQ(read("\"\\uD83D\\uDE00\"").string, "\xF0\x9F\x98\x80");
}

TEST(JsonRead, KeepsUtf8AsItIs) {
    EXPECT_EQ(read("\"\xC3\xA9\"").string, "\xC3\xA9");
}

TEST(JsonRead, RefusesBadStrings) {
    EXPECT_TRUE(refused("\"open"));
    EXPECT_TRUE(refused("\"a\nb\""));
    EXPECT_TRUE(refused("\"\\x\""));
    EXPECT_TRUE(refused("\"\\u12\""));
    EXPECT_TRUE(refused("\"\\u12G4\""));
    EXPECT_TRUE(refused("\"\\uD83D\""));
    EXPECT_TRUE(refused("\"\\uD83Dx\""));
    EXPECT_TRUE(refused("\"\\uD83D\\u0041\""));
    EXPECT_TRUE(refused("\"\\uDE00\""));
    // A NUL would cut the string short wherever it's used as a C string.
    EXPECT_TRUE(refused("\"a\\u0000b\""));
}

TEST(JsonRead, RefusesBadStructure) {
    EXPECT_TRUE(refused(""));
    EXPECT_TRUE(refused("   "));
    EXPECT_TRUE(refused("{\"a\": 1,}"));
    EXPECT_TRUE(refused("[1,]"));
    EXPECT_TRUE(refused("[1 2]"));
    EXPECT_TRUE(refused("{\"a\" 1}"));
    EXPECT_TRUE(refused("{1: 2}"));
    EXPECT_TRUE(refused("{\"a\": 1"));
    EXPECT_TRUE(refused("[1"));
    EXPECT_TRUE(refused("tru"));
    EXPECT_TRUE(refused("nul"));
    EXPECT_TRUE(refused("{} {}"));
    EXPECT_TRUE(refused("1 x"));
}

TEST(JsonRead, RefusesNestingPastTheLimit) {
    const int deep = dragoon::kJsonMaxDepth;
    EXPECT_FALSE(refused(std::string(deep, '[') + std::string(deep, ']')));
    EXPECT_TRUE(refused(std::string(deep + 1, '[') + std::string(deep + 1, ']')));
    std::string objects, ends;
    for (int i = 0; i < deep; i++) {
        objects += "{\"a\": ";
        ends += "}";
    }
    EXPECT_FALSE(refused(objects + "1" + ends));
    EXPECT_TRUE(refused("{\"a\": " + objects + "1" + ends + "}"));
    EXPECT_TRUE(refused("[" + objects + "1" + ends + "]"));
}

}  // namespace
