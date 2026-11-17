"""make_install_script.py, and the install.sh it writes run under /bin/sh on a fixture zip of a
small fake app, with a HOME whose path has a space and fakes leading PATH."""
from __future__ import annotations

import hashlib
import os
import subprocess
import unittest
from pathlib import Path

import fake_tools
import make_install_script
from testutil import run_main, temp_dir, tree

# The fakes log each call to $FAKE_RECORDS as "NAME ARGS".
# - sysctl -n hw.optional.arm64 prints 1, as on Apple silicon, or fails as an Intel Mac's does
#   when the switch "intel" is on. The script runs /usr/sbin/sysctl by its full path, so this fake
#   sits apart from the others, off PATH, and reaches the script through DRAGOON_INSTALL_SYSCTL.
# - uname says x86_64, as it does in a Terminal under Rosetta, so a script that asked it would
#   refuse every Mac here.
# - sw_vers says what the switch file "macos" holds, or 14.0, the oldest macOS the app runs on.
# - pgrep finds Dragoon when "launcher running" is on and dragoon when "game running" is, names that
#   differ by more than case, since the switches sit on a volume that ignores case.
# - open only logs. curl logs and runs the real one, which reads the fixture's file:// URL.
# - mv counts its calls. On call N it fails when "fail mv N" is on, sends SIGTERM to the script
#   and fails when "term on mv N" is on, and moves and then makes a new directory where its first
#   argument was when "intruder on mv N" is on. Otherwise it runs the real one.
# - rm counts its calls and sends SIGTERM to the script on call N when "term on rm N" is on, then
#   runs the real one. Only the exit trap runs rm.
FAKES: dict[str, str] = {}
SYSCTL = {
    "sysctl": '#!/bin/sh\necho "sysctl $*" >> "$FAKE_RECORDS"\n'
              'if [ -e "$FAKE_SWITCHES/intel" ]; then echo "sysctl: unknown oid \'$2\'" >&2; exit 1; fi\n'
              'echo 1\n',
}
SCRIPTS = {
    "rm": '#!/bin/sh\necho "rm $*" >> "$FAKE_RECORDS"\nn=$(grep -c "^rm " "$FAKE_RECORDS")\n'
          'if [ -e "$FAKE_SWITCHES/term on rm $n" ]; then kill -TERM "$PPID"; fi\n'
          'exec /bin/rm "$@"\n',
    "uname": '#!/bin/sh\necho "uname $*" >> "$FAKE_RECORDS"\necho x86_64\n',
    "sw_vers": '#!/bin/sh\necho "sw_vers $*" >> "$FAKE_RECORDS"\n'
               'if [ -e "$FAKE_SWITCHES/macos" ]; then cat "$FAKE_SWITCHES/macos"; else echo 14.0; fi\n',
    "pgrep": '#!/bin/sh\necho "pgrep $*" >> "$FAKE_RECORDS"\nfor name; do :; done\n'
             'case $name in Dragoon) what=launcher ;; dragoon) what=game ;; *) exit 1 ;; esac\n'
             '[ -e "$FAKE_SWITCHES/$what running" ]\n',
    "open": '#!/bin/sh\necho "open $*" >> "$FAKE_RECORDS"\n',
    "curl": '#!/bin/sh\necho "curl $*" >> "$FAKE_RECORDS"\nexec /usr/bin/curl "$@"\n',
    "mv": '#!/bin/sh\necho "mv $*" >> "$FAKE_RECORDS"\nn=$(grep -c "^mv " "$FAKE_RECORDS")\n'
          'if [ -e "$FAKE_SWITCHES/fail mv $n" ]; then echo "mv: fake failure" >&2; exit 1; fi\n'
          'if [ -e "$FAKE_SWITCHES/term on mv $n" ]; then kill -TERM "$PPID"; exit 1; fi\n'
          'if [ -e "$FAKE_SWITCHES/intruder on mv $n" ]; then /bin/mv "$@" && mkdir "$1"; exit; fi\n'
          'exec /bin/mv "$@"\n',
}
UID = str(os.getuid())
CHECKS = [("sysctl", "-n hw.optional.arm64"), ("sw_vers", "-productVersion"),
          ("pgrep", f"-x -U {UID} Dragoon"), ("pgrep", f"-x -U {UID} dragoon")]
LOCK = ".Dragoon-install.lock"
V1 = {"Contents/Info.plist": "<plist>1</plist>\n", "Contents/MacOS/Dragoon": "the launcher\n",
      "Contents/Resources/kit/kit.mk": "KIT = 1\n", "Contents/Resources/source/a file.txt": "one\n",
      "Contents/Resources/gone.txt": "only in the first\n"}
V2 = {"Contents/Info.plist": "<plist>2</plist>\n", "Contents/MacOS/Dragoon": "the next launcher\n",
      "Contents/Resources/kit/kit.mk": "KIT = 2\n", "Contents/Resources/source/a file.txt": "two\n",
      "Contents/Resources/new.txt": "only in the second\n"}


def setUpModule() -> None:
    FAKES.update(fake_tools.write(SCRIPTS))
    FAKES.update(fake_tools.write(SYSCTL))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstallScript(fake_tools.FakeToolsTest):
    def setUp(self) -> None:
        super().setUp()
        self.home = self.dir / "home with space"
        self.home.mkdir()
        self.tmp = self.dir / "tmp dir"
        self.tmp.mkdir()
        self.apps = self.home / "Applications"
        self.app = self.apps / "Dragoon.app"
        self.saves = self.home / "Library/Application Support/Dragoon/saves"
        self.saves.mkdir(parents=True)
        (self.saves / "memcard.txt").write_text("a save\n")

    def fixture(self, name: str, files: dict[str, str]) -> Path:
        """NAME/Dragoon.app holding FILES, with the launcher executable and a symlink, zipped as
        the release zips it into NAME.zip, which is returned."""
        app = self.dir / name / "Dragoon.app"
        for rel, text in files.items():
            (app / rel).parent.mkdir(parents=True, exist_ok=True)
            (app / rel).write_text(text)
        (app / "Contents/MacOS/Dragoon").chmod(0o755)
        (app / "Contents/Resources/kit.mk").symlink_to("kit/kit.mk")
        zipped = self.dir / f"{name}.zip"
        subprocess.run(["ditto", "-c", "-k", "--norsrc", "--keepParent", str(app), str(zipped)], check=True)
        return zipped

    def script(self, zipped: Path, served: Path | None = None) -> Path:
        """install.sh for ZIPPED's hash, downloading SERVED, which is ZIPPED unless given."""
        out = self.dir / f"install {zipped.stem}.sh"
        code, stdout, err = run_main(make_install_script.main, "--zip", str(zipped), "--url",
                                     (served or zipped).as_uri(), "--out", str(out))
        self.assertEqual((code, err), (0, ""))
        return out

    def install(self, script: Path, piped: bool = False, home: str | None = None,
                left: int = 0, lock: bool = False, real_sysctl: bool = False,
                path: str = "/usr/bin:/bin:/usr/sbin:/sbin") -> subprocess.CompletedProcess:
        """Run SCRIPT under /bin/sh as `sh FILE`, or fed on stdin as `curl ... | sh` does, with HOME
        set to HOME if given and the fakes ahead of PATH. The fake sysctl stands in for the real one
        unless REAL_SYSCTL. Check it left no download folder and, beside the app, LEFT stage
        folders and a lock only if LOCK."""
        env = {"HOME": str(self.home) if home is None else home, "TMPDIR": str(self.tmp),
               "PATH": f"{Path(FAKES['open']).parent}:{path}",
               "FAKE_RECORDS": str(self.records), "FAKE_SWITCHES": str(self.switches)}
        if not real_sysctl:
            env["DRAGOON_INSTALL_SYSCTL"] = FAKES["sysctl"]
        if piped:
            with script.open("rb") as f:
                done = subprocess.run(["/bin/sh"], stdin=f, env=env, capture_output=True, text=True)
        else:
            done = subprocess.run(["/bin/sh", str(script)], env=env, capture_output=True, text=True)
        self.assertEqual(os.listdir(self.tmp), [], done.stderr)
        if self.apps.exists():
            self.assertEqual(len(self.stages()), left, done.stderr)
            self.assertLessEqual(set(os.listdir(self.apps)) - set(self.stages()),
                                 {"Dragoon.app", LOCK} if lock else {"Dragoon.app"}, done.stderr)
        return done

    def stages(self) -> list[str]:
        return [n for n in os.listdir(self.apps) if n.startswith(".Dragoon-install.") and n != LOCK]

    def installed(self, name: str, at: Path | None = None) -> None:
        """The app at AT, the installed one unless given, is NAME's fixture app file for file, and
        the saves are untouched."""
        at = at or self.app
        self.assertFalse(at.is_symlink())
        self.assertEqual(tree(at), tree(self.dir / name / "Dragoon.app"))
        self.assertTrue(os.access(at / "Contents/MacOS/Dragoon", os.X_OK))
        self.assertEqual(tree(self.saves), {"memcard.txt": b"a save\n"})

    def calls(self, tool: str) -> list[str]:
        return [args for name, args in self.recorded() if name == tool]

    def first_install(self) -> Path:
        """Install v1 and return a script for v2, with the records cleared."""
        self.assertEqual(self.install(self.script(self.fixture("v1", V1))).returncode, 0)
        v2 = self.script(self.fixture("v2", V2))
        self.records.unlink()
        return v2

    def test_a_good_zip_installs_the_app_file_for_file_and_opens_it_once(self):
        zipped = self.fixture("v1", V1)
        done = self.install(self.script(zipped), piped=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.installed("v1")
        self.assertEqual(os.listdir(self.apps), ["Dragoon.app"])
        self.assertEqual(self.recorded()[:4], CHECKS)
        [curl] = self.calls("curl")
        self.assertTrue(curl.startswith(f"-fsSL -g -o {self.tmp}/"), curl)
        self.assertTrue(curl.endswith(f"/Dragoon.zip {zipped.as_uri()}"), curl)
        self.assertEqual(self.calls("open"), [str(self.app)])
        self.assertIn(f"Dragoon is in {self.apps}", done.stdout)

    def test_a_rosetta_terminal_installs_since_uname_isnt_asked(self):
        self.assertEqual(self.install(self.script(self.fixture("v1", V1))).returncode, 0)
        self.assertEqual(self.calls("uname"), [])
        self.installed("v1")

    def test_a_newer_macos_installs_too(self):
        (self.switches / "macos").write_text("26.1\n")
        self.assertEqual(self.install(self.script(self.fixture("v1", V1))).returncode, 0)
        self.installed("v1")

    def test_a_second_run_replaces_the_app_and_leaves_no_stray_copy(self):
        v2 = self.first_install()
        done = self.install(v2)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.installed("v2")
        self.assertEqual(os.listdir(self.apps), ["Dragoon.app"])
        self.assertEqual(self.calls("open"), [str(self.app)])

    def test_a_file_or_a_symlink_at_the_app_is_replaced_and_a_symlinks_target_left_alone(self):
        elsewhere = self.dir / "elsewhere"
        (elsewhere / "Contents").mkdir(parents=True)
        (elsewhere / "Contents/mine.txt").write_text("mine\n")
        for case in ("a file", "a dangling symlink", "a symlink to a folder"):
            with self.subTest(case=case):
                self.apps.mkdir(exist_ok=True)
                if case == "a file":
                    self.app.write_text("not an app\n")
                else:
                    self.app.symlink_to(self.dir / "nowhere" if case == "a dangling symlink" else elsewhere)
                done = self.install(self.script(self.fixture(f"v1 {case}", V1)))
                self.assertEqual(done.returncode, 0, done.stderr)
                self.installed(f"v1 {case}")
                self.assertEqual(os.listdir(self.apps), ["Dragoon.app"])
                self.assertEqual(tree(elsewhere), {"Contents": "dir", "Contents/mine.txt": b"mine\n"})
                subprocess.run(["rm", "-r", str(self.app)], check=True)

    def test_a_failed_swap_puts_the_earlier_app_back(self):
        v2 = self.first_install()
        self.switch("fail mv 2")
        done = self.install(v2)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"Couldn't move Dragoon.app into {self.apps}. Nothing was installed.", done.stderr)
        self.installed("v1")
        self.assertEqual(len(self.calls("mv")), 3)
        self.assertEqual(self.calls("open"), [])

    def test_a_signal_between_the_two_moves_puts_the_earlier_app_back(self):
        v2 = self.first_install()
        self.switch("term on mv 2")
        done = self.install(v2)
        self.assertNotEqual(done.returncode, 0)
        self.installed("v1")
        self.assertEqual(self.calls("open"), [])

    def test_a_second_signal_during_the_exit_trap_still_puts_the_earlier_app_back(self):
        v2 = self.first_install()
        # The swap fails, and the trap's first rm, of the download folder, sends a SIGTERM.
        self.switch("fail mv 2", "term on rm 1")
        done = self.install(v2)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"Couldn't move Dragoon.app into {self.apps}. Nothing was installed.", done.stderr)
        self.installed("v1")
        self.assertEqual(len(self.calls("mv")), 3)

    def test_a_failed_move_back_keeps_the_earlier_app_and_names_where_it_is(self):
        v2 = self.first_install()
        self.switch("fail mv 2", "fail mv 3")
        done = self.install(v2, left=1)
        self.assertEqual(done.returncode, 1)
        [stage] = self.stages()
        kept = self.apps / stage / "previous.app"
        self.assertIn(f"The app that was at {self.app} is now at {kept}\n", done.stderr)
        self.installed("v1", at=kept)
        self.assertFalse(self.app.exists())

    def test_an_app_that_appears_during_the_swap_is_left_and_the_earlier_one_kept(self):
        v2 = self.first_install()
        self.switch("intruder on mv 1")
        done = self.install(v2, left=1)
        self.assertEqual(done.returncode, 1)
        self.assertIn("Something else put a Dragoon.app in", done.stderr)
        [stage] = self.stages()
        kept = self.apps / stage / "previous.app"
        self.assertIn(f"is now at {kept}\n", done.stderr)
        self.installed("v1", at=kept)
        self.assertEqual(tree(self.app), {})
        self.assertEqual(self.calls("open"), [])

    def test_a_held_lock_refuses_the_install_and_stays(self):
        v2 = self.first_install()
        (self.apps / LOCK).mkdir()
        done = self.install(v2, lock=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn(f'Another copy of this installer is running. If none is, run rmdir "{self.apps / LOCK}"'
                      " and then this again.", done.stderr)
        self.assertTrue((self.apps / LOCK).is_dir())
        self.installed("v1")
        self.assertEqual(self.calls("mv"), [])

    def test_a_wrong_hash_exits_1_and_leaves_an_earlier_install_as_it_was(self):
        v1 = self.fixture("v1", V1)
        self.assertEqual(self.install(self.script(v1)).returncode, 0)
        v2 = self.fixture("v2", V2)
        done = self.install(self.script(v1, served=v2))
        self.assertEqual(done.returncode, 1)
        self.assertIn("doesn't match", done.stderr)
        self.assertIn(f"release   {sha256(v1)}", done.stderr)
        self.assertIn(f"download  {sha256(v2)}", done.stderr)
        self.installed("v1")
        self.assertEqual(self.calls("open"), [str(self.app)])

    def test_a_wrong_hash_on_a_first_install_installs_nothing(self):
        done = self.install(self.script(self.fixture("v1", V1), served=self.fixture("v2", V2)))
        self.assertEqual(done.returncode, 1)
        self.assertFalse(self.apps.exists())
        self.assertEqual(self.calls("open"), [])

    def test_a_failed_download_installs_nothing(self):
        zipped = self.fixture("v1", V1)
        done = self.install(self.script(zipped, served=self.dir / "missing.zip"))
        self.assertEqual(done.returncode, 1)
        self.assertIn("The download failed. Nothing was installed.", done.stderr)
        self.assertFalse(self.apps.exists())

    @unittest.skipUnless(subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True,
                                        text=True).stdout.strip() == "1", "needs a Mac with Apple silicon")
    def test_the_real_sysctl_is_found_without_usr_sbin_on_path(self):
        done = self.install(self.script(self.fixture("v1", V1)), real_sysctl=True, path="/usr/bin:/bin")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.installed("v1")

    def test_an_intel_mac_is_refused_before_any_download(self):
        self.switch("intel")
        done = self.install(self.script(self.fixture("v1", V1)))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr, "Dragoon needs a Mac with Apple silicon. This one has an Intel processor.\n")
        self.assertEqual(self.recorded(), CHECKS[:1])
        self.assertFalse(self.apps.exists())

    def test_macos_13_is_refused_before_any_download(self):
        for version in ("13.7.4", "10.15.7"):
            with self.subTest(version=version):
                if self.records.exists():
                    self.records.unlink()
                (self.switches / "macos").write_text(version + "\n")
                done = self.install(self.script(self.fixture(f"v1 {version}", V1)))
                self.assertEqual(done.returncode, 1)
                self.assertIn(f"This Mac has macOS {version}.", done.stderr)
                self.assertEqual(self.recorded(), CHECKS[:2])
                self.assertFalse(self.apps.exists())

    def test_this_users_running_launcher_or_game_is_refused_before_any_download(self):
        v2 = self.first_install()
        for name, what in (("Dragoon", "launcher"), ("dragoon", "game")):
            with self.subTest(name=name):
                self.switch(f"{what} running")
                done = self.install(v2)
                self.assertEqual(done.returncode, 1)
                self.assertIn("Dragoon is open. Quit Dragoon and its game, then run this again.", done.stderr)
                self.assertEqual(self.recorded()[-1], ("pgrep", f"-x -U {UID} {name}"))
                self.assertEqual(self.calls("curl"), [])
                self.installed("v1")
                (self.switches / f"{what} running").unlink()
                self.records.unlink()

    def test_a_home_that_isnt_a_full_path_is_refused_before_any_download(self):
        script = self.script(self.fixture("v1", V1))
        for home in ("", "home with space"):
            with self.subTest(home=home):
                done = self.install(script, home=home)
                self.assertEqual(done.returncode, 1)
                self.assertEqual(done.stderr, f"HOME is '{home}', which isn't a full path. Nothing was installed.\n")
                self.assertEqual(self.calls("curl"), [])
                self.records.unlink()

    def test_the_script_parses_and_never_runs_sudo_xattr_or_the_tools_installer(self):
        script = self.script(self.fixture("v1", V1))
        self.assertEqual(subprocess.run(["/bin/sh", "-n", str(script)], capture_output=True).returncode, 0)
        lines = script.read_text().splitlines()
        self.assertEqual(lines[0], "#!/bin/sh")
        self.assertIn("set -eu", lines)
        code = [line.split("#", 1)[0] for line in lines]
        for word in ("sudo", "xattr", "xcode-select", "softwareupdate", "uname"):
            self.assertFalse([line for line in code if word in line], word)
        self.assertEqual(lines[-1], "install_dragoon")


class MakeInstallScript(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = temp_dir(self) / "a dir"
        self.dir.mkdir()
        self.zip = self.dir / "Dragoon.zip"
        self.zip.write_bytes(b"not really a zip")
        self.out = self.dir / "install.sh"

    def make(self, *args: str) -> tuple[int, str, str]:
        return run_main(make_install_script.main, *args)

    def test_fills_in_the_url_and_the_zips_hash_and_makes_it_executable(self):
        url = "https://github.com/lunchbox-recomp/dragoon/releases/download/v1.2.3/Dragoon.zip"
        code, out, err = self.make("--zip", str(self.zip), "--url", url, "--out", str(self.out))
        self.assertEqual((code, out, err), (0, f"{self.out}\n", ""))
        text = self.out.read_text()
        self.assertIn(f"url='{url}'\n", text)
        self.assertIn(f"sha256='{hashlib.sha256(b'not really a zip').hexdigest()}'\n", text)
        self.assertNotIn("@URL@", text)
        self.assertNotIn("@SHA256@", text)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o755)

    def test_a_missing_zip_exits_2_and_writes_nothing(self):
        code, out, err = self.make("--zip", str(self.dir / "missing.zip"), "--url", "file:///x.zip",
                                   "--out", str(self.out))
        self.assertEqual(code, 2)
        self.assertIn("missing.zip isn't a file", err)
        self.assertFalse(self.out.exists())

    def test_a_url_that_would_break_the_quotes_exits_2_and_writes_nothing(self):
        for url in ("https://x/it's.zip", "https://x/a b.zip", "https://x/a\\b.zip", "http://x/a.zip",
                    "ftp://x/a.zip", "https://x/a\n.zip", ""):
            with self.subTest(url=url):
                code, out, err = self.make("--zip", str(self.zip), "--url", url, "--out", str(self.out))
                self.assertEqual(code, 2)
                self.assertIn("--url", err)
                self.assertFalse(self.out.exists())

    def test_a_missing_argument_exits_2(self):
        self.assertEqual(self.make("--zip", str(self.zip))[0], 2)

    def test_a_template_must_hold_each_placeholder_once(self):
        self.assertEqual(make_install_script.fill("a @URL@ b @SHA256@", "u", "h"), "a u b h")
        for template in ("@URL@", "@URL@ @URL@ @SHA256@", "@SHA256@"):
            with self.subTest(template=template):
                with self.assertRaises(ValueError):
                    make_install_script.fill(template, "u", "h")

    def test_a_url_holding_a_placeholder_keeps_it(self):
        self.assertEqual(make_install_script.fill("@URL@ @SHA256@", "https://x/@SHA256@.zip", "h"),
                         "https://x/@SHA256@.zip h")


if __name__ == "__main__":
    unittest.main()
