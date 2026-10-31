import itertools
import json
import math
import os
import re
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import interp_bisect
from testutil import run_main, write_file

FIRST = 0x80001000


def addr(i: int) -> int:
    """Where made-up function i starts. They sit 0x20 apart."""
    return FIRST + 0x20 * i


def symbols(count: int) -> str:
    """A symbols file of COUNT made-up functions called func0 to funcN, with an object and a
    label among them that aren't functions."""
    lines = ["data_0 = .data:0x80500000; // type:object size:0x10 scope:local data:4byte\n",
             "label_0 = .text:0x80001010; // type:label\n"]
    lines += [f"func{i} = .text:0x{addr(i):08X}; // type:function size:0x20 scope:global\n"
              for i in range(count)]
    return "".join(lines)


def address_set(indexes: tuple[int, ...]) -> str:
    return "{" + ", ".join(str(addr(i)) for i in indexes) + "}"


def fails_on(*indexes: int) -> str:
    """A list fails when it holds any of these functions."""
    return f"bool({address_set(indexes)} & set(listed))"


def fails_together(*indexes: int) -> str:
    """A list fails only when it holds all of these functions."""
    return f"{address_set(indexes)} <= set(listed)"


class StartsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_reads_the_function_starts_and_their_names_in_address_order(self):
        path = write_file(self.dir, "symbols.txt", "\n".join([
            "second = .text:0x80001040; // type:function size:0x20 scope:global",
            "first = .init:0x80001000; // size:0x40 type:function",
            "",
            "table = .data:0x80500000; // type:object size:0x10",
            "here = .text:0x80001020; // type:label scope:local",
            "third = .text:0x80001060; // type:function",
            "",
        ]))
        self.assertEqual(interp_bisect.read_starts(path),
                         [(0x80001000, "first"), (0x80001040, "second"), (0x80001060, "third")])

    def test_an_address_named_twice_is_listed_once_under_its_first_name(self):
        path = write_file(self.dir, "symbols.txt",
                          "a = .text:0x80001000; // type:function\nb = .text:0x80001000; // type:function\n")
        self.assertEqual(interp_bisect.read_starts(path), [(0x80001000, "a")])

    def test_a_line_that_is_not_a_symbol_is_refused_with_the_path_and_line(self):
        path = write_file(self.dir, "symbols.txt", "a = .text:0x80001000; // type:function\njunk\n")
        with self.assertRaisesRegex(ValueError, f"{path}: line 2: not a symbol"):
            interp_bisect.read_starts(path)

    def test_a_file_with_no_functions_is_refused(self):
        path = write_file(self.dir, "symbols.txt", "t = .data:0x80500000; // type:object\n")
        with self.assertRaisesRegex(ValueError, f"{path}: no functions"):
            interp_bisect.read_starts(path)

    def test_reads_the_repositorys_own_symbols(self):
        starts = interp_bisect.read_starts(interp_bisect.ROOT / "analysis" / "symbols.txt")
        self.assertGreater(len(starts), 10000)
        self.assertEqual([a for a, _ in starts], sorted({a for a, _ in starts}))
        self.assertTrue(all(a % 4 == 0 for a, _ in starts))

    def test_a_list_is_one_upper_case_hex_address_a_line(self):
        self.assertEqual(interp_bisect.list_text([0x80001000, 0x8000A0B0]), "80001000\n8000A0B0\n")


class NarrowTest(unittest.TestCase):
    def narrow(self, n: int, bad: set[int]) -> tuple[list[int], list[list[int]]]:
        calls: list[list[int]] = []

        def fails(funcs: list[int]) -> bool:
            calls.append(list(funcs))
            return bool(set(funcs) & bad)

        return interp_bisect.narrow(list(range(n)), fails), calls

    def stuck(self, n: int, rule: Callable[[set[int]], bool]) -> tuple[interp_bisect.Irreducible, list[list[int]]]:
        """What narrow raises over functions 0 to N-1 when a list fails by RULE, and the lists it ran."""
        calls: list[list[int]] = []

        def fails(funcs: list[int]) -> bool:
            calls.append(list(funcs))
            return rule(set(funcs))

        with self.assertRaises(interp_bisect.Irreducible) as caught:
            interp_bisect.narrow(list(range(n)), fails)
        return caught.exception, calls

    def test_finds_every_set_of_bad_functions_in_a_short_list(self):
        for n in range(1, 9):
            for size in range(1, n + 1):
                for bad in itertools.combinations(range(n), size):
                    with self.subTest(n=n, bad=bad):
                        found, calls = self.narrow(n, set(bad))
                        self.assertEqual(found, list(bad))
                        self.assertLessEqual(len(calls), size * (math.ceil(math.log2(n)) + 2))
                        self.assertEqual(len({tuple(c) for c in calls}), len(calls))

    def test_a_function_reached_by_a_passing_left_half_is_run_alone_before_it_is_named(self):
        found, calls = self.narrow(8, {7})
        self.assertEqual(found, [7])
        self.assertEqual(calls, [[0, 1, 2, 3], [4, 5], [6], [7]])

    def test_a_pair_that_fails_only_together_is_not_blamed_on_the_last_function(self):
        # 0 changes the route alone. The pair changes it only when both are listed, and 7 is innocent.
        for pair in ({5, 6}, {2, 6}):
            with self.subTest(pair=pair):
                stuck, calls = self.stuck(8, lambda s: 0 in s or pair <= s)
                self.assertEqual((stuck.found, stuck.smallest), ([0], [1, 2, 3, 4, 5, 6, 7]))
                self.assertEqual(calls[-1], [7])

    def test_a_pair_in_the_followed_half_stops_the_search_before_a_function_that_fails_alone(self):
        # 7 changes the route alone, but the left half holds the pair 1 and 2, and 3 is innocent.
        stuck, calls = self.stuck(8, lambda s: 7 in s or {1, 2} <= s)
        self.assertEqual((stuck.found, stuck.smallest), ([], [0, 1, 2, 3]))
        self.assertEqual(calls[-1], [3])

    def test_lists_too_long_to_reach_the_checkpoints_are_not_blamed_on_the_last_function(self):
        # 2 changes the route alone, and any list of 4 or more changes it by running too slowly.
        stuck, calls = self.stuck(8, lambda s: 2 in s or len(s) >= 4)
        self.assertEqual((stuck.found, stuck.smallest), ([2], [3, 4, 5, 6, 7]))
        self.assertEqual(calls[-1], [7])

    def test_a_lone_pair_that_fails_only_together_is_not_blamed_on_the_last_function(self):
        stuck, calls = self.stuck(8, lambda s: {1, 6} <= s)
        self.assertEqual((stuck.found, stuck.smallest), ([], list(range(8))))
        self.assertEqual(calls, [[0, 1, 2, 3], [4, 5], [6], [7]])

    def test_stops_once_the_limit_is_found_and_the_halves_left_still_fail(self):
        with self.assertRaises(interp_bisect.TooManyFound) as caught:
            interp_bisect.narrow(list(range(20)), lambda s: True, limit=3)
        self.assertEqual(caught.exception.found, [0, 1, 2])

    def test_the_limit_itself_is_not_too_many(self):
        for bad in ({3, 4, 5}, {0, 10, 19}):
            with self.subTest(bad=bad):
                found = interp_bisect.narrow(list(range(20)), lambda s: bool(set(s) & bad), limit=3)
                self.assertEqual(found, sorted(bad))

    def test_one_more_than_the_limit_stops_with_the_first_ones_found(self):
        bad = {3, 4, 9, 15}
        with self.assertRaises(interp_bisect.TooManyFound) as caught:
            interp_bisect.narrow(list(range(20)), lambda s: bool(set(s) & bad), limit=3)
        self.assertEqual(caught.exception.found, [3, 4, 9])

    def test_the_limit_is_16_functions_unless_one_is_given(self):
        self.assertEqual(interp_bisect.MOST_FOUND, 16)
        with self.assertRaises(interp_bisect.TooManyFound) as caught:
            interp_bisect.narrow(list(range(100)), lambda s: True)
        self.assertEqual(caught.exception.found, list(range(16)))

    def test_only_ever_runs_lists_in_address_order_of_functions_it_was_given(self):
        _, calls = self.narrow(20, {3, 11, 12})
        for funcs in calls:
            self.assertTrue(funcs)
            self.assertEqual(funcs, sorted(set(funcs)))
            self.assertTrue(set(funcs) <= set(range(20)))

    def test_one_function_in_20003_takes_about_log2_of_that_many_runs(self):
        for bad in (0, 9999, 20002):
            with self.subTest(bad=bad):
                found, calls = self.narrow(20003, {bad})
                self.assertEqual(found, [bad])
                self.assertLessEqual(len(calls), math.ceil(math.log2(20003)) + 2)

    def test_two_functions_take_about_twice_that(self):
        found, calls = self.narrow(20003, {17, 19000})
        self.assertEqual(found, [17, 19000])
        self.assertLessEqual(len(calls), 2 * (math.ceil(math.log2(20003)) + 2))

    def test_adjacent_and_far_apart_functions_are_both_found(self):
        for bad in ({100, 101}, {0, 20002}, {5000, 15000}):
            with self.subTest(bad=bad):
                self.assertEqual(self.narrow(20003, bad)[0], sorted(bad))

    def test_a_list_of_one_is_that_function_and_runs_nothing(self):
        self.assertEqual(self.narrow(1, {0}), ([0], []))


FAKE_TOOL = r"""import json, os, sys
path = os.environ.get("GCN_INTERPRET")
listed = None
if path is not None:
    with open(path) as f:
        listed = sorted(int(line, 16) for line in f.read().split())
with open(@RECORDS@, "a") as f:
    f.write(json.dumps({"tool": os.path.basename(sys.argv[0]), "args": sys.argv[1:],
                        "interpret": path, "listed": listed}) + "\n")
print("fake report: " + ("nothing interpreted" if listed is None else f"{len(listed)} functions"))
if listed is None:
    sys.exit(@NATIVE@)
sys.exit(1 if (@FAILS@) else 0)
"""


class MainTest(unittest.TestCase):
    """The bisect against a stand-in for the hash tools that fails any list holding a bad function."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.records = self.dir / "records.jsonl"
        self.bisect = self.dir / "build" / "bisect"
        self.tools = self.dir / "tools"
        self.tools.mkdir()
        write_file(self.dir, "manifest.txt", "title 20 60 120\nmenu 10 60 60\n")
        for patch in (mock.patch.object(interp_bisect, "MANIFEST", self.dir / "manifest.txt"),
                      mock.patch.object(interp_bisect, "SYMBOLS", self.dir / "symbols.txt"),
                      mock.patch.object(interp_bisect, "BISECT", self.bisect),
                      mock.patch.object(interp_bisect, "TOOLS",
                                        {"frames": self.tools / "frame_hashes.py",
                                         "audio": self.tools / "audio_hashes.py"})):
            patch.start()
            self.addCleanup(patch.stop)
        self.functions(8)
        self.install("False")

    def functions(self, count: int) -> None:
        write_file(self.dir, "symbols.txt", symbols(count))

    def install(self, fails: str, native: int = 0) -> None:
        text = (FAKE_TOOL.replace("@RECORDS@", repr(str(self.records))).replace("@NATIVE@", str(native))
                .replace("@FAILS@", fails))
        write_file(self.tools, "frame_hashes.py", text)
        write_file(self.tools, "audio_hashes.py", text)

    def runs(self) -> list[dict]:
        if not self.records.exists():
            return []
        return [json.loads(line) for line in self.records.read_text().splitlines()]

    def main(self, *argv: str) -> tuple[int, str, str]:
        return run_main(interp_bisect.main, *argv)

    def found(self, out: str) -> list[tuple[str, str]]:
        return re.findall(r"^  ([0-9A-F]{8})  (\S+)$", out, re.M)

    def test_names_the_one_function_that_changes_the_route_in_about_log2_runs(self):
        self.functions(64)
        for bad in (0, 17, 63):
            with self.subTest(bad=bad):
                self.records.unlink(missing_ok=True)
                self.install(fails_on(bad))
                code, out, err = self.main("title", "--slow=3")
                self.assertEqual(code, 1, err)
                self.assertEqual(self.found(out), [(f"{addr(bad):08X}", f"func{bad}")])
                self.assertLessEqual(len(self.runs()), math.log2(64) + 4)

    def test_names_two_functions_when_both_halves_change_the_route(self):
        self.functions(64)
        for bad in ((5, 40), (20, 21), (0, 63)):
            with self.subTest(bad=bad):
                self.records.unlink(missing_ok=True)
                self.install(fails_on(*bad))
                code, out, err = self.main("title", "--slow=3")
                self.assertEqual(code, 1, err)
                self.assertEqual(self.found(out), [(f"{addr(i):08X}", f"func{i}") for i in bad])
                self.assertLessEqual(len(self.runs()), 2 * (math.log2(64) + 2) + 3)

    def test_a_route_that_nothing_changes_exits_0_after_two_runs(self):
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 0, err)
        self.assertIn("Interpreting all 8 functions leaves title matching", out)
        self.assertEqual(self.found(out), [])
        self.assertEqual([r["interpret"] is None for r in self.runs()], [True, False])

    def test_a_route_that_changes_with_nothing_interpreted_exits_2_after_one_run(self):
        self.install(fails_on(1), native=1)
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 2)
        self.assertIn("title changes with nothing interpreted", err)
        self.assertIn("frame_hashes.py printed this on run 1:\nfake report: nothing interpreted\n", err)
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(out.count("run "), 1)
        self.assertNotIn("fake report", out)

    def test_a_hash_tool_that_cannot_run_exits_2_naming_it_and_showing_what_it_printed(self):
        for native, fails, report in ((2, "False", "nothing interpreted"),
                                      (0, "sys.exit(2) if len(listed) == 4 else True", "4 functions")):
            with self.subTest(native=native):
                self.install(fails, native=native)
                code, out, err = self.main("title", "--slow=3")
                self.assertEqual(code, 2)
                self.assertIn("frame_hashes.py exited 2", err)
                self.assertRegex(err, rf"frame_hashes.py printed this on run \d+:\nfake report: {report}\n")
                self.assertNotIn("fake report", out)
                self.assertEqual(self.found(out), [])

    def test_runs_that_go_as_expected_print_a_progress_line_and_none_of_the_hash_tools_output(self):
        self.install(fails_on(2, 5))
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 1, err)
        self.assertEqual(err, "")
        self.assertNotIn("fake report", out)
        progress = [line for line in out.splitlines() if line.startswith("run ")]
        self.assertEqual(len(progress), len(self.runs()))
        for line in progress:
            self.assertRegex(line, r"^run \d+, .+: (changes|matches) title \(\d+ s\)$")

    def test_functions_that_change_the_route_only_together_exit_2_with_the_smallest_list(self):
        self.install(fails_together(1, 6))
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 2)
        smallest = self.bisect / "title-frames-smallest.txt"
        self.assertIn(f"Interpreting the 8 functions in {smallest} changes title", err)
        self.assertIn("several functions together, or a list ran too slowly", err)
        self.assertIn("the functions after it weren't searched", err)
        self.assertEqual(smallest.read_text(), "".join(f"{addr(i):08X}\n" for i in range(8)))
        self.assertFalse((self.bisect / "title-frames-found.txt").exists())
        self.assertEqual(self.found(out), [])

    def test_a_build_that_fails_every_list_stops_at_16_functions_and_shows_the_full_list_run(self):
        self.functions(64)
        self.install("True")
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 2)
        found = self.bisect / "title-frames-found.txt"
        self.assertEqual(found.read_text(), "".join(f"{addr(i):08X}\n" for i in range(16)))
        self.assertIn(f"More than 16 functions change title alone, so the search stopped at the first 16, "
                      f"listed in {found}.", err)
        self.assertIn("A build that fails every list looks like this", err)
        self.assertIn("frame_hashes.py printed this on run 2:\nfake report: 64 functions\n", err)
        self.assertEqual(err.count("fake report"), 1)
        self.assertEqual(self.found(out), [])
        self.assertLessEqual(len(self.runs()), 2 + 16 * (math.log2(64) + 2))

    def test_16_functions_are_named_and_17_are_too_many(self):
        for count, code in ((16, 1), (17, 2)):
            with self.subTest(count=count):
                self.functions(68)
                self.records.unlink(missing_ok=True)
                self.install(fails_on(*range(0, 4 * count, 4)))
                got, out, err = self.main("title", "--slow=3")
                self.assertEqual(got, code, err)
                listed = (self.bisect / "title-frames-found.txt").read_text()
                self.assertEqual(listed, "".join(f"{addr(i):08X}\n" for i in range(0, 64, 4)))
                self.assertEqual(len(self.found(out)), 16 if count == 16 else 0)

    def test_a_function_found_alone_before_the_search_gives_out_is_left_in_the_found_list(self):
        # 2 changes the route alone, and any list of 4 or more changes it by running too slowly.
        self.install(f"{addr(2)} in listed or len(listed) >= 4")
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 2)
        smallest, found = self.bisect / "title-frames-smallest.txt", self.bisect / "title-frames-found.txt"
        self.assertEqual(smallest.read_text(), "".join(f"{addr(i):08X}\n" for i in range(3, 8)))
        self.assertEqual(found.read_text(), f"{addr(2):08X}\n")
        self.assertIn(f"Interpreting the 5 functions in {smallest} changes title", err)
        self.assertIn(f"found alone before that are listed in {found}", err)
        self.assertEqual(self.found(out), [])

    def test_a_function_reached_without_a_run_is_run_alone_once_before_it_is_named(self):
        self.install(fails_on(7))
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.found(out), [(f"{addr(7):08X}", "func7")])
        # native, all 8, then 4 and 2 and 1 functions that pass, then function 7 alone, which the final
        # check of what was found doesn't repeat.
        self.assertEqual([r["listed"] for r in self.runs()][-2:], [[addr(6)], [addr(7)]])
        self.assertEqual(len(self.runs()), 6)

    def test_functions_that_change_the_route_alone_but_not_together_exit_2_naming_them(self):
        # 2 and 5 each change the route alone, and listed together they don't.
        self.install(f"({address_set((2, 5))} & set(listed)) and len(listed) != 2")
        code, out, err = self.main("title", "--slow=3")
        self.assertEqual(code, 2)
        found = self.bisect / "title-frames-found.txt"
        self.assertEqual(found.read_text(), f"{addr(2):08X}\n{addr(5):08X}\n")
        self.assertIn(f"Interpreting the 2 functions found together leaves title matching, though each changes "
                      f"it alone. They're listed in {found}.", err)
        self.assertNotIn("mix", err)
        self.assertIn(f"frame_hashes.py printed this on run {len(self.runs())}:\nfake report: 2 functions\n", err)
        self.assertNotIn("fake report", out)

    def test_audio_runs_the_audio_tool_and_frames_is_the_default(self):
        self.install(fails_on(2))
        for flags, tool, kind in (((), "frame_hashes.py", "frames"), (("--frames",), "frame_hashes.py", "frames"),
                                  (("--audio",), "audio_hashes.py", "audio")):
            with self.subTest(flags=flags):
                self.records.unlink(missing_ok=True)
                code, _, err = self.main("title", "--slow=2", *flags)
                self.assertEqual(code, 1, err)
                self.assertEqual({r["tool"] for r in self.runs()}, {tool})
                self.assertTrue((self.bisect / f"title-{kind}-02.txt").exists())

    def test_every_run_is_a_check_of_the_route_at_the_given_slow_but_the_native_one(self):
        self.install(fails_on(2))
        self.main("menu", "--slow=7")
        runs = self.runs()
        self.assertGreater(len(runs), 2)
        self.assertEqual(runs[0]["args"], ["check", "menu"])
        self.assertEqual({tuple(r["args"]) for r in runs[1:]}, {("check", "menu", "--slow=7")})

    def test_the_first_run_is_native_even_when_the_environment_forces_the_interpreter(self):
        self.install(fails_on(2))
        with mock.patch.dict(os.environ, {"GCN_INTERPRET": "all"}):
            code, _, err = self.main("title", "--slow=3")
        self.assertEqual(code, 1, err)
        runs = self.runs()
        self.assertIsNone(runs[0]["interpret"])
        self.assertTrue(all(r["interpret"] != "all" for r in runs))

    def test_each_run_names_its_list_by_absolute_path_and_the_list_is_one_address_a_line(self):
        self.install(fails_on(5))
        self.main("title", "--slow=3")
        runs = self.runs()
        self.assertGreater(len(runs), 3)
        for n, run in enumerate(runs[1:], 2):
            with self.subTest(run=n):
                self.assertEqual(run["interpret"], str(self.bisect / f"title-frames-{n:02d}.txt"))
                text = (self.bisect / f"title-frames-{n:02d}.txt").read_text()
                self.assertEqual(text, "".join(f"{a:08X}\n" for a in run["listed"]))
                self.assertEqual(text.split(), sorted(text.split()))
        self.assertEqual(runs[1]["listed"], [addr(i) for i in range(8)])

    def test_a_list_is_named_by_absolute_path_whatever_the_build_folder_is(self):
        before = os.getcwd()
        self.addCleanup(os.chdir, before)
        os.chdir(self.dir)
        with mock.patch.object(interp_bisect, "BISECT", Path("rel") / "bisect"):
            code, _, err = self.main("title", "--slow=3")
        self.assertEqual(code, 0, err)
        listed = self.runs()[1]["interpret"]
        self.assertTrue(os.path.isabs(listed), listed)
        self.assertTrue(Path(listed).is_file())

    def test_the_functions_found_are_left_in_a_list_that_names_just_them(self):
        self.install(fails_on(2, 5))
        code, out, _ = self.main("title", "--slow=3")
        self.assertEqual(code, 1)
        path = self.bisect / "title-frames-found.txt"
        self.assertEqual(path.read_text(), f"{addr(2):08X}\n{addr(5):08X}\n")
        self.assertIn(str(path), out)

    def test_clears_the_lists_of_an_earlier_bisect_of_this_route_and_kind_only(self):
        self.bisect.mkdir(parents=True)
        stale = write_file(self.bisect, "title-frames-31.txt", "80001000\n")
        stale_found = write_file(self.bisect, "title-frames-found.txt", "80001000\n")
        stale_smallest = write_file(self.bisect, "title-frames-smallest.txt", "80001000\n")
        kept = [write_file(self.bisect, name, "x\n") for name in
                ("title-audio-01.txt", "title-audio-smallest.txt", "menu-frames-01.txt", "title-frames-4p-01.txt",
                 "notes.txt")]
        self.install(fails_on(2))
        self.main("title", "--slow=3")
        self.assertFalse(stale.exists())
        self.assertFalse(stale_smallest.exists())
        self.assertNotEqual(stale_found.read_text(), "80001000\n")
        self.assertTrue(all(p.exists() for p in kept))

    def test_does_not_run_a_list_it_has_already_run(self):
        self.install(fails_on(0))
        code, _, err = self.main("title", "--slow=3")
        self.assertEqual(code, 1, err)
        # native, all 8, then 4, 2 and 1 functions down the left side, then the 7 left over. The
        # check of the one function found was the third of those.
        self.assertEqual(len(self.runs()), 6)

    def test_bad_arguments_exit_2_without_running_anything(self):
        for argv in ((), ("title",), ("title", "--slow=0"), ("title", "--slow=x"), ("title", "--slow="),
                     ("nope", "--slow=3"), ("title", "--slow=3", "--frames", "--audio")):
            with self.subTest(argv=argv):
                code, _, err = self.main(*argv)
                self.assertEqual(code, 2)
                self.assertTrue(err)
                self.assertEqual(self.runs(), [])
                self.assertFalse(self.bisect.exists())

    def test_a_bad_slow_and_an_unknown_route_are_named(self):
        self.assertIn("--slow=0 isn't a whole number from 1", self.main("title", "--slow=0")[2])
        self.assertIn("nope", self.main("nope", "--slow=3")[2])

    def test_symbols_it_cannot_use_exit_2_naming_the_file_without_running_anything(self):
        path = self.dir / "symbols.txt"
        for label, text in (("none", None), ("no functions", "t = .data:0x80500000; // type:object\n"),
                            ("junk", "junk\n")):
            if text is None:
                path.unlink()
            else:
                write_file(self.dir, "symbols.txt", text)
            with self.subTest(label):
                code, _, err = self.main("title", "--slow=3")
                self.assertEqual(code, 2)
                self.assertIn(str(path), err)
                self.assertEqual(self.runs(), [])
                self.assertFalse(self.bisect.exists())

    def test_help_exits_0(self):
        code, out, _ = self.main("--help")
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out)
        self.assertIn("--slow=N", out)


if __name__ == "__main__":
    unittest.main()
