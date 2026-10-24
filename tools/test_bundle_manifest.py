import posixpath
import unittest
from pathlib import Path

import bundle_manifest

REAL = Path(__file__).resolve().parents[1] / "launcher" / "bundle-manifest.txt"
GOOD = """# What the app may hold
source Contents/Resources/source

budget app 20000
budget dmg 40000   # the download
file Contents/Info.plist
dir Contents/Resources/licenses
macho Contents/MacOS/Dragoon
engine Contents/Resources/kit/engine.o
object Contents/Resources/kit/libSDL3.a
link Contents/Resources/cmake/bin/cmake ../../../MacOS/cmake
"""


class ParseTest(unittest.TestCase):
    def test_reads_every_directive(self):
        m = bundle_manifest.parse(GOOD)
        self.assertEqual(m.source, "Contents/Resources/source")
        self.assertEqual(m.budgets, {"app": 20000, "dmg": 40000})
        self.assertEqual(m.files, frozenset({"Contents/Info.plist"}))
        self.assertEqual(m.dirs, ("Contents/Resources/licenses/",))
        self.assertEqual(m.machos, frozenset({"Contents/MacOS/Dragoon"}))
        self.assertEqual(m.objects, frozenset({"Contents/Resources/kit/engine.o",
                                               "Contents/Resources/kit/libSDL3.a"}))
        self.assertEqual(m.engine, "Contents/Resources/kit/engine.o")
        self.assertEqual(m.links, {"Contents/Resources/cmake/bin/cmake": "../../../MacOS/cmake"})

    def test_a_file_is_allowed_by_name_or_by_prefix(self):
        m = bundle_manifest.parse(GOOD)
        for path in ("Contents/Info.plist", "Contents/MacOS/Dragoon", "Contents/Resources/kit/engine.o",
                     "Contents/Resources/kit/libSDL3.a",
                     "Contents/Resources/licenses/CMake.txt",
                     "Contents/Resources/licenses/deeper/Ninja.txt"):
            with self.subTest(path=path):
                self.assertTrue(m.allows_file(path))
        for path in ("Contents/Resources/dragoon", "Contents/Info.plist.bak",
                     "Contents/Resources/licenses2/x", "Contents/Resources/licenses",
                     "Contents/Resources/cmake/bin/cmake"):
            with self.subTest(path=path):
                self.assertFalse(m.allows_file(path))

    def test_a_directory_is_under_a_prefix_or_not(self):
        m = bundle_manifest.parse(GOOD)
        self.assertTrue(m.under_dir("Contents/Resources/licenses/"))
        self.assertTrue(m.under_dir("Contents/Resources/licenses/deeper/"))
        self.assertFalse(m.under_dir("Contents/Resources/"))

    def test_refuses_what_it_cannot_read(self):
        bad = {
            "an unknown directive": GOOD + "folder Contents/x\n",
            "no source": GOOD.replace("source Contents/Resources/source\n", ""),
            "two sources": GOOD + "source Contents/other\n",
            "no dmg budget": GOOD.replace("budget dmg 40000", ""),
            "a third budget": GOOD + "budget disc 5\n",
            "a budget that isn't a number": GOOD.replace("20000", "big"),
            "a budget of zero": GOOD.replace("20000", "0"),
            "a path listed twice": GOOD + "file Contents/Info.plist\n",
            "a path in two lists": GOOD + "macho Contents/Info.plist\n",
            "an absolute path": GOOD + "file /Contents/x\n",
            "a path with ..": GOOD + "file Contents/../x\n",
            "a path with a double slash": GOOD + "file Contents//x\n",
            "a file with a trailing slash": GOOD + "file Contents/x/\n",
            "a link with no target": GOOD + "link Contents/x\n",
            "a link to an absolute target": GOOD + "link Contents/x /usr/bin/cmake\n",
            "an extra word": GOOD + "file Contents/x Contents/y\n",
            "a bare directive": GOOD + "file\n",
            "two engines": GOOD + "engine Contents/Resources/kit/other.o\n",
            "an engine that's also an object": GOOD + "object Contents/Resources/kit/engine.o\n",
            "an object not named .a or .o": GOOD + "object Contents/Resources/kit/libSDL3.dylib\n",
            "an engine not named .a or .o": GOOD.replace("kit/engine.o", "kit/engine"),
            "an engine named .a": GOOD.replace("kit/engine.o", "kit/engine.a"),
        }
        for why, text in bad.items():
            with self.subTest(why):
                with self.assertRaises(ValueError):
                    bundle_manifest.parse(text)

    def test_the_error_names_the_line(self):
        with self.assertRaisesRegex(ValueError, "line 3"):
            bundle_manifest.parse("source a\nbudget app 1\nfolder b\nbudget dmg 1\n")


class RealManifestTest(unittest.TestCase):
    def setUp(self):
        self.m = bundle_manifest.read(REAL)

    def test_the_download_budget_is_60_mb(self):
        self.assertEqual(self.m.budgets["dmg"], 60_000_000)

    def test_follows_the_dev_apps_layout(self):
        self.assertEqual(self.m.source, "Contents/Resources/source")
        self.assertTrue({"Contents/MacOS/Dragoon", "Contents/MacOS/cmake",
                         "Contents/MacOS/ninja"} <= self.m.machos)
        self.assertEqual(self.m.links["Contents/Resources/cmake/bin/cmake"], "../../../MacOS/cmake")
        self.assertIn("Contents/Resources/third_party/SDL3-3.4.18.tar.gz", self.m.files)
        for prefix in ("Contents/Resources/cmake/share/cmake-4.4/", "Contents/Resources/licenses/",
                       "Contents/Frameworks/Sparkle.framework/"):
            self.assertIn(prefix, self.m.dirs)

    def test_the_cmake_link_lands_on_the_bundles_cmake(self):
        link = "Contents/Resources/cmake/bin/cmake"
        landing = posixpath.normpath(posixpath.join(posixpath.dirname(link), self.m.links[link]))
        self.assertEqual(landing, "Contents/MacOS/cmake")
        self.assertIn(landing, self.m.machos)

    def test_every_link_stays_inside_contents(self):
        for link, target in self.m.links.items():
            with self.subTest(link=link):
                landing = posixpath.normpath(posixpath.join(posixpath.dirname(link), target))
                self.assertTrue(landing.startswith("Contents/"), landing)

    def test_sparkles_xpc_services_are_not_allowed(self):
        self.assertFalse(any("XPCServices" in p or ".xpc" in p
                             for p in self.m.machos | self.m.files | set(self.m.links)))

    def test_nothing_listed_is_inside_the_snapshot(self):
        inside = self.m.source + "/"
        listed = self.m.files | self.m.machos | self.m.objects | set(self.m.links) | set(self.m.dirs)
        self.assertEqual([p for p in listed if p.startswith(inside)], [])

    def test_the_kits_engine_is_the_one_object_that_may_hold_the_disc_id(self):
        self.assertEqual(self.m.engine, "Contents/Resources/kit/engine.o")
        self.assertEqual(self.m.objects, {self.m.engine, "Contents/Resources/kit/libSDL3.a"})


if __name__ == "__main__":
    unittest.main()
