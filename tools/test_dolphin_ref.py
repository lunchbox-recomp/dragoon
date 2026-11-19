from __future__ import annotations

import argparse
import configparser
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import dolphin_ref
from testutil import commit, git, run_main, temp_dir

ISO = "/discs/game.iso"
HAS_SANDBOX = sys.platform == "darwin" and os.path.exists(dolphin_ref.SANDBOX_EXEC)
MDNS = "/var/run/mDNSResponder"


class FakeDolphin:
    """Stands in for a Dolphin process: popen sends MESSAGES to the memory watcher's socket, one
    datagram each, before it returns. play binds the socket before it starts the process, so
    they're all waiting when it first reads, however slow the machine, and a short timeout
    can't run out before the first comes."""

    pid = 4242

    def __init__(self, sock_path: Path, messages: list[bytes]) -> None:
        self.sock_path = sock_path
        self.messages = messages
        self.returncode = None
        self.cmd: list[str] = []
        self.kwargs: dict = {}

    def popen(self, cmd: list[str], **kwargs) -> "FakeDolphin":
        self.cmd = cmd
        self.kwargs = kwargs
        out = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        for message in self.messages:
            out.sendto(message, str(self.sock_path))
        out.close()
        return self

    def poll(self):
        """Exits once it has sent everything, as Dolphin does on SIGINT."""
        self.returncode = 0
        return self.returncode

    wait = poll


class FakeGroup:
    """os.killpg for a process group that's gone once it gets SIGINT, unless it SURVIVES."""

    def __init__(self, survives: bool = False) -> None:
        self.survives = survives
        self.calls: list[tuple[int, int]] = []

    def __call__(self, pid: int, sig: int) -> None:
        self.calls.append((pid, sig))
        if sig == 0 and not self.survives:
            raise ProcessLookupError


def frame_message(*pairs: tuple[str, int]) -> bytes:
    return "".join(f"{a.lower()}\n{v:x}\n" for a, v in pairs).encode() + b"\0"


def add_submodule(repo: Path, name: str) -> str:
    """Record REPO/NAME, a repository already there, as REPO's submodule and commit it."""
    (repo / ".gitmodules").write_text(f'[submodule "{name}"]\n\tpath = {name}\n'
                                      f"\turl = ./{name}\n")
    git(repo, "add", ".gitmodules", name)
    git(repo, "commit", "-q", "-m", "submodule")
    git(repo, "submodule", "init")
    return git(repo, "rev-parse", "HEAD")


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.src = temp_dir(self) / "src"
        self.head = commit(self.src, {"README.md": "dolphin"})

    def test_a_tree_at_its_pin_passes(self):
        self.assertEqual(dolphin_ref.check_tree(self.src, sha=self.head, patch=""), self.head)

    def test_a_tree_off_its_pin_is_refused(self):
        with self.assertRaisesRegex(dolphin_ref.Refused, "not the pinned"):
            dolphin_ref.check_tree(self.src, sha="0" * 40)

    def test_the_real_pin_refuses_a_fixture(self):
        with self.assertRaises(dolphin_ref.Refused):
            dolphin_ref.check_tree(self.src)

    def test_a_folder_without_git_is_refused(self):
        bare = temp_dir(self)
        with self.assertRaisesRegex(dolphin_ref.Refused, "not a git checkout"):
            dolphin_ref.check_tree(bare, sha=self.head, patch="")

    def test_an_edited_file_is_refused(self):
        (self.src / "README.md").write_text("edited")
        with self.assertRaisesRegex(dolphin_ref.Refused, "changed or untracked:  M README.md"):
            dolphin_ref.check_tree(self.src, sha=self.head, patch="")

    def test_an_untracked_file_is_refused(self):
        (self.src / "Movie.cpp").write_text("new")
        with self.assertRaisesRegex(dolphin_ref.Refused, r"\?\? Movie.cpp"):
            dolphin_ref.check_tree(self.src, sha=self.head, patch="")

    def test_drift_lists_moved_missing_and_conflicted_submodules(self):
        status = "\n".join([f" {'a' * 40} ok (x)", f"+{'b' * 40} moved (y)",
                            f"-{'c' * 40} missing", f"U{'d' * 40} conflict"])
        self.assertEqual([line[1:41] for line in dolphin_ref.submodule_drift(status)],
                         ["b" * 40, "c" * 40, "d" * 40])


class NestedSubmoduleTest(unittest.TestCase):
    """A tree with a submodule holding a submodule of its own, all real repositories."""

    def setUp(self):
        self.top = temp_dir(self) / "top"
        self.mid = self.top / "mid"
        self.leaf = self.mid / "leaf"
        commit(self.leaf, {"leaf.txt": "1"})
        commit(self.mid, {"mid.txt": "1"})
        add_submodule(self.mid, "leaf")
        commit(self.top, {"top.txt": "1"})
        self.head = add_submodule(self.top, "mid")

    def test_a_clean_nested_tree_passes(self):
        self.assertEqual(dolphin_ref.check_tree(self.top, sha=self.head, patch=""), self.head)

    def test_a_nested_submodule_off_its_pin_is_refused_as_drift(self):
        commit(self.leaf, {"leaf.txt": "2"})
        with self.assertRaisesRegex(dolphin_ref.Refused, r"submodules off their pins: \+\w+ "
                                                         r"mid/leaf"):
            dolphin_ref.check_tree(self.top, sha=self.head, patch="")

    def test_an_edit_inside_a_nested_submodule_is_refused(self):
        (self.leaf / "leaf.txt").write_text("edited")
        with self.assertRaisesRegex(dolphin_ref.Refused, "changed or untracked:  M mid"):
            dolphin_ref.check_tree(self.top, sha=self.head, patch="")


FRONTEND = "Source/Core/DolphinNoGUI/MainNoGUI.cpp"
CORE = "Source/Core/Core/Movie.cpp"
MAIN = "int main()\n{\n  return 0;\n}\n"
PLAYED = "int main()\n{\n  PlayInput();\n  return 0;\n}\n"


class PatchTreeTest(unittest.TestCase):
    """A real repository with a frontend and a core file, and a patch made by editing the
    frontend and taking check_tree's own git diff."""

    def setUp(self):
        self.src = temp_dir(self) / "src"
        self.head = commit(self.src, {FRONTEND: MAIN, CORE: "movie\n"})
        self.patch = self.diff_of(PLAYED)

    def diff_of(self, text: str) -> str:
        (self.src / FRONTEND).write_text(text)
        diff = dolphin_ref.git(self.src, *dolphin_ref.DIFF)
        git(self.src, "checkout", "--", FRONTEND)
        return diff

    def check(self) -> str:
        return dolphin_ref.check_tree(self.src, sha=self.head, patch=self.patch)

    def test_the_tree_with_exactly_the_patch_passes(self):
        (self.src / FRONTEND).write_text(PLAYED)
        self.assertEqual(self.check(), self.head)

    def test_the_patch_and_one_more_edit_in_its_file_is_refused(self):
        (self.src / FRONTEND).write_text(PLAYED + "// more\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, "git diff isn't headless-movie.patch"):
            self.check()

    def test_the_patch_and_an_edit_to_another_file_is_refused(self):
        (self.src / FRONTEND).write_text(PLAYED)
        (self.src / CORE).write_text("edited\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, f"changed or untracked:  M {CORE}"):
            self.check()

    def test_a_different_patch_is_refused(self):
        (self.src / FRONTEND).write_text(MAIN.replace("return 0", "return 1"))
        with self.assertRaisesRegex(dolphin_ref.Refused, "git diff isn't headless-movie.patch"):
            self.check()

    def test_a_clean_tree_is_refused_when_the_patch_is_due(self):
        with self.assertRaisesRegex(dolphin_ref.Refused, "git diff isn't headless-movie.patch"):
            self.check()

    def test_the_patch_with_an_untracked_file_is_refused(self):
        (self.src / FRONTEND).write_text(PLAYED)
        (self.src / "Source/Core/DolphinNoGUI/New.cpp").write_text("new\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, r"\?\? Source/Core/DolphinNoGUI/New"):
            self.check()

    def test_the_patch_staged_is_refused(self):
        (self.src / FRONTEND).write_text(PLAYED)
        git(self.src, "add", FRONTEND)
        with self.assertRaisesRegex(dolphin_ref.Refused, f"changed or untracked: M  {FRONTEND}"):
            self.check()

    def test_an_edit_marked_assume_unchanged_or_skip_worktree_is_refused(self):
        for flag, tag in (("--assume-unchanged", "h "), ("--skip-worktree", "S ")):
            with self.subTest(flag=flag):
                (self.src / FRONTEND).write_text(PLAYED)
                (self.src / CORE).write_text("edited\n")
                git(self.src, "update-index", flag, CORE)
                with self.assertRaisesRegex(dolphin_ref.Refused, f"skip-worktree\\): {tag}{CORE}"):
                    self.check()
                git(self.src, "update-index", flag.replace("--", "--no-"), CORE)
                git(self.src, "checkout", "--", CORE)

    def test_an_untracked_file_in_a_new_folder_is_named(self):
        (self.src / FRONTEND).write_text(PLAYED)
        (self.src / "Source/Core/New").mkdir()
        (self.src / "Source/Core/New/Movie2.cpp").write_text("new\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, r"\?\? Source/Core/New/Movie2.cpp"):
            self.check()

    def test_an_untracked_file_info_exclude_hides_is_refused(self):
        (self.src / FRONTEND).write_text(PLAYED)
        (self.src / ".git" / "info").mkdir(exist_ok=True)
        (self.src / ".git" / "info" / "exclude").write_text("*.h\n")
        (self.src / "Source/Core/Core/Movie.h").write_text("hidden\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, "!! Source/Core/Core/Movie.h"):
            self.check()

    def test_an_untracked_file_the_trees_gitignore_hides_is_refused(self):
        self.head = commit(self.src, {".gitignore": "*.h\n"})
        (self.src / FRONTEND).write_text(PLAYED)
        (self.src / "Source/Core/Core/Movie.h").write_text("hidden\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, "!! Source/Core/Core/Movie.h"):
            self.check()

    def test_info_attributes_or_a_local_filter_is_refused(self):
        (self.src / FRONTEND).write_text(PLAYED)
        attributes = self.src / ".git" / "info" / "attributes"
        attributes.parent.mkdir(exist_ok=True)
        attributes.write_text("*.cpp filter=hide\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, "attributes isn't empty"):
            self.check()
        attributes.write_text("\n")
        self.check()
        git(self.src, "config", "filter.hide.clean", "cat")
        with self.assertRaisesRegex(dolphin_ref.Refused, "local git config sets filter.hide.clean"):
            self.check()

    def test_the_users_git_config_cant_hide_an_edit(self):
        base = temp_dir(self)
        (base / "attributes").write_text("*.cpp filter=hide\n")
        (base / "config").write_text(f"[core]\n\tattributesFile = {base / 'attributes'}\n"
                                     "[filter \"hide\"]\n\tclean = sed -e s/MOVIE/movie/\n")
        (self.src / FRONTEND).write_text(PLAYED)
        (self.src / CORE).write_text("MOVIE\n")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": str(base / "config")}
        with mock.patch.dict(os.environ, env):
            # With that config git itself no longer sees the edit to CORE.
            seen = subprocess.run(["git", "-C", str(self.src), "status", "--porcelain"],
                                  capture_output=True, text=True, env=env, check=True).stdout
            self.assertEqual(seen, f" M {FRONTEND}\n")
            with self.assertRaisesRegex(dolphin_ref.Refused, f"changed or untracked:  M {CORE}"):
                self.check()

    def test_a_patch_outside_the_frontend_or_not_in_place_is_refused(self):
        (self.src / CORE).write_text("edited\n")
        core = dolphin_ref.git(self.src, *dolphin_ref.DIFF)
        git(self.src, "checkout", "--", CORE)
        with self.assertRaisesRegex(dolphin_ref.Refused, f"{CORE} outside"):
            dolphin_ref.patch_paths(core)
        for line in ("new file mode 100644", "deleted file mode 100644", "old mode 100644",
                     "rename from x", "Binary files a/x and b/x differ"):
            with self.subTest(line=line), self.assertRaises(dolphin_ref.Refused):
                dolphin_ref.patch_paths(self.patch + line + "\n")
        self.assertEqual(dolphin_ref.patch_paths(self.patch), [FRONTEND])

    def test_patch_applies_to_a_clean_tree_then_finds_it_applied(self):
        path = temp_dir(self) / "headless-movie.patch"
        path.write_text(self.patch)
        root = self.src.parent
        for said in ("applied", "already applied"):
            code, out, err = run_main(lambda argv: dolphin_ref.cmd_patch(root, self.head, path))
            self.assertEqual(code, 0, err)
            self.assertTrue(out.strip().endswith(f"headless-movie.patch {said}"), out)
            self.assertEqual((self.src / FRONTEND).read_text(), PLAYED)

    def test_patch_refuses_a_tree_with_another_edit_and_applies_nothing(self):
        path = temp_dir(self) / "headless-movie.patch"
        path.write_text(self.patch)
        (self.src / CORE).write_text("edited\n")
        with self.assertRaisesRegex(dolphin_ref.Refused, "changed or untracked"):
            dolphin_ref.cmd_patch(self.src.parent, self.head, path)
        self.assertEqual((self.src / FRONTEND).read_text(), MAIN)

    def test_patch_applies_with_git_apply(self):
        self.assertEqual(dolphin_ref.apply_command(Path("/r/src"), Path("/p/x.patch")),
                         ["git", "-C", "/r/src", "apply", "--whitespace=nowarn", "/p/x.patch"])


class RealPatchTest(unittest.TestCase):
    def test_it_changes_only_the_headless_frontend(self):
        text = dolphin_ref.PATCH.read_text(encoding="utf-8")
        self.assertEqual(dolphin_ref.patch_paths(text),
                         [dolphin_ref.PATCH_SCOPE + "MainNoGUI.cpp"])

    def test_it_plays_the_movie_before_boot_and_opts_out_of_relaunch(self):
        added = [line[1:] for line in dolphin_ref.PATCH.read_text(encoding="utf-8").splitlines()
                 if line.startswith("+") and not line.startswith("+++")]
        body = "\n".join(added)
        self.assertIn("GetMovie().PlayInput(movie_path, &savestate_path)", body)
        self.assertIn('sel_registerName("disableRelaunchOnLogin")', body)
        self.assertIn('sel_registerName("respondsToSelector:"), disable))', body)
        self.assertLess(body.index("if (!boot)"), body.index("PlayInput"))
        self.assertFalse(any(line.startswith("-") and not line.startswith("---") for line in
                             dolphin_ref.PATCH.read_text(encoding="utf-8").splitlines()))


class BuildRecordTest(unittest.TestCase):
    def setUp(self):
        self.build = temp_dir(self)

    def record(self, **fields) -> None:
        (self.build / dolphin_ref.BUILT).write_text(json.dumps(fields))

    def test_a_build_from_the_tree_with_the_patch_passes(self):
        self.record(src="a" * 40, patch=dolphin_ref.patch_sha())
        dolphin_ref.check_build(self.build, "a" * 40)

    def test_a_build_from_another_tree_is_refused(self):
        self.record(src="b" * 40, patch=dolphin_ref.patch_sha())
        with self.assertRaisesRegex(dolphin_ref.Refused, f"built from {'b' * 40}"):
            dolphin_ref.check_build(self.build, "a" * 40)

    def test_a_build_without_the_patch_or_with_another_is_refused(self):
        for patch in (None, dolphin_ref.patch_sha("other")):
            self.record(src="a" * 40, **({} if patch is None else {"patch": patch}))
            with self.subTest(patch=patch), \
                    self.assertRaisesRegex(dolphin_ref.Refused, f"built with patch {patch}"):
                dolphin_ref.check_build(self.build, "a" * 40)

    def test_the_patch_sha_is_the_files_sha256(self):
        self.assertEqual(dolphin_ref.patch_sha("x"),
                         "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881")

    def test_a_build_with_no_record_is_refused(self):
        with self.assertRaisesRegex(dolphin_ref.Refused, "no record"):
            dolphin_ref.check_build(self.build, "a" * 40)


class UserFolderTest(unittest.TestCase):
    def setUp(self):
        base = temp_dir(self).resolve()
        self.home = base / "dolphin-ref"
        self.home.mkdir()
        self.elsewhere = base / "elsewhere"
        self.elsewhere.mkdir()
        patch = mock.patch.object(dolphin_ref, "default_root", lambda: self.home)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_default_roots_user_folder_passes(self):
        self.assertEqual(dolphin_ref.check_user(self.home), self.home / "user")

    def test_another_roots_user_folder_is_refused(self):
        with self.assertRaisesRegex(dolphin_ref.Refused, "outside"):
            dolphin_ref.check_user(self.elsewhere)

    def test_a_user_folder_linked_out_of_the_root_is_refused(self):
        library = self.elsewhere / "Dolphin"
        library.mkdir()
        (self.home / "user").symlink_to(library)
        with self.assertRaisesRegex(dolphin_ref.Refused, "outside"):
            dolphin_ref.check_user(self.home)


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir(self).resolve()
        patch = mock.patch.object(dolphin_ref, "user_dirs", lambda: ("/folders/T", "/folders/C"))
        patch.start()
        self.addCleanup(patch.stop)

    def test_each_profile_writes_its_own_folder_and_the_users_temp_and_cache(self):
        writes = ('(allow file-write* (subpath "{}") (subpath "/folders/T") '
                  '(subpath "/folders/C") (literal "/dev/null"))')
        denies = ('(deny network* (with message "dolphin-ref"))'
                  '(deny file-write* (with message "dolphin-ref"))')
        for profile, own in ((dolphin_ref.build_profile(self.root), "build"),
                             (dolphin_ref.run_profile(self.root), "user")):
            self.assertIn(denies + writes.format(self.root / own), profile)

    def test_boot_runs_dolphin_awake_niced_and_sandboxed_with_its_user_folder(self):
        user = self.root / "user"
        cmd = dolphin_ref.boot_command(self.root, user, Path(ISO))
        self.assertEqual(cmd[:8], ["/usr/bin/caffeinate", "-i", "/usr/bin/nice", "-n", "19",
                                   "/usr/bin/sandbox-exec", "-p",
                                   dolphin_ref.run_profile(self.root)])
        self.assertEqual(cmd[8], str(self.root / "build" / "Binaries" / "dolphin-emu-nogui"))
        self.assertEqual(cmd[9:15], ["-u", str(user), "-p", "headless", "-v", "Metal"])
        self.assertEqual(cmd[-4:], ["-C", "Dolphin.Core.FastDiscSpeed=False", "-e", ISO])
        self.assertEqual(cmd.count("-C"), 1)

    def test_boot_reads_the_disc_at_the_speed_it_is_given(self):
        cmd = dolphin_ref.boot_command(self.root, self.root / "user", Path(ISO), disc="fast")
        self.assertEqual(cmd[-4:], ["-C", "Dolphin.Core.FastDiscSpeed=True", "-e", ISO])

    def test_boot_with_dumps_turns_frame_dumping_on(self):
        cmd = dolphin_ref.boot_command(self.root, self.root / "user", Path(ISO), dump=True)
        self.assertEqual(cmd[-6:], ["-C", "Dolphin.Core.FastDiscSpeed=False", "-C", "Dolphin.Movie.DumpFrames=True",
                                    "-e", ISO])

    def test_boot_with_a_movie_plays_it_with_m_before_the_disc(self):
        cmd = dolphin_ref.boot_command(self.root, self.root / "user", Path(ISO), dump=True,
                                       movie=Path("/movies/route.dtm"))
        self.assertEqual(cmd[-6:], ["-C", "Dolphin.Movie.DumpFrames=True", "-m",
                                    "/movies/route.dtm", "-e", ISO])
        self.assertNotIn("-m", dolphin_ref.boot_command(self.root, self.root / "user", Path(ISO)))

    def test_configure_runs_sandboxed_with_everything_online_off(self):
        cmd = dolphin_ref.configure_command(self.root)
        self.assertEqual(cmd[:3], ["/usr/bin/sandbox-exec", "-p",
                                   dolphin_ref.build_profile(self.root)])
        self.assertEqual(cmd[3:10], ["cmake", "-S", str(self.root / "src"), "-B",
                                     str(self.root / "build"), "-G", "Ninja"])
        for define in ("-DENABLE_AUTOUPDATE=OFF", "-DENABLE_ANALYTICS=OFF",
                       "-DUSE_RETRO_ACHIEVEMENTS=OFF", "-DUSE_DISCORD_PRESENCE=OFF",
                       "-DUSE_UPNP=OFF", "-DENABLE_VULKAN=OFF", "-DUSE_BUNDLED_MOLTENVK=OFF",
                       "-DUSE_SYSTEM_LIBS=OFF", "-DENABLE_QT=OFF", "-DENABLE_NOGUI=ON",
                       "-DDOLPHIN_DEFAULT_UPDATE_TRACK="):
            self.assertIn(define, cmd)

    def test_build_runs_sandboxed_and_builds_the_headless_frontend_and_the_tool(self):
        cmd = dolphin_ref.build_command(self.root)
        self.assertEqual(cmd, ["/usr/bin/sandbox-exec", "-p", dolphin_ref.build_profile(self.root),
                               "/usr/bin/nice", "-n", "10", "ninja", "-C",
                               str(self.root / "build"), "dolphin-nogui", "dolphin-tool"])

    def test_fetch_clones_the_tag_with_its_submodules(self):
        cmd = dolphin_ref.fetch_command(self.root / "src")
        self.assertEqual(cmd, ["git", "clone", "--depth", "1", "--branch", "2609a",
                               "--recurse-submodules", "--jobs", "8",
                               "https://github.com/dolphin-emu/dolphin.git",
                               str(self.root / "src")])

    def test_the_pin_is_a_full_commit(self):
        self.assertRegex(dolphin_ref.PIN.sha, r"^[0-9a-f]{40}$")

    def test_a_profile_refuses_a_path_that_would_break_its_string(self):
        with self.assertRaises(dolphin_ref.Refused):
            dolphin_ref.build_profile(self.root / 'a"b')


@unittest.skipUnless(HAS_SANDBOX, "needs macOS's sandbox-exec")
class ProfileTest(unittest.TestCase):
    """Each profile run for real: what it lets a process write and reach."""

    def setUp(self):
        self.base = temp_dir(self, prefix="sb").resolve()
        self.root = self.base / "root"
        for name in ("user", "build", "src"):
            (self.root / name).mkdir(parents=True)
        self.scratch = self.base / "scratch"
        self.scratch.mkdir()
        self.other = self.base / "other"
        self.other.mkdir()
        self.build = dolphin_ref.build_profile(self.root, [str(self.scratch)])
        self.run_ = dolphin_ref.run_profile(self.root, [str(self.scratch)])

    def sandboxed(self, profile: str, *cmd: str) -> int:
        return subprocess.run(dolphin_ref.sandboxed(profile, cmd), capture_output=True,
                              timeout=30).returncode

    def python(self, profile: str, code: str, *args: str) -> int:
        return self.sandboxed(profile, sys.executable, "-I", "-c", code, *args)

    def test_each_profile_writes_only_its_folder_the_scratch_and_dev_null(self):
        for make, own, others in ((dolphin_ref.build_profile, "build", ("user", "src", "")),
                                  (dolphin_ref.run_profile, "user", ("build", "src", ""))):
            with self.subTest(own=own):
                root = self.base / f"root-{own}"
                for name in ("user", "build", "src"):
                    (root / name).mkdir(parents=True)
                profile = make(root, [str(self.scratch)])
                self.assertEqual(self.sandboxed(profile, "/usr/bin/touch", str(root / own / "a"),
                                                str(self.scratch / own)), 0)
                self.assertEqual(self.python(profile, "open('/dev/null', 'w').write('x')"), 0)
                for path in (*(root / name / "b" for name in others), self.other / own):
                    self.assertNotEqual(self.sandboxed(profile, "/usr/bin/touch", str(path)), 0,
                                        path)
                    self.assertFalse(path.exists(), path)

    def test_the_scratch_folders_are_this_users_temp_and_cache_alone(self):
        temp, cache = dolphin_ref.user_dirs()
        self.assertEqual((Path(temp).name, Path(cache).name), ("T", "C"))
        self.assertEqual(Path(temp).parent, Path(cache).parent)
        for path in (temp, cache):
            self.assertEqual(path, os.path.realpath(path))
            self.assertTrue(path.startswith("/private/var/folders/"), path)

    def test_no_tcp_even_to_this_machine(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        self.addCleanup(server.close)
        port = str(server.getsockname()[1])
        connect = "import socket, sys; socket.create_connection(('127.0.0.1', int(sys.argv[1])))"
        self.assertEqual(self.python("(version 1)(allow default)", connect, port), 0)
        for profile in (self.build, self.run_):
            with self.subTest(profile=profile):
                self.assertNotEqual(self.python(profile, connect, port), 0)

    @unittest.skipUnless(os.path.exists(MDNS), "no mDNSResponder socket")
    def test_no_dns_through_mdnsresponder(self):
        connect = ("import socket, sys; s = socket.socket(socket.AF_UNIX); "
                   "s.connect(sys.argv[1])")
        self.assertEqual(self.python("(version 1)(allow default)", connect, MDNS), 0)
        for profile in (self.build, self.run_):
            with self.subTest(profile=profile):
                self.assertNotEqual(self.python(profile, connect, MDNS), 0)

    def test_only_dolphins_profile_sends_to_a_socket_and_only_inside_the_user_folder(self):
        send = ("import socket, sys; socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)"
                ".sendto(b'x', sys.argv[1])")
        inside, outside = self.root / "user" / "w", self.other / "w"
        for path in (inside, outside):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.bind(str(path))
            self.addCleanup(sock.close)
        self.assertEqual(self.python(self.run_, send, str(inside)), 0)
        self.assertNotEqual(self.python(self.run_, send, str(outside)), 0)
        self.assertNotEqual(self.python(self.build, send, str(inside)), 0)


class ConfigTest(unittest.TestCase):
    def test_config_turns_online_features_off(self):
        user = temp_dir(self) / "user"
        dolphin_ref.write_config(user)
        ini = configparser.ConfigParser(interpolation=None)
        ini.optionxform = str
        ini.read(user / "Config" / "Dolphin.ini")
        self.assertEqual(ini["Analytics"]["Enabled"], "False")
        self.assertEqual(ini["AutoUpdate"]["UpdateTrack"], "")
        self.assertEqual(ini["General"]["UseDiscordPresence"], "False")
        self.assertEqual(ini["General"]["GDBPort"], "-1")
        self.assertEqual(ini["Core"]["SerialPort1"], "255")
        self.assertEqual(ini["Core"]["EnableCheats"], "False")
        # What a movie with bSaveConfig off leaves to the run's config.
        self.assertEqual([ini["Core"][k] for k in ("CPUCore", "DSPHLE", "CPUThread",
                                                   "SlotA", "SlotB")],
                         ["4", "True", "False", "1", "255"])
        self.assertNotIn("FastDiscSpeed", ini["Core"])  # boot's --disc sets it
        dsu = configparser.ConfigParser(interpolation=None)
        dsu.read(user / "Config" / "DSUClient.ini")
        self.assertEqual(dsu["Server"]["Enabled"], "False")
        pad = configparser.ConfigParser(interpolation=None)
        pad.optionxform = str
        pad.read(user / "Config" / "GCPadNew.ini")
        self.assertEqual(pad["GCPad1"]["Device"], "Pipe/0/pad1")
        self.assertEqual(pad["GCPad1"]["Buttons/Start"], "`Button START`")
        self.assertEqual(pad["GCPad1"]["D-Pad/Down"], "`Button D_DOWN`")


class FreshConsoleTest(unittest.TestCase):
    def test_the_card_sram_and_pipe_are_new_and_nothing_else_goes(self):
        user = temp_dir(self) / "user"
        for name in ("GC/MemoryCardA.USA.raw", "GC/MovieA.raw", "GC/SRAM.raw",
                     "GC/MemoryCardB.USA.raw", "Pipes/pad1"):
            (user / name).parent.mkdir(parents=True, exist_ok=True)
            (user / name).write_text("old")
        pipe = dolphin_ref.fresh_console(user, ["805361AC", "80536000"])
        self.assertEqual(pipe, user / "Pipes" / "pad1")
        self.assertTrue(stat.S_ISFIFO(pipe.stat().st_mode))
        self.assertFalse((user / "GC" / "MemoryCardA.USA.raw").exists())
        self.assertFalse((user / "GC" / "MovieA.raw").exists())
        self.assertFalse((user / "GC" / "SRAM.raw").exists())
        self.assertTrue((user / "GC" / "MemoryCardB.USA.raw").exists())
        self.assertEqual((user / "MemoryWatcher" / "Locations.txt").read_text(),
                         "805361AC\n80536000\n")


class PressTest(unittest.TestCase):
    def test_a_press_goes_down_at_its_frame_and_up_its_duration_later(self):
        self.assertEqual(dolphin_ref.parse_presses("260:A:5, 1300:DOWN+START:2", 2000), {
            260: ["PRESS A"], 265: ["RELEASE A"], 1300: ["PRESS START", "PRESS D_DOWN"],
            1302: ["RELEASE START", "RELEASE D_DOWN"]})

    def test_it_reads_presses_as_the_routes_parser_does(self):
        self.assertEqual(dolphin_ref.parse_presses("10:UP+LEFT+RIGHT:1", 20)[10],
                         ["PRESS D_UP", "PRESS D_LEFT", "PRESS D_RIGHT"])
        with mock.patch.object(dolphin_ref.routes, "parse_route",
                               side_effect=ValueError("bad")) as parse:
            with self.assertRaisesRegex(dolphin_ref.Refused, "--press bad"):
                dolphin_ref.parse_presses("10:A:1", 20)
        parse.assert_called_once_with("10:A:1")

    def test_a_press_has_to_end_by_the_last_frame(self):
        self.assertEqual(dolphin_ref.parse_presses("95:A:5", 100), {95: ["PRESS A"],
                                                                    100: ["RELEASE A"]})
        with self.assertRaisesRegex(dolphin_ref.Refused, "after frame 100"):
            dolphin_ref.parse_presses("96:A:5", 100)

    def test_bad_presses_are_refused(self):
        for script in ("260:A", "260:Q:5", "0:A:5", "260:A:0", "x:A:5", "1:A:2:3",
                       "260:D_DOWN:5", "2/260:A:5", "260:SR:5"):
            with self.subTest(script=script), self.assertRaises(dolphin_ref.Refused):
                dolphin_ref.parse_presses(script, 2000)

    def test_the_pipe_gets_each_frames_commands_on_that_frame(self):
        path = temp_dir(self) / "pad1"
        path.write_text("")
        pipe = dolphin_ref.Pipe(path, {3: ["PRESS A", "PRESS B"], 5: ["RELEASE A"]})
        expected = ["", "", "PRESS A\nPRESS B\n", "PRESS A\nPRESS B\n",
                    "PRESS A\nPRESS B\nRELEASE A\n", "PRESS A\nPRESS B\nRELEASE A\n"]
        for n, text in enumerate(expected, 1):
            pipe.frame(n)
            self.assertEqual(path.read_text(), text, f"after frame {n}")
        pipe.close()


class WatchTest(unittest.TestCase):
    def test_the_default_is_the_word_holding_scene_major(self):
        self.assertEqual(dolphin_ref.default_watch(), "805361AC")

    def test_the_default_is_scene_majors_word_wherever_it_sits_in_it(self):
        for address in (0x80001234, 0x80001237):
            table = {"scene.major": SimpleNamespace(address=address, path=())}
            with self.subTest(address=address), \
                    mock.patch.object(dolphin_ref.kar_ram, "load", return_value=table):
                self.assertEqual(dolphin_ref.default_watch(), "80001234")

    def test_an_aligned_word_in_main_ram_passes(self):
        for text, word in (("80000000", "80000000"), ("817ffffc", "817FFFFC"),
                           ("805361AC", "805361AC")):
            self.assertEqual(dolphin_ref.watch_address(text), word)

    def test_a_kar_ram_name_gives_the_word_holding_it(self):
        for name, word in (("scene.minor", "805361AC"), ("vi.renew_count", "805DE2CC"),
                           ("pad.queue_write", "8058B080")):
            with self.subTest(name=name):
                self.assertEqual(dolphin_ref.watch_address(name), word)
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "behind a pointer"):
            dolphin_ref.watch_address("player1.x")

    def test_a_word_outside_main_ram_or_unaligned_is_refused(self):
        for text in ("7FFFFFFC", "81800000", "817FFFFE", "805361AD", "805361AE",
                     "805361AF", "zz"):
            with self.subTest(text=text), self.assertRaises(argparse.ArgumentTypeError):
                dolphin_ref.watch_address(text)

    def test_a_datagram_names_the_words_that_changed(self):
        self.assertEqual(dolphin_ref.parse_watch(b"805361ac\n2000000\n80536000\n0\n\0"),
                         {"805361AC": 0x2000000, "80536000": 0})
        self.assertEqual(dolphin_ref.parse_watch(b"\0"), {})


class PlayTest(unittest.TestCase):
    def setUp(self):
        self.sock = temp_dir(self, prefix="dr") / "w"

    def test_it_stops_the_process_group_with_sigint_after_n_frames(self):
        messages = [frame_message(("805361AC", 0x12000000))] + [b"\0"] * 3 + [
            frame_message(("805361AC", 0x02000000))] + [b"\0"] * 5
        fake, group = FakeDolphin(self.sock, messages), FakeGroup()
        seen = []
        run = dolphin_ref.play(["dolphin"], self.sock, 5, 5.0, ["805361AC"], seen.append,
                               popen=fake.popen, killpg=group)
        self.assertEqual(run.frames, 5)
        self.assertEqual(seen, [1, 2, 3, 4, 5])
        self.assertEqual([w["805361AC"] for w in run.ram],
                         [0x12000000] * 4 + [0x02000000])
        self.assertEqual(fake.kwargs, {"start_new_session": True})
        self.assertEqual(group.calls, [(4242, signal.SIGINT), (4242, 0)])
        self.assertFalse(self.sock.exists())

    def test_it_stops_when_frames_stop_coming(self):
        fake, group = FakeDolphin(self.sock, [b"\0", b"\0"]), FakeGroup()
        began = time.monotonic()
        run = dolphin_ref.play(["dolphin"], self.sock, 10, 0.3, ["805361AC"], popen=fake.popen,
                               killpg=group)
        self.assertEqual(run.frames, 2)
        self.assertLess(time.monotonic() - began, 5)  # the 0.3 s wait, with room for a slow run
        self.assertEqual(group.calls[0], (4242, signal.SIGINT))

    def test_a_group_still_there_after_the_grace_gets_sigkill(self):
        proc = mock.Mock(pid=77)
        group = FakeGroup(survives=True)
        dolphin_ref.stop(proc, grace=0.3, killpg=group)
        self.assertEqual(group.calls[0], (77, signal.SIGINT))
        self.assertEqual(group.calls[-1], (77, signal.SIGKILL))
        proc.wait.assert_called_once_with()

    def test_a_group_already_gone_is_left_alone(self):
        proc = mock.Mock(pid=77)
        dolphin_ref.stop(proc, killpg=mock.Mock(side_effect=ProcessLookupError))
        proc.wait.assert_not_called()

    def test_a_socket_path_too_long_is_refused(self):
        long = temp_dir(self) / ("x" * 120)
        with self.assertRaisesRegex(dolphin_ref.Refused, "too long"):
            dolphin_ref.play(["dolphin"], long, 1, 1.0, ["805361AC"], popen=self.fail)


class SaveRunTest(unittest.TestCase):
    def test_dumps_are_listed_and_moved_in_frame_order(self):
        base = temp_dir(self)
        dumps = base / "Frames"
        dumps.mkdir()
        for n in (1, 2, 10):
            (dumps / f"framedump_{n}.png").write_bytes(b"png%d" % n)
        run = dolphin_ref.Run(2, 1.5, 0, [{"805361AC": 1}, {"805361AC": 2}])
        count = dolphin_ref.save_run(base / "out", ["dolphin"], run, ["805361AC"], dumps)
        self.assertEqual(count, 3)
        names = [line.split()[1] for line in (base / "out" / "frames.txt").read_text().splitlines()]
        self.assertEqual(names, ["framedump_1.png", "framedump_2.png", "framedump_10.png"])
        self.assertEqual((base / "out" / "ram.txt").read_text(),
                         "frame 805361AC\n1 00000001\n2 00000002\n")
        self.assertEqual(sorted(p.name for p in (base / "out" / "frames").iterdir()),
                         ["framedump_1.png", "framedump_10.png", "framedump_2.png"])
        self.assertEqual(list(dumps.iterdir()), [])


class MainTest(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir(self).resolve()
        commit(self.root / "src", {"README.md": "not the pin"})
        self.iso = self.root / "game.iso"
        self.iso.write_bytes(b"GKYE01")
        for name, value in (("default_root", lambda: self.root),
                            ("user_dirs", lambda: ("/folders/T", "/folders/C"))):
            patch = mock.patch.object(dolphin_ref, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def boot(self, *extra: str) -> tuple[int, str, str]:
        with mock.patch.object(dolphin_ref, "play", side_effect=AssertionError("ran")):
            return run_main(dolphin_ref.main, "--root", str(self.root), "boot", str(self.iso),
                            "--frames", "10", *extra)

    def test_boot_refuses_a_tree_off_its_pin_and_runs_nothing(self):
        code, out, err = self.boot()
        self.assertEqual(code, 2)
        self.assertIn("not the pinned", err)
        self.assertFalse((self.root / "user").exists())

    def test_boot_refuses_a_build_from_another_tree_and_runs_nothing(self):
        (self.root / "build").mkdir()
        (self.root / "build" / dolphin_ref.BUILT).write_text(json.dumps({"src": "b" * 40}))
        with mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40):
            code, out, err = self.boot()
        self.assertEqual(code, 2)
        self.assertIn("built from", err)
        self.assertFalse((self.root / "user").exists())

    def built(self) -> None:
        (self.root / "build").mkdir()
        (self.root / "build" / dolphin_ref.BUILT).write_text(
            json.dumps({"src": "a" * 40, "patch": dolphin_ref.patch_sha()}))

    def test_boot_refuses_a_press_past_the_run_and_runs_nothing(self):
        self.built()
        with mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40):
            code, out, err = self.boot("--press", "8:A:5")
        self.assertEqual(code, 2)
        self.assertIn("after frame 10", err)
        self.assertFalse((self.root / "user").exists())

    def test_boot_refuses_a_movie_with_presses_or_no_movie_and_runs_nothing(self):
        self.built()
        movie = self.root / "route.dtm"
        movie.write_bytes(b"DTM\x1a")
        for extra, said in ((("--movie", str(movie), "--press", "1:A:1"), "one or the other"),
                            (("--movie", str(self.root / "none.dtm")), "no such movie")):
            with self.subTest(said=said), \
                    mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40):
                code, out, err = self.boot(*extra)
            self.assertEqual(code, 2)
            self.assertIn(said, err)
            self.assertFalse((self.root / "user").exists())

    def test_boot_plays_a_movie_by_its_full_path(self):
        self.built()
        (self.root / "route.dtm").write_bytes(b"DTM\x1aGKYE01" + bytes(246))
        run = dolphin_ref.Run(10, 1.0, 0, [{"805361AC": 0}] * 10)
        with mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40), \
                mock.patch.object(dolphin_ref, "check_user", return_value=self.root / "user"), \
                mock.patch.object(dolphin_ref, "play", return_value=run) as play:
            code, out, err = run_main(dolphin_ref.main, "--root", str(self.root), "boot",
                                      str(self.iso), "--frames", "10", "--movie",
                                      str(self.root / "route.dtm"))
        self.assertEqual(code, 0, err)
        cmd = play.call_args.args[0]
        self.assertEqual(cmd[-4:], ["-m", str(self.root / "route.dtm"), "-e", str(self.iso)])

    def test_boot_refuses_a_movie_for_another_game_and_runs_nothing(self):
        self.built()
        (self.root / "route.dtm").write_bytes(b"DTM\x1aGALE01" + bytes(246))
        with mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40), \
                mock.patch.object(dolphin_ref, "play", side_effect=AssertionError("ran")):
            code, out, err = self.boot("--movie", str(self.root / "route.dtm"))
        self.assertEqual(code, 2)
        self.assertIn("a movie for GALE01, not GKYE01", err)
        self.assertFalse((self.root / "user").exists())

    def test_build_refuses_a_tree_off_its_pin_and_runs_nothing(self):
        real_run = dolphin_ref.subprocess.run
        with mock.patch.object(dolphin_ref.subprocess, "run", wraps=real_run) as run:
            code, out, err = run_main(dolphin_ref.main, "--root", str(self.root), "build")
        self.assertEqual(code, 2)
        self.assertIn("not the pinned", err)
        self.assertFalse(any(call.args[0][0] != "git" for call in run.call_args_list))
        self.assertFalse((self.root / "build").exists())

    def test_build_records_the_commit_it_built(self):
        (self.root / "build").mkdir()
        with mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40), \
                mock.patch.object(dolphin_ref.subprocess, "run",
                                  return_value=SimpleNamespace(returncode=0)) as run:
            code, out, err = run_main(dolphin_ref.main, "--root", str(self.root), "build")
        self.assertEqual(code, 0)
        self.assertEqual([call.args[0][3] for call in run.call_args_list],
                         ["cmake", "/usr/bin/nice"])
        self.assertEqual(json.loads((self.root / "build" / dolphin_ref.BUILT).read_text()),
                         {"src": "a" * 40, "patch": dolphin_ref.patch_sha()})
        self.assertTrue((self.root / "build" / dolphin_ref.SYS_LINK).is_symlink())

    def test_build_names_the_step_that_failed(self):
        for failing, name in ((1, "cmake"), (2, "ninja")):
            calls = []

            def run(cmd, failing=failing, calls=calls):
                calls.append(cmd)
                return SimpleNamespace(returncode=1 if len(calls) == failing else 0)

            with self.subTest(step=name), \
                    mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40), \
                    mock.patch.object(dolphin_ref.subprocess, "run", run):
                code, out, err = run_main(dolphin_ref.main, "--root", str(self.root), "build")
            self.assertEqual(code, 2)
            self.assertIn(f"{name} failed", err)
            self.assertFalse((self.root / "build" / dolphin_ref.BUILT).exists())

    def test_fetch_refuses_a_tree_that_is_there(self):
        with mock.patch.object(dolphin_ref.subprocess, "run", side_effect=AssertionError("ran")):
            code, out, err = run_main(dolphin_ref.main, "--root", str(self.root), "fetch")
        self.assertEqual(code, 2)
        self.assertIn("already there", err)

    def test_audit_notes_name_the_pin_and_each_finding(self):
        code, out, err = run_main(dolphin_ref.main, "audit-notes")
        self.assertEqual(code, 0)
        self.assertIn(dolphin_ref.PIN.sha, out)
        for category in ("binary", "updater", "net-build", "net-src"):
            self.assertIn(f"\n{category}: ", out)


if __name__ == "__main__":
    unittest.main()
