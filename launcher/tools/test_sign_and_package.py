from __future__ import annotations

import contextlib
import io
import os
import plistlib
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sign_and_package
import sign_plan

IDENTITY = "Fake Identity (NOT REAL)"
BUNDLE_ID = "io.example.dragoon.test"
KEY_ID, ISSUER = "KEY1234567", "11111111-2222-3333-4444-555555555555"
SECRET = "-----BEGIN PRIVATE KEY----- not a real key"
APP = "Dragoon.app"

# The fakes are shell scripts that all the tests share. macOS scans a new executable the first
# time it runs, which costs more than a script does, so each test gets its own records file
# and switches through the environment instead of writing new fakes. A fake appends a record
# of its call to $FAKE_RECORDS as lines: "tool NAME", one "arg X" per argument, "exists" if its
# last argument was there as it ran, what a -srcfolder held as "listing X" lines and its
# Applications link as "applications X", and "end". A file named after a failure in
# $FAKE_SWITCHES turns that failure on.
HEAD = r"""#!/bin/sh
marker() { [ -e "$FAKE_SWITCHES/$1" ]; }
{
  printf 'tool %s\n' "@TOOL@"
  prev=
  last=
  for arg in "$@"; do
    printf 'arg %s\n' "$arg"
    if [ "$prev" = "-srcfolder" ]; then
      for entry in "$arg"/* "$arg"/.[!.]*; do
        if [ -e "$entry" ] || [ -L "$entry" ]; then printf 'listing %s\n' "${entry##*/}"; fi
      done
      printf 'applications %s\n' "$(readlink "$arg/Applications")"
    fi
    prev=$arg
    last=$arg
  done
  if [ -e "$last" ] || [ -L "$last" ]; then echo exists; fi
  echo end
} >> "$FAKE_RECORDS"
"""
BODIES = {
    "codesign": """
if marker "fail codesign"; then exit 1; fi
if [ "$1" = "--verify" ] && marker "fail verify"; then exit 1; fi
""",
    "ditto": """
cp -R "$1" "$2"
""",
    "hdiutil": """
if marker "fail hdiutil"; then exit 1; fi
if marker "hdiutil flakes"; then
  tries=$(grep -c '^tool hdiutil' "$FAKE_RECORDS")
  if [ "$tries" -le 2 ]; then echo "hdiutil: create failed - Resource busy" >&2; exit 1; fi
fi
printf 'a fake dmg' > "$last"
""",
    "xcrun": """
if [ "$1 $2" = "notarytool submit" ]; then
  if marker "notarytool hangs"; then exec sleep 30; fi
  if marker "no json"; then echo "notarytool broke"; exit 1; fi
  status=Accepted
  if marker "invalid"; then status=Invalid; fi
  printf '{"id": "SUB-123", "status": "%s", "message": "Processing complete"}\\n' "$status"
  if marker "notarytool exits 1"; then exit 1; fi
  exit 0
fi
if [ "$1 $2" = "stapler staple" ] && marker "fail stapler"; then exit 65; fi
""",
    "spctl": """
if marker "fail spctl"; then exit 3; fi
""",
}


def make_app(path: Path, sparkle: bool = True, xpc: bool = False) -> Path:
    """A stand-in app with the engine kit in its Resources, which nothing signs, and Sparkle
    2.9.1's layout. make_app.py removes the XPC services, so they are there only when XPC is
    true."""
    files = {"Contents/MacOS/Dragoon": "launcher",
             "Contents/Resources/kit/engine.o": "the engine", "Contents/Resources/kit/libSDL3.a": "SDL"}
    if sparkle:
        version = "Contents/Frameworks/Sparkle.framework/Versions/B"
        files.update({f"{version}/Sparkle": "s", f"{version}/Autoupdate": "a",
                      f"{version}/Updater.app/Contents/MacOS/Updater": "u"})
        if xpc:
            files.update({f"{version}/XPCServices/Installer.xpc/Contents/MacOS/Installer": "i",
                          f"{version}/XPCServices/Downloader.xpc/Contents/MacOS/Downloader": "d"})
    for name, data in files.items():
        file = path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(data)
    with (path / "Contents" / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleIdentifier": BUNDLE_ID, "CFBundleExecutable": "Dragoon"}, f)
    if sparkle:
        framework = path / "Contents/Frameworks/Sparkle.framework"
        os.symlink("B", framework / "Versions" / "Current")
        for name in ("Sparkle", "Autoupdate", "Updater.app") + (("XPCServices",) if xpc else ()):
            os.symlink(f"Versions/Current/{name}", framework / name)
    return path


FAKES: dict[str, str] = {}


def setUpModule() -> None:
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    directory = Path(tmp.name) / "fake tools"
    directory.mkdir()
    for tool, body in BODIES.items():
        path = directory / tool
        path.write_text(HEAD.replace("@TOOL@", tool) + body)
        path.chmod(0o755)
        FAKES[tool] = str(path)


class SignTestCase(unittest.TestCase):
    """The shared fake codesign, ditto, hdiutil, xcrun and spctl, a records file and a switches
    directory of this test's own, and an app, all at paths with spaces."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.records = self.dir / "records.txt"
        self.switches = self.dir / "fake switches"
        self.switches.mkdir()
        env = mock.patch.dict(os.environ, {"FAKE_RECORDS": str(self.records),
                                           "FAKE_SWITCHES": str(self.switches)})
        env.start()
        self.addCleanup(env.stop)
        self.fakes = FAKES
        for tool, path in FAKES.items():
            patch = mock.patch.object(sign_plan, tool.upper(), path)
            patch.start()
            self.addCleanup(patch.stop)
        pause = mock.patch.object(sign_and_package, "RETRY_PAUSE_SECONDS", 0)
        pause.start()
        self.addCleanup(pause.stop)
        self.app = make_app(self.dir / "dist dir" / "Dragoon Dev.app")
        self.out = self.dir / "release out"
        self.key = self.dir / "AuthKey.p8"
        self.key.write_text(SECRET)

    def switch(self, *names: str) -> None:
        """Turn on the failures NAMES."""
        for name in names:
            (self.switches / name).write_text("")

    def run_tool(self, *extra: str, notary: bool = True, identity: str = IDENTITY
                 ) -> tuple[int, str, str]:
        argv = ["--app", str(self.app), "--identity", identity, "--out", str(self.out)]
        if notary:
            argv += ["--notary-key", str(self.key), "--notary-key-id", KEY_ID,
                     "--notary-issuer", ISSUER]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = sign_and_package.main(argv + list(extra))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def calls(self) -> list[dict]:
        """What the fakes recorded: tool, argv, exists and for hdiutil listing and applications."""
        calls, call = [], {}
        if not self.records.exists():
            return calls
        for line in self.records.read_text().splitlines():
            key, _, value = line.partition(" ")
            if key == "tool":
                call = {"tool": value, "argv": [], "exists": False}
            elif key == "arg":
                call["argv"].append(value)
            elif key == "exists":
                call["exists"] = True
            elif key == "listing":
                call["listing"] = sorted(call.get("listing", []) + [value])
            elif key == "applications":
                call["applications"] = value
            elif key == "end":
                calls.append(call)
        return calls

    def argvs(self) -> list[list[str]]:
        return [[self.fakes[c["tool"]], *c["argv"]] for c in self.calls()]

    def sign(self, path: Path, identity: str = IDENTITY) -> list[str]:
        """The command for an item. A Developer ID signature has the hardened runtime and a
        secure timestamp. An ad hoc one (identity -) has neither."""
        cmd = [self.fakes["codesign"], "-f", "-s", identity]
        cmd += ["--timestamp=none"] if identity == "-" else ["-o", "runtime", "--timestamp"]
        return cmd + [str(path)]

    def expected(self, notarize: bool = True, sparkle: bool = True,
                 identity: str = IDENTITY) -> list[list[str]]:
        """Every command in the plan's order. The first two aren't fakes."""
        staged = self.out / "dmg-root"
        app, dmg = staged / APP, self.out / "Dragoon.dmg"
        framework = app / "Contents/Frameworks/Sparkle.framework"
        commands = [
            [self.fakes["ditto"], str(self.app), str(app)],
            ["/bin/ln", "-s", "/Applications", str(staged / "Applications")],
        ]
        if sparkle:
            commands += [self.sign(framework / "Versions/B/Autoupdate", identity=identity),
                         self.sign(framework / "Versions/B/Updater.app", identity=identity),
                         self.sign(framework, identity=identity)]
        commands += [
            self.sign(app, identity=identity),
            [self.fakes["codesign"], "--verify", "--strict", "--deep", str(app)],
            [self.fakes["hdiutil"], "create", "-format", "UDZO", "-volname", "Dragoon", "-ov",
             "-srcfolder", str(staged), str(dmg)],
            [self.fakes["codesign"], "-s", identity,
             "--timestamp=none" if identity == "-" else "--timestamp", "-i", BUNDLE_ID + ".dmg",
             str(dmg)],
        ]
        key = ["--key", str(self.key), "--key-id", KEY_ID, "--issuer", ISSUER]
        if notarize:
            commands += [[self.fakes["xcrun"], "notarytool", "submit", str(dmg), *key, "--wait",
                          "--output-format", "json"],
                         [self.fakes["xcrun"], "stapler", "staple", str(dmg)]]
        if notarize:
            commands += [
                [self.fakes["xcrun"], "stapler", "validate", str(dmg)],
                [self.fakes["spctl"], "--assess", "--type", "execute", "-vv", str(app)],
                [self.fakes["spctl"], "--assess", "--type", "open", "--context",
                 "context:primary-signature", "-vv", str(dmg)]]
        return commands

    def printed(self, stdout: str) -> list[list[str]]:
        return [shlex.split(line[2:]) for line in stdout.splitlines() if line.startswith("+ ")]


class OrderTest(SignTestCase):
    def test_a_full_run_signs_inside_out_then_packages_notarizes_staples_and_verifies(self):
        code, out, err = self.run_tool()
        self.assertEqual((code, err), (0, ""))
        want = self.expected()
        self.assertEqual(self.argvs(), [c for c in want if c[0] != "/bin/ln"])
        self.assertEqual(self.printed(out), want)
        self.assertEqual(out.splitlines()[-1], str(self.out / "Dragoon.dmg"))

    def test_without_sparkle_it_signs_the_tools_then_the_app(self):
        self.app = make_app(self.dir / "plain" / "Dragoon.app", sparkle=False)
        code, _, _ = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual(self.argvs(), [c for c in self.expected(sparkle=False) if c[0] != "/bin/ln"])

    def test_the_dmg_is_signed_after_it_is_made_and_notarized_before_it_is_stapled(self):
        self.run_tool()
        calls = self.calls()

        def first(tool: str, *start: str, dmg: bool = False) -> int:
            return next(i for i, c in enumerate(calls) if c["tool"] == tool
                        and c["argv"][:len(start)] == list(start)
                        and (not dmg or c["argv"][-1].endswith(".dmg")))

        made = first("hdiutil", "create")
        signed = first("codesign", "-s", dmg=True)
        notarized = first("xcrun", "notarytool", "submit")
        stapled = first("xcrun", "stapler", "staple")
        self.assertLess(made, signed)
        self.assertLess(signed, notarized)
        self.assertLess(notarized, stapled)
        self.assertTrue(calls[signed]["exists"], "the DMG wasn't there to sign")
        self.assertTrue(calls[stapled]["exists"], "the DMG wasn't there to staple")

    def test_the_input_app_is_never_signed(self):
        self.run_tool()
        for argv in self.argvs():
            self.assertFalse(any(word.startswith(str(self.app)) for word in argv[1:]
                                 if argv[0] != self.fakes["ditto"]), argv)


class FlagTest(SignTestCase):
    def signing(self) -> list[list[str]]:
        return [a for a in self.argvs() if a[0] == self.fakes["codesign"] and "-s" in a]

    def test_every_signature_is_timestamped_and_none_is_deep(self):
        self.run_tool()
        calls = self.signing()
        self.assertEqual(len(calls), 5)  # Sparkle's three, the app and the DMG
        for argv in calls:
            with self.subTest(argv[-1]):
                self.assertIn("--timestamp", argv)
                self.assertNotIn("--deep", argv)

    def test_every_signature_but_the_dmgs_has_the_hardened_runtime(self):
        self.run_tool()
        for argv in self.signing():
            with self.subTest(argv[-1]):
                has = argv[argv.index("-o") + 1] == "runtime" if "-o" in argv else False
                self.assertEqual(has, not argv[-1].endswith(".dmg"))

    def test_the_launcher_claims_no_entitlements(self):
        self.run_tool()
        for argv in self.argvs():
            with self.subTest(argv[-1]):
                self.assertFalse([a for a in argv if a.startswith(("--entitlements", "--preserve"))])

    def test_only_the_dmg_gets_an_identifier_and_sparkles_pieces_keep_theirs(self):
        self.run_tool()
        ids = {Path(a[-1]).name: a[a.index("-i") + 1] for a in self.signing() if "-i" in a}
        self.assertEqual(ids, {"Dragoon.dmg": BUNDLE_ID + ".dmg"})

    def test_the_dmg_holds_the_app_and_an_applications_link_and_nothing_else(self):
        self.run_tool()
        (made,) = [c for c in self.calls() if c["tool"] == "hdiutil"]
        self.assertEqual(made["listing"], ["Applications", APP])
        self.assertEqual(made["applications"], "/Applications")
        self.assertEqual(made["argv"][:5], ["create", "-format", "UDZO", "-volname", "Dragoon"])

    def test_the_team_key_goes_to_notarytool_by_path_and_is_never_printed(self):
        self.key.chmod(0)
        self.addCleanup(self.key.chmod, 0o600)
        code, out, err = self.run_tool()
        self.assertEqual(code, 0)
        (submit,) = [c for c in self.calls() if c["argv"][:2] == ["notarytool", "submit"]]
        self.assertIn("--wait", submit["argv"])
        self.assertEqual(submit["argv"][submit["argv"].index("--key") + 1], str(self.key))
        self.assertNotIn("PRIVATE KEY", out + err + self.records.read_text())

    def test_an_ad_hoc_run_asks_for_no_timestamp_and_no_hardened_runtime(self):
        code, out, err = self.run_tool(notary=False, identity="-")
        self.assertEqual(code, 0)
        calls = self.signing()
        self.assertEqual(len(calls), 5)  # Sparkle's three, the app and the DMG
        for argv in calls:
            with self.subTest(argv[-1]):
                self.assertIn("--timestamp=none", argv)
                self.assertNotIn("--timestamp", argv)  # the server wants an Apple identity
                self.assertNotIn("-o", argv)  # library validation would stop an ad hoc Sparkle
                self.assertNotIn("--deep", argv)
        want = self.expected(notarize=False, identity="-")
        self.assertEqual(self.argvs(), [c for c in want if c[0] != "/bin/ln"])
        self.assertEqual(self.printed(out), want)

    def test_a_developer_id_run_has_the_runtime_and_a_secure_timestamp_on_every_item(self):
        self.run_tool()
        for argv in self.signing()[:-1]:  # the DMG is no code, so it has no runtime
            with self.subTest(argv[-1]):
                self.assertEqual(argv[argv.index("-o") + 1], "runtime")
                self.assertIn("--timestamp", argv)
                self.assertFalse([a for a in argv if a.startswith("--timestamp=")])

    def test_ad_hoc_with_no_notary_key_signs_and_makes_the_dmg_only(self):
        code, out, err = self.run_tool(notary=False, identity="-")
        self.assertEqual(code, 0)
        self.assertIn("isn't notarized", err)
        tools = [a[0] for a in self.argvs()]
        self.assertNotIn(self.fakes["xcrun"], tools)
        self.assertNotIn(self.fakes["spctl"], tools)
        self.assertEqual(self.argvs()[-1][:3], [self.fakes["codesign"], "-s", "-"])  # the DMG's
        self.assertEqual(self.argvs()[-1][-1], str(self.out / "Dragoon.dmg"))
        self.assertEqual({a[a.index("-s") + 1] for a in self.signing()}, {"-"})
        self.assertEqual(out.splitlines()[-1], str(self.out / "Dragoon.dmg"))


class DryRunTest(SignTestCase):
    def test_it_prints_every_command_and_runs_none(self):
        code, dry, err = self.run_tool("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.printed(dry), self.expected())
        self.assertFalse(self.records.exists(), "a command ran")
        self.assertFalse(self.out.exists(), "the output directory was made")
        self.assertTrue(dry.splitlines()[-1].startswith("+ "), "something besides a command")

    def test_a_live_run_prints_the_same_commands(self):
        _, dry, _ = self.run_tool("--dry-run")
        _, live, _ = self.run_tool()
        self.assertEqual(self.printed(live), self.printed(dry))

    def test_it_does_not_need_the_key_file(self):
        self.key.unlink()
        code, _, _ = self.run_tool("--dry-run")
        self.assertEqual(code, 0)


class FailureTest(SignTestCase):
    def test_a_failed_codesign_stops_everything(self):
        self.switch("fail codesign")
        code, _, err = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual([c["tool"] for c in self.calls()], ["ditto", "codesign"])
        self.assertIn("Autoupdate", err)
        self.assertIn("exited 1", err)

    def test_a_failed_dmg_stops_before_it_is_signed_after_three_tries(self):
        self.switch("fail hdiutil")
        code, _, _ = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls()[-1]["tool"], "hdiutil")
        self.assertEqual([c["tool"] for c in self.calls()].count("hdiutil"), 3)

    def test_hdiutil_create_is_tried_again_after_a_busy_failure(self):
        self.switch("hdiutil flakes")  # fails twice, as its Resource busy flake does
        code, out, err = self.run_tool()
        self.assertEqual(code, 0)
        self.assertEqual([c["tool"] for c in self.calls()].count("hdiutil"), 3)
        self.assertIn("trying again", err)
        self.assertEqual(out.splitlines()[-1], str(self.out / "Dragoon.dmg"))

    def test_a_signature_that_does_not_verify_stops_before_the_dmg_exists(self):
        self.switch("fail verify")
        code, _, err = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls()[-1]["argv"][:3], ["--verify", "--strict", "--deep"])
        self.assertNotIn("hdiutil", [c["tool"] for c in self.calls()])
        self.assertFalse((self.out / "Dragoon.dmg").exists())
        self.assertIn("exited 1", err)

    def test_a_notarization_that_never_finishes_is_cut_off_and_says_how_to_look(self):
        self.switch("notarytool hangs")
        code, _, err = self.run_tool("--notary-timeout", "0.02")  # 1.2 s
        self.assertEqual(code, 1)
        self.assertIn("didn't finish in 0.02 min", err)
        history = shlex.join([self.fakes["xcrun"], "notarytool", "history", "--key", str(self.key),
                              "--key-id", KEY_ID, "--issuer", ISSUER])
        self.assertIn(history, err)
        self.assertEqual(self.calls()[-1]["argv"][:2], ["notarytool", "submit"])  # never stapled

    def test_the_notarization_cut_off_is_30_minutes_unless_given(self):
        defaults = sign_and_package.parse_args(["--app", "a", "--identity", "-", "--out", "o"])
        self.assertEqual(defaults.notary_timeout, 30)
        self.assertEqual(self.notarytool_timeout("default out"), 30 * 60)
        self.assertEqual(self.notarytool_timeout("given out", "--notary-timeout", "45"), 45 * 60)

    def notarytool_timeout(self, out: str, *extra: str) -> float:
        """The seconds a run's notarytool submit was given, with its output in OUT."""
        self.out = self.dir / out
        with mock.patch.object(sign_and_package.subprocess, "run",
                               wraps=sign_and_package.subprocess.run) as run:
            code, _, _ = self.run_tool(*extra)
        self.assertEqual(code, 0)
        (submit,) = [c for c in run.call_args_list if c.args[0][1:3] == ["notarytool", "submit"]]
        return submit.kwargs["timeout"]

    def test_a_rejected_notarization_stops_and_says_how_to_see_why(self):
        self.switch("invalid", "notarytool exits 1")
        code, _, err = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls()[-1]["argv"][:2], ["notarytool", "submit"])
        self.assertIn("SUB-123", err)
        self.assertIn("Invalid", err)
        log = shlex.join([self.fakes["xcrun"], "notarytool", "log", "SUB-123", "--key", str(self.key),
                          "--key-id", KEY_ID, "--issuer", ISSUER])
        self.assertIn(log, err)

    def test_a_rejection_that_exits_0_still_stops(self):
        self.switch("invalid")
        code, _, err = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls()[-1]["argv"][:2], ["notarytool", "submit"])
        self.assertIn("SUB-123", err)

    def test_an_accepted_status_from_a_notarytool_that_exited_1_still_stops(self):
        self.switch("notarytool exits 1")
        code, _, err = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls()[-1]["argv"][:2], ["notarytool", "submit"])  # never stapled
        self.assertIn("SUB-123", err)

    def test_notarytool_failing_without_an_id_says_so(self):
        self.switch("no json")
        code, _, err = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls()[-1]["argv"][:2], ["notarytool", "submit"])
        self.assertIn("no submission ID", err)
        self.assertNotIn("notarytool log", err)

    def test_a_failed_staple_stops_before_verifying(self):
        self.switch("fail stapler")
        code, _, _ = self.run_tool()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls()[-1]["argv"][:2], ["stapler", "staple"])

    def test_a_failed_assessment_is_a_failure(self):
        self.switch("fail spctl")
        code, _, err = self.run_tool()
        self.assertEqual(code, 1)
        self.assertIn("exited 3", err)


class RefusalTest(SignTestCase):
    def assert_refused(self, why: str, *extra: str, **kwargs) -> None:
        code, out, err = self.run_tool(*extra, **kwargs)
        self.assertEqual((code, out), (2, ""))
        self.assertIn(why, err)
        self.assertFalse(self.records.exists(), "a command ran")
        self.assertFalse(self.out.exists(), "the output directory was made")

    def test_an_app_that_is_not_there(self):
        self.app = self.dir / "Gone.app"
        self.assert_refused(str(self.app))
        self.assert_refused(str(self.app), "--dry-run")

    def test_an_app_with_no_bundle_identifier(self):
        with (self.app / "Contents" / "Info.plist").open("wb") as f:
            plistlib.dump({"CFBundleName": "Dragoon"}, f)
        self.assert_refused("CFBundleIdentifier")

    def test_an_app_with_no_info_plist(self):
        (self.app / "Contents" / "Info.plist").unlink()
        self.assert_refused("Info.plist")

    def test_an_output_directory_inside_the_app(self):
        self.out = self.app / "release out"  # ditto would copy the app into itself
        self.assert_refused("inside")
        self.assert_refused("inside", "--dry-run")

    def test_an_app_that_still_has_sparkles_xpc_services(self):
        self.app = make_app(self.dir / "with xpc" / "Dragoon.app", xpc=True)
        self.assert_refused("Versions/B/XPCServices")
        self.assert_refused("Versions/B/XPCServices", "--dry-run")

    def test_an_app_with_a_leftover_link_to_the_xpc_services(self):
        framework = self.app / "Contents/Frameworks/Sparkle.framework"
        os.symlink("Versions/Current/XPCServices", framework / "XPCServices")
        self.assert_refused("Sparkle.framework/XPCServices")

    def test_an_output_directory_that_is_not_empty(self):
        self.out.mkdir()
        (self.out / "left over").write_text("x")
        code, out, err = self.run_tool()
        self.assertEqual((code, out), (2, ""))
        self.assertIn(str(self.out), err)
        self.assertEqual(os.listdir(self.out), ["left over"])
        self.assertFalse(self.records.exists(), "a command ran")

    def test_a_notary_key_without_its_id_and_issuer(self):
        for missing in ("--notary-key", "--notary-key-id", "--notary-issuer"):
            with self.subTest(missing):
                argv = ["--app", str(self.app), "--identity", IDENTITY, "--out", str(self.out)]
                given = {"--notary-key": str(self.key), "--notary-key-id": KEY_ID,
                         "--notary-issuer": ISSUER}
                for flag, value in given.items():
                    if flag != missing:
                        argv += [flag, value]
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    code = sign_and_package.main(argv)
                self.assertEqual(code, 2)
                self.assertIn("all three", err.getvalue())

    def test_an_ad_hoc_identity_with_a_notary_key(self):
        self.assert_refused("ad hoc", identity="-")
        self.assert_refused("ad hoc", "--dry-run", identity="-")

    def test_a_notary_timeout_outside_zero_to_a_day(self):
        # subprocess.run raises OverflowError for 36000 minutes and for 1e300, once notarytool runs
        for bad in ("0", "-5", "nan", "inf", "1441", "36000", "1e300"):
            with self.subTest(bad):
                self.assert_refused("--notary-timeout", f"--notary-timeout={bad}")

    def test_a_day_is_the_longest_notary_timeout(self):
        code, _, _ = self.run_tool("--dry-run", "--notary-timeout", "1440")
        self.assertEqual(code, 0)
        self.assert_refused("between 0 and 1440 minutes", "--dry-run", "--notary-timeout", "1440.5")

    def test_a_notary_key_file_that_is_not_there(self):
        self.key.unlink()
        self.assert_refused(str(self.key))

    def test_no_identity(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                sign_and_package.main(["--app", str(self.app), "--out", str(self.out)])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--identity", err.getvalue())

    def test_help_exits_0_and_prints_usage(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as raised:
                sign_and_package.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Usage:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
