from __future__ import annotations

import configparser
import signal
import socket
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import dolphin_ref
from testutil import commit, run_main, temp_dir

ISO = "/discs/game.iso"


class FakeDolphin:
    """Stands in for a Dolphin process: once started it sends MESSAGES to the memory watcher's
    socket, one datagram each, and records the signal that stops it."""

    def __init__(self, sock_path: Path, messages: list[bytes]) -> None:
        self.sock_path = sock_path
        self.messages = messages
        self.signals: list[int] = []
        self.returncode = None
        self.cmd: list[str] = []

    def popen(self, cmd: list[str]) -> "FakeDolphin":
        self.cmd = cmd
        self.thread = threading.Thread(target=self.send)
        self.thread.start()
        return self

    def send(self) -> None:
        out = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        for message in self.messages:
            out.sendto(message, str(self.sock_path))
        out.close()

    def poll(self):
        return self.returncode

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        self.returncode = 0

    def wait(self, timeout=None):
        self.thread.join()
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def frame_message(*pairs: tuple[str, int]) -> bytes:
    return "".join(f"{a.lower()}\n{v:x}\n" for a, v in pairs).encode() + b"\0"


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.src = temp_dir(self) / "src"
        self.head = commit(self.src, {"README.md": "dolphin"})

    def test_a_tree_at_its_pin_passes(self):
        dolphin_ref.check_tree(self.src, sha=self.head)

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

    def test_a_submodule_off_its_pin_is_refused(self):
        status = f" {self.head} Externals/ok (v1)\n+{'1' * 40} Externals/moved (v2)\n"
        replies = {"rev-parse": self.head + "\n", "submodule": status}
        with mock.patch.object(dolphin_ref, "git", lambda src, *args: replies[args[0]]):
            with self.assertRaisesRegex(dolphin_ref.Refused, "Externals/moved"):
                dolphin_ref.check_tree(self.src, sha=self.head)

    def test_drift_lists_moved_missing_and_conflicted_submodules(self):
        status = "\n".join([f" {'a' * 40} ok (x)", f"+{'b' * 40} moved (y)",
                            f"-{'c' * 40} missing", f"U{'d' * 40} conflict"])
        self.assertEqual([line[1:41] for line in dolphin_ref.submodule_drift(status)],
                         ["b" * 40, "c" * 40, "d" * 40])


class UserFolderTest(unittest.TestCase):
    def test_the_user_folder_is_inside_root(self):
        root = temp_dir(self)
        self.assertEqual(dolphin_ref.check_user(root), root / "user")

    def test_a_user_folder_that_is_dolphins_own_is_refused(self):
        root = temp_dir(self)
        library = temp_dir(self) / "Dolphin"
        library.mkdir()
        (root / "user").symlink_to(library)
        with mock.patch.object(dolphin_ref, "FORBIDDEN_USER", library):
            with self.assertRaisesRegex(dolphin_ref.Refused, "Dolphin's own user folder"):
                dolphin_ref.check_user(root)
            with self.assertRaises(dolphin_ref.Refused):
                dolphin_ref.boot_command(root, Path(ISO))


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir(self)

    def test_boot_runs_dolphin_awake_niced_and_sandboxed_with_its_own_user_folder(self):
        cmd = dolphin_ref.boot_command(self.root, Path(ISO))
        self.assertEqual(cmd[:8], ["/usr/bin/caffeinate", "-i", "/usr/bin/nice", "-n", "19",
                                   "/usr/bin/sandbox-exec", "-p", dolphin_ref.SANDBOX])
        self.assertEqual(cmd[8], str(self.root / "build" / "Binaries" / "dolphin-emu-nogui"))
        self.assertEqual(cmd[9:15], ["-u", str(self.root / "user"), "-p", "headless", "-v",
                                     "Metal"])
        self.assertEqual(cmd[-2:], ["-e", ISO])
        self.assertNotIn("-C", cmd)

    def test_boot_with_dumps_turns_frame_dumping_on(self):
        cmd = dolphin_ref.boot_command(self.root, Path(ISO), dump=True)
        self.assertEqual(cmd[-4:], ["-C", "Dolphin.Movie.DumpFrames=True", "-e", ISO])

    def test_the_sandbox_denies_every_network_but_unix_sockets(self):
        self.assertEqual(dolphin_ref.SANDBOX, "(version 1)(allow default)(deny network*)"
                                              "(allow network* (local unix))")

    def test_configure_runs_sandboxed_with_everything_online_off(self):
        cmd = dolphin_ref.configure_command(self.root / "src", self.root / "build")
        self.assertEqual(cmd[:3], ["/usr/bin/sandbox-exec", "-p", dolphin_ref.SANDBOX])
        self.assertEqual(cmd[3:10], ["cmake", "-S", str(self.root / "src"), "-B",
                                     str(self.root / "build"), "-G", "Ninja"])
        for define in ("-DENABLE_AUTOUPDATE=OFF", "-DENABLE_ANALYTICS=OFF",
                       "-DUSE_RETRO_ACHIEVEMENTS=OFF", "-DUSE_DISCORD_PRESENCE=OFF",
                       "-DUSE_UPNP=OFF", "-DENABLE_VULKAN=OFF", "-DUSE_BUNDLED_MOLTENVK=OFF",
                       "-DUSE_SYSTEM_LIBS=OFF", "-DENABLE_QT=OFF", "-DENABLE_NOGUI=ON",
                       "-DDOLPHIN_DEFAULT_UPDATE_TRACK="):
            self.assertIn(define, cmd)

    def test_build_runs_sandboxed_and_builds_the_headless_frontend_and_the_tool(self):
        cmd = dolphin_ref.build_command(self.root / "build")
        self.assertEqual(cmd, ["/usr/bin/sandbox-exec", "-p", dolphin_ref.SANDBOX,
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


class PressTest(unittest.TestCase):
    def test_a_press_goes_down_at_its_frame_and_up_its_duration_later(self):
        self.assertEqual(dolphin_ref.parse_presses("260:A:5, 1300:START+B:2"), {
            260: ["PRESS A"], 265: ["RELEASE A"], 1300: ["PRESS START", "PRESS B"],
            1302: ["RELEASE START", "RELEASE B"]})

    def test_bad_presses_are_refused(self):
        for script in ("260:A", "260:Q:5", "0:A:5", "260:A:0", "x:A:5", "1:A:2:3"):
            with self.subTest(script=script), self.assertRaises(dolphin_ref.Refused):
                dolphin_ref.parse_presses(script)

    def test_the_pipe_gets_each_frames_commands(self):
        path = temp_dir(self) / "pad1"
        path.write_text("")
        pipe = dolphin_ref.Pipe(path, {3: ["PRESS A", "PRESS B"], 5: ["RELEASE A"]})
        for n in range(1, 4):
            pipe.frame(n)
        self.assertEqual(path.read_text(), "PRESS A\nPRESS B\n")
        for n in range(4, 7):
            pipe.frame(n)
        pipe.close()
        self.assertEqual(path.read_text(), "PRESS A\nPRESS B\nRELEASE A\n")


class PlayTest(unittest.TestCase):
    def setUp(self):
        self.sock = temp_dir(self, prefix="dr") / "w"

    def test_it_stops_dolphin_with_sigint_after_n_frames(self):
        messages = [frame_message(("805361AC", 0x12000000))] + [b"\0"] * 3 + [
            frame_message(("805361AC", 0x02000000))] + [b"\0"] * 5
        fake = FakeDolphin(self.sock, messages)
        seen = []
        run = dolphin_ref.play(["dolphin"], self.sock, 5, 5.0, ["805361AC"], seen.append,
                               popen=fake.popen)
        self.assertEqual(run.frames, 5)
        self.assertEqual(seen, [1, 2, 3, 4, 5])
        self.assertEqual([w["805361AC"] for w in run.ram],
                         [0x12000000] * 4 + [0x02000000])
        self.assertEqual(fake.signals, [signal.SIGINT])
        self.assertFalse(self.sock.exists())

    def test_it_stops_when_frames_stop_coming(self):
        fake = FakeDolphin(self.sock, [b"\0", b"\0"])
        began = time.monotonic()
        run = dolphin_ref.play(["dolphin"], self.sock, 10, 0.3, ["805361AC"], popen=fake.popen)
        self.assertEqual(run.frames, 2)
        self.assertLess(time.monotonic() - began, 5)
        self.assertEqual(fake.signals, [signal.SIGINT])

    def test_a_socket_path_too_long_is_refused(self):
        long = temp_dir(self) / ("x" * 120)
        with self.assertRaisesRegex(dolphin_ref.Refused, "too long"):
            dolphin_ref.play(["dolphin"], long, 1, 1.0, ["805361AC"], popen=self.fail)

    def test_a_datagram_names_the_words_that_changed(self):
        self.assertEqual(dolphin_ref.parse_watch(b"805361ac\n2000000\n80536000\n0\n\0"),
                         {"805361AC": 0x2000000, "80536000": 0})
        self.assertEqual(dolphin_ref.parse_watch(b"\0"), {})


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
        self.root = temp_dir(self)
        commit(self.root / "src", {"README.md": "not the pin"})
        self.iso = self.root / "game.iso"
        self.iso.write_bytes(b"GKYE01")

    def test_boot_refuses_a_tree_off_its_pin_and_runs_nothing(self):
        with mock.patch.object(dolphin_ref, "play", side_effect=AssertionError("ran")):
            code, out, err = run_main(dolphin_ref.main, "--root", str(self.root), "boot",
                                      str(self.iso), "--frames", "10")
        self.assertEqual(code, 2)
        self.assertIn("not the pinned", err)
        self.assertFalse((self.root / "user").exists())

    def test_build_refuses_a_tree_off_its_pin_and_runs_nothing(self):
        real_run = dolphin_ref.subprocess.run
        with mock.patch.object(dolphin_ref.subprocess, "run", wraps=real_run) as run:
            code, out, err = run_main(dolphin_ref.main, "--root", str(self.root), "build")
        self.assertEqual(code, 2)
        self.assertIn("not the pinned", err)
        self.assertFalse(any(call.args[0][0] != "git" for call in run.call_args_list))
        self.assertFalse((self.root / "build").exists())

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
