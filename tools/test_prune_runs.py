from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

import prune_runs
from testutil import run_main

HOUR = 3600
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


class PruneTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        # A whole second, so a time set with os.utime reads back exactly.
        self.now = float(int(time.time()))
        self.clone = self.make_clone("clone")
        self.probe = self.clone / "build" / "probe"

    def make_clone(self, name: str) -> Path:
        clone = self.root / name
        (clone / "build" / "probe").mkdir(parents=True)
        return clone

    def touch(self, path: Path, hours: float) -> None:
        """Set PATH's own mtime, or a link's own, to HOURS before now."""
        stamp = self.now - hours * HOUR
        os.utime(path, (stamp, stamp), follow_symlinks=False)

    def age(self, path: Path, hours: float) -> None:
        """Touch PATH and everything under it, going through no links."""
        self.touch(path, hours)
        if path.is_dir() and not path.is_symlink():
            for here, dirs, files in os.walk(path):
                for name in dirs + files:
                    self.touch(Path(here, name), hours)

    def make_run(self, name: str, hours: float, size: int = 100, clone: Path | None = None) -> Path:
        """A run directory holding two files of SIZE bytes, all HOURS old."""
        run = (clone or self.clone) / "build" / "probe" / name
        (run / "saves").mkdir(parents=True)
        (run / "stdout.txt").write_bytes(b"x" * size)
        (run / "saves" / "card").write_bytes(b"y" * size)
        self.age(run, hours)
        return run

    def make_file(self, name: str, hours: float, size: int = 100) -> Path:
        path = self.probe / name
        path.write_bytes(b"f" * size)
        self.touch(path, hours)
        return path

    def make_target(self) -> Path:
        """A directory outside the clone, with a fresh file and an old one."""
        target = self.root / "elsewhere"
        target.mkdir()
        (target / "fresh.txt").write_text("fresh")
        (target / "old.txt").write_text("old")
        self.touch(target / "old.txt", 500)
        return target

    def assert_target_intact(self, target: Path) -> None:
        self.assertEqual((target / "fresh.txt").read_text(), "fresh")
        self.assertEqual((target / "old.txt").read_text(), "old")

    def prune(self, *args: str) -> tuple[int, str, str]:
        return run_main(lambda argv: prune_runs.main(argv, now=self.now), *args)

    def names(self) -> list[str]:
        return sorted(os.listdir(self.probe))


class StaleTest(PruneTestCase):
    def test_a_dry_run_lists_the_stale_children_with_size_and_age_and_a_total(self):
        old = self.make_run("old", 48)
        older = self.make_run("older", 26.5, size=1000)
        self.make_run("fresh", 1)
        code, out, err = self.prune(str(self.clone))
        self.assertEqual(code, 0)
        self.assertEqual(out, f"     200 B    2d 0h  {old}\n"
                              f"   2.0 KiB    1d 2h  {older}\n"
                              "would free 2.1 KiB from 2 entries\n")
        self.assertEqual(err, "")

    def test_a_dry_run_removes_nothing(self):
        self.make_run("old", 48)
        self.make_file("old-file", 48)
        before = [(here, sorted(dirs), sorted(files)) for here, dirs, files in os.walk(self.clone)]
        code, out, err = self.prune(str(self.clone))
        self.assertEqual(code, 0)
        self.assertIn("would free", out)
        self.assertEqual(before, [(here, sorted(dirs), sorted(files))
                                  for here, dirs, files in os.walk(self.clone)])

    def test_delete_removes_the_stale_children_and_keeps_the_fresh_ones(self):
        old = self.make_run("old", 48)
        fresh = self.make_run("fresh", 1)
        old_file = self.make_file("old.txt", 48)
        fresh_file = self.make_file("fresh.txt", 1)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 0)
        self.assertEqual(self.names(), [fresh.name, fresh_file.name])
        self.assertEqual(out, f"     200 B    2d 0h  {old}\n"
                              f"     100 B    2d 0h  {old_file}\n"
                              "freed 300 B from 2 entries\n")
        self.assertEqual(err, "")

    def test_nothing_stale_prints_a_zero_total(self):
        self.make_run("fresh", 1)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual((code, out, err), (0, "freed 0 B from 0 entries\n", ""))

    def test_a_fresh_file_deep_inside_an_old_directory_keeps_it(self):
        run = self.make_run("long", 72)
        deep = run / "a" / "b"
        deep.mkdir(parents=True)
        late = deep / "late.txt"
        late.write_text("late")
        self.age(run, 72)
        self.touch(late, 1)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 0)
        self.assertEqual(self.names(), ["long"])
        self.assertTrue(late.exists())

    def test_a_fresh_empty_directory_inside_an_old_one_keeps_it_too(self):
        run = self.make_run("long", 72)
        (run / "new").mkdir()
        self.age(run, 72)
        self.touch(run / "new", 1)
        self.prune("--delete", str(self.clone))
        self.assertEqual(self.names(), ["long"])

    def test_an_old_file_inside_a_fresh_directory_does_not_make_it_stale(self):
        run = self.make_run("run", 72)
        self.touch(run, 1)
        self.prune("--delete", str(self.clone))
        self.assertEqual(self.names(), ["run"])

    def test_hours_sets_how_old_is_old(self):
        three = self.make_run("three", 3)
        one = self.make_run("one", 1)
        code, out, err = self.prune("--hours", "2", str(self.clone))
        self.assertEqual(code, 0)
        self.assertIn(str(three), out)
        self.assertNotIn(str(one), out)
        code, out, err = self.prune(str(self.clone))
        self.assertEqual(out, "would free 0 B from 0 entries\n")

    def test_the_limit_is_24_hours_unless_given(self):
        self.make_run("day-and-a-bit", 24.5)
        self.make_run("just-under", 23.5)
        self.prune("--delete", str(self.clone))
        self.assertEqual(self.names(), ["just-under"])

    def test_a_child_exactly_as_old_as_the_limit_is_kept(self):
        self.make_run("edge", 2)
        self.make_run("past", 2.01)
        code, out, err = self.prune("--hours", "2", "--delete", str(self.clone))
        self.assertEqual(self.names(), ["edge"])

    def test_hours_can_be_a_fraction_or_zero(self):
        self.make_run("half", 0.75)
        self.make_run("minutes", 0.25)
        self.prune("--hours", "0.5", "--delete", str(self.clone))
        self.assertEqual(self.names(), ["minutes"])
        self.prune("--hours", "0", "--delete", str(self.clone))
        self.assertEqual(self.names(), [])

    def test_a_bad_hours_is_a_bad_argument(self):
        for value in ("-1", "abc", "nan", "inf"):
            code, out, err = self.prune(f"--hours={value}", str(self.clone))
            self.assertEqual(code, 2, value)
            self.assertIn("hours", err)

    def test_several_clones_share_one_total_and_one_clone_named_twice_counts_once(self):
        other = self.make_clone("other")
        a = self.make_run("a", 48)
        b = self.make_run("b", 48, clone=other)
        code, out, err = self.prune(str(self.clone), str(other), str(self.clone))
        self.assertEqual(code, 0)
        self.assertEqual(out, f"     200 B    2d 0h  {a}\n"
                              f"     200 B    2d 0h  {b}\n"
                              "would free 400 B from 2 entries\n")

    def test_help_prints_the_usage_and_exits_0(self):
        code, out, err = run_main(prune_runs.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("--hours", out)
        self.assertIn("--delete", out)


class KeepTest(PruneTestCase):
    def test_names_in_keep_stay_and_keep_itself_is_never_touched(self):
        for name in ("pinned", "also", "gone", "stale"):
            self.make_run(name, 100)
        keep = self.probe / "keep"
        text = b"# runs the report cites\npinned\n\n  also  \r\n# stale\nnot-there\n"
        keep.write_bytes(text)
        self.touch(keep, 100)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 0)
        self.assertEqual(self.names(), ["also", "keep", "pinned"])
        self.assertNotIn(str(keep), out)
        self.assertEqual(keep.read_bytes(), text)
        self.assertEqual(out.splitlines()[-1], "freed 400 B from 2 entries")

    def test_a_dry_run_leaves_the_kept_names_out_of_the_list(self):
        pinned = self.make_run("pinned", 100)
        stale = self.make_run("stale", 100)
        (self.probe / "keep").write_text("pinned\n")
        code, out, err = self.prune(str(self.clone))
        self.assertIn(str(stale), out)
        self.assertNotIn(str(pinned), out)

    def test_a_file_named_in_keep_stays_too(self):
        self.make_file("notes.txt", 100)
        (self.probe / "keep").write_text("notes.txt\n")
        self.prune("--delete", str(self.clone))
        self.assertEqual(self.names(), ["keep", "notes.txt"])

    def test_a_keep_that_is_not_a_plain_file_refuses_the_clone(self):
        run = self.make_run("old", 100)
        (self.probe / "keep").mkdir()
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 2)
        self.assertIn("keep: not a plain file", err)
        self.assertTrue(run.exists())

    def test_a_keep_that_is_a_link_refuses_the_clone(self):
        run = self.make_run("old", 100)
        names = self.root / "names.txt"
        names.write_text("old\n")
        (self.probe / "keep").symlink_to(names)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 2)
        self.assertTrue(run.exists())

    @unittest.skipIf(IS_ROOT, "root reads any file")
    def test_a_keep_that_cannot_be_read_refuses_the_clone(self):
        run = self.make_run("old", 100)
        keep = self.probe / "keep"
        keep.write_text("old\n")
        keep.chmod(0)
        self.addCleanup(keep.chmod, 0o644)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 2)
        self.assertTrue(run.exists())


class LinkTest(PruneTestCase):
    def test_a_stale_symlinked_child_goes_as_a_link_and_its_target_stays(self):
        target = self.make_target()
        link = self.probe / "ln"
        link.symlink_to(target, target_is_directory=True)
        self.touch(link, 48)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 0)
        self.assertFalse(os.path.lexists(link))
        self.assert_target_intact(target)
        self.assertIn(str(link), out)

    def test_a_stale_link_to_a_file_goes_and_the_file_stays(self):
        target = self.root / "outside.txt"
        target.write_text("outside")
        link = self.probe / "file-link"
        link.symlink_to(target)
        self.touch(link, 48)
        self.prune("--delete", str(self.clone))
        self.assertFalse(os.path.lexists(link))
        self.assertEqual(target.read_text(), "outside")

    def test_a_dangling_link_is_removed_too(self):
        link = self.probe / "dangling"
        link.symlink_to(self.root / "nowhere")
        self.touch(link, 48)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 0)
        self.assertFalse(os.path.lexists(link))

    def test_a_fresh_link_stays_whatever_its_target_looks_like(self):
        target = self.make_target()
        self.touch(target, 500)
        link = self.probe / "ln"
        link.symlink_to(target, target_is_directory=True)
        self.touch(link, 1)
        self.prune("--delete", str(self.clone))
        self.assertEqual(self.names(), ["ln"])
        self.assert_target_intact(target)

    def test_a_link_inside_a_stale_run_is_not_followed_in_the_walk_or_the_delete(self):
        target = self.make_target()
        run = self.make_run("old", 48)
        (run / "out").symlink_to(target, target_is_directory=True)
        self.age(run, 48)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 0)
        self.assertFalse(run.exists())
        self.assert_target_intact(target)
        self.assertIn("freed 200 B from 1 entry", out)

    def test_a_link_inside_a_run_that_points_up_does_not_loop_or_keep_it(self):
        run = self.make_run("old", 48)
        (run / "up").symlink_to(self.probe, target_is_directory=True)
        self.age(run, 48)
        fresh = self.make_run("fresh", 1)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 0)
        self.assertEqual(self.names(), ["fresh"])
        self.assertTrue(fresh.exists())


class RefusalTest(PruneTestCase):
    def linked_clone(self, target: Path, name: str = "linked") -> Path:
        clone = self.root / name
        (clone / "build").mkdir(parents=True)
        (clone / "build" / "probe").symlink_to(target, target_is_directory=True)
        return clone

    def test_a_build_probe_linked_outside_the_clone_is_refused_and_its_target_untouched(self):
        outside = self.root / "outside"
        outside.mkdir()
        old = outside / "old"
        old.mkdir()
        self.age(old, 48)
        clone = self.linked_clone(outside)
        code, out, err = self.prune("--delete", str(clone))
        self.assertEqual(code, 2)
        self.assertIn(f"{clone / 'build' / 'probe'}: resolves to {outside}", err)
        self.assertEqual(out, "")
        self.assertTrue(old.exists())

    def test_a_refused_clone_stops_the_others_from_losing_anything(self):
        old = self.make_run("old", 48)
        clone = self.linked_clone(self.root)
        code, out, err = self.prune("--delete", str(self.clone), str(clone))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(old.exists())

    def test_a_build_probe_linked_to_another_place_in_the_clone_is_refused(self):
        clone = self.root / "sneaky"
        (clone / "build").mkdir(parents=True)
        (clone / "src").mkdir()
        (clone / "src" / "main.c").write_text("int main;")
        self.age(clone / "src", 500)
        (clone / "build" / "probe").symlink_to(clone / "src", target_is_directory=True)
        code, out, err = self.prune("--delete", str(clone))
        self.assertEqual(code, 2)
        self.assertTrue((clone / "src" / "main.c").exists())

    def test_a_build_linked_outside_the_clone_is_refused(self):
        outside = self.root / "fast-disk"
        (outside / "probe" / "old").mkdir(parents=True)
        self.age(outside / "probe" / "old", 48)
        clone = self.root / "relinked"
        clone.mkdir()
        (clone / "build").symlink_to(outside, target_is_directory=True)
        code, out, err = self.prune("--delete", str(clone))
        self.assertEqual(code, 2)
        self.assertTrue((outside / "probe" / "old").exists())

    def test_a_dangling_build_probe_link_is_refused(self):
        clone = self.linked_clone(self.root / "nowhere")
        code, out, err = self.prune("--delete", str(clone))
        self.assertEqual(code, 2)
        self.assertIn("resolves to", err)

    def test_a_build_probe_link_loop_does_not_crash(self):
        clone = self.root / "loop"
        (clone / "build").mkdir(parents=True)
        (clone / "build" / "probe").symlink_to("probe")
        code, out, err = self.prune("--delete", str(clone))
        self.assertIn(code, (0, 2))
        self.assertNotIn("Traceback", err)

    def test_a_clone_reached_through_a_link_is_fine(self):
        old = self.make_run("old", 48)
        alias = self.root / "alias"
        alias.symlink_to(self.clone, target_is_directory=True)
        code, out, err = self.prune("--delete", str(alias))
        self.assertEqual(code, 0)
        self.assertFalse(old.exists())

    def test_a_clone_that_is_not_a_directory_is_refused(self):
        code, out, err = self.prune(str(self.root / "typo"))
        self.assertEqual(code, 2)
        self.assertIn("typo: not a directory", err)

    def test_a_clone_without_build_probe_is_skipped_with_a_note(self):
        bare = self.root / "bare"
        bare.mkdir()
        no_probe = self.root / "no-probe"
        (no_probe / "build").mkdir(parents=True)
        old = self.make_run("old", 48)
        code, out, err = self.prune("--delete", str(bare), str(no_probe), str(self.clone))
        self.assertEqual(code, 0)
        self.assertEqual(err, f"{bare}: no build/probe, skipped\n{no_probe}: no build/probe, skipped\n")
        self.assertFalse(old.exists())
        self.assertTrue(bare.exists() and (no_probe / "build").exists())

    def test_only_clones_without_build_probe_still_exit_0(self):
        bare = self.root / "bare"
        bare.mkdir()
        code, out, err = self.prune(str(bare))
        self.assertEqual((code, out), (0, "would free 0 B from 0 entries\n"))


class FailureTest(PruneTestCase):
    @unittest.skipIf(IS_ROOT, "root ignores permissions")
    def test_a_child_that_fails_to_delete_is_reported_and_the_rest_still_go(self):
        locked = self.make_run("a-locked", 48)
        inner = locked / "saves"
        inner.chmod(0o555)
        self.addCleanup(inner.chmod, 0o755)
        later = self.make_run("z-later", 48)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 1)
        self.assertEqual(err.count("\n"), 1)
        self.assertTrue(err.startswith(f"{locked}: cannot remove: "))
        self.assertTrue(locked.exists())
        self.assertFalse(later.exists())
        self.assertEqual(out, f"     200 B    2d 0h  {later}\n"
                              "freed 200 B from 1 entry, 1 failed\n")

    @unittest.skipIf(IS_ROOT, "root ignores permissions")
    def test_files_and_links_that_fail_to_delete_are_reported_each(self):
        a = self.make_file("a.txt", 48)
        link = self.probe / "b-link"
        link.symlink_to(a)
        self.touch(link, 48)
        self.probe.chmod(0o555)
        self.addCleanup(self.probe.chmod, 0o755)
        code, out, err = self.prune(str(self.clone))
        self.assertEqual(code, 0)
        code, out, err = self.prune("--delete", str(self.clone))
        self.assertEqual(code, 1)
        self.assertEqual([line.split(": cannot remove: ")[0] for line in err.splitlines()],
                         [str(a), str(link)])
        self.assertEqual(out, "freed 0 B from 0 entries, 2 failed\n")
        self.assertTrue(a.exists() and os.path.lexists(link))

    @unittest.skipIf(IS_ROOT, "root ignores permissions")
    def test_a_child_it_cannot_read_is_reported_and_kept_even_on_a_dry_run(self):
        sealed = self.make_run("sealed", 48)
        inner = sealed / "saves"
        inner.chmod(0)
        self.addCleanup(inner.chmod, 0o755)
        other = self.make_run("other", 48)
        code, out, err = self.prune(str(self.clone))
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith(f"{sealed}: cannot read: "))
        self.assertIn(str(other), out)
        self.assertNotIn(str(sealed), out)
        self.assertTrue(out.endswith("would free 200 B from 1 entry, 1 failed\n"))

    @unittest.skipIf(IS_ROOT, "root ignores permissions")
    def test_a_build_probe_it_can_search_but_not_list_is_reported_and_the_other_clones_still_go(self):
        locked = self.make_clone("locked")
        self.make_run("old", 48, clone=locked)
        locked_probe = locked / "build" / "probe"
        locked_probe.chmod(0o100)
        self.addCleanup(locked_probe.chmod, 0o755)
        mine = self.make_run("old", 48)
        code, out, err = self.prune("--delete", str(locked), str(self.clone))
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith(f"{locked_probe}: cannot read: "))
        self.assertFalse(mine.exists())
        self.assertTrue(out.endswith("freed 200 B from 1 entry, 1 failed\n"))

    @unittest.skipIf(IS_ROOT, "root ignores permissions")
    def test_a_build_probe_it_cannot_search_refuses_the_clone_and_nothing_goes(self):
        locked = self.make_clone("locked")
        locked_probe = locked / "build" / "probe"
        locked_probe.chmod(0)
        self.addCleanup(locked_probe.chmod, 0o755)
        mine = self.make_run("old", 48)
        code, out, err = self.prune("--delete", str(locked), str(self.clone))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(mine.exists())


class FormatTest(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual([prune_runs.human_size(n) for n in
                          (0, 1023, 1024, 1500, 5 * 1024 ** 3, 3 * 1024 ** 4, 2048 * 1024 ** 4)],
                         ["0 B", "1023 B", "1.0 KiB", "1.5 KiB", "5.0 GiB", "3.0 TiB",
                          "2048.0 TiB"])

    def test_ages(self):
        self.assertEqual([prune_runs.human_age(s) for s in
                          (-5, 59, 60, 5 * HOUR + 12 * 60 + 59, 26 * HOUR, 100 * 24 * HOUR)],
                         ["0m", "0m", "1m", "5h 12m", "1d 2h", "100d 0h"])

    def test_entries(self):
        self.assertEqual([prune_runs.n_entries(n) for n in (0, 1, 2)],
                         ["0 entries", "1 entry", "2 entries"])


if __name__ == "__main__":
    unittest.main()
