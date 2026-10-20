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
