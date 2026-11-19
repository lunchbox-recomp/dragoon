from __future__ import annotations

import configparser
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import threading
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
    """Stands in for a Dolphin process: once started it sends MESSAGES to the memory watcher's
    socket, one datagram each."""

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
        self.thread = threading.Thread(target=self.send)
        self.thread.start()
        return self

    def send(self) -> None:
        out = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        for message in self.messages:
            out.sendto(message, str(self.sock_path))
        out.close()

    def poll(self):
        """Exits once it has sent everything, as Dolphin does on SIGINT."""
        self.thread.join()
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
        self.assertEqual(dolphin_ref.check_tree(self.src, sha=self.head), self.head)

    def test_a_tree_off_its_pin_is_refused(self):
        with self.assertRaisesRegex(dolphin_ref.Refused, "not the pinned"):
            dolphin_ref.check_tree(self.src, sha="0" * 40)

    def test_the_real_pin_refuses_a_fixture(self):
        with self.assertRaises(dolphin_ref.Refused):
            dolphin_ref.check_tree(self.src)

    def test_a_folder_without_git_is_refused(self):
        bare = temp_dir(self)
        with self.assertRaisesRegex(dolphin_ref.Refused, "not a git checkout"):
            dolphin_ref.check_tree(bare, sha=self.head)

    def test_an_edited_file_is_refused(self):
        (self.src / "README.md").write_text("edited")
        with self.assertRaisesRegex(dolphin_ref.Refused, "changed or untracked:  M README.md"):
            dolphin_ref.check_tree(self.src, sha=self.head)

    def test_an_untracked_file_is_refused(self):
        (self.src / "Movie.cpp").write_text("new")
        with self.assertRaisesRegex(dolphin_ref.Refused, r"\?\? Movie.cpp"):
            dolphin_ref.check_tree(self.src, sha=self.head)

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
        self.assertEqual(dolphin_ref.check_tree(self.top, sha=self.head), self.head)

    def test_a_nested_submodule_off_its_pin_is_refused_as_drift(self):
        commit(self.leaf, {"leaf.txt": "2"})
        with self.assertRaisesRegex(dolphin_ref.Refused, r"submodules off their pins: \+\w+ "
                                                         r"mid/leaf"):
            dolphin_ref.check_tree(self.top, sha=self.head)

    def test_an_edit_inside_a_nested_submodule_is_refused(self):
        (self.leaf / "leaf.txt").write_text("edited")
        with self.assertRaisesRegex(dolphin_ref.Refused, "changed or untracked:  M mid"):
            dolphin_ref.check_tree(self.top, sha=self.head)


class BuildRecordTest(unittest.TestCase):
    def setUp(self):
        self.build = temp_dir(self)

    def test_a_build_from_the_tree_passes(self):
        (self.build / dolphin_ref.BUILT).write_text(json.dumps({"src": "a" * 40}))
        dolphin_ref.check_build(self.build, "a" * 40)

    def test_a_build_from_another_tree_is_refused(self):
        (self.build / dolphin_ref.BUILT).write_text(json.dumps({"src": "b" * 40}))
        with self.assertRaisesRegex(dolphin_ref.Refused, f"built from {'b' * 40}"):
            dolphin_ref.check_build(self.build, "a" * 40)

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

    def test_boot_runs_dolphin_awake_niced_and_sandboxed_with_its_user_folder(self):
        user = self.root / "user"
        cmd = dolphin_ref.boot_command(self.root, user, Path(ISO))
        self.assertEqual(cmd[:8], ["/usr/bin/caffeinate", "-i", "/usr/bin/nice", "-n", "19",
                                   "/usr/bin/sandbox-exec", "-p",
                                   dolphin_ref.run_profile(self.root)])
        self.assertEqual(cmd[8], str(self.root / "build" / "Binaries" / "dolphin-emu-nogui"))
        self.assertEqual(cmd[9:15], ["-u", str(user), "-p", "headless", "-v", "Metal"])
        self.assertEqual(cmd[-2:], ["-e", ISO])
        self.assertNotIn("-C", cmd)

    def test_boot_with_dumps_turns_frame_dumping_on(self):
        cmd = dolphin_ref.boot_command(self.root, self.root / "user", Path(ISO), dump=True)
        self.assertEqual(cmd[-4:], ["-C", "Dolphin.Movie.DumpFrames=True", "-e", ISO])

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
        (self.root / "user").mkdir(parents=True)
        self.scratch = self.base / "scratch"
        self.scratch.mkdir()
        self.other = self.base / "other"
        self.other.mkdir()
        self.build = dolphin_ref.build_profile(self.root, str(self.scratch))
        self.run_ = dolphin_ref.run_profile(self.root, str(self.scratch))

    def sandboxed(self, profile: str, *cmd: str) -> int:
        return subprocess.run(dolphin_ref.sandboxed(profile, cmd), capture_output=True,
                              timeout=30).returncode

    def python(self, profile: str, code: str, *args: str) -> int:
        return self.sandboxed(profile, sys.executable, "-I", "-c", code, *args)

    def test_writes_go_only_to_the_root_scratch_and_dev_null(self):
        for profile in (self.build, self.run_):
            with self.subTest(profile=profile):
                self.assertEqual(self.sandboxed(profile, "/usr/bin/touch", str(self.root / "a"),
                                                str(self.scratch / "b")), 0)
                self.assertEqual(self.python(profile, "open('/dev/null', 'w').write('x')"), 0)
                self.assertNotEqual(self.sandboxed(profile, "/usr/bin/touch",
                                                   str(self.other / "c")), 0)
                self.assertFalse((self.other / "c").exists())

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
        for name in ("GC/MemoryCardA.USA.raw", "GC/SRAM.raw", "GC/MemoryCardB.USA.raw",
                     "Pipes/pad1"):
            (user / name).parent.mkdir(parents=True, exist_ok=True)
            (user / name).write_text("old")
        pipe = dolphin_ref.fresh_console(user, ["805361AC", "80536000"])
        self.assertEqual(pipe, user / "Pipes" / "pad1")
        self.assertTrue(stat.S_ISFIFO(pipe.stat().st_mode))
        self.assertFalse((user / "GC" / "MemoryCardA.USA.raw").exists())
        self.assertFalse((user / "GC" / "SRAM.raw").exists())
        self.assertTrue((user / "GC" / "MemoryCardB.USA.raw").exists())
        self.assertEqual((user / "MemoryWatcher" / "Locations.txt").read_text(),
                         "805361AC\n80536000\n")


class PressTest(unittest.TestCase):
    def test_a_press_goes_down_at_its_frame_and_up_its_duration_later(self):
        self.assertEqual(dolphin_ref.parse_presses("260:A:5, 1300:START+D_DOWN:2", 2000), {
            260: ["PRESS A"], 265: ["RELEASE A"], 1300: ["PRESS START", "PRESS D_DOWN"],
            1302: ["RELEASE START", "RELEASE D_DOWN"]})

    def test_a_press_has_to_end_by_the_last_frame(self):
        self.assertEqual(dolphin_ref.parse_presses("95:A:5", 100), {95: ["PRESS A"],
                                                                    100: ["RELEASE A"]})
        with self.assertRaisesRegex(dolphin_ref.Refused, "after frame 100"):
            dolphin_ref.parse_presses("96:A:5", 100)

    def test_bad_presses_are_refused(self):
        for script in ("260:A", "260:Q:5", "0:A:5", "260:A:0", "x:A:5", "1:A:2:3", "260:DOWN:5"):
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
            table = {"scene.major": SimpleNamespace(address=address)}
            with self.subTest(address=address), \
                    mock.patch.object(dolphin_ref.kar_ram, "load", return_value=table):
                self.assertEqual(dolphin_ref.default_watch(), "80001234")

    def test_an_aligned_word_in_main_ram_passes(self):
        for text, word in (("80000000", "80000000"), ("817ffffc", "817FFFFC"),
                           ("805361AC", "805361AC")):
            self.assertEqual(dolphin_ref.watch_address(text), word)

    def test_a_word_outside_main_ram_or_unaligned_is_refused(self):
        for text in ("7FFFFFFC", "81800000", "817FFFFE", "805361AD", "805361AE",
                     "805361AF", "zz"):
            with self.subTest(text=text), self.assertRaises(Exception) as caught:
                dolphin_ref.watch_address(text)
            self.assertEqual(type(caught.exception).__name__, "ArgumentTypeError")

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
        fake.thread.join()
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
        fake.thread.join()
        self.assertEqual(run.frames, 2)
        self.assertLess(time.monotonic() - began, 5)
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
        patch = mock.patch.object(dolphin_ref, "default_root", lambda: self.root)
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

    def test_boot_refuses_a_press_past_the_run_and_runs_nothing(self):
        (self.root / "build").mkdir()
        (self.root / "build" / dolphin_ref.BUILT).write_text(json.dumps({"src": "a" * 40}))
        with mock.patch.object(dolphin_ref, "check_tree", return_value="a" * 40):
            code, out, err = self.boot("--press", "8:A:5")
        self.assertEqual(code, 2)
        self.assertIn("after frame 10", err)
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
                         {"src": "a" * 40})
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
