from __future__ import annotations

import contextlib
import io
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import swift_test

FRAMEWORKS = "Library/Developer/Frameworks"
TESTING = f"{FRAMEWORKS}/Testing.framework"
LIBS = "Library/Developer/usr/lib"

# The fakes are two shell scripts that all the tests share. macOS scans a new executable the
# first time it runs, which costs more than a script does, so each test gets its own records
# file and switches through the environment. The fake xcode-select records "select" and its
# arguments to $FAKE_RECORDS and prints $FAKE_DEVELOPER_DIR, or fails with nothing on stdout
# when that isn't set. $FAKE_SELECT_STATUS makes it exit with that status after printing. The
# fake swift records "call" and one "arg X" per argument, ends itself with SIGTERM when
# $FAKE_SWIFT_KILL is set and otherwise exits with $FAKE_SWIFT_STATUS (0 if unset).
FAKE_SELECT = r"""#!/bin/sh
printf 'select %s\n' "$*" >> "$FAKE_RECORDS"
if [ -z "${FAKE_DEVELOPER_DIR+x}" ]; then
  echo "xcode-select: error: unable to get active developer directory" >&2
  exit 1
fi
echo "$FAKE_DEVELOPER_DIR"
exit "${FAKE_SELECT_STATUS:-0}"
"""
FAKE_SWIFT = r"""#!/bin/sh
{
  echo call
  for arg in "$@"; do
    printf 'arg %s\n' "$arg"
  done
} >> "$FAKE_RECORDS"
if [ -n "$FAKE_SWIFT_KILL" ]; then
  kill -TERM $$
fi
exit "${FAKE_SWIFT_STATUS:-0}"
"""
FAKES: dict[str, str] = {}


def setUpModule() -> None:
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    directory = Path(tmp.name) / "fake tools"
    directory.mkdir()
    for name, text in (("xcode-select", FAKE_SELECT), ("swift", FAKE_SWIFT)):
        path = directory / name
        path.write_text(text)
        path.chmod(0o755)
        FAKES[name] = str(path)


def make_tools(path: Path, testing: bool = True) -> Path:
    """A Command Line Tools directory at PATH, as a Mac with no Xcode has one. Testing.framework
    is there unless TESTING is false, and its sibling frameworks and the interop library are
    there either way."""
    (path / FRAMEWORKS / "_Testing_Foundation.framework").mkdir(parents=True)
    if testing:
        (path / TESTING).mkdir()
    (path / LIBS).mkdir(parents=True)
    (path / LIBS / "lib_TestingInterop.dylib").write_bytes(b"\xcf\xfa\xed\xfe")
    return path


def make_xcode(path: Path) -> Path:
    """An Xcode developer directory at PATH, where Testing.framework is in the platform."""
    (path / "Platforms/MacOSX.platform/Developer/Library/Frameworks/Testing.framework").mkdir(parents=True)
    (path / "usr/bin").mkdir(parents=True)
    return path


def testing_flags(developer: Path) -> list[str]:
    """What swift should get for the Command Line Tools at DEVELOPER."""
    frameworks = f"{developer}/{FRAMEWORKS}"
    return ["-Xswiftc", "-F", "-Xswiftc", frameworks,
            "-Xlinker", "-rpath", "-Xlinker", frameworks,
            "-Xlinker", "-rpath", "-Xlinker", f"{developer}/{LIBS}"]


class SwiftTestCase(unittest.TestCase):
    """The fake tools, a records file of this test's own and a place for developer directories,
    at paths with spaces."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.records = self.dir / "records.txt"
        env = mock.patch.dict(os.environ, {"FAKE_RECORDS": str(self.records)})
        env.start()
        self.addCleanup(env.stop)
        for name in ("FAKE_DEVELOPER_DIR", "FAKE_SELECT_STATUS", "FAKE_SWIFT_KILL", "FAKE_SWIFT_STATUS"):
            os.environ.pop(name, None)
        for name, constant in (("swift", "SWIFT"), ("xcode-select", "XCODE_SELECT")):
            patch = mock.patch.object(swift_test, constant, FAKES[name])
            patch.start()
            self.addCleanup(patch.stop)
        self.tools = make_tools(self.dir / "a dir" / "CommandLineTools")
        self.xcode = make_xcode(self.dir / "Applications" / "Xcode 26.app" / "Contents" / "Developer")

    def select(self, developer: Path | str) -> None:
        """Make the fake xcode-select print DEVELOPER."""
        os.environ["FAKE_DEVELOPER_DIR"] = str(developer)

    def run_tool(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = swift_test.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def records_of(self, key: str) -> list[str]:
        """The values the fakes recorded under KEY, in order."""
        if not self.records.exists():
            return []
        found = []
        for line in self.records.read_text().splitlines():
            name, _, value = line.partition(" ")
            if name == key:
                found.append(value)
        return found

    def swift_args(self) -> list[str]:
        """What the one call to swift was given."""
        self.assertEqual(self.records_of("call"), [""], "swift should have run once")
        return self.records_of("arg")


class FlagsTest(SwiftTestCase):
    def test_the_command_line_tools_with_testing_get_the_framework_and_both_rpaths(self):
        self.select(self.tools)
        code, _, _ = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(self.swift_args(),
                         ["test", "--package-path", str(swift_test.LAUNCHER)] + testing_flags(self.tools))

    def test_the_flags_are_for_the_selected_directory_wherever_it_is(self):
        other = make_tools(self.dir / "elsewhere" / "CommandLineTools")
        self.select(other)
        self.run_tool()
        self.assertEqual(self.swift_args()[3:], testing_flags(other))

    def test_xcode_gets_no_flags(self):
        self.select(self.xcode)
        self.run_tool()
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])

    def test_a_tools_copy_under_another_name_gets_the_flags(self):
        copy = make_tools(self.dir / "a copy" / "clt 26.5")
        self.select(copy)
        self.run_tool()
        self.assertEqual(self.swift_args(),
                         ["test", "--package-path", str(swift_test.LAUNCHER)] + testing_flags(copy))

    def test_an_xcode_shaped_directory_gets_none_even_with_the_framework(self):
        make_tools(self.xcode)
        self.assertTrue((self.xcode / TESTING).is_dir())
        self.select(self.xcode)
        self.run_tool()
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])

    def test_a_platforms_file_does_not_make_it_xcode(self):
        tools = make_tools(self.dir / "odd platforms" / "CommandLineTools")
        (tools / "Platforms").write_text("")
        self.select(tools)
        self.run_tool()
        self.assertEqual(self.swift_args(),
                         ["test", "--package-path", str(swift_test.LAUNCHER)] + testing_flags(tools))

    def test_the_tools_without_testing_framework_get_none(self):
        bare = make_tools(self.dir / "bare" / "CommandLineTools", testing=False)
        self.select(bare)
        self.run_tool()
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])

    def test_a_testing_framework_that_is_a_file_gets_none(self):
        tools = make_tools(self.dir / "odd" / "CommandLineTools", testing=False)
        (tools / TESTING).write_text("")
        self.select(tools)
        self.run_tool()
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])

    def test_extra_arguments_follow_the_flags_whole(self):
        self.select(self.tools)
        self.run_tool("--filter", "a test with spaces", "--parallel")
        self.assertEqual(self.swift_args(),
                         ["test", "--package-path", str(swift_test.LAUNCHER)] + testing_flags(self.tools)
                         + ["--filter", "a test with spaces", "--parallel"])

    def test_extra_arguments_reach_swift_under_xcode_too(self):
        self.select(self.xcode)
        self.run_tool("--filter", "x")
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER), "--filter", "x"])


class SelectionTest(SwiftTestCase):
    def test_it_asks_xcode_select_for_the_path_once(self):
        self.select(self.tools)
        self.run_tool()
        self.assertEqual(self.records_of("select"), ["-p"])

    def test_a_failing_xcode_select_adds_nothing_and_swift_still_runs(self):
        code, _, _ = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(self.records_of("select"), ["-p"])
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])

    def test_xcode_select_failing_after_it_printed_a_directory_adds_nothing(self):
        self.select(self.tools)
        os.environ["FAKE_SELECT_STATUS"] = "1"
        self.run_tool()
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])

    def test_an_xcode_select_that_prints_nothing_adds_nothing(self):
        self.select("")
        self.run_tool()
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])

    def test_the_answer_is_the_directory_without_its_newline(self):
        self.select(self.tools)
        self.assertEqual(swift_test.selected_developer_dir(), self.tools)

    def test_a_failure_an_empty_answer_and_a_missing_tool_are_no_directory(self):
        self.assertIsNone(swift_test.selected_developer_dir())
        self.select("")
        self.assertIsNone(swift_test.selected_developer_dir())
        self.select(self.tools)
        os.environ["FAKE_SELECT_STATUS"] = "1"
        self.assertIsNone(swift_test.selected_developer_dir())
        with mock.patch.object(swift_test, "XCODE_SELECT", str(self.dir / "no xcode-select")):
            self.assertIsNone(swift_test.selected_developer_dir())

    def test_a_missing_xcode_select_adds_nothing_and_swift_still_runs(self):
        with mock.patch.object(swift_test, "XCODE_SELECT", str(self.dir / "no xcode-select")):
            code, _, _ = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(self.swift_args(), ["test", "--package-path", str(swift_test.LAUNCHER)])


@unittest.skipUnless(os.path.exists("/usr/bin/xcode-select"), "needs xcode-select")
class RealXcodeSelectTest(unittest.TestCase):
    """The real xcode-select reports DEVELOPER_DIR, so a directory can stand in for the tools."""

    def test_it_reads_the_directory_xcode_select_prints(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = make_tools(Path(tmp) / "a dir" / "CommandLineTools")
            with mock.patch.dict(os.environ, {"DEVELOPER_DIR": str(tools)}):
                found = swift_test.selected_developer_dir()
                self.assertEqual(found, tools)
                self.assertEqual(swift_test.command(["--filter", "x"], found),
                                 [swift_test.SWIFT, "test", "--package-path", str(swift_test.LAUNCHER)]
                                 + testing_flags(tools) + ["--filter", "x"])

    def test_xcode_select_is_run_by_full_path_and_swift_by_name(self):
        self.assertEqual(swift_test.XCODE_SELECT, "/usr/bin/xcode-select")
        self.assertEqual(swift_test.SWIFT, "swift")


class RunTest(SwiftTestCase):
    def test_the_package_is_the_launcher_beside_tools(self):
        self.assertEqual(Path(swift_test.__file__).resolve().parent, swift_test.LAUNCHER / "tools")
        self.assertTrue((swift_test.LAUNCHER / "Package.swift").is_file())

    def test_swifts_status_is_the_exit_status(self):
        for status in (0, 1, 3):
            with self.subTest(status):
                os.environ["FAKE_SWIFT_STATUS"] = str(status)
                code, _, _ = self.run_tool()
                self.assertEqual(code, status)

    def test_a_signal_that_ends_swift_is_128_plus_its_number(self):
        os.environ["FAKE_SWIFT_KILL"] = "1"
        code, _, _ = self.run_tool()
        self.assertEqual(code, 143)

    def test_a_missing_swift_exits_2_with_one_line_on_stderr(self):
        with mock.patch.object(swift_test, "SWIFT", str(self.dir / "no swift")):
            code, out, err = self.run_tool()
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(len(err.splitlines()), 2, err)  # the command, then why it failed
        self.assertIn("swift_test.py: can't run ", err.splitlines()[1])

    def test_the_command_prints_on_stderr_with_a_plus(self):
        self.select(self.tools)
        code, out, err = self.run_tool("--filter", "a b")
        self.assertEqual((code, out), (0, ""))
        want = [FAKES["swift"], "test", "--package-path", str(swift_test.LAUNCHER)]
        want += testing_flags(self.tools) + ["--filter", "a b"]
        self.assertEqual(err.splitlines(), ["+ " + shlex.join(want)])

    def test_help_prints_the_usage_and_runs_nothing(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag):
                code, out, err = self.run_tool(flag, "--filter", "x")
                self.assertEqual((code, err), (0, ""))
                self.assertIn("Usage: swift_test.py", out)
                self.assertEqual(self.records_of("call"), [])
                self.assertEqual(self.records_of("select"), [])

    def test_help_later_in_the_arguments_goes_to_swift(self):
        self.run_tool("--filter", "--help")
        self.assertEqual(self.swift_args()[-2:], ["--filter", "--help"])


if __name__ == "__main__":
    unittest.main()
