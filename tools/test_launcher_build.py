from __future__ import annotations

import fcntl
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import launcher_build
import source_info
from testutil import run_main, write_file

ROOT = Path(__file__).resolve().parents[1]
MAKE = "/usr/bin/make"
COMMIT = "d" * 40
ENGINE = "e" * 40
DOL_SHA1 = "a" * 40
OLD = "20260101-000000-old"
ROUTES = "title 20 60 960\ncity-trial-4p 30 60 3480 --pads=4\n"
STEPS = ["recompile", "compile", "warmup", "package", "swap"]

# Each fake appends what it was given to RECORDS, then does its job unless FAIL exists.
FAKE_HEAD = """#!{python}
import json, os, sys
with open({records!r}, "a") as f:
    f.write(json.dumps({{"tool": {tool!r}, "script": sys.argv[0], "argv": sys.argv[1:],
                        "cwd": os.getcwd(), "env": dict(os.environ),
                        "nobytecode": sys.flags.dont_write_bytecode}}) + "\\n")
FAIL = os.path.exists({fail!r})
"""
EXTRACT_DOL = """
if FAIL:
    print("extract_dol.py failed on purpose")
    sys.exit(1)
with open(sys.argv[2], "wb") as f:
    f.write(b"a fake dol")
"""
RECOMP = """
if FAIL:
    print("recomp.py failed on purpose")
    sys.exit(1)
os.makedirs(sys.argv[3], exist_ok=True)
for name in ("a", "b", "c"):
    with open(os.path.join(sys.argv[3], name + ".c"), "w") as f:
        f.write("int " + name + ";\\n")
"""
# Prints what the kit's Makefile has make print: each compile, a warning, then the link.
MAKE_FAKE = """
var = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
for c in sorted(n for n in os.listdir("gen") if n.endswith(".c")):
    print(var["CC"] + ' -arch arm64 -isysroot "' + var["SDK"] + '" -O2 -I"' + var["KIT"]
          + '/include" -Igen -c gen/' + c + " -o obj/" + c[:-2] + ".o")
print("gen/b.c:1:5: warning: a line that isn't a compile")
print(var["CXX"] + ' -O2 -o dragoon obj/a.o obj/b.o obj/c.o "' + var["KIT"] + '/engine.o"')
if FAIL:
    print("make failed on purpose")
    sys.exit(1)
with open("dragoon", "w") as f:
    f.write("a fake dragoon")
"""
CODESIGN = """
if FAIL:
    print("codesign failed on purpose")
    sys.exit(1)
"""
WARM = """
saves = sys.argv[sys.argv.index("--saves") + 1]
# Like the real tool, do nothing when the stamp the player's last warm-up left is current.
stamp = os.path.join(saves, ".shader-warmup")
if os.path.exists(stamp) and open(stamp).read() == "current stamp\\n":
    print("shader cache is current, nothing to do")
    sys.exit(0)
print("title: 1860 frames, 0.1 s", flush=True)
if FAIL:
    print("warm_shaders.py failed on purpose", file=sys.stderr)
    sys.exit(1)
print("city-trial-4p: 4380 frames, 0.2 s")
with open(os.path.join(saves, "shaders.bin"), "ab") as f:
    f.write(b"warm\\n")
with open(os.path.join(saves, ".shader-warmup"), "w") as f:
    f.write("new stamp\\n")
print("warm: 2 passes")
"""


def tree(root: Path) -> dict[str, object]:
    """Every path under ROOT with its bytes, its link target or "dir"; links aren't followed."""
    found = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            found[rel] = "-> " + os.readlink(path)
        elif path.is_file():
            found[rel] = path.read_bytes()
        else:
            found[rel] = "dir"
    return found


class RecipeTestCase(unittest.TestCase):
    """Fake tools, a snapshot, a kit and the player's directories, all at paths with spaces,
    as the launcher's are."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.records = self.dir / "records.jsonl"
        self.tools = self.dir / "fake tools"
        self.tools.mkdir()
        self.make = self.fake("make", MAKE_FAKE)
        codesign = self.fake("codesign", CODESIGN)
        self.cc = self.fake("clang", "")
        self.cxx = self.fake("clang++", "")
        self.sdk = self.dir / "SDKs" / "MacOSX26.5.sdk"
        self.sdk.mkdir(parents=True)
        self.disc = write_file(self.dir, "Kirby Air Ride (USA).gcm", b"disc")
        resources = self.dir / "Dragoon.app" / "Contents" / "Resources"
        self.source = resources / "source"
        self.make_snapshot()
        self.kit = resources / "kit"
        (self.kit / "include").mkdir(parents=True)
        for name in ("Makefile", "kit.mk", "engine.o", "libSDL3.a", "include/recomp.h"):
            write_file(self.kit, name, f"a fake {name}\n")
        self.data = self.dir / "Application Support" / "Dragoon"
        self.cache = self.dir / "Caches" / "Dragoon"
        self.log = self.dir / "Logs" / "build 1.log"
        patch = mock.patch.object(launcher_build, "CODESIGN", str(codesign))
        patch.start()
        self.addCleanup(patch.stop)

    def fake(self, tool: str, body: str, directory: Path | None = None, name: str = "") -> Path:
        text = FAKE_HEAD.format(python=sys.executable, records=str(self.records), tool=tool,
                                fail=str(self.fail_marker(tool))) + body
        path = write_file(directory or self.tools, name or tool, text)
        path.chmod(0o755)
        return path

    def fail_marker(self, tool: str) -> Path:
        return self.dir / f"fail {tool}"

    def make_snapshot(self, commit: str = COMMIT) -> None:
        for d in ("gcn-recomp/recomp", "tools", "tests/hashes", "analysis", "recomp"):
            (self.source / d).mkdir(parents=True, exist_ok=True)
        self.fake("extract_dol", EXTRACT_DOL, self.source / "gcn-recomp" / "recomp", "extract_dol.py")
        self.fake("recomp", RECOMP, self.source / "gcn-recomp" / "recomp", "recomp.py")
        self.fake("warm_shaders", WARM, self.source / "tools", "warm_shaders.py")
        write_file(self.source / "analysis", "symbols.txt", "fake symbols\n")
        write_file(self.source / "recomp", "names.txt", "fake names\n")
        write_file(self.source / "tests" / "hashes", "manifest.txt", ROUTES)
        source_info.write(self.source / source_info.NAME, {
            "dragoon": commit, "gcn-recomp": ENGINE, "disc_id": "GKYE01", "dol_sha1": DOL_SHA1})

    def old_game(self) -> None:
        """A build that's current and the player's saves, as an earlier build left them."""
        exe = self.data / "game" / OLD / "Dragoon.app" / "Contents" / "MacOS"
        exe.mkdir(parents=True)
        write_file(exe, "dragoon", "the old game")
        os.symlink(OLD, self.data / "game" / "current")
        saves = self.data / "saves"
        (saves / "inputs").mkdir(parents=True)
        write_file(saves, "memcard_a.raw", b"the player's card")
        write_file(saves, "shaders.bin", b"old keys\n")
        write_file(saves, ".shader-warmup", "old stamp\n")
        write_file(saves / "inputs", "session 1.bin", b"inputs")

    def argv(self, *extra: str) -> list[str]:
        return ["--source", str(self.source), "--kit", str(self.kit), "--disc", str(self.disc),
                "--data", str(self.data), "--cache", str(self.cache), "--make", str(self.make),
                "--cc", str(self.cc), "--cxx", str(self.cxx), "--python", sys.executable,
                "--sdk", str(self.sdk), "--log", str(self.log), *extra]

    def build(self, *extra: str) -> tuple[int, list[dict], str]:
        code, out, err = run_main(launcher_build.main, *self.argv(*extra))
        return code, [json.loads(line) for line in out.splitlines()], err

    def records_of(self, tool: str) -> list[dict]:
        if not self.records.exists():
            return []
        return [r for r in map(json.loads, self.records.read_text().splitlines()) if r["tool"] == tool]

    def record(self, tool: str) -> dict:
        (only,) = self.records_of(tool)
        return only

    @staticmethod
    def of(events: list[dict], kind: str, step: str | None = None) -> list[dict]:
        return [e for e in events if e["event"] == kind and (step is None or e.get("step") == step)]

    def current(self) -> str:
        return os.readlink(self.data / "game" / "current")

    def links_left_in_game(self) -> list[str]:
        """The names of the .current.<pid>.partial links in <data>/game, a swap's temp names."""
        return sorted(p.name for p in (self.data / "game").glob(".current.*.partial"))


class GoodRunTest(RecipeTestCase):
    def test_commands_and_environment_exactly(self):
        leaky = {"PATH": "/opt/homebrew/bin:/usr/bin", "MAKEFLAGS": "-j1 CC=gcc",
                 "PYTHONPATH": "/usr/local/lib/python", "SDKROOT": "/elsewhere"}
        with mock.patch.dict(os.environ, leaky):
            code, _, _ = self.build()
            want_env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()),
                        "TMPDIR": tempfile.gettempdir(), "LANG": "en_US.UTF-8",
                        "PYTHONDONTWRITEBYTECODE": "1"}
        self.assertEqual(code, 0)
        build = self.cache / "build"
        recomp = self.source / "gcn-recomp" / "recomp"
        self.assertEqual(self.record("extract_dol")["script"], str(recomp / "extract_dol.py"))
        self.assertEqual(self.record("extract_dol")["argv"],
                         [str(self.disc), str(build / "main.dol"), "GKYE01", DOL_SHA1])
        self.assertEqual(self.record("recomp")["script"], str(recomp / "recomp.py"))
        self.assertEqual(self.record("recomp")["argv"], [
            str(build / "main.dol"), str(self.source / "analysis" / "symbols.txt"),
            str(build / "gen"), str(self.source / "recomp")])
        self.assertEqual(self.record("make")["argv"], [
            "-f", str(self.kit / "Makefile"), f"-j{os.cpu_count()}", f"KIT={self.kit}",
            f"SDK={self.sdk}", f"CC={self.cc}", f"CXX={self.cxx}", "dragoon"])
        for tool, cwd in (("extract_dol", build), ("recomp", build), ("make", build),
                          ("warm_shaders", self.cache), ("codesign", self.cache)):
            with self.subTest(tool):
                # macOS's CoreFoundation sets this one in every process that loads it, the
                # fakes' Python included, whatever environment the parent passed.
                env = {k: v for k, v in self.record(tool)["env"].items()
                       if k != "__CF_USER_TEXT_ENCODING"}
                self.assertEqual(env, want_env)
                self.assertEqual(Path(self.record(tool)["cwd"]).resolve(), cwd.resolve())
        for tool in ("extract_dol", "recomp", "warm_shaders"):
            self.assertTrue(self.record(tool)["nobytecode"], tool)

    def test_no_tool_reads_the_launchers_stdin(self):
        with mock.patch.object(launcher_build.subprocess, "Popen",
                               wraps=launcher_build.subprocess.Popen) as popen:
            code, _, _ = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(len(popen.call_args_list), 5)  # extract, recomp, make, warm-up, codesign
        for call in popen.call_args_list:
            self.assertIs(call.kwargs.get("stdin"), launcher_build.subprocess.DEVNULL, call)

    def test_python_runs_with_B_so_nothing_lands_in_the_signed_app(self):
        # PYTHONDONTWRITEBYTECODE says it too, but -B holds whatever the environment says.
        with mock.patch.object(launcher_build.subprocess, "Popen",
                               wraps=launcher_build.subprocess.Popen) as popen:
            self.assertEqual(self.build()[0], 0)
        recomp = self.source / "gcn-recomp" / "recomp"
        self.assertEqual([c.args[0][:3] for c in popen.call_args_list if c.args[0][0] == sys.executable], [
            [sys.executable, "-B", str(recomp / "extract_dol.py")],
            [sys.executable, "-B", str(recomp / "recomp.py")],
            [sys.executable, "-B", str(self.source / "tools" / "warm_shaders.py")]])

    def test_each_compile_make_prints_is_a_progress_event(self):
        code, events, _ = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(self.of(events, "progress", "compile"), [
            {"event": "progress", "step": "compile", "done": n, "total": 3} for n in (1, 2, 3)])
        log = self.log.read_text()
        self.assertIn("gen/b.c:1:5: warning: a line that isn't a compile\n", log)
        self.assertIn(" -o dragoon obj/a.o", log)

    def test_events_follow_the_steps_and_end_with_the_game(self):
        code, events, _ = self.build()
        self.assertEqual(code, 0)
        self.assertEqual([e["step"] for e in self.of(events, "step")], STEPS)
        self.assertEqual(self.of(events, "error"), [])
        self.assertEqual(events[-1], {"event": "done",
                                      "game": str(self.data / "game" / "current" / "Dragoon.app")})

    def test_a_good_run_moves_current_and_installs_the_warmed_files(self):
        self.old_game()
        before = tree(self.data / "saves")
        code, _, _ = self.build()
        self.assertEqual(code, 0)
        self.assertNotEqual(self.current(), OLD)
        self.assertTrue((self.data / "game" / OLD / "Dragoon.app").is_dir())  # left for the launcher
        exe = self.data / "game" / self.current() / "Dragoon.app" / "Contents" / "MacOS" / "dragoon"
        self.assertEqual(exe.read_text(), "a fake dragoon")
        after = tree(self.data / "saves")
        self.assertEqual(after.pop("shaders.bin"), b"old keys\nwarm\n")  # warmed from the player's
        self.assertEqual(after.pop(".shader-warmup"), b"new stamp\n")
        del before["shaders.bin"], before[".shader-warmup"]
        self.assertEqual(after, before)
        self.assertEqual(os.listdir(self.cache), ["build.lock"])  # the intermediates are gone
        self.assertEqual(sorted(os.listdir(self.data)), ["game", "saves"])

    def test_the_snapshot_and_the_kit_are_only_read(self):
        source, kit = tree(self.source), tree(self.kit)
        self.assertEqual(self.build()[0], 0)
        self.assertEqual((tree(self.source), tree(self.kit)), (source, kit))

    def test_the_recompile_starts_from_an_empty_build_directory(self):
        stale = self.cache / "build"
        for name in ("gen/stale.c", "obj/stale.o", "dragoon"):
            (stale / name).parent.mkdir(parents=True, exist_ok=True)
            write_file(stale, name, "from a build that failed")
        code, events, _ = self.build("--keep-build")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(stale)), ["dragoon", "gen", "main.dol"])
        self.assertEqual(sorted(os.listdir(stale / "gen")), ["a.c", "b.c", "c.c"])
        self.assertEqual(self.of(events, "progress", "compile")[-1]["total"], 3)

    def test_each_step_logs_its_time_and_what_data_and_cache_hold(self):
        self.old_game()
        write_file(self.data / "saves", "big.bin", bytes(3_000_000))
        self.assertEqual(self.build()[0], 0)
        lines = [m.groups() for m in re.finditer(
            r"^== (\w+) took \d+\.\d s, with (\d+\.\d) MB in --data and --cache$",
            self.log.read_text(), re.M)]
        self.assertEqual([step for step, _ in lines], STEPS)
        self.assertGreaterEqual(min(float(mb) for _, mb in lines), 3.0)

    def test_disk_use_counts_blocks_as_du_does_and_no_link_targets(self):
        files, links = self.dir / "files", self.dir / "links"
        (files / "deeper").mkdir(parents=True)
        links.mkdir()
        write_file(files / "deeper", "a", bytes(1_000_000))
        write_file(files, "b", b"x")
        os.symlink(files / "deeper" / "a", links / "a")
        used = launcher_build.disk_use(files)
        du = subprocess.run(["/usr/bin/du", "-sk", str(files)], capture_output=True, text=True,
                            check=True).stdout.split()[0]
        self.assertEqual(used, int(du) * 1024)
        self.assertGreaterEqual(used, 1_000_000)
        self.assertLess(launcher_build.disk_use(links), 1_000_000)
        self.assertEqual(launcher_build.disk_use(files, links),
                         used + launcher_build.disk_use(links))

    def test_disk_use_skips_a_file_removed_after_the_listing(self):
        files = self.dir / "files"
        files.mkdir()
        write_file(files, "kept", bytes(1_000_000))
        write_file(files, "gone", bytes(1_000_000))
        lstat = os.lstat

        def removed_first(path, *args, **kwargs):
            if os.path.basename(path) == "gone":
                raise FileNotFoundError(2, "No such file or directory", path)
            return lstat(path, *args, **kwargs)

        with mock.patch.object(launcher_build.os, "lstat", side_effect=removed_first):
            used = launcher_build.disk_use(files)
        self.assertEqual(used, lstat(files / "kept").st_blocks * 512)
        self.assertGreaterEqual(used, 1_000_000)

    def test_a_measurement_that_fails_is_a_note_and_never_fails_the_step(self):
        denied = PermissionError(13, "Permission denied", "/a/dir")
        with mock.patch.object(launcher_build, "disk_use", side_effect=denied):
            code, events, _ = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(self.of(events, "error"), [])
        self.assertEqual(re.findall(
            r"^== (\w+) took \d+\.\d s, and --data and --cache couldn't be measured "
            r"\(\[Errno 13\] Permission denied: '/a/dir'\)$", self.log.read_text(), re.M), STEPS)

    def test_links_a_killed_swap_left_are_cleaned_up_at_the_next_swap(self):
        self.old_game()
        os.symlink("somewhere", self.data / "game" / ".current.99999.partial")
        self.assertEqual(self.build()[0], 0)
        self.assertEqual(self.links_left_in_game(), [])
        self.assertNotEqual(self.current(), OLD)

    def test_the_package_is_an_app_sealed_ad_hoc_with_its_stamp(self):
        self.assertEqual(self.build()[0], 0)
        game = self.data / "game" / self.current()
        with (game / "Dragoon.app" / "Contents" / "Info.plist").open("rb") as f:
            plist = plistlib.load(f)
        self.assertEqual(plist["CFBundleExecutable"], "dragoon")
        # Placeholders until the user chooses the bundle ID and the name the Dock shows.
        self.assertEqual(plist["CFBundleIdentifier"], "io.github.lunchbox-recomp.dragoon.game")
        self.assertEqual(plist["CFBundleName"], "Dragoon")
        self.assertEqual(plist["CFBundlePackageType"], "APPL")
        self.assertEqual(plist["LSApplicationCategoryType"], "public.app-category.games")
        self.assertEqual(plist["LSMinimumSystemVersion"], "14.0")
        self.assertIs(plist["LSSupportsGameMode"], True)
        self.assertIs(plist["GCSupportsGameMode"], True)
        self.assertEqual(self.record("codesign")["argv"],
                         ["--force", "--sign", "-", str(game / "Dragoon.app")])
        stamp = json.loads((game / "stamp.json").read_text())
        self.assertRegex(stamp.pop("built"), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(stamp, {"dragoon": COMMIT, "gcn-recomp": ENGINE, "sdk": str(self.sdk)})

    def test_the_warmup_runs_the_snapshots_tool_on_the_disc(self):
        self.old_game()
        code, events, _ = self.build()
        self.assertEqual(code, 0)
        warm = self.record("warm_shaders")
        self.assertEqual(warm["script"], str(self.source / "tools" / "warm_shaders.py"))
        self.assertEqual(warm["argv"], ["--game", str(self.cache / "build" / "dragoon"),
                                        "--saves", str(self.cache / "warm" / "saves"),
                                        "--disc", str(self.disc)])
        self.assertEqual(self.of(events, "progress", "warmup"), [
            {"event": "progress", "step": "warmup", "done": 1, "total": 2},
            {"event": "progress", "step": "warmup", "done": 2, "total": 2}])

    def test_the_players_stamp_reaches_the_warmup_so_a_current_cache_is_skipped(self):
        self.old_game()
        write_file(self.data / "saves", ".shader-warmup", "current stamp\n")
        before = tree(self.data / "saves")
        code, events, _ = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.records_of("warm_shaders")), 1)
        self.assertEqual(self.of(events, "progress", "warmup"), [])  # no pass ran
        self.assertEqual(tree(self.data / "saves"), before)
        self.assertNotEqual(self.current(), OLD)

    def test_no_warmup_skips_it_and_installs_nothing(self):
        self.old_game()
        before = tree(self.data / "saves")
        code, events, _ = self.build("--no-warmup")
        self.assertEqual(code, 0)
        self.assertNotIn("warmup", [e["step"] for e in self.of(events, "step")])
        self.assertEqual(self.records_of("warm_shaders"), [])
        self.assertEqual(tree(self.data / "saves"), before)
        self.assertNotEqual(self.current(), OLD)

    def test_keep_build_keeps_the_build(self):
        self.assertEqual(self.build("--keep-build")[0], 0)
        self.assertEqual(sorted(os.listdir(self.cache)), ["build", "build.lock"])
        self.assertEqual((self.cache / "build" / "dragoon").read_text(), "a fake dragoon")

    def test_a_second_run_keeps_the_first_build(self):
        self.assertEqual(self.build()[0], 0)
        first = self.current()
        self.assertEqual(self.build()[0], 0)
        second = self.current()
        self.assertNotEqual(first, second)
        self.assertEqual(sorted(os.listdir(self.data / "game")), sorted(["current", first, second]))


class FailureTest(RecipeTestCase):
    def test_a_failed_step_leaves_data_alone(self):
        for step, tool, name in (("recompile", "extract_dol", "extract_dol.py"),
                                 ("recompile", "recomp", "recomp.py"), ("compile", "make", "make"),
                                 ("warmup", "warm_shaders", "warm_shaders.py"),
                                 ("package", "codesign", "codesign")):
            with self.subTest(tool):
                self.data = self.dir / f"Application Support {tool}" / "Dragoon"
                self.old_game()
                before = tree(self.data)
                write_file(self.dir, f"fail {tool}", "")
                code, events, _ = self.build()
                self.fail_marker(tool).unlink()
                self.assertEqual(code, 1)
                self.assertEqual(self.of(events, "error"), [{"event": "error", "step": step,
                                 "message": f"{name} exited 1", "log": str(self.log)}])
                self.assertEqual(events[-1]["event"], "error")
                self.assertEqual(tree(self.data), before)
                self.assertIn(f"{name} failed on purpose", self.log.read_text())

    def test_a_swap_that_fails_installs_nothing_in_the_saves(self):
        self.old_game()
        os.unlink(self.data / "game" / "current")
        (self.data / "game" / "current").mkdir()  # a directory, which no link can be renamed over
        before = tree(self.data / "saves")
        code, events, _ = self.build()
        self.assertEqual(code, 1)
        (error,) = self.of(events, "error")
        self.assertEqual(error["step"], "swap")
        self.assertEqual(tree(self.data / "saves"), before)  # not even the warmed files
        self.assertTrue((self.data / "game" / "current").is_dir())
        self.assertEqual(self.links_left_in_game(), [])  # the one this run made is gone

    def test_a_failed_package_removes_the_half_made_build(self):
        self.old_game()
        write_file(self.dir, "fail codesign", "")
        code, events, _ = self.build()
        self.assertEqual((code, [e["step"] for e in self.of(events, "error")]), (1, ["package"]))
        self.assertEqual(sorted(os.listdir(self.data / "game")), sorted(["current", OLD]))

    def test_a_failure_before_the_first_tool_still_names_a_step(self):
        self.cache.mkdir(parents=True)
        write_file(self.cache, "warm", "not a directory")  # the leftover cleanup can't remove it
        code, events, _ = self.build()
        self.assertEqual(code, 1)
        (error,) = self.of(events, "error")
        self.assertEqual(error["step"], "recompile")
        self.assertFalse(self.records.exists())


class LockTest(RecipeTestCase):
    def test_a_second_build_exits_3_touching_nothing(self):
        self.old_game()
        self.cache.mkdir(parents=True)
        with (self.cache / "build.lock").open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            data, cache = tree(self.data), tree(self.cache)
            code, events, _ = self.build()
            self.assertEqual((tree(self.data), tree(self.cache)), (data, cache))
        self.assertEqual(code, 3)
        self.assertEqual([(e["event"], e["step"]) for e in events], [("error", "lock")])
        self.assertFalse(self.records.exists())
        self.assertFalse(self.log.exists())

    def test_the_loser_leaves_the_log_it_was_given_alone(self):
        """The launcher gives each build its own log, but a developer's second run may name
        the first one's, which the running build is still writing."""
        self.log.parent.mkdir(parents=True)
        self.log.write_text("== recompile\n")
        self.cache.mkdir(parents=True)
        with (self.cache / "build.lock").open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, events, _ = self.build()
        self.assertEqual(code, 3)
        self.assertEqual(events[0]["log"], str(self.log))
        self.assertEqual(self.log.read_text(), "== recompile\n")


class ArgumentTest(RecipeTestCase):
    def test_bad_arguments_exit_2_before_anything(self):
        def swap(flag: str, value: str) -> list[str]:
            args = self.argv()
            args[args.index(flag) + 1] = value
            return args

        def without(flag: str) -> list[str]:
            args = self.argv()
            del args[args.index(flag):args.index(flag) + 2]
            return args

        cases = {
            "a relative path": (swap("--data", "Application Support/Dragoon"), "absolute"),
            "a relative kit": (swap("--kit", "Dragoon.app/Contents/Resources/kit"), "absolute"),
            "a relative make": (swap("--make", "fake tools/make"), "absolute"),
            "a missing tool": (swap("--make", str(self.tools / "nope")), "--make"),
            "a tool that isn't executable": (swap("--cc", str(self.disc)), "--cc"),
            "a missing disc": (swap("--disc", str(self.dir / "nope.iso")), "--disc"),
            "a disc that is a directory": (swap("--disc", str(self.tools)), "--disc"),
            "no disc": (without("--disc"), "required"),
            "no kit": (without("--kit"), "required"),
            "a missing kit": (swap("--kit", str(self.dir / "nope")), "--kit"),
            "a kit that is a file": (swap("--kit", str(self.disc)), "--kit"),
            "a missing SDK": (swap("--sdk", str(self.dir / "nope.sdk")), "--sdk"),
            "an SDK that is a file": (swap("--sdk", str(self.disc)), "--sdk"),
            "a source that is a file": (swap("--source", str(self.disc)), "--source"),
            "a source with no source-info.json": (swap("--source", str(self.tools)),
                                                  source_info.NAME),
        }
        for name, (args, why) in cases.items():
            with self.subTest(name):
                code, out, err = run_main(launcher_build.main, *args)
                self.assertEqual((code, out), (2, ""))
                self.assertIn(why, err)
                self.assertFalse(self.data.exists() or self.cache.exists() or self.log.exists())
                self.assertFalse(self.records.exists())


class RealTreeTest(unittest.TestCase):
    """The recipe against this repository's own recompiler, CMakeLists.txt and kit Makefile."""

    def test_the_recompiler_and_its_inputs_are_where_the_recipe_looks(self):
        for rel in (launcher_build.EXTRACT_DOL, launcher_build.RECOMP, launcher_build.SYMBOLS):
            self.assertTrue((ROOT / rel).is_file(), rel)
        self.assertTrue((ROOT / launcher_build.TABLES).is_dir())

    def test_gcn_add_game_takes_nothing_the_recipe_doesnt_pass(self):
        """A DOL fixup, modules or sources of the game's own would need steps the recipe
        doesn't have."""
        (call,) = re.findall(r"\bgcn_add_game\s*\(([^)]*)\)", (ROOT / "CMakeLists.txt").read_text())
        keywords = set(re.findall(r"^\s*([A-Z_]+)\s", call, re.M))
        self.assertLessEqual(keywords, {"NAME", "TITLE", "LABEL", "DISC_ID", "DOL_SHA1", "SYMBOLS",
                                        "TABLES", "FPS", "IMAGE_DIR"})
        self.assertIn(f"SYMBOLS ${{CMAKE_SOURCE_DIR}}/{launcher_build.SYMBOLS}\n", call)
        self.assertIn(f"TABLES ${{CMAKE_SOURCE_DIR}}/{launcher_build.TABLES}\n", call)

    def test_the_kit_makefile_prints_each_compile_as_the_progress_counts_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "game dir"
            (game / "gen").mkdir(parents=True)
            for name in ("a.c", "b_1.c"):
                write_file(game / "gen", name, "int x;\n")
            kit = Path(tmp) / "engine kit"
            (kit / "include").mkdir(parents=True)
            write_file(kit, "Makefile", (ROOT / "launcher" / "kit" / "Makefile").read_text())
            write_file(kit, "kit.mk", "MACOSX_MIN := 14.0\nGAME_CFLAGS := -O2 -g\n"
                                      "LINK_FLAGS := -O2\nGAME_LIBS := -framework Metal\n")
            for name in ("engine.o", "libSDL3.a", "include/recomp.h", "include/compat.h"):
                write_file(kit, name, "")
            args = launcher_build.parse_args([
                "--source", tmp, "--kit", str(kit), "--disc", tmp, "--data", tmp, "--cache", tmp,
                "--make", MAKE, "--cc", "/x/clang", "--cxx", "/x/clang++", "--python", tmp,
                "--sdk", str(Path(tmp) / "Mac OSX.sdk"), "--log", tmp])
            cmd = launcher_build.make_command(args)
            done = subprocess.run([cmd[0], "-n", *cmd[1:]], cwd=game, capture_output=True,
                                  text=True, check=True)
        lines = done.stdout.splitlines()
        compiles = [line for line in lines if launcher_build.COMPILE_LINE.fullmatch(line)]
        self.assertEqual(len(compiles), 2, lines)
        self.assertEqual(compiles, [line for line in lines if " -c " in line])
        self.assertEqual(len([line for line in lines if " -o dragoon " in line]), 1, lines)


if __name__ == "__main__":
    unittest.main()
