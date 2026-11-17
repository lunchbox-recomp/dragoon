from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import settings_fixtures
from testutil import run_main, temp_dir

CHECKED_OUT = (settings_fixtures.RUNTIME / "settings.cpp").is_file()


@unittest.skipUnless(CHECKED_OUT, "gcn-recomp isn't checked out: git submodule update --init gcn-recomp")
class HarnessTest(unittest.TestCase):
    """The harness built against the submodule's engine, once for the class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="settings fixtures test ")
        cls.work = Path(cls.tmp.name)
        cls.exe = settings_fixtures.build(cls.work, "c++")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def made(self) -> Path:
        work = temp_dir(self, prefix="settings fixtures run ")
        settings_fixtures.write(work / "made", self.exe, work)
        return work / "made"

    def test_it_writes_the_committed_fixtures_and_tables_byte_for_byte(self) -> None:
        made = self.made()
        self.assertEqual(settings_fixtures.differences(made, settings_fixtures.FIXTURES), [])
        names = {p.name for p in made.iterdir()}
        self.assertEqual(len([n for n in names if n.endswith(".out")]), len(settings_fixtures.CASES))
        self.assertLessEqual({"cases.txt", "window-sizes.txt", "fits.txt", "scales.txt"}, names)
        self.assertNotIn("missing.in", names)

    def test_a_changed_missing_or_extra_file_is_named(self) -> None:
        made = self.made()
        committed = temp_dir(self) / "committed"
        shutil.copytree(made, committed)
        (committed / "fits.txt").write_bytes((committed / "fits.txt").read_bytes() + b"x")
        (committed / "empty.out").unlink()
        (committed / "stray.txt").write_bytes(b"")
        self.assertEqual(settings_fixtures.differences(made, committed),
                         ["empty.out: missing", "fits.txt: differs", "stray.txt: not one the harness writes"])

    def test_the_saved_bytes_are_the_engines_not_the_inputs(self) -> None:
        made = self.made()
        self.assertEqual((made / "plain-lf.out").read_bytes(),
                         b"aspect 21:9\nfullscreen 1\nscale 4\ndisc fast\nmenu_sounds off\n")
        self.assertEqual((made / "missing.out").read_bytes(),
                         b"aspect 16:9\nfullscreen 1\nscale 3\ndisc fast\nmenu_sounds off\n")
        self.assertEqual((made / "menu-sounds-on.out").read_bytes(),
                         b"menu_sounds on\naspect 16:9\nfullscreen 0\nscale 2\ndisc fast\n")
        self.assertEqual((made / "menu-sounds-on-then-off.out").read_bytes(),
                         b"menu_sounds off\nmenu_sounds off\naspect 16:9\nfullscreen 0\nscale 2\ndisc fast\n")
        self.assertEqual((made / "scales.txt").read_text().splitlines()[-1], "10 5120 3840")


@unittest.skipUnless(CHECKED_OUT, "gcn-recomp isn't checked out: git submodule update --init gcn-recomp")
class CommandLineTest(unittest.TestCase):
    def test_check_passes_on_the_committed_folder(self) -> None:
        self.assertEqual(run_main(settings_fixtures.main, "--check"), (0, "", ""))

    def test_check_prints_each_difference_and_exits_1(self) -> None:
        committed = temp_dir(self, prefix="committed ") / "fixtures"
        shutil.copytree(settings_fixtures.FIXTURES, committed)
        (committed / "scales.txt").write_text("1 640 480\n")
        self.assertEqual(run_main(settings_fixtures.main, "--check", "--out", str(committed)),
                         (1, "scales.txt: differs\n", ""))

    def test_it_writes_a_folder_that_check_then_passes(self) -> None:
        out = temp_dir(self, prefix="out ") / "fixtures"
        self.assertEqual(run_main(settings_fixtures.main, "--out", str(out)), (0, "", ""))
        self.assertEqual(run_main(settings_fixtures.main, "--check", "--out", str(out)), (0, "", ""))

    def test_a_case_whose_menu_sounds_isnt_the_engines_exits_2(self) -> None:
        wrong = settings_fixtures.Case("on-then-off", b"menu_sounds on\nmenu_sounds off\n", "4:3", 0, 2, "fast", "on")
        with mock.patch.object(settings_fixtures, "CASES", [wrong]):
            self.assertEqual(run_main(settings_fixtures.main, "--check"),
                             (2, "", "on-then-off: the engine loads menu_sounds off, not the case's on\n"))

    def test_a_compiler_that_fails_exits_2(self) -> None:
        code, out, err = run_main(settings_fixtures.main, "--check", "--cxx", "/usr/bin/false")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("settings_fixtures.cpp: doesn't compile", err)


@unittest.skipUnless(CHECKED_OUT, "gcn-recomp isn't checked out: git submodule update --init gcn-recomp")
class CopiedLinesTest(unittest.TestCase):
    """main.cpp's window choices and the renderer's 640, which the harness copies by hand."""

    def check_with(self, name: str, old: str, new: str) -> tuple[int, str, str]:
        """--check against a copy of the engine's files the harness reads, with OLD in NAME made NEW."""
        root = temp_dir(self, prefix="engine copy ")
        runtime = root / "gcn-recomp" / "runtime"
        for each in {"settings.cpp", "platform.cpp", "gx/aspect.h", *(n for n, _ in settings_fixtures.COPIED)}:
            (runtime / each).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(settings_fixtures.RUNTIME / each, runtime / each)
        text = (runtime / name).read_text(encoding="utf-8")
        self.assertIn(old, text)
        (runtime / name).write_text(text.replace(old, new), encoding="utf-8")
        with mock.patch.object(settings_fixtures, "ROOT", root), \
                mock.patch.object(settings_fixtures, "RUNTIME", runtime):
            return run_main(settings_fixtures.main, "--check")

    def test_the_engine_holds_every_copied_line(self) -> None:
        settings_fixtures.check_copied()

    def test_a_title_bar_of_28_in_main_cpp_is_named_and_exits_2(self) -> None:
        self.assertEqual(self.check_with("main.cpp", "kTitleBar = 40;", "kTitleBar = 28;"),
                         (2, "", "gcn-recomp/runtime/main.cpp: no line \"constexpr int kTitleBar = 40;\", "
                                 "which settings_fixtures.cpp copies\n"))

    def test_each_copied_line_commented_out_is_named(self) -> None:
        for name, line in settings_fixtures.COPIED:
            with self.subTest(line=line):
                self.assertEqual(self.check_with(name, line, "// " + line),
                                 (2, "", f"gcn-recomp/runtime/{name}: no line \"{line}\", "
                                         "which settings_fixtures.cpp copies\n"))

    # The frame's fit in render_gl_present.cpp and the held frame's in render_gl_blur.cpp are the
    # same line.
    FIT = "const OutputRect fit = fit_aspect(w, h, output_aspect());"

    def test_the_held_frames_fit_at_4_3_exits_2(self) -> None:
        changed = "const OutputRect fit = fit_aspect(w, h, 4.0f / 3.0f);"
        self.assertEqual(self.check_with("gx/render_gl_blur.cpp", self.FIT, changed),
                         (2, "", f"gcn-recomp/runtime/gx/render_gl_blur.cpp: no line \"{self.FIT}\", "
                                 "which settings_fixtures.cpp copies\n"))


class NoEngineTest(unittest.TestCase):
    def test_without_the_submodule_it_says_how_to_check_it_out_and_exits_2(self) -> None:
        empty = temp_dir(self)
        with mock.patch.object(settings_fixtures, "ROOT", empty), \
                mock.patch.object(settings_fixtures, "RUNTIME", empty / "gcn-recomp" / "runtime"):
            code, out, err = run_main(settings_fixtures.main, "--check")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "gcn-recomp/runtime/settings.cpp: not there, so check gcn-recomp out: "
                              "git submodule update --init gcn-recomp\n")

    @unittest.skipUnless(CHECKED_OUT, "gcn-recomp isn't checked out: git submodule update --init gcn-recomp")
    def test_a_compiler_that_isnt_there_exits_2(self) -> None:
        gone = str(temp_dir(self) / "c++")
        self.assertEqual(run_main(settings_fixtures.main, "--check", "--cxx", gone),
                         (2, "", f"{gone}: No such file or directory\n"))


if __name__ == "__main__":
    unittest.main()
