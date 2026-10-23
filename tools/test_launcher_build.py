from __future__ import annotations

import fcntl
import hashlib
import json
import os
import plistlib
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import export_source
import launcher_build
import source_info
from testutil import make_tarball, run_main, tar_member, write_file

COMMIT = "d" * 40
ENGINE = "e" * 40
OLD = "20260101-000000-old"
SDL_DECLARE = """FetchContent_Declare(sdl3
  URL https://example.com/release-3.4.18/SDL3-3.4.18.tar.gz
  URL_HASH SHA256={sha}
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
"""
ROUTES = "title 20 60 960\ncity-trial-4p 30 60 3480 --pads=4\n"

# Each fake appends what it was given to RECORDS, then does its job unless FAIL exists.
FAKE_HEAD = """#!{python}
import json, os, sys
with open({records!r}, "a") as f:
    f.write(json.dumps({{"tool": {tool!r}, "script": sys.argv[0], "argv": sys.argv[1:],
                        "cwd": os.getcwd(), "env": dict(os.environ),
                        "nobytecode": sys.flags.dont_write_bytecode}}) + "\\n")
FAIL = os.path.exists({fail!r})
"""
CMAKE = """
build = sys.argv[sys.argv.index("-B") + 1]
source = sys.argv[sys.argv.index("-S") + 1]
cache = os.path.join(build, "CMakeCache.txt")
# Like CMake, refuse a build directory that an earlier configure made from another source.
if os.path.exists(cache):
    with open(cache) as f:
        made_from = f.read().strip().split("=", 1)[1]
    if made_from != source:
        print("CMake Error: " + source + " does not match the source " + made_from
              + " used to generate cache")
        sys.exit(1)
os.makedirs(build, exist_ok=True)
with open(cache, "w") as f:
    f.write("CMAKE_HOME_DIRECTORY:INTERNAL=" + source + "\\n")
if FAIL:
    print("cmake failed on purpose")
    sys.exit(1)
"""
NINJA = """
print("ninja: Entering directory `" + sys.argv[2] + "'")
print("[12/183] Building C object a.o")
print("[183/183] Linking CXX executable " + sys.argv[3])
if FAIL:
    print("ninja failed on purpose")
    sys.exit(1)
with open(os.path.join(sys.argv[2], sys.argv[3]), "w") as f:
    f.write("a fake " + sys.argv[3])
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
    """Fake tools, an SDL tarball, a snapshot and the player's directories, all at paths
    with spaces, as the launcher's are."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.records = self.dir / "records.jsonl"
        self.tools = self.dir / "fake tools"
        self.tools.mkdir()
        self.cmake = self.fake("cmake", CMAKE)
        self.ninja = self.fake("ninja", NINJA)
        codesign = self.fake("codesign", CODESIGN)
        self.cc = self.fake("clang", "")
        self.cxx = self.fake("clang++", "")
        self.sdk = self.dir / "SDKs" / "MacOSX26.5.sdk"
        self.sdk.mkdir(parents=True)
        self.disc = write_file(self.dir, "Kirby Air Ride (USA).gcm", b"disc")
        self.tarball = self.dir / "Third Party" / "SDL3-3.4.18.tar.gz"
        self.tarball.parent.mkdir()
        make_tarball(self.tarball, [
            (tar_member("SDL3-3.4.18/", tarfile.DIRTYPE, 0o755), b""),
            (tar_member("SDL3-3.4.18/CMakeLists.txt"), b"project(SDL3)\n")])
        self.source = self.dir / "Dragoon.app" / "Contents" / "Resources" / "source"
        self.make_snapshot(self.tarball)
        self.data = self.dir / "Application Support" / "Dragoon"
        self.cache = self.dir / "Caches" / "Dragoon"
        self.log = self.dir / "Logs" / "build 1.log"
        patch = mock.patch.object(launcher_build, "CODESIGN", str(codesign))
        patch.start()
        self.addCleanup(patch.stop)

    def fake(self, tool: str, body: str, directory: Path | None = None) -> Path:
        text = FAKE_HEAD.format(python=sys.executable, records=str(self.records), tool=tool,
                                fail=str(self.fail_marker(tool))) + body
        path = write_file(directory or self.tools, "warm_shaders.py" if tool == "warm_shaders" else tool, text)
        path.chmod(0o755)
        return path

    def fail_marker(self, tool: str) -> Path:
        return self.dir / f"fail {tool}"

    def make_snapshot(self, tarball: Path, commit: str = COMMIT) -> None:
        if self.source.exists():
            shutil.rmtree(self.source)
        for d in ("gcn-recomp", "tools", "tests/hashes"):
            (self.source / d).mkdir(parents=True)
        write_file(self.source, "CMakeLists.txt", "project(dragoon)\n")
        sha = hashlib.sha256(tarball.read_bytes()).hexdigest()
        write_file(self.source / "gcn-recomp", "CMakeLists.txt", SDL_DECLARE.format(sha=sha))
        self.fake("warm_shaders", WARM, self.source / "tools")
        write_file(self.source / "tests" / "hashes", "manifest.txt", ROUTES)
        source_info.write(self.source / source_info.NAME, {
            "dragoon": commit, "gcn-recomp": ENGINE, "disc_id": "GKYE01", "dol_sha1": "a" * 40})
        write_file(self.source, export_source.MANIFEST,
                   export_source.format_manifest(export_source.manifest(self.source)))

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

    def argv(self, *extra: str, disc: bool = True) -> list[str]:
        args = ["--source", str(self.source), "--data", str(self.data), "--cache", str(self.cache),
                "--cmake", str(self.cmake), "--ninja", str(self.ninja), "--cc", str(self.cc),
                "--cxx", str(self.cxx), "--python", sys.executable, "--sdk", str(self.sdk),
                "--sdl-tarball", str(self.tarball), "--log", str(self.log)]
        return args + (["--disc", str(self.disc)] if disc else []) + list(extra)

    def build(self, *extra: str, disc: bool = True) -> tuple[int, list[dict], str]:
        code, out, err = run_main(launcher_build.main, *self.argv(*extra, disc=disc))
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
    def test_configure_line_and_environment_exactly(self):
        leaky = {"PATH": "/opt/homebrew/bin:/usr/bin", "CMAKE_PREFIX_PATH": "/opt/homebrew",
                 "PYTHONPATH": "/usr/local/lib/python", "SDKROOT": "/elsewhere"}
        with mock.patch.dict(os.environ, leaky):
            code, _, _ = self.build()
            want_env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()),
                        "TMPDIR": tempfile.gettempdir(), "LANG": "en_US.UTF-8",
                        "PYTHONDONTWRITEBYTECODE": "1", "NINJA_STATUS": "[%f/%t] "}
        self.assertEqual(code, 0)
        self.assertEqual(self.record("cmake")["argv"], [
            "-S", str(self.data / "source" / COMMIT), "-B", str(self.cache / "build"), "-G", "Ninja",
            f"-DCMAKE_MAKE_PROGRAM={self.ninja}", "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
            f"-DCMAKE_OSX_SYSROOT={self.sdk}", f"-DCMAKE_C_COMPILER={self.cc}",
            f"-DCMAKE_CXX_COMPILER={self.cxx}", f"-DPython3_EXECUTABLE={sys.executable}",
            f"-DGAME_ISO={self.disc}", "-DDRAGOON_WARMUP=OFF",
            f"-DFETCHCONTENT_SOURCE_DIR_SDL3={self.cache / 'sdl' / 'SDL3-3.4.18'}",
            "-DFETCHCONTENT_FULLY_DISCONNECTED=ON", "-DSDL_HIDAPI_LIBUSB=OFF",
            "-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew;/usr/local;/opt/local"])
        for tool in ("cmake", "ninja", "codesign", "warm_shaders"):
            with self.subTest(tool):
                # macOS's CoreFoundation sets this one in every process that loads it, the
                # fakes' Python included, whatever environment the parent passed.
                env = {k: v for k, v in self.record(tool)["env"].items()
                       if k != "__CF_USER_TEXT_ENCODING"}
                self.assertEqual(env, want_env)
                self.assertEqual(Path(self.record(tool)["cwd"]).resolve(), self.cache.resolve())
        self.assertEqual(self.record("ninja")["argv"], ["-C", str(self.cache / "build"), "dragoon"])

    def test_no_tool_reads_the_launchers_stdin(self):
        with mock.patch.object(launcher_build.subprocess, "Popen",
                               wraps=launcher_build.subprocess.Popen) as popen:
            code, _, _ = self.build()
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(popen.call_args_list), 4)  # cmake, ninja, warm-up, codesign
        for call in popen.call_args_list:
            self.assertIs(call.kwargs.get("stdin"), launcher_build.subprocess.DEVNULL, call)

    def test_ninja_status_lines_become_compile_progress(self):
        code, events, _ = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(self.of(events, "progress", "compile"), [
            {"event": "progress", "step": "compile", "done": 12, "total": 183},
            {"event": "progress", "step": "compile", "done": 183, "total": 183}])
        log = self.log.read_text()
        self.assertIn("[12/183] Building C object a.o\n", log)
        self.assertIn("ninja: Entering directory", log)

    def test_events_follow_the_steps_and_end_with_the_game(self):
        code, events, _ = self.build()
        self.assertEqual(code, 0)
        self.assertEqual([e["step"] for e in self.of(events, "step")],
                         ["sdl", "source", "configure", "compile", "warmup", "package", "swap"])
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

    def test_the_warmup_runs_on_a_copy_without_bytecode(self):
        self.old_game()
        code, events, _ = self.build()
        self.assertEqual(code, 0)
        warm = self.record("warm_shaders")
        self.assertEqual(warm["script"], str(self.data / "source" / COMMIT / "tools" / "warm_shaders.py"))
        self.assertEqual(warm["argv"], ["--game", str(self.cache / "build" / "dragoon"),
                                        "--saves", str(self.cache / "warm" / "saves")])
        self.assertTrue(warm["nobytecode"])
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

    def test_keep_build_keeps_the_build_and_the_sdl_it_points_at(self):
        self.assertEqual(self.build("--keep-build")[0], 0)
        self.assertEqual(sorted(os.listdir(self.cache)), ["build", "build.lock", "sdl"])

    def test_a_second_run_copies_again_and_keeps_the_first_build(self):
        self.assertEqual(self.build()[0], 0)
        first = self.current()
        self.assertEqual(self.build()[0], 0)
        second = self.current()
        self.assertNotEqual(first, second)
        self.assertEqual(sorted(os.listdir(self.data / "game")), sorted(["current", first, second]))
        self.assertEqual(os.listdir(self.data / "source"), [COMMIT])
        self.assertEqual(export_source.manifest(self.data / "source" / COMMIT),
                         export_source.manifest(self.source))


class FailureTest(RecipeTestCase):
    def test_a_failed_step_leaves_current_and_saves_alone(self):
        for step, tool, name in (("configure", "cmake", "cmake"), ("compile", "ninja", "ninja"),
                                 ("warmup", "warm_shaders", "warm_shaders.py"),
                                 ("package", "codesign", "codesign")):
            with self.subTest(step):
                self.data = self.dir / f"Application Support {step}" / "Dragoon"
                self.old_game()
                before = tree(self.data)
                write_file(self.dir, f"fail {tool}", "")
                code, events, _ = self.build()
                self.fail_marker(tool).unlink()
                self.assertEqual(code, 1)
                self.assertEqual(self.of(events, "error"), [{"event": "error", "step": step,
                                 "message": f"{name} exited 1", "log": str(self.log)}])
                self.assertEqual(events[-1]["event"], "error")
                after = tree(self.data)
                self.assertEqual({p: after.get(p) for p in before}, before)
                new = [p for p in after if p not in before]
                self.assertTrue(new)
                self.assertEqual([p for p in new if not self.a_new_build(p)], [])
                self.assertIn(f"{name} failed on purpose", self.log.read_text())

    @staticmethod
    def a_new_build(path: str) -> bool:
        """Whether PATH is in what a build may add before its swap: source/<commit> and game/<id>."""
        parts = path.split("/")
        return parts in (["source"], ["source", COMMIT]) or parts[:2] == ["source", COMMIT] \
            or (parts[0] == "game" and len(parts) > 1 and parts[1] not in ("current", OLD))

    def build_again_at_another_commit(self) -> None:
        """A good build of a snapshot at another commit into the cache the last run left, as
        the fake cmake refuses a build directory made from another source, like CMake's."""
        self.assertTrue((self.cache / "build" / "CMakeCache.txt").is_file())
        later = "f" * 40
        self.make_snapshot(self.tarball, later)
        code, events, _ = self.build()
        self.assertEqual((code, self.of(events, "error")), (0, []))
        self.assertEqual(self.records_of("cmake")[-1]["argv"][1], str(self.data / "source" / later))

    def test_the_build_directory_of_a_failed_run_doesnt_stop_the_next_commit(self):
        write_file(self.dir, "fail ninja", "")
        self.assertEqual(self.build()[0], 1)
        self.fail_marker("ninja").unlink()
        self.build_again_at_another_commit()

    def test_the_build_directory_kept_by_a_good_run_doesnt_stop_the_next_commit(self):
        self.assertEqual(self.build("--keep-build")[0], 0)
        self.build_again_at_another_commit()

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

    def test_a_tarball_with_the_wrong_hash_stops_before_anything(self):
        make_tarball(self.tarball, [(tar_member("SDL3-3.4.18/other"), b"not the pinned one")])
        code, events, _ = self.build()
        self.assertEqual(code, 1)
        (error,) = self.of(events, "error")
        self.assertEqual(error["step"], "sdl")
        self.assertIn("SHA-256", error["message"])
        self.assertFalse(self.data.exists())
        self.assertFalse((self.cache / "sdl").exists())
        self.assertEqual(self.records_of("cmake"), [])

    def test_a_pinned_tarball_with_a_symlink_is_refused(self):
        make_tarball(self.tarball, [(tar_member("SDL3-3.4.18/", tarfile.DIRTYPE, 0o755), b""),
                                    (tar_member("SDL3-3.4.18/x", tarfile.SYMTYPE, link="/etc"), b"")])
        self.make_snapshot(self.tarball)
        code, events, _ = self.build()
        self.assertEqual(code, 1)
        (error,) = self.of(events, "error")
        self.assertEqual((error["step"], "SDL3-3.4.18/x" in error["message"]), ("sdl", True))
        self.assertFalse((self.cache / "sdl").exists())

    def test_the_extracted_files_are_the_bytes_that_were_hashed(self):
        real = launcher_build.sdl_source.extract

        def rewritten_then_extracted(tarball, dest):
            # Someone replaces the file after its hash was checked.
            make_tarball(self.tarball, [(tar_member("SDL3-3.4.18/CMakeLists.txt"), b"swapped\n")])
            real(tarball, dest)

        with mock.patch.object(launcher_build.sdl_source, "extract", rewritten_then_extracted):
            code, _, _ = self.build("--keep-build")
        self.assertEqual(code, 0)
        self.assertEqual((self.cache / "sdl" / "SDL3-3.4.18" / "CMakeLists.txt").read_text(),
                         "project(SDL3)\n")

    def test_a_failed_package_removes_the_half_made_build(self):
        self.old_game()
        write_file(self.dir, "fail codesign", "")
        code, events, _ = self.build()
        self.assertEqual((code, [e["step"] for e in self.of(events, "error")]), (1, ["package"]))
        self.assertEqual(sorted(os.listdir(self.data / "game")), sorted(["current", OLD]))

    def test_a_failure_before_the_first_step_still_names_a_step(self):
        self.cache.mkdir(parents=True)
        write_file(self.cache, "warm", "not a directory")  # the leftover cleanup can't remove it
        code, events, _ = self.build()
        self.assertEqual(code, 1)
        (error,) = self.of(events, "error")
        self.assertEqual(error["step"], "sdl")

    def test_a_snapshot_that_doesnt_match_its_manifest_is_refused(self):
        write_file(self.source, "CMakeLists.txt", "project(edited)\n")
        code, events, _ = self.build()
        self.assertEqual(code, 1)
        self.assertEqual([e["step"] for e in self.of(events, "error")], ["source"])
        self.assertEqual(os.listdir(self.data / "source"), [])


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
        self.log.write_text("== configure\n")
        self.cache.mkdir(parents=True)
        with (self.cache / "build.lock").open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, events, _ = self.build()
        self.assertEqual(code, 3)
        self.assertEqual(events[0]["log"], str(self.log))
        self.assertEqual(self.log.read_text(), "== configure\n")


class NoDiscTest(RecipeTestCase):
    def test_builds_runtime_check_and_stops(self):
        code, events, _ = self.build("--no-disc", disc=False)
        self.assertEqual(code, 0)
        self.assertEqual([e["step"] for e in self.of(events, "step")],
                         ["sdl", "source", "configure", "compile"])
        self.assertFalse([a for a in self.record("cmake")["argv"] if a.startswith("-DGAME_ISO")])
        self.assertEqual(self.record("ninja")["argv"], ["-C", str(self.cache / "build"), "runtime_check"])
        self.assertEqual(events[-1], {"event": "done", "game": None})
        self.assertFalse((self.data / "game").exists())
        self.assertEqual(self.records_of("codesign") + self.records_of("warm_shaders"), [])


class ArgumentTest(RecipeTestCase):
    def test_bad_arguments_exit_2_before_anything(self):
        def swap(flag: str, value: str) -> list[str]:
            args = self.argv()
            args[args.index(flag) + 1] = value
            return args

        cases = {
            "a relative path": (swap("--data", "Application Support/Dragoon"), "absolute"),
            "a missing tool": (swap("--cmake", str(self.tools / "nope")), "--cmake"),
            "a tool that isn't executable": (swap("--ninja", str(self.disc)), "--ninja"),
            "a missing disc": (swap("--disc", str(self.dir / "nope.iso")), "--disc"),
            "a disc that is a directory": (swap("--disc", str(self.tools)), "--disc"),
            "a missing SDL tarball": (swap("--sdl-tarball", str(self.dir / "nope.tar.gz")),
                                      "--sdl-tarball"),
            "an SDL tarball that is a directory": (swap("--sdl-tarball", str(self.tools)),
                                                   "--sdl-tarball"),
            "a missing SDK": (swap("--sdk", str(self.dir / "nope.sdk")), "--sdk"),
            "an SDK that is a file": (swap("--sdk", str(self.disc)), "--sdk"),
            "a source that is a file": (swap("--source", str(self.disc)), "--source"),
            "both disc options": (self.argv("--no-disc"), "not allowed with"),
            "neither disc option": (self.argv(disc=False), "required"),
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


if __name__ == "__main__":
    unittest.main()
