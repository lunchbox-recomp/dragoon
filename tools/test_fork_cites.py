"""fork_cites.py on a Dragoon-shaped repository whose gcn-recomp holds two commits, all under paths
with spaces, and find() on the cite forms the docs use."""
from __future__ import annotations

import os
import unittest
from unittest import mock

import fork_cites
from fork_cites import Cite
from testutil import GIT_ENV, commit, git, run_main, temp_dir, write_file

TEN = [f"line {i}" for i in range(1, 11)]


def text(lines: list[str]) -> str:
    return "".join(f"{line}\n" for line in lines)


class FindTest(unittest.TestCase):
    def test_a_path_under_gcn_recomp_with_a_range(self):
        self.assertEqual(fork_cites.find("see `gcn-recomp/runtime/main.cpp:404-407` here\n", True),
                         [Cite(1, "gcn-recomp/runtime/main.cpp", 404, 407)])

    def test_a_fork_relative_path_and_a_bare_name(self):
        self.assertEqual(fork_cites.find("x\n(`runtime/hw/drive.h:64`) and ax.cpp:12.\n", True),
                         [Cite(2, "runtime/hw/drive.h", 64, 64), Cite(2, "ax.cpp", 12, 12)])

    def test_a_colon_continuation_takes_the_file_before_it(self):
        self.assertEqual(fork_cites.find("`ax.cpp:42`, `:53-60`, `:504`\n", True),
                         [Cite(1, "ax.cpp", 42, 42), Cite(1, "ax.cpp", 53, 60),
                          Cite(1, "ax.cpp", 504, 504)])

    def test_a_continuation_follows_the_nearest_cite(self):
        self.assertEqual(fork_cites.find("`ax.cpp:1`, `xf.cpp:2`, `:3`\n", True),
                         [Cite(1, "ax.cpp", 1, 1), Cite(1, "xf.cpp", 2, 2), Cite(1, "xf.cpp", 3, 3)])

    def test_a_continuation_never_crosses_a_line(self):
        self.assertEqual(fork_cites.find("`ax.cpp:1`\n`:3`\n", True), [Cite(1, "ax.cpp", 1, 1)])

    def test_a_comma_list_after_a_cite(self):
        self.assertEqual(fork_cites.find("after (render_gl_batch.cpp:180, 522-523), so\n", False),
                         [Cite(1, "render_gl_batch.cpp", 180, 180),
                          Cite(1, "render_gl_batch.cpp", 522, 523)])

    def test_a_comma_and_a_count_are_not_a_list(self):
        self.assertEqual(fork_cites.find("ax.cpp:42, 3 voices\n", False), [Cite(1, "ax.cpp", 42, 42)])

    def test_a_compiler_diagnostic_with_a_column_is_not_a_cite(self):
        self.assertEqual(fork_cites.find("runtime/gx/view.cpp:286:13: warning\n", False), [])

    def test_times_ratios_and_bare_colons_are_not_cites(self):
        self.assertEqual(fork_cites.find("at 16:01:02, in 16:9, x :3 and dragoon[5150:20a1]\n", True), [])

    def test_markdown_skips_fenced_blocks_and_other_files_do_not(self):
        doc = "`ax.cpp:1`\n```\nCMake Error at gcn-recomp/CMakeLists.txt:472 (message):\n```\n" \
              "~~~\nax.cpp:5\n~~~\n`ax.cpp:9`\n"
        self.assertEqual(fork_cites.find(doc, True), [Cite(1, "ax.cpp", 1, 1), Cite(8, "ax.cpp", 9, 9)])
        self.assertEqual([c.line for c in fork_cites.find(doc, False)], [1, 3, 6, 8])


class ForkCitesTest(unittest.TestCase):
    def setUp(self):
        self.dir = temp_dir(self, prefix="fork cites ")
        patch = mock.patch.dict(os.environ, GIT_ENV)
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = self.dir / "Dragoon repo"
        self.fork = self.repo / "gcn-recomp"

    def bump(self, old: dict[str, str], new: dict[str, str], removed: tuple[str, ...] = (),
             docs: dict[str, str] | None = None) -> tuple[int, str, str]:
        """Commit OLD to the fork, then NEW with REMOVED gone, commit DOCS to Dragoon pinning
        the second and run the tool on the two."""
        self.old = commit(self.fork, {"README": "one\n", **old})
        for path in removed:
            git(self.fork, "rm", "-q", "--", path)
        self.new = commit(self.fork, {"README": "two\n", **new})
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "update-index", "--add", "--cacheinfo", f"160000,{self.new},gcn-recomp")
        commit(self.repo, docs or {})
        return self.run_tool()

    def run_tool(self, *extra: str) -> tuple[int, str, str]:
        return run_main(fork_cites.main, self.old, self.new, "--repo", str(self.repo), *extra)

    def report(self, out: str) -> list[str]:
        """OUT's lines but the total."""
        return out.splitlines()[:-1]

    def test_lines_that_stay_put_are_ok(self):
        code, out, err = self.bump({"runtime/main.cpp": text(TEN)},
                                   {"runtime/main.cpp": text(TEN + ["line 11"])},
                                   docs={"docs/a doc.md": "`gcn-recomp/runtime/main.cpp:3-5`\n"})
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, "ok docs/a doc.md:1 runtime/main.cpp:3-5\n"
                              "total 1, ok 1, moved 0, gone 0, outside 0, unchanged 0\n")

    def test_lines_pushed_down_are_moved_to_where_they_went(self):
        code, out, _ = self.bump({"runtime/main.cpp": text(TEN)},
                                 {"runtime/main.cpp": text(["new 1", "new 2"] + TEN)},
                                 docs={"docs/a.md": "x\n`gcn-recomp/runtime/main.cpp:3-5`, `:8`\n"})
        self.assertEqual(code, 1)
        self.assertEqual(out, "moved docs/a.md:2 runtime/main.cpp:3-5 now 5-7\n"
                              "moved docs/a.md:2 runtime/main.cpp:8 now 10\n"
                              "total 2, ok 0, moved 2, gone 0, outside 0, unchanged 0\n")

    def test_lines_whose_text_changed_are_gone(self):
        new = TEN[:3] + ["line four"] + TEN[4:]
        code, out, _ = self.bump({"runtime/main.cpp": text(TEN)}, {"runtime/main.cpp": text(new)},
                                 docs={"docs/a.md": "`runtime/main.cpp:3-5` and `:9`\n"})
        self.assertEqual(code, 1)
        self.assertEqual(self.report(out), ["gone docs/a.md:1 runtime/main.cpp:3-5",
                                            "ok docs/a.md:1 runtime/main.cpp:9"])

    def test_text_found_in_several_places_names_each(self):
        new = ["new"] + TEN + ["line 3", "line 4"]
        code, out, _ = self.bump({"runtime/main.cpp": text(TEN)}, {"runtime/main.cpp": text(new)},
                                 docs={"docs/a.md": "`main.cpp:3-4`\n"})
        self.assertEqual(code, 1)
        self.assertEqual(self.report(out), ["moved docs/a.md:1 runtime/main.cpp:3-4 now 4-5, 12-13"])

    def test_lines_that_stay_put_are_ok_even_when_found_again_elsewhere(self):
        code, out, _ = self.bump({"runtime/main.cpp": text(TEN)},
                                 {"runtime/main.cpp": text(TEN + ["line 3"])},
                                 docs={"docs/a.md": "`main.cpp:3`\n"})
        self.assertEqual((code, self.report(out)), (0, ["ok docs/a.md:1 runtime/main.cpp:3"]))

    def test_reindented_lines_are_ok(self):
        new = TEN[:3] + ["    line 4\t"] + TEN[4:]
        code, out, _ = self.bump({"runtime/main.cpp": text(TEN)}, {"runtime/main.cpp": text(new)},
                                 docs={"docs/a.md": "`main.cpp:3-5`\n"})
        self.assertEqual((code, self.report(out)), (0, ["ok docs/a.md:1 runtime/main.cpp:3-5"]))

    def test_a_file_removed_at_new_is_gone(self):
        code, out, _ = self.bump({"runtime/old.cpp": text(TEN)}, {}, removed=("runtime/old.cpp",),
                                 docs={"docs/a.md": "`gcn-recomp/runtime/old.cpp:2`\n"})
        self.assertEqual((code, self.report(out)), (1, ["gone docs/a.md:1 runtime/old.cpp:2"]))

    def test_a_cite_past_the_end_at_old_is_outside_even_in_an_unchanged_file(self):
        code, out, _ = self.bump({"runtime/same.cpp": text(TEN)}, {},
                                 docs={"docs/a.md": "`runtime/same.cpp:10-11`, `:0`\n"})
        self.assertEqual(code, 1)
        self.assertEqual(out, "outside docs/a.md:1 runtime/same.cpp:10-11, OLD has 10 lines\n"
                              "outside docs/a.md:1 runtime/same.cpp:0, OLD has 10 lines\n"
                              "total 2, ok 0, moved 0, gone 0, outside 2, unchanged 0\n")

    def test_a_range_that_runs_backwards_is_outside(self):
        code, out, _ = self.bump({"runtime/same.cpp": text(TEN)}, {},
                                 docs={"docs/a.md": "`runtime/same.cpp:5-3`\n"})
        self.assertEqual((code, self.report(out)),
                         (1, ["outside docs/a.md:1 runtime/same.cpp:5-3, OLD has 10 lines"]))

    def test_a_gcn_recomp_path_old_lacks_is_outside(self):
        code, out, _ = self.bump({}, {"runtime/added.cpp": text(TEN)},
                                 docs={"docs/a.md": "`gcn-recomp/runtime/added.cpp:2`\n"
                                                    "`gcn-recomp/runtime/nowhere.cpp:2`\n"})
        self.assertEqual(code, 1)
        self.assertEqual(self.report(out), [
            "outside docs/a.md:1 runtime/added.cpp:2, not at OLD",
            "outside docs/a.md:2 runtime/nowhere.cpp:2, not at OLD"])

    def test_cites_in_unchanged_files_are_counted_and_not_listed(self):
        code, out, _ = self.bump({"runtime/same.cpp": text(TEN), "runtime/main.cpp": text(TEN)},
                                 {"runtime/main.cpp": text(TEN + ["x"])},
                                 docs={"docs/a.md": "`same.cpp:2` `main.cpp:2`\n"})
        self.assertEqual(code, 0)
        self.assertEqual(out, "ok docs/a.md:1 runtime/main.cpp:2\n"
                              "total 2, ok 1, moved 0, gone 0, outside 0, unchanged 1\n")

    def test_a_bare_name_dragoon_also_has_needs_the_gcn_recomp_prefix(self):
        code, out, _ = self.bump({"CMakeLists.txt": text(TEN)}, {"CMakeLists.txt": text(["x"] + TEN)},
                                 docs={"CMakeLists.txt": "project(dragoon)\n",
                                       "docs/a.md": "`CMakeLists.txt:2` `gcn-recomp/CMakeLists.txt:2`\n"})
        self.assertEqual((code, self.report(out)), (1, ["moved docs/a.md:1 CMakeLists.txt:2 now 3"]))

    def test_a_relative_path_dragoon_has_is_dragoons_and_so_is_its_continuation(self):
        code, out, _ = self.bump({"tools/ci.py": text(TEN)}, {"tools/ci.py": text(["x"] + TEN)},
                                 docs={"tools/ci.py": "pass\n", "docs/a.md": "`tools/ci.py:2`, `:3`\n"})
        self.assertEqual(code, 0)
        self.assertEqual(out, "total 0, ok 0, moved 0, gone 0, outside 0, unchanged 0\n")

    def test_a_bare_name_two_fork_files_share_is_warned_about_and_skipped(self):
        code, out, err = self.bump({"runtime/a/twin.cpp": text(TEN), "runtime/b/twin.cpp": text(TEN)},
                                   {"runtime/a/twin.cpp": text(["x"] + TEN)},
                                   docs={"docs/a.md": "x\n`twin.cpp:2` and `a/twin.cpp:2`\n"})
        self.assertEqual(code, 1)
        self.assertEqual(self.report(out), ["moved docs/a.md:2 runtime/a/twin.cpp:2 now 3"])
        self.assertEqual(err, "fork_cites.py: docs/a.md:2: twin.cpp names 2 fork files "
                              "(runtime/a/twin.cpp, runtime/b/twin.cpp), so it isn't checked\n")

    def test_its_own_two_files_are_left_out(self):
        own = {name: (fork_cites.ROOT / name).read_text() for name in fork_cites.OWN}
        paths = {c.path[len(fork_cites.PREFIX):] if c.path.startswith(fork_cites.PREFIX) else c.path
                 for body in own.values() for c in fork_cites.find(body, False)}
        fork = {path for path in paths if "/" in path}
        fork |= {"runtime/" + name for name in paths - fork
                 if not any(f.endswith("/" + name) for f in fork)}
        code, out, err = self.bump({path: text(TEN) for path in fork}, {},
                                   docs={**own, "docs/a.md": "`main.cpp:2`\n"})
        self.assertGreater(len(fork), 5)
        self.assertEqual((code, out, err),
                         (0, "total 1, ok 0, moved 0, gone 0, outside 0, unchanged 1\n", ""))

    def test_a_name_the_fork_lacks_is_not_a_fork_cite(self):
        code, out, err = self.bump({"runtime/main.cpp": text(TEN)}, {},
                                   docs={"tools/t.py": "'guest panic: foo.c:12: boom'\n"})
        self.assertEqual((code, out, err), (0, "total 0, ok 0, moved 0, gone 0, outside 0, unchanged 0\n", ""))

    def test_a_file_added_at_new_resolves_a_bare_name(self):
        code, out, _ = self.bump({}, {"runtime/added.cpp": text(TEN)}, docs={"docs/a.md": "`added.cpp:2`\n"})
        self.assertEqual((code, self.report(out)), (1, ["outside docs/a.md:1 runtime/added.cpp:2, not at OLD"]))

    def test_reads_the_working_tree_of_tracked_files_and_nothing_untracked(self):
        self.bump({"runtime/main.cpp": text(TEN)}, {"runtime/main.cpp": text(["x"] + TEN)},
                  docs={"docs/a.md": "`main.cpp:2`\n"})
        write_file(self.repo / "docs", "a.md", "`main.cpp:1`\n")
        write_file(self.repo / "docs", "untracked.md", "`main.cpp:5`\n")
        code, out, _ = self.run_tool()
        self.assertEqual((code, self.report(out)), (1, ["moved docs/a.md:1 runtime/main.cpp:1 now 2"]))

    def test_at_reads_a_dragoon_commit_and_not_the_working_tree(self):
        self.bump({"runtime/main.cpp": text(TEN)}, {"runtime/main.cpp": text(["x"] + TEN)},
                  docs={"docs/a.md": "`main.cpp:2`\n", "a link.md": "`main.cpp:4`\n"})
        before = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "a link.md").unlink()
        os.symlink("docs/a.md", self.repo / "a link.md")
        git(self.repo, "add", "a link.md")
        commit(self.repo, {"docs/a.md": "`main.cpp:3`\n", "docs/b.md": "`main.cpp:5`\n"})
        write_file(self.repo / "docs", "a.md", "`main.cpp:1`\n")
        code, out, _ = self.run_tool("--at", before)
        self.assertEqual((code, self.report(out)), (1, ["moved a link.md:1 runtime/main.cpp:4 now 5",
                                                        "moved docs/a.md:1 runtime/main.cpp:2 now 3"]))
        code, out, _ = self.run_tool("--at", "HEAD")
        self.assertEqual(self.report(out), ["moved docs/a.md:1 runtime/main.cpp:3 now 4",
                                            "moved docs/b.md:1 runtime/main.cpp:5 now 6"])

    def test_at_a_commit_dragoon_lacks_exits_2(self):
        self.bump({"runtime/main.cpp": text(TEN)}, {}, docs={"docs/a.md": "`main.cpp:2`\n"})
        code, out, err = self.run_tool("--at", "e" * 40)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("e" * 40, err)

    def test_lists_by_file_then_line(self):
        code, out, _ = self.bump({"runtime/main.cpp": text(TEN)}, {"runtime/main.cpp": text(TEN + ["x"])},
                                 docs={"z.md": "`main.cpp:1`\n", "a.md": "x\n`main.cpp:3` `main.cpp:2`\n",
                                       "a.py": "# main.cpp:4\n"})
        self.assertEqual(self.report(out), ["ok a.md:2 runtime/main.cpp:3", "ok a.md:2 runtime/main.cpp:2",
                                            "ok a.py:1 runtime/main.cpp:4", "ok z.md:1 runtime/main.cpp:1"])

    def test_a_binary_file_is_skipped(self):
        code, out, _ = self.bump({"runtime/main.cpp": text(TEN)}, {"runtime/main.cpp": text(["x"] + TEN)},
                                 docs={"docs/a.md": "`main.cpp:2`\n"})
        write_file(self.repo, "blob.bin", b"\0main.cpp:3\n")
        git(self.repo, "add", "blob.bin")
        code, out, _ = self.run_tool()
        self.assertEqual(self.report(out), ["moved docs/a.md:1 runtime/main.cpp:2 now 3"])

    def test_a_commit_the_fork_lacks_exits_2(self):
        self.bump({"runtime/main.cpp": text(TEN)}, {}, docs={"docs/a.md": "`main.cpp:2`\n"})
        code, out, err = run_main(fork_cites.main, self.old, "f" * 40, "--repo", str(self.repo))
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith("fork_cites.py: ") and err.count("\n") == 1, err)
        self.assertIn("f" * 40, err)

    def test_a_repo_with_no_gcn_recomp_checkout_exits_2(self):
        commit(self.repo, {"docs/a.md": "`main.cpp:2`\n"})
        code, out, err = run_main(fork_cites.main, "HEAD", "HEAD", "--repo", str(self.repo))
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, f"fork_cites.py: {self.fork.resolve()} isn't a git checkout\n")
        self.fork.mkdir()
        code, out, err = run_main(fork_cites.main, "HEAD", "HEAD", "--repo", str(self.repo))
        self.assertEqual((code, err), (2, f"fork_cites.py: {self.fork.resolve()} isn't a git checkout\n"))

    def test_help_exits_0_and_names_the_forms(self):
        code, out, _ = run_main(fork_cites.main, "--help")
        self.assertEqual(code, 0)
        self.assertIn("usage: fork_cites.py OLD NEW", out)
        self.assertIn("continuation", out)


if __name__ == "__main__":
    unittest.main()
