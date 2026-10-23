cmake_minimum_required(VERSION 3.20)
project(dragoon C CXX)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

# The recompiler, the GameCube runtime, the renderer and the frontends are gcn-recomp, a
# submodule pinned to the dragoon branch of lunchbox-recomp/gcn-recomp. Only Kirby Air
# Ride's own tables and code live in this repository.
add_subdirectory(gcn-recomp)

gcn_add_game(
  NAME dragoon
  TITLE "Kirby Air Ride"
  LABEL "Dragoon"
  DISC_ID GKYE01
  DOL_SHA1 977533bb96e6a16e127946396489be1b4164ac42
  SYMBOLS ${CMAKE_SOURCE_DIR}/analysis/symbols.txt
  TABLES ${CMAKE_SOURCE_DIR}/recomp
  FPS 60
  SOURCES ${CMAKE_SOURCE_DIR}/src/census.cpp ${CMAKE_SOURCE_DIR}/src/cameras.cpp)

# The unit tests of src/'s pure parts, run by ctest. Off by default, since they download
# GoogleTest's source release, checked by its SHA-256. They need no disc.
option(DRAGOON_TESTS "Build the unit tests of src/ (downloads GoogleTest)" OFF)
if(DRAGOON_TESTS)
  include(FetchContent)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(googletest
    URL https://github.com/google/googletest/releases/download/v1.17.0/googletest-1.17.0.tar.gz
    URL_HASH SHA256=65fab701d9829d38cb77c14acdc431d2108bfdbf8979e40eb8ae567edf10b27c
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
  FetchContent_MakeAvailable(googletest)
  enable_testing()
  include(GoogleTest)
  add_executable(dragoon_tests ${CMAKE_SOURCE_DIR}/tests/src/test_census.cpp
                               ${CMAKE_SOURCE_DIR}/tests/src/test_cameras.cpp)
  set_target_properties(dragoon_tests PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
  target_include_directories(dragoon_tests PRIVATE ${CMAKE_SOURCE_DIR}/src)
  target_link_libraries(dragoon_tests PRIVATE GTest::gtest_main)
  gtest_discover_tests(dragoon_tests)
endif()

# Play the game once, hidden and silent, so a player's first session doesn't stall on shader
# compiles. It runs again only when the engine pin, the route list or a route changes. It
# needs the game, so a configure with no disc has no such target, and it runs the game on
# the build host, so a cross build has none either.
option(DRAGOON_WARMUP "Warm the shader cache after the build" ON)
if(DRAGOON_WARMUP AND TARGET dragoon AND NOT CMAKE_CROSSCOMPILING)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_custom_target(dragoon_warmup ALL
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/warm_shaders.py
            --game $<TARGET_FILE:dragoon> --saves ${CMAKE_SOURCE_DIR}/saves
    DEPENDS dragoon
    COMMENT "Warming up shaders, about a minute the first time"
    USES_TERMINAL VERBATIM)
endif()
