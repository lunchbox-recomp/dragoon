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

# The fakes log each call to $FAKE_RECORDS as "NAME ARGS". uname -m says x86_64 when the switch
# "x86_64" is on and arm64 otherwise. sw_vers says what the switch file "macos" holds, or 14.0,
# the oldest macOS the app runs on. pgrep -x NAME finds NAME when "running NAME" is on. open
# only logs. curl logs and then runs the real one, which reads the fixture's file:// URL.
FAKES: dict[str, str] = {}
SCRIPTS = {
    "uname": '#!/bin/sh\necho "uname $*" >> "$FAKE_RECORDS"\n'
             'if [ -e "$FAKE_SWITCHES/x86_64" ]; then echo x86_64; else echo arm64; fi\n',
    "sw_vers": '#!/bin/sh\necho "sw_vers $*" >> "$FAKE_RECORDS"\n'
               'if [ -e "$FAKE_SWITCHES/macos" ]; then cat "$FAKE_SWITCHES/macos"; else echo 14.0; fi\n',
    "pgrep": '#!/bin/sh\necho "pgrep $*" >> "$FAKE_RECORDS"\n[ -e "$FAKE_SWITCHES/running $2" ]\n',
    "open": '#!/bin/sh\necho "open $*" >> "$FAKE_RECORDS"\n',
    "curl": '#!/bin/sh\necho "curl $*" >> "$FAKE_RECORDS"\nexec /usr/bin/curl "$@"\n',
}
CHECKS = [("uname", "-m"), ("sw_vers", "-productVersion"), ("pgrep", "-x Dragoon"), ("pgrep", "-x dragoon")]
V1 = {"Contents/Info.plist": "<plist>1</plist>\n", "Contents/MacOS/Dragoon": "the launcher\n",
      "Contents/Resources/kit/kit.mk": "KIT = 1\n", "Contents/Resources/source/a file.txt": "one\n",
      "Contents/Resources/gone.txt": "only in the first\n"}
V2 = {"Contents/Info.plist": "<plist>2</plist>\n", "Contents/MacOS/Dragoon": "the next launcher\n",
      "Contents/Resources/kit/kit.mk": "KIT = 2\n", "Contents/Resources/source/a file.txt": "two\n",
      "Contents/Resources/new.txt": "only in the second\n"}


def setUpModule() -> None:
    FAKES.update(fake_tools.write(SCRIPTS))


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

    def install(self, script: Path, piped: bool = False) -> subprocess.CompletedProcess:
        """Run SCRIPT under /bin/sh as `sh FILE`, or fed on stdin as `curl ... | sh` does, and check
        it left no temporary directory, either the download's or the one beside the app."""
        env = {"HOME": str(self.home), "TMPDIR": str(self.tmp),
               "PATH": f"{Path(FAKES['open']).parent}:/usr/bin:/bin:/usr/sbin:/sbin",
               "FAKE_RECORDS": str(self.records), "FAKE_SWITCHES": str(self.switches)}
        if piped:
            with script.open("rb") as f:
                done = subprocess.run(["/bin/sh"], stdin=f, env=env, capture_output=True, text=True)
        else:
            done = subprocess.run(["/bin/sh", str(script)], env=env, capture_output=True, text=True)
        self.assertEqual(os.listdir(self.tmp), [], done.stderr)
        if self.apps.exists():
            self.assertLessEqual(set(os.listdir(self.apps)), {"Dragoon.app"}, done.stderr)
        return done

    def installed(self, name: str) -> None:
        """The installed app is NAME's fixture app file for file, and the saves are untouched."""
        self.assertEqual(tree(self.app), tree(self.dir / name / "Dragoon.app"))
        self.assertTrue(os.access(self.app / "Contents/MacOS/Dragoon", os.X_OK))
        self.assertEqual(tree(self.saves), {"memcard.txt": b"a save\n"})

    def calls(self, tool: str) -> list[str]:
        return [args for name, args in self.recorded() if name == tool]

    def test_a_good_zip_installs_the_app_file_for_file_and_opens_it_once(self):
        zipped = self.fixture("v1", V1)
        done = self.install(self.script(zipped), piped=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.installed("v1")
        self.assertEqual(os.listdir(self.apps), ["Dragoon.app"])
        self.assertEqual(self.recorded()[:4], CHECKS)
        [curl] = self.calls("curl")
        self.assertTrue(curl.startswith(f"-fsSL -o {self.tmp}/"), curl)
        self.assertTrue(curl.endswith(f"/Dragoon.zip {zipped.as_uri()}"), curl)
        self.assertEqual(self.calls("open"), [str(self.app)])
        self.assertIn(f"Dragoon is in {self.apps}", done.stdout)

    def test_a_newer_macos_installs_too(self):
        (self.switches / "macos").write_text("26.1\n")
        self.assertEqual(self.install(self.script(self.fixture("v1", V1))).returncode, 0)
        self.installed("v1")

    def test_a_second_run_replaces_the_app_and_leaves_no_stray_copy(self):
        self.assertEqual(self.install(self.script(self.fixture("v1", V1))).returncode, 0)
        done = self.install(self.script(self.fixture("v2", V2)))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.installed("v2")
        self.assertEqual(os.listdir(self.apps), ["Dragoon.app"])
        self.assertEqual(self.calls("open"), [str(self.app)] * 2)

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

    def test_an_intel_mac_is_refused_before_any_download(self):
        self.switch("x86_64")
        done = self.install(self.script(self.fixture("v1", V1)))
        self.assertEqual(done.returncode, 1)
        self.assertIn("This one reports x86_64.", done.stderr)
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

    def test_a_running_launcher_or_game_is_refused_before_any_download(self):
        self.assertEqual(self.install(self.script(self.fixture("v1", V1))).returncode, 0)
        v2 = self.script(self.fixture("v2", V2))
        for name in ("Dragoon", "dragoon"):
            with self.subTest(name=name):
                self.switch(f"running {name}")
                self.records.unlink()
                done = self.install(v2)
                self.assertEqual(done.returncode, 1)
                self.assertIn("Dragoon is open. Quit Dragoon and its game, then run this again.", done.stderr)
                self.assertEqual(self.calls("curl"), [])
                self.installed("v1")
                (self.switches / f"running {name}").unlink()

    def test_the_script_parses_and_never_runs_sudo_xattr_or_the_tools_installer(self):
        script = self.script(self.fixture("v1", V1))
        self.assertEqual(subprocess.run(["/bin/sh", "-n", str(script)], capture_output=True).returncode, 0)
        lines = script.read_text().splitlines()
        self.assertEqual(lines[0], "#!/bin/sh")
        self.assertIn("set -eu", lines)
        code = [line.split("#", 1)[0] for line in lines]
        for word in ("sudo", "xattr", "xcode-select", "softwareupdate"):
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


if __name__ == "__main__":
    unittest.main()
