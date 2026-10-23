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
  FPS 60)

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
    COMMENT "Warming up shaders, about a minute the first time on an M4 Max"
    USES_TERMINAL VERBATIM)
endif()
