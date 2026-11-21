from __future__ import annotations

import re
import time
import unittest

import quality_page
from testutil import git, run_main, temp_dir

PIN = "def5678" + "0" * 33
SCORED = "abc1234"
HEAD = "# Scored on gcn-recomp {}, which is a fake.\ntolerance=4 budget=0.1%\n"
LINE = "{route} {frame} share=0.000% max=0 mean=0.00 state=same {cls} {why}"
TRIAGE_LINES = [
    LINE.format(route="top-ride-grass", frame=60, cls="within", why="the card"),
    LINE.format(route="top-ride-grass", frame=304, cls="within", why="the opening"),
    LINE.format(route="top-ride-grass", frame=950, cls="within", why="the title"),
    LINE.format(route="top-ride-grass", frame=1003, cls="within", why="the main menu"),
    LINE.format(route="top-ride-grass", frame=1399, cls="timing", why="DOWN keeps the mode select"),
    LINE.format(route="top-ride-grass", frame=1704, cls="unclear", why="the mode's movie"),
    LINE.format(route="top-ride-grass", frame=3600, cls="unclear",
                why="every compared value matches through pass 564"),
    LINE.format(route="air-ride-race", frame=60, cls="within", why="the card"),
    "air-ride-race 4200 share=81.192% max=255 mean=23.90 state=differs bug player4.speed first "
    "differs at frame 3884, pass 763, and later",
]
TRIAGE = HEAD.format(SCORED) + "\n".join(TRIAGE_LINES) + "\n"
MENU = "120:A:5,300:A:5,900:A:5,\n1000:START:5"
ROUTES = {
    "title": "# card, then 300 A past its message and 900 A skips the opening\n120:A:5,300:A:5,900:A:5\n",
    "menu": f"# title.txt, then 1000 START\n{MENU}\n",
    "top-ride-grass": f"{MENU},\n1300:DOWN:5,1400:A:5,3200:START:5\n",
    "air-ride-race": f"{MENU},\n1300:A:5,3100:START:5\n",
}
MANIFEST = """# route seconds dump_every required_frames
title          20 60 60,960
air-ride-race  30 60 4200
city-trial-4p  30 60 2700 --pads=4
top-ride-grass 30 60 3600
"""
GOLDENS = {
    "gl/title.txt": "frame_00060 a\nframe_00120 b\nframe_00180 c\n",
    "gl-16x9/title.txt": "frame_00060 d\nframe_00120 e\nframe_00180 f\n",
    "state/title.txt": "# a comment\nframe 60 read 60 scene.major=18\nframe 960 read 960 scene.major=2\n",
    "audio/title.txt": "# a comment\n7200 15F5\n20000 2C06\n",
    "audio/air-ride-race.txt": "12000 AB\n",
    "gl/city-trial-4p.txt": "frame_00060 g\nframe_00120 h\n",
}
KNOWN = "# a comment\nstate city-trial-4p 16:9 2700 player1.speed=1 plays differently\n"


def status_md(features: list) -> str:
    rows = "".join(f"| {f} | Works | a note |\n" for f in features)
    return ("# Status\n\nWhat's true.\n\n| Feature | Status | Note |\n|---|---|---|\n" + rows +
            "\n## Later\n\n| Feature | Status |\n|---|---|\n| Not a feature | Works |\n")


class Tree:
    """A fake checkout: status.md naming every COVERS feature, a manifest, route files, a triage
    file, a few goldens, a known issue and a git index pinning gcn-recomp at PIN."""

    def __init__(self, test: unittest.TestCase, triage: str = TRIAGE,
                 features: list | None = None) -> None:
        self.root = temp_dir(test, prefix="quality page ")
        self.write("docs/dev/status.md", status_md(list(quality_page.COVERS) if features is None
                                                   else features))
        self.write("tests/hashes/manifest.txt", MANIFEST)
        self.write("tests/hashes/dolphin-triage.txt", triage)
        self.write("tests/hashes/known-issues.txt", KNOWN)
        for name, text in GOLDENS.items():
            self.write(f"tests/hashes/{name}", text)
        for name, text in ROUTES.items():
            self.write(f"tests/routes/{name}.txt", text)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{PIN},gcn-recomp")

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def main(self, *args: str) -> tuple[int, str, str]:
        return run_main(quality_page.main, "--root", str(self.root), *args)

    def page(self) -> str:
        return (self.root / quality_page.PAGE).read_text()

    def rows(self) -> dict:
        """The page's table, by feature: (checked, status, numbers, measured, files)."""
        out = {}
        for line in self.page().splitlines():
            cells = [c.strip() for c in line.strip("|").split("|")]
            if line.startswith("| ") and len(cells) == 6 and cells[0] in quality_page.COVERS:
                out[cells[0]] = tuple(cells[1:])
        return out


GOLDENS_OF_TITLE = ("Goldens of 1 route: 3 frames at 4:3, 3 frames at 16:9, 2 state checkpoints "
                    "and 2 audio rows.")


class PageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = Tree(self)
        self.assertEqual(self.tree.main(), (0, "wrote docs/dev/quality.md\n", ""))
        self.rows = self.tree.rows()

    def test_every_feature_has_a_row_in_status_order(self) -> None:
        self.assertEqual(list(self.rows), list(quality_page.COVERS))

    def test_marks_come_from_the_evidence(self) -> None:
        marks = {f: r[0] for f, r in self.rows.items()}
        self.assertEqual({f: m for f, m in marks.items() if m != "Unchecked"}, {
            "Boot and memory card": "Dolphin", "Opening movie": "Dolphin", "Title screen": "Dolphin",
            "Mode select": "Dolphin", "Top Ride": "Dolphin", "Air Ride race": "Dolphin",
            "City Trial": "Goldens", "Audio": "Goldens", "Controllers": "Goldens",
            "Picture": "Goldens"})

    def test_dolphin_beats_goldens_and_shared_frames_count_once(self) -> None:
        """The card prompt has the title route's goldens and a Dolphin checkpoint on each route."""
        mark, _, numbers, measured, files = self.rows["Boot and memory card"]
        self.assertEqual(mark, "Dolphin")
        self.assertEqual(numbers, "Frame 60 on each of air-ride-race and top-ride-grass, which play "
                         "the same presses up to those frames: 1 `within` on each. " + GOLDENS_OF_TITLE)
        self.assertEqual(measured, f"Dolphin on gcn-recomp `{SCORED}`, the goldens held to the pin "
                         "`def5678`")
        self.assertTrue(files.startswith("[dolphin-triage.txt](../../tests/hashes/dolphin-triage.txt), "
                                         "[gl/](../../tests/hashes/gl/)"), files)

    def test_each_scene_from_the_presses(self) -> None:
        self.assertEqual(self.rows["Opening movie"][2], "Frame 304 on top-ride-grass: 1 `within`. "
                         + GOLDENS_OF_TITLE)
        self.assertEqual(self.rows["Title screen"][2], "Frame 950 on top-ride-grass: 1 `within`. "
                         + GOLDENS_OF_TITLE)
        self.assertEqual(self.rows["Mode select"][2], "Frames 1003 and 1399 on top-ride-grass: 1 "
                         "`within` and 1 `timing` at 1399.")

    def test_a_mode_splits_at_its_last_start(self) -> None:
        self.assertEqual(self.rows["Top Ride"][2:4], (
            "Before START at 3200, frame 1704 on top-ride-grass: 1 `unclear` at 1704. From START at "
            "3200, frame 3600 on top-ride-grass: 1 `unclear` at 3600. On top-ride-grass the race "
            "matches Dolphin's through pass 564.", f"Dolphin on gcn-recomp `{SCORED}`"))

    def test_a_race_bug_gives_its_first_difference(self) -> None:
        self.assertEqual(self.rows["Air Ride race"][2], "From START at 3100, frame 4200 on "
                         "air-ride-race: 1 `bug` at 4200. On air-ride-race the race first differs "
                         "from Dolphin's at pass 763. Goldens of 1 route: 1 audio row.")

    def test_goldens_count_only_the_routes_and_kinds_a_feature_covers(self) -> None:
        self.assertEqual(self.rows["Audio"][2:4], (
            "Goldens of 2 routes: 3 audio rows. The click and clipping counts, scored with nobody "
            "listening, are in the audio scorecard.", "Held to the pin, gcn-recomp `def5678`"))
        self.assertIn("[scorecard.md](scorecard.md)", self.rows["Audio"][4])
        self.assertEqual(self.rows["Picture"][2], "Goldens of 1 route: 3 frames at 16:9.")
        self.assertEqual(self.rows["Picture"][4], "[gl-16x9/](../../tests/hashes/gl-16x9/)")

    def test_state_goldens_count_checkpoints_not_comments(self) -> None:
        self.tree.write("tests/hashes/state/title.txt", GOLDENS["state/title.txt"] + "# more\n\n")
        self.tree.main()
        self.assertIn("2 state checkpoints", self.tree.rows()["Title screen"][2])

    def test_controllers_take_the_routes_with_more_pads_and_their_known_issues(self) -> None:
        _, _, numbers, _, files = self.rows["Controllers"]
        self.assertTrue(numbers.startswith("Goldens of 1 route: 2 frames at 4:3. 1 state check "
                                           "expected to fail as a known issue."), numbers)
        self.assertIn("[known-issues.txt](../../tests/hashes/known-issues.txt)", files)
        self.assertEqual(self.rows["City Trial"][0], "Goldens")

    def test_unchecked_says_status_md_is_the_only_source(self) -> None:
        self.assertEqual(self.rows["Idle loop"], (
            "Unchecked", "Works", "No golden or Dolphin compare covers it. status.md is the only "
            "source.", "Not measured here", "[status.md](status.md)"))
        self.assertEqual(self.rows["Speed"][2], "No golden or Dolphin compare covers it. "
                         + quality_page.COVERS["Speed"].note)

    def test_summary(self) -> None:
        self.assertIn(f"Of {len(quality_page.COVERS)} features, 6 are checked against Dolphin, 4 "
                      f"against our goldens only and {len(quality_page.COVERS) - 10} are unchecked. "
                      "The Dolphin compare has 9 checkpoints on 2 routes, 5 `within`, 1 `timing`, "
                      "2 `unclear` and 1 `bug`.", " ".join(self.tree.page().split()))

    def test_prose_is_wrapped(self) -> None:
        prose = [ln for ln in self.tree.page().splitlines() if not ln.startswith("|")]
        self.assertLessEqual(max(map(len, prose)), quality_page.WIDTH)

    def test_a_triage_file_scored_on_the_pin(self) -> None:
        tree = Tree(self, triage=HEAD.format(PIN[:7]) + TRIAGE_LINES[0] + "\n")
        self.assertEqual(tree.main()[0], 0)
        self.assertEqual(tree.rows()["Boot and memory card"][3],
                         "Dolphin on gcn-recomp `def5678`, the goldens held to that pin")

    def test_a_triage_file_with_no_scored_commit(self) -> None:
        tree = Tree(self, triage=HEAD.split("\n", 1)[1] + TRIAGE_LINES[0] + "\n")
        self.assertEqual(tree.main()[0], 0)
        self.assertEqual(tree.rows()["Boot and memory card"][3],
                         "Dolphin on a commit the triage file's head doesn't name, the goldens "
                         "held to the pin `def5678`")


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = Tree(self)
        self.tree.main()
        self.written = self.tree.page()

    def assert_stale(self, word: str = "stale") -> None:
        self.assertEqual(self.tree.main("--check"),
                         (1, f"docs/dev/quality.md is {word}: run tools/quality_page.py\n", ""))

    def test_current(self) -> None:
        self.assertEqual(self.tree.main("--check"), (0, "docs/dev/quality.md is current\n", ""))
        self.assertEqual(self.tree.main(), (0, "docs/dev/quality.md is current\n", ""))

    def test_a_triage_change_makes_it_stale_and_check_writes_nothing(self) -> None:
        self.tree.write("tests/hashes/dolphin-triage.txt",
                        TRIAGE.replace("state=same unclear the mode's", "state=same within the mode's"))
        self.assert_stale()
        self.assertEqual(self.tree.page(), self.written)

    def test_a_new_golden_line_makes_it_stale(self) -> None:
        self.tree.write("tests/hashes/audio/title.txt", GOLDENS["audio/title.txt"] + "24000 FF\n")
        self.assert_stale()

    def test_a_moved_press_makes_it_stale(self) -> None:
        self.tree.write("tests/routes/top-ride-grass.txt", f"{MENU},\n1300:DOWN:5,1400:A:5,3700:START:5\n")
        self.assert_stale()

    def test_a_new_pin_makes_it_stale(self) -> None:
        git(self.tree.root, "update-index", "--cacheinfo", f"160000,{'9' * 40},gcn-recomp")
        self.assert_stale()

    def test_an_edit_by_hand_makes_it_stale(self) -> None:
        self.tree.write(quality_page.PAGE, self.written.replace("Unchecked", "Dolphin", 1))
        self.assert_stale()

    def test_a_missing_page(self) -> None:
        (self.tree.root / quality_page.PAGE).unlink()
        self.assert_stale("missing")


class RefusedTest(unittest.TestCase):
    def assert_refused(self, tree: Tree, why: str) -> None:
        code, out, err = tree.main("--check")
        self.assertEqual((code, out), (2, ""))
        self.assertIn(why, err)
        self.assertFalse((tree.root / quality_page.PAGE).exists())

    def test_a_feature_covers_lacks(self) -> None:
        self.assert_refused(Tree(self, features=[*quality_page.COVERS, "Netplay"]),
                            "only in status.md ['Netplay']")

    def test_a_feature_status_md_lost(self) -> None:
        self.assert_refused(Tree(self, features=list(quality_page.COVERS)[1:]),
                            "only in COVERS ['Boot and memory card']")

    def test_a_triaged_route_no_feature_covers(self) -> None:
        tree = Tree(self, triage=HEAD.format(SCORED) + LINE.format(route="kirby-race", frame=1400,
                                                                   cls="within", why="x") + "\n")
        tree.write("tests/routes/kirby-race.txt", f"{MENU},\n1300:A:5\n")
        self.assert_refused(tree, "kirby-race starts with the COVERS prefix of 0 features")

    def test_a_triaged_route_that_skips_menu_txt(self) -> None:
        tree = Tree(self)
        tree.write("tests/routes/air-ride-race.txt", "120:A:5,300:A:5,1000:START:5,1300:A:5\n")
        self.assert_refused(tree, "tests/routes/air-ride-race.txt doesn't start with menu.txt's presses")

    def test_a_triaged_route_with_no_route_file(self) -> None:
        tree = Tree(self)
        (tree.root / "tests/routes/air-ride-race.txt").unlink()
        self.assert_refused(tree, "tests/routes/air-ride-race.txt: No such file")

    def test_a_triage_line_that_doesnt_parse(self) -> None:
        self.assert_refused(Tree(self, triage=HEAD.format(SCORED) + "top-ride-grass 60 within\n"),
                            "line 3")

    def test_no_pin(self) -> None:
        tree = Tree(self)
        git(tree.root, "rm", "-q", "--cached", "gcn-recomp")
        self.assert_refused(tree, "git's index has no gcn-recomp pin")

    def test_no_status_md(self) -> None:
        tree = Tree(self)
        (tree.root / quality_page.STATUS).unlink()
        self.assert_refused(tree, "docs/dev/status.md: No such file")


class SceneTest(unittest.TestCase):
    """The scenes the real route files give city-trial, which picks its mode with A at 1500."""

    def test_boundaries(self) -> None:
        s = quality_page.scenes(quality_page.ROOT, "city-trial")
        frames = (0, 299, 300, 899, 900, 999, 1000, 1499, 1500)
        got = [quality_page.place(checkpoint_at(f), s).feature for f in frames]
        self.assertEqual(got, ["Boot and memory card"] * 2 + ["Opening movie"] * 2 +
                         ["Title screen"] * 2 + ["Mode select"] * 2 + ["City Trial"])

    def test_the_city_starts_at_its_last_start(self) -> None:
        s = quality_page.scenes(quality_page.ROOT, "city-trial")
        self.assertEqual([quality_page.place(checkpoint_at(f), s).part for f in (1500, 2699, 2700)],
                         ["before", "before", "play"])


def checkpoint_at(frame: int):
    return quality_page.dolphin_diff.Triage("city-trial", frame, 0.0, 0, 0.0, "same", "within", "x")


class RealTreeTest(unittest.TestCase):
    def test_the_committed_page_matches_the_tree(self) -> None:
        """Rebuilt with the pin the page names, so it holds in a copy with no .git too."""
        have = (quality_page.ROOT / quality_page.PAGE).read_text()
        pin = re.search(r"Held to the pin, gcn-recomp `([0-9a-f]+)`", have)
        self.assertIsNotNone(pin)
        self.assertEqual(quality_page.page(quality_page.ROOT, pin[1]), have)

    @unittest.skipUnless((quality_page.ROOT / ".git").exists(), "not a git checkout, so no pin to read")
    def test_check_passes_and_is_quick(self) -> None:
        began = time.monotonic()
        self.assertEqual(run_main(quality_page.main, "--check"),
                         (0, "docs/dev/quality.md is current\n", ""))
        self.assertLess(time.monotonic() - began, 1.0)


if __name__ == "__main__":
    unittest.main()
