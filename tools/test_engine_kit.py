"""engine_kit.py on a no-disc build made of tiny objects, and the kit's Makefile under the Command
Line Tools' make with compilers that record what they're asked to do."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import engine_kit
from testutil import run_main, write_file

CC = "/usr/bin/cc"
AR = "/usr/bin/ar"
NM = "/usr/bin/nm"
MAKE = "/usr/bin/make"
FLAGS = ("-O2 -g -DNDEBUG -std=gnu11 -O2 -fno-strict-aliasing -Wno-unused-label "
         "-ffp-contract=off -gline-tables-only")
LDFLAGS = "-O2 -g -DNDEBUG -Wl,-search_paths_first -Wl,-headerpad_max_install_names"
LIBS = "-framework OpenGL -lm -Xlinker -weak_framework -Xlinker CoreHaptics -lpthread"
SDK = "/Applications/Xcode 26.5.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
RUNTIME = "CMakeFiles/runtime_check.dir/gcn-recomp/runtime"
NINJA = f"""build {RUNTIME}/a.cpp.o: CXX_COMPILER__runtime_check_unscanned_RelWithDebInfo a.cpp
  FLAGS = -O2 -g
build {RUNTIME}/hw/b.cpp.o: CXX_COMPILER__runtime_check_unscanned_RelWithDebInfo b.cpp
build CMakeFiles/gcn_core.dir/gcn-recomp/runtime/a.cpp.o: CXX_COMPILER__gcn_core a.cpp
"""


def compile_c(source: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    src = write_file(out.parent, out.name + ".c", source)
    subprocess.run([CC, "-g", "-O2", "-c", str(src), "-o", str(out)], check=True)
    src.unlink()
    return out


def fake_build(root: Path, disc: str = "", target: str = "14.0") -> Path:
    """A no-disc build as CMake and Ninja leave it, runtime_check's two objects compiled from
    one-line C with debug info, beside the gcn-recomp and SDL sources its cache names."""
    build, engine, sdl = root / "build", root / "gcn-recomp", root / "sdl"
    sdl_build = build / "_deps" / "sdl3-build"
    for path, text in {engine / "LICENSE": "MIT gcn-recomp\n",
                       engine / "runtime" / "recomp.h": "/* recomp */\n",
                       engine / "runtime" / "compat.h": "/* compat */\n",
                       sdl / "LICENSE.txt": "zlib SDL\n",
                       sdl / "src" / "hidapi" / "LICENSE-bsd.txt": "BSD hidapi\n"}.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    compile_c("int engine_a(int x) { return x + 1; }\n", build / RUNTIME / "a.cpp.o")
    compile_c("int engine_b(int x) { return x * 2; }\n", build / RUNTIME / "hw" / "b.cpp.o")
    sdl_obj = compile_c("int SDL_Fake(void) { return 3; }\n", sdl_build / "fake.o")
    subprocess.run([AR, "rcs", str(sdl_build / "libSDL3.a"), str(sdl_obj)], check=True)
    write_file(build, "CMakeCache.txt",
               f"GAME_ISO:FILEPATH={disc}\nCMAKE_OSX_DEPLOYMENT_TARGET:STRING={target}\n"
               f"gcn_recomp_SOURCE_DIR:STATIC={engine}\nSDL3_SOURCE_DIR:STATIC={sdl}\n"
               f"SDL3_BINARY_DIR:STATIC={sdl_build}\n")
    write_file(build, "build.ninja", NINJA)
    write_file(build, "game_cflags.txt", FLAGS + "\n")
    write_file(build, "game_ldflags.txt", LDFLAGS + "\n")
    write_file(build, "game_libs.txt", LIBS + "\n")
    return build


class EngineKitTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.out = self.root / "the kit"

    def kit(self, build: Path, *extra: str) -> tuple[int, str, str]:
        return run_main(engine_kit.main, "--build", str(build), "--out", str(self.out), *extra)

    def assert_refused(self, build: Path, message: str) -> None:
        code, _, err = self.kit(build)
        self.assertEqual(code, 2)
        self.assertIn(message, err)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["build", "gcn-recomp", "sdl"])

    def test_kit_holds_the_engine_sdl_headers_flags_makefile_and_licenses(self) -> None:
        build = fake_build(self.root)
        code, out, err = self.kit(build)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.strip(), str(self.out))
        defined = subprocess.run([NM, "-g", "--defined-only", str(self.out / "engine.o")],
                                 capture_output=True, text=True, check=True).stdout
        self.assertEqual(sorted(line.split()[-1] for line in defined.splitlines()),
                         ["_engine_a", "_engine_b"])
        copies = {"libSDL3.a": build / "_deps/sdl3-build/libSDL3.a",
                  "Makefile": engine_kit.MAKEFILE,
                  "include/recomp.h": self.root / "gcn-recomp/runtime/recomp.h",
                  "include/compat.h": self.root / "gcn-recomp/runtime/compat.h",
                  "licenses/gcn-recomp.txt": self.root / "gcn-recomp/LICENSE",
                  "licenses/SDL3.txt": self.root / "sdl/LICENSE.txt",
                  "licenses/hidapi.txt": self.root / "sdl/src/hidapi/LICENSE-bsd.txt"}
        for rel, src in copies.items():
            self.assertEqual((self.out / rel).read_bytes(), src.read_bytes(), rel)
        mk = (self.out / "kit.mk").read_text().splitlines()
        self.assertEqual(mk[-4:], [f"GAME_CFLAGS := {FLAGS}", f"LINK_FLAGS := {LDFLAGS}",
                                   f"GAME_LIBS := {LIBS}", "MACOSX_MIN := 14.0"])
        self.assertEqual(sorted(str(p.relative_to(self.out)) for p in self.out.rglob("*") if p.is_file()),
                         sorted(["engine.o", "kit.mk", *copies]))

    def test_strip_debug_drops_the_debug_map_and_sdls_dwarf(self) -> None:
        build = fake_build(self.root)
        self.assertEqual(self.kit(build)[0], 0)
        as_built = {name: (self.out / name).read_bytes() for name in ("engine.o", "libSDL3.a")}
        self.assertIn(str(build / RUNTIME / "a.cpp.o").encode(), as_built["engine.o"])
        self.assertIn(b"__debug_info", as_built["libSDL3.a"])
        self.out.rename(self.root / "unstripped")
        self.assertEqual(self.kit(build, "--strip-debug")[0], 0)
        engine, sdl = (self.out / "engine.o").read_bytes(), (self.out / "libSDL3.a").read_bytes()
        self.assertNotIn(str(build / RUNTIME).encode(), engine)
        self.assertNotIn(b"__debug_info", sdl)
        self.assertLess(len(engine), len(as_built["engine.o"]))
        self.assertIn(b"_engine_b", engine)

    def test_refuses_a_build_with_a_disc(self) -> None:
        self.assert_refused(fake_build(self.root, disc="/discs/game.iso"), "GAME_ISO=/discs/game.iso")

    def test_refuses_a_build_without_a_deployment_target(self) -> None:
        self.assert_refused(fake_build(self.root, target=""), "no CMAKE_OSX_DEPLOYMENT_TARGET")

    def test_refuses_a_gcn_recomp_that_writes_no_flags(self) -> None:
        build = fake_build(self.root)
        (build / "game_cflags.txt").unlink()
        self.assert_refused(build, "game_cflags.txt is missing: this gcn-recomp doesn't write the game's flags")

    def test_refuses_a_build_missing_either_link_file(self) -> None:
        for name in ("game_ldflags.txt", "game_libs.txt"):
            with self.subTest(name):
                build = fake_build(self.root)
                (build / name).unlink()
                self.assert_refused(build, f"{name} is missing: this gcn-recomp doesn't write the game's"
                                           " link, or the configure warned that it couldn't")

    def test_refuses_an_empty_link_file(self) -> None:
        build = fake_build(self.root)
        write_file(build, "game_libs.txt", "\n")
        self.assert_refused(build, "game_libs.txt is empty")

    def test_refuses_libraries_named_by_path(self) -> None:
        build = fake_build(self.root)
        write_file(build, "game_libs.txt", "-framework Cocoa /opt/homebrew/lib/libSDL3.dylib -lm\n")
        self.assert_refused(build, "names /opt/homebrew/lib/libSDL3.dylib, a path a player's Mac may not have")

    def test_refuses_flags_make_would_read_differently(self) -> None:
        for name in ("game_cflags.txt", "game_ldflags.txt", "game_libs.txt"):
            with self.subTest(name):
                build = fake_build(self.root)
                write_file(build, name, "-O2 -DX=$(Y)\n")
                self.assert_refused(build, f"{name} isn't one line of flags make can take")

    def test_refuses_runtime_check_unbuilt(self) -> None:
        build = fake_build(self.root)
        (build / RUNTIME / "hw" / "b.cpp.o").unlink()
        self.assert_refused(build, "1 of 2 objects are missing")

    def test_refuses_an_out_that_exists(self) -> None:
        build = fake_build(self.root)
        self.out.mkdir()
        code, _, err = self.kit(build)
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_a_failed_ld_leaves_no_kit(self) -> None:
        build = fake_build(self.root)
        code, _, err = self.kit(build, "--ld", "/usr/bin/false")
        self.assertEqual(code, 1)
        self.assertIn("false exited 1", err)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["build", "gcn-recomp", "sdl"])


# Stands in for clang and clang++: records its arguments, then writes its -o.
FAKE_COMPILER = """#!{python}
import json, sys
args = sys.argv[1:]
with open({records!r}, "a") as f:
    f.write(json.dumps({{"tool": {tool!r}, "argv": args}}) + "\\n")
open(args[args.index("-o") + 1], "w").close()
"""


class KitMakefileTest(unittest.TestCase):
    """A kit engine_kit.py made, used where a player's would be: under paths with spaces."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.kit, self.work, self.records = root / "the kit", root / "Application Support", root / "records"
        code, _, err = run_main(engine_kit.main, "--build", str(fake_build(root)), "--out", str(self.kit))
        self.assertEqual((code, err), (0, ""))
        (self.work / "gen").mkdir(parents=True)
        for name in ("recomp_000.c", "recomp_001.c", "recomp_table.c"):
            write_file(self.work / "gen", name, "")
        write_file(self.work / "gen", "recomp_funcs.h", "")
        self.cc, self.cxx = (self.fake(root, tool) for tool in ("cc", "cxx"))

    def fake(self, root: Path, tool: str) -> Path:
        path = write_file(root, tool, FAKE_COMPILER.format(python=sys.executable,
                                                           records=str(self.records), tool=tool))
        path.chmod(0o755)
        return path

    def make(self, *args: str, kit: bool = True) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "KIT", "SDK")}
        return subprocess.run([MAKE, "-f", str(self.kit / "Makefile"), f"CC={self.cc}", f"CXX={self.cxx}",
                               *([f"KIT={self.kit}"] if kit else []), *args],
                              cwd=self.work, env=env, capture_output=True, text=True)

    def calls(self) -> list[dict]:
        if not self.records.exists():
            return []
        calls = [json.loads(line) for line in self.records.read_text().splitlines()]
        self.records.unlink()
        return calls

    def test_compiles_each_file_with_the_kits_flags_then_links_once(self) -> None:
        done = self.make("-j4", f"SDK={SDK}")
        self.assertEqual(done.returncode, 0, done.stderr)
        target = ["-arch", "arm64", "-isysroot", SDK, "-mmacosx-version-min=14.0"]
        calls = self.calls()
        compiles = sorted((c["argv"] for c in calls if c["tool"] == "cc"), key=lambda a: a[-1])
        stems = ["recomp_000", "recomp_001", "recomp_table"]
        self.assertEqual(compiles, [target + shlex.split(FLAGS) + [f"-I{self.kit}/include", "-Igen", "-c",
                                    f"gen/{s}.c", "-o", f"obj/{s}.o"] for s in stems])
        self.assertEqual(calls[-1]["tool"], "cxx")
        self.assertEqual(sum(c["tool"] == "cxx" for c in calls), 1)
        self.assertEqual(calls[-1]["argv"], shlex.split(LDFLAGS) + target + ["-o", "dragoon"]
                         + [f"obj/{s}.o" for s in stems] + [f"{self.kit}/engine.o", f"{self.kit}/libSDL3.a"]
                         + shlex.split(LIBS))
        self.assertTrue((self.work / "dragoon").exists())

    def test_rebuilds_only_what_changed(self) -> None:
        self.assertEqual(self.make("-j4", f"SDK={SDK}").returncode, 0)
        self.calls()
        self.assertEqual(self.make(f"SDK={SDK}").returncode, 0)
        self.assertEqual(self.calls(), [])
        # make 3.81 compares whole seconds, so the outputs are dated well before the edit.
        now = time.time()
        for age, paths in ((200, [*(self.work / "gen").iterdir(), *self.kit.iterdir()]),
                           (100, [self.work / "dragoon", *(self.work / "obj").iterdir()]),
                           (50, [self.work / "gen" / "recomp_001.c"])):
            for path in paths:
                os.utime(path, (now - age, now - age))
        self.assertEqual(self.make(f"SDK={SDK}").returncode, 0)
        self.assertEqual([(c["tool"], c["argv"][-1]) for c in self.calls()],
                         [("cc", "obj/recomp_001.o"), ("cxx", "-lpthread")])

    def test_relinks_when_the_kits_engine_changes(self) -> None:
        self.assertEqual(self.make(f"SDK={SDK}").returncode, 0)
        self.calls()
        now = time.time()
        for path in [*(self.work / "gen").iterdir(), *self.kit.iterdir(), *(self.work / "obj").iterdir()]:
            os.utime(path, (now - 200, now - 200))
        os.utime(self.work / "dragoon", (now - 100, now - 100))
        os.utime(self.kit / "engine.o", (now - 50, now - 50))
        self.assertEqual(self.make(f"SDK={SDK}").returncode, 0)
        self.assertEqual([c["tool"] for c in self.calls()], ["cxx"])

    def test_needs_a_kit(self) -> None:
        done = self.make(f"SDK={SDK}", kit=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("KIT isn't set", done.stderr)
        self.assertEqual(self.calls(), [])

    def test_needs_an_sdk(self) -> None:
        done = self.make()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SDK isn't set", done.stderr)
        self.assertEqual(self.calls(), [])

    def test_needs_generated_c(self) -> None:
        for path in (self.work / "gen").glob("*.c"):
            path.unlink()
        done = self.make(f"SDK={SDK}")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no gen/*.c here", done.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
