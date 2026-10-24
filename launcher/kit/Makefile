# The player's half of the prebuilt engine: compiles the recompiled game's C in ./gen and links
# it with this kit's engine and SDL, using Apple's Command Line Tools alone. Run it in the
# directory that holds gen/:
#   make -f <kit>/Makefile -j<cores> KIT=<kit> SDK=<MacOSX.sdk> CC=<clang> CXX=<clang++>
# Objects go to obj/ and the game to ./dragoon. The compile and link flags, the frameworks and
# the libraries come from kit.mk, which tools/engine_kit.py writes from what gcn-recomp's CMake
# builds the game with.
# KIT is named on the command line, since make splits the Makefile's own path at its spaces.
# Make reads KITQ, KIT with each space escaped, and the shell reads "$(KIT)".
ifndef KIT
$(error KIT isn't set: make -f <kit>/Makefile KIT=<kit> SDK=<path to MacOSX.sdk>)
endif
space := $(subst x, ,x)
KITQ := $(subst $(space),\ ,$(KIT))
include $(KITQ)/kit.mk
ifndef SDK
$(error SDK isn't set: make -f <kit>/Makefile KIT=<kit> SDK=<path to MacOSX.sdk>)
endif
OBJS := $(patsubst gen/%.c,obj/%.o,$(wildcard gen/*.c))
ifeq ($(OBJS),)
$(error no gen/*.c here: run make in the directory recomp.py wrote gen/ into)
endif
TARGET := -arch arm64 -isysroot "$(SDK)" -mmacosx-version-min=$(MACOSX_MIN)

dragoon: $(OBJS) $(KITQ)/engine.o $(KITQ)/libSDL3.a
	$(CXX) $(LINK_FLAGS) $(TARGET) -o $@ $(OBJS) "$(KIT)/engine.o" "$(KIT)/libSDL3.a" $(GAME_LIBS)

obj/%.o: gen/%.c | obj
	$(CC) $(TARGET) $(GAME_CFLAGS) -I"$(KIT)/include" -Igen -c $< -o $@

obj:
	mkdir $@
