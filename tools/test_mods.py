"""Checks for mods.py. Every mods folder, image and DOL is made here, so no disc is needed.

PrepareTest runs prepare against fake gcn-recomp tools that record their calls. RealToolsTest
runs it against the pinned gcn-recomp's own tools, and skips when gcn-recomp isn't checked out.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import clone_file
import mods
import tool_env
from testutil import run_main

ROOT = Path(__file__).resolve().parents[1]
FORK = ROOT / "gcn-recomp" / "recomp"
MODS_PY = Path(__file__).resolve().parent / "mods.py"
SHA = "0123456789abcdef0123456789abcdef01234567"  # a made-up DOL's SHA-1
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
DOL_TXT = f"# a comment\n\ndol {SHA}\n"


class ModsCase(unittest.TestCase):
    """A mods folder at a path with spaces, as Application Support has."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="mods test ")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.mods = self.tmp / "Application Support" / "Dragoon" / "mods"
        self.mods.mkdir(parents=True)
        self.made = 0

    def put(self, rel: str, data: bytes | str = b"x", root: Path | None = None) -> Path:
        path = (root or self.mods) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
        return path

    def make(self, tree: dict[str, bytes | str]) -> Path:
        """A new mods folder holding TREE, relative path to contents."""
        self.made += 1
        root = self.tmp / f"mods {self.made}"
        root.mkdir()
        for rel, data in tree.items():
            self.put(rel, data, root)
        return root

    def link(self, rel: str, target: Path) -> None:
        path = self.mods / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, path)

    def scan(self, root: Path | None = None) -> list[mods.Mod]:
        return mods.scan(root or self.mods, SHA)

    def refused(self, mod: str, path: str, why: str) -> None:
        with self.assertRaises(mods.ModError) as cm:
            self.scan()
        self.assertEqual((cm.exception.mod, cm.exception.path), (mod, path))
        self.assertRegex(cm.exception.why, why)

    def sparse(self, rel: str, size: int) -> None:
        path = self.put(rel)
        os.truncate(path, size)
        if os.stat(path).st_blocks * 512 > 1 << 24:
            self.skipTest("this file system has no sparse files")


class ScanTest(ModsCase):
    def test_a_missing_or_empty_folder_has_no_mods(self) -> None:
        self.assertEqual(mods.scan(self.tmp / "no mods here", SHA), [])
        self.assertEqual(self.scan(), [])

    def test_a_mod_maps_disc_paths_to_its_files(self) -> None:
        readme = self.put("Big Mod/files/Data/readme text.txt")
        added = self.put("Big Mod/files/new file.bin")
        (found,) = self.scan()
        self.assertEqual(found, mods.Mod("Big Mod", {"Data/readme text.txt": readme,
                                                    "new file.bin": added}))

    def test_mods_sort_by_folder_name_ignoring_case(self) -> None:
        for name in ("b mod", "C mod", "A mod"):
            (self.mods / name).mkdir()
        self.assertEqual([m.name for m in self.scan()], ["A mod", "b mod", "C mod"])

    def test_a_folder_with_neither_part_is_an_empty_mod(self) -> None:
        (self.mods / "Empty").mkdir()
        self.assertEqual(self.scan(), [mods.Mod("Empty", {})])

    def test_a_loose_file_in_the_mods_folder_isnt_a_mod(self) -> None:
        self.put("readme.txt")
        self.assertEqual(self.scan(), [])

    def test_dotfiles_and_dot_folders_are_skipped_everywhere(self) -> None:
        kept = self.put("Mod/files/a.bin")
        for rel in (".DS_Store", ".hidden mod/files/b.bin", "Mod/.DS_Store", "Mod/files/.DS_Store",
                    "Mod/files/.git/config", "Mod/files/Data/._a.bin", "Mod/.notes"):
            self.put(rel)
        self.link("Mod/files/.a link", self.tmp)
        self.put("Mod/dol.txt", DOL_TXT)
        (found,) = self.scan()
        self.assertEqual(found.files, {"a.bin": kept})
        self.assertEqual(found.beside, {})

    def test_dol_txt_and_every_file_beside_it(self) -> None:
        dol = self.put("Code Mod/dol.txt", DOL_TXT)
        hook = self.put("Code Mod/hook.bin")
        more = self.put("Code Mod/code/more.bin")
        added = self.put("Code Mod/files/a.bin")
        (found,) = self.scan()
        self.assertEqual(found, mods.Mod("Code Mod", {"a.bin": added}, dol,
                                         {"hook.bin": hook, "code/more.bin": more}))

    def test_files_and_dol_txt_may_come_in_any_letter_case(self) -> None:
        added = self.put("Big Mod/Files/a.bin")
        dol = self.put("Code Mod/DOL.txt", DOL_TXT)
        hook = self.put("Code Mod/hook.bin")
        big, code = self.scan()
        self.assertEqual(big, mods.Mod("Big Mod", {"a.bin": added}))
        self.assertEqual(code, mods.Mod("Code Mod", {}, dol, {"hook.bin": hook}))

    def test_files_beside_a_mod_without_dol_txt_are_left_alone(self) -> None:
        self.put("Mod/readme.txt")
        self.link("Mod/a link", self.tmp)
        (found,) = self.scan()
        self.assertEqual(found, mods.Mod("Mod", {}))

    def test_held_lists_every_file_by_its_path_in_the_mod(self) -> None:
        dol = self.put("Mod/dol.txt", DOL_TXT)
        hook = self.put("Mod/hook.bin")
        added = self.put("Mod/files/a.bin")
        (found,) = self.scan()
        self.assertEqual(found.held(), [("dol.txt", dol), ("files/a.bin", added),
                                        ("hook.bin", hook)])


class RefusalTest(ModsCase):
    def test_a_mod_folder_that_is_a_link(self) -> None:
        (self.tmp / "elsewhere").mkdir()
        self.link("Linked Mod", self.tmp / "elsewhere")
        self.refused("Linked Mod", "", "is a link")

    def test_a_link_inside_a_mod(self) -> None:
        for rel in ("files", "files/a.bin", "files/Data", "dol.txt", "hook.bin"):
            with self.subTest(rel=rel):
                self.mods = self.make({"Mod/files/b.bin": b"x", "Mod/dol.txt": DOL_TXT})
                if rel in ("files", "dol.txt"):
                    (self.mods / "Mod" / rel).rename(self.tmp / f"moved {self.made}")
                self.link(f"Mod/{rel}", self.tmp)
                self.refused("Mod", rel, "is a link")

    def test_something_that_isnt_a_file_or_a_folder(self) -> None:
        (self.mods / "Mod" / "files").mkdir(parents=True)
        os.mkfifo(self.mods / "Mod" / "files" / "a pipe")
        self.refused("Mod", "files/a pipe", "isn't a file or a folder")

    def test_a_files_that_isnt_a_folder(self) -> None:
        self.put("Mod/files")
        self.refused("Mod", "files", "isn't a folder")

    def test_two_spellings_of_files_or_dol_txt(self) -> None:
        # A volume that ignores case can't hold both, so the second spelling is in another folder.
        real = mods._entries
        for n, (one, two, put) in enumerate((("files", "Files", "Files/b.bin"),
                                             ("dol.txt", "DOL.TXT", "DOL.TXT"))):
            with self.subTest(two=two):
                self.mods = self.make({"Mod/files/a.bin": b"x", "Mod/dol.txt": DOL_TXT})
                other = self.tmp / f"other {n}"
                self.put(put, DOL_TXT, other)
                mod = self.mods / "Mod"

                def entries(folder: Path) -> list[os.DirEntry]:
                    got = real(folder)
                    if folder == mod:
                        got = sorted(got + [e for e in real(other) if e.name == two],
                                     key=lambda e: e.name)
                    return got

                with mock.patch.object(mods, "_entries", entries):
                    self.refused("Mod", one, f"same name as {two} ignoring case")

    def test_a_refusal_spells_files_and_dol_txt_as_the_mod_does(self) -> None:
        for rel, why in (("Files/main.dol", "whole DOL"), ("DOL.txt", "no dol line")):
            with self.subTest(rel=rel):
                self.mods = self.make({f"Mod/{rel}": "# not yet\n"})
                self.refused("Mod", rel, why)

    def test_a_dol_txt_that_isnt_a_file(self) -> None:
        (self.mods / "Mod" / "dol.txt").mkdir(parents=True)
        self.refused("Mod", "dol.txt", "isn't a file")

    def test_a_name_that_isnt_ascii(self) -> None:
        self.put("Mod/files/Données/a.bin")
        self.refused("Mod", "files/Données/a.bin",
                     "^has a name that isn't ASCII, and the disc's file table takes only ASCII names$")

    def test_a_name_with_a_control_character(self) -> None:
        self.put("Mod/files/a\tb.bin")
        self.refused("Mod", "files/a\tb.bin", "control character")

    def test_a_name_that_isnt_ascii_is_fine_outside_files(self) -> None:
        self.put("Modé/dol.txt", DOL_TXT)
        self.put("Modé/crochet é.bin")
        self.assertEqual(len(self.scan()), 1)

    def test_a_file_of_4_gib_or_more(self) -> None:
        self.sparse("Mod/files/big.bin", 1 << 32)
        self.refused("Mod", "files/big.bin", "4 GiB or more")

    def test_a_file_just_under_4_gib_is_fine(self) -> None:
        self.sparse("Mod/files/big.bin", (1 << 32) - 1)
        self.assertEqual(len(self.scan()), 1)

    def test_a_main_dol_at_the_top_of_files(self) -> None:
        self.put("Mod/files/Main.DOL")
        self.refused("Mod", "files/Main.DOL", "whole DOL")

    def test_a_main_dol_further_down_is_a_file_like_any_other(self) -> None:
        self.put("Mod/files/Data/main.dol")
        (found,) = self.scan()
        self.assertEqual(list(found.files), ["Data/main.dol"])

    def test_a_dol_line_for_another_dol(self) -> None:
        self.put("Mod/dol.txt", f"# for another version\ndol {OTHER.upper()}\n")
        self.refused("Mod", "dol.txt:2", f"SHA-1 {OTHER}, not this game's {SHA}")

    def test_a_dol_line_naming_something_that_isnt_a_sha1(self) -> None:
        for n, word in enumerate(("xyz", SHA[:-1] + "g", SHA + "0")):
            with self.subTest(word=word):
                self.mods = self.make({"Mod/dol.txt": f"dol {word}\n"})
                self.refused("Mod", "dol.txt:1", f"^names {word}, which isn't a SHA-1$")

    def test_the_game_dol_sha1_may_come_in_upper_case(self) -> None:
        self.put("Mod/dol.txt", f"dol {SHA.upper()}\n")
        self.assertEqual(len(mods.scan(self.mods, SHA.upper())), 1)

    def test_a_list_that_doesnt_start_with_dol(self) -> None:
        for text in (f"word 80003104 38600002 38600001\ndol {SHA}\n", f"dol {SHA} extra\n", "dol\n"):
            with self.subTest(text=text):
                self.mods = self.make({"Mod/dol.txt": text})
                self.refused("Mod", "dol.txt:1", "has to be the dol line")

    def test_a_list_with_no_dol_line(self) -> None:
        self.put("Mod/dol.txt", "# nothing yet\n\n")
        self.refused("Mod", "dol.txt", "has no dol line")

    def test_a_byte_order_mark_and_carriage_returns_are_fine(self) -> None:
        self.put("Mod/dol.txt", f"﻿dol {SHA}\r\nword 80003104 38600002 38600001\r\n")
        self.assertEqual(len(self.scan()), 1)

    def test_a_list_that_isnt_utf_8(self) -> None:
        self.put("Mod/dol.txt", f"dol {SHA}\n# \xff\n".encode("latin-1"))
        self.refused("Mod", "dol.txt", "isn't UTF-8")

    def test_a_list_of_more_than_a_mebibyte(self) -> None:
        self.put("Mod/dol.txt", f"dol {SHA}\n".ljust(mods.LIST_MAX + 1, "#"))
        self.refused("Mod", "dol.txt", "more than 1 MiB")
        self.put("Mod/dol.txt", f"dol {SHA}\n".ljust(mods.LIST_MAX, "#"))
        self.assertEqual(len(self.scan()), 1)

    def test_two_mods_with_one_disc_path_ignoring_case(self) -> None:
        self.put("A Mod/files/Data/Readme.txt")
        self.put("b mod/files/data/README.TXT")
        self.refused("b mod", "files/data/README.TXT",
                     "same disc file as A Mod/files/Data/Readme.txt")

    def test_two_mods_may_share_a_folder(self) -> None:
        self.put("A Mod/files/Data/a.bin")
        self.put("B Mod/files/data/b.bin")
        self.assertEqual(len(self.scan()), 2)

    def test_a_file_where_another_mod_needs_a_folder(self) -> None:
        self.put("A Mod/files/data")
        self.put("B Mod/files/Data/b.bin")
        self.refused("B Mod", "files/Data/b.bin",
                     "needs files/Data to be a folder, and A Mod/files/data is a file")

    @unittest.skipIf(os.geteuid() == 0, "root reads a folder whatever its mode")
    def test_a_folder_that_cant_be_read(self) -> None:
        self.put("Mod/files/Data/a.bin")
        locked = self.mods / "Mod" / "files" / "Data"
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        self.refused("Mod", "files/Data", "can't be read")

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def test_a_file_that_cant_be_read(self) -> None:
        for rel in ("files/Data/a.bin", "hook.bin"):
            with self.subTest(rel=rel):
                self.mods = self.make({"Mod/dol.txt": DOL_TXT, f"Mod/{rel}": b"x"})
                locked = self.mods / "Mod" / rel
                locked.chmod(0)
                self.addCleanup(locked.chmod, 0o644)
                self.refused("Mod", rel, "can't be read")

    def test_the_error_names_the_mod_and_the_path(self) -> None:
        self.put("Big Mod/files/main.dol")
        with self.assertRaises(mods.ModError) as cm:
            self.scan()
        self.assertTrue(str(cm.exception).startswith("Big Mod/files/main.dol: is a whole DOL"))
        self.assertEqual(str(mods.ModError("Big Mod", "", "is a link")), "Big Mod: is a link")


def record(path: str, data: bytes) -> bytes:
    return f"{path}\0{len(data)}\0{hashlib.sha256(data).hexdigest()}\n".encode()


class DigestTest(ModsCase):
    BASE = {"A Mod/files/a.bin": b"one", "A Mod/files/Data/b.bin": b"two",
            "B Mod/dol.txt": DOL_TXT, "B Mod/hook.bin": b"\x38\x60\x00\x03"}

    def digest(self, tree: dict[str, bytes | str]) -> str:
        return mods.digest(self.scan(self.make(tree)))

    def test_the_digest_is_over_each_files_path_size_and_sha256(self) -> None:
        want = hashlib.sha256(record("A Mod/files/Data/b.bin", b"two")
                              + record("A Mod/files/a.bin", b"one")
                              + record("B Mod/dol.txt", DOL_TXT.encode())
                              + record("B Mod/hook.bin", b"\x38\x60\x00\x03")).hexdigest()
        self.assertEqual(self.digest(self.BASE), want)

    def test_no_files_is_none(self) -> None:
        self.assertEqual(mods.digest([]), "none")
        (self.mods / "Empty Mod" / "files").mkdir(parents=True)
        self.assertEqual(mods.digest(self.scan()), "none")

    def test_any_added_removed_edited_or_renamed_file_changes_it(self) -> None:
        base = self.digest(self.BASE)
        changes = {
            "added": {**self.BASE, "A Mod/files/c.bin": b""},
            "removed": {k: v for k, v in self.BASE.items() if k != "A Mod/files/a.bin"},
            "edited": {**self.BASE, "A Mod/files/a.bin": b"two"},
            "renamed": {("A Mod/files/c.bin" if k == "A Mod/files/a.bin" else k): v
                        for k, v in self.BASE.items()},
            "moved to another mod": {("C Mod/files/a.bin" if k == "A Mod/files/a.bin" else k): v
                                     for k, v in self.BASE.items()},
            "a mod renamed": {k.replace("A Mod", "Z Mod"): v for k, v in self.BASE.items()},
            "a file beside dol.txt edited": {**self.BASE, "B Mod/hook.bin": b"\x38\x60\x00\x04"},
        }
        for what, tree in changes.items():
            with self.subTest(what):
                self.assertNotEqual(self.digest(tree), base)

    def test_a_dotfile_doesnt_change_it(self) -> None:
        base = self.digest(self.BASE)
        self.assertEqual(self.digest({**self.BASE, "A Mod/files/.DS_Store": b"x",
                                      "B Mod/.DS_Store": b"y", ".DS_Store": b"z"}), base)


class CheckTest(ModsCase):
    def check(self, *args: str) -> tuple[int, str, str]:
        return run_main(mods.main, "check", str(self.mods), "--dol-sha1", SHA, *args)

    def test_it_prints_each_mod_and_the_digest(self) -> None:
        self.put("b mod/files/a.bin", b"abc")
        self.put("A Mod/dol.txt", DOL_TXT)
        self.put("A Mod/hook.bin", b"12345678")
        code, out, err = self.check()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {
            "mods": [{"name": "A Mod", "files": 2, "bytes": len(DOL_TXT) + 8},
                     {"name": "b mod", "files": 1, "bytes": 3}],
            "digest": mods.digest(self.scan())})
        self.assertEqual(len(out.splitlines()), 1)

    def test_a_missing_folder_has_no_mods(self) -> None:
        code, out, _ = run_main(mods.main, "check", str(self.tmp / "none"), "--dol-sha1", SHA)
        self.assertEqual((code, json.loads(out)), (0, {"mods": [], "digest": "none"}))

    def test_a_refused_mod_exits_1_with_one_error(self) -> None:
        self.put("Big Mod/files/main.dol")
        code, out, err = self.check()
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(json.loads(out), {
            "error": "Big Mod/files/main.dol: is a whole DOL, and a mod changes the game's code "
                     "with dol.txt",
            "mod": "Big Mod", "path": "files/main.dol"})

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def test_a_file_that_cant_be_read_exits_1_naming_it(self) -> None:
        locked = self.put("Big Mod/files/a.bin")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o644)
        code, out, err = self.check()
        self.assertEqual((code, err), (1, ""))
        got = json.loads(out)
        self.assertEqual((got["mod"], got["path"]), ("Big Mod", "files/a.bin"))
        self.assertIn("can't be read", got["error"])

    def test_bad_arguments_exit_2(self) -> None:
        for argv in ([], ["check"], ["check", str(self.mods)],
                     ["check", str(self.mods), "--dol-sha1", "abc"],
                     ["check", str(self.mods), "--dol-sha1", SHA[:-1] + "g"]):
            with self.subTest(argv=argv):
                code, out, err = run_main(mods.main, *argv)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err)

    def test_a_mods_path_that_isnt_a_folder_exits_2(self) -> None:
        file = self.put("not a folder", b"", self.tmp)
        code, out, err = run_main(mods.main, "check", str(file), "--dol-sha1", SHA)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("not a folder", err)

    def test_it_runs_as_a_script_from_another_folder(self) -> None:
        self.put("Mod/files/a.bin", b"abc")
        done = subprocess.run([sys.executable, "-B", str(MODS_PY), "check", str(self.mods),
                               "--dol-sha1", SHA], cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["mods"], [{"name": "Mod", "files": 1, "bytes": 3}])


# Stands in for dol_patch.py and disc_overlay.py. Each call goes to calls.jsonl beside it. A
# TOOL.refuse file beside it makes the tool print its text on stderr and exit 1, and a TOOL.edit
# file names a file the tool appends to, as an edit made while a build runs.
FAKE_TOOL = r"""import json, os, shutil, sys
here = os.path.dirname(os.path.abspath(__file__))
tool = os.path.basename(__file__)
with open(os.path.join(here, "calls.jsonl"), "a") as f:
    f.write(json.dumps({"tool": tool, "argv": sys.argv[1:], "cwd": os.getcwd(),
                        "path": os.environ.get("PATH"), "env": sorted(os.environ),
                        "nobytecode": sys.flags.dont_write_bytecode,
                        "nousersite": sys.flags.no_user_site}) + "\n")
refusal = os.path.join(here, tool + ".refuse")
if os.path.exists(refusal):
    with open(refusal) as f:
        sys.stderr.write(f.read())
    sys.exit(1)
edit = os.path.join(here, tool + ".edit")
if os.path.exists(edit):
    with open(edit) as f, open(f.read(), "ab") as g:
        g.write(b" and an edit")
if tool == "dol_patch.py":
    shutil.copyfile(sys.argv[1], sys.argv[2])
else:
    with open(os.path.join(sys.argv[2], "disc-overlay.txt"), "w") as f:
        f.write("gcn-disc-overlay 1\n")
"""


class PrepareTest(ModsCase):
    def setUp(self) -> None:
        super().setUp()
        self.recomp = self.tmp / "fake recomp"
        self.recomp.mkdir()
        for tool in ("dol_patch.py", "disc_overlay.py"):
            self.put(tool, FAKE_TOOL, self.recomp)
        self.disc = self.put("the disc.iso", b"an image", self.tmp)
        self.dol = self.put("cache dir/build/main.dol", b"a dol", self.tmp)
        self.out = self.tmp / "cache dir" / "build" / "disc-overlay"

    def prepare(self) -> mods.Prepared:
        return mods.prepare(self.scan(), self.disc, self.dol, self.out, Path(sys.executable),
                            self.recomp)

    def calls(self) -> list[dict]:
        path = self.recomp / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_lists_apply_in_mod_order_and_the_overlay_boots_the_patched_dol(self) -> None:
        self.put("b mod/dol.txt", DOL_TXT)
        self.put("A mod/dol.txt", DOL_TXT)
        self.put("C mod/files/a.bin")
        p = self.prepare()
        patch, overlay = self.calls()
        self.assertEqual(patch["argv"], [str(self.dol), "main.dol", "patches/1/dol.txt",
                                         "patches/2/dol.txt"])
        self.assertEqual(overlay["argv"], [str(self.disc), ".", "--files", "files",
                                           "--dol", "main.dol"])
        for call in (patch, overlay):
            self.assertEqual(call["cwd"], str(self.out))
            self.assertTrue(call["nobytecode"])
            self.assertTrue(call["nousersite"])
            self.assertEqual(call["path"], "/usr/bin:/bin:/usr/sbin:/sbin")
        self.assertEqual(p.dol, self.out / "main.dol")
        self.assertEqual(p.manifest, self.out / "disc-overlay.txt")
        self.assertEqual((self.out / "patches" / "1" / "dol.txt").read_text(), DOL_TXT)

    def test_the_tools_get_nothing_from_the_callers_environment(self) -> None:
        self.put("Mod/dol.txt", DOL_TXT)
        caller = {"PYTHONPATH": str(self.tmp / "site"), "DYLD_FALLBACK_LIBRARY_PATH": str(self.tmp)}
        with mock.patch.dict(os.environ, caller):
            self.prepare()
        calls = self.calls()
        self.assertEqual([c["tool"] for c in calls], ["dol_patch.py", "disc_overlay.py"])
        for call in calls:  # macOS gives every process __CF_USER_TEXT_ENCODING
            self.assertEqual([k for k in call["env"] if k != "__CF_USER_TEXT_ENCODING"],
                             sorted(tool_env.tool_env()))

    def test_without_a_patch_list_the_dol_given_is_the_one_to_recompile(self) -> None:
        self.put("Mod/files/a.bin")
        p = self.prepare()
        (overlay,) = self.calls()
        self.assertEqual(overlay["tool"], "disc_overlay.py")
        self.assertEqual(overlay["argv"], [str(self.disc), ".", "--files", "files"])
        self.assertEqual(p.dol, self.dol)
        self.assertFalse((self.out / "main.dol").exists())

    def test_no_mods_still_gets_an_empty_files_folder(self) -> None:
        p = self.prepare()
        self.assertEqual(list((self.out / "files").iterdir()), [])
        self.assertEqual(p.digest, "none")

    def test_every_file_is_cloned_by_disc_path_and_each_list_with_what_is_beside_it(self) -> None:
        self.put("A Mod/files/Data/readme text.txt", b"readme")
        self.put("B Mod/files/b.bin", b"bee")
        self.put("B Mod/files/.DS_Store", b"finder")
        self.put("B Mod/dol.txt", DOL_TXT)
        hook = self.put("B Mod/code/hook.bin", b"hook")
        self.prepare()
        files = self.out / "files"
        self.assertEqual(sorted(str(p.relative_to(files)) for p in files.rglob("*") if p.is_file()),
                         ["Data/readme text.txt", "b.bin"])
        self.assertEqual((files / "Data" / "readme text.txt").read_bytes(), b"readme")
        self.assertEqual((self.out / "patches" / "2" / "code" / "hook.bin").read_bytes(), b"hook")
        self.assertFalse((self.out / "patches" / "1").exists())
        hook.write_bytes(b"edited")
        self.assertEqual((self.out / "patches" / "2" / "code" / "hook.bin").read_bytes(), b"hook")

    def test_a_clone_that_fails_falls_back_to_a_copy(self) -> None:
        self.put("Mod/files/a.bin", b"abc")
        self.put("Mod/dol.txt", DOL_TXT)
        with mock.patch.object(clone_file, "CLONEFILE", lambda src, dst, flags: -1):
            p = self.prepare()
        self.assertEqual((self.out / "files" / "a.bin").read_bytes(), b"abc")
        self.assertEqual(p.digest, mods.digest(self.scan()))

    def test_the_digest_is_the_clones_and_not_what_the_mods_folder_holds_later(self) -> None:
        edited = self.put("Mod/files/a.bin", b"abc")
        before = mods.digest(self.scan())
        self.put("disc_overlay.py.edit", str(edited), self.recomp)
        p = self.prepare()
        self.assertEqual(edited.read_bytes(), b"abc and an edit")
        self.assertEqual(p.digest, before)
        self.assertNotEqual(mods.digest(self.scan()), before)

    def test_a_patch_list_refusal_names_the_mod_and_each_list_by_its_mod(self) -> None:
        self.put("A Mod/dol.txt", DOL_TXT)
        self.put("B Mod/dol.txt", DOL_TXT)
        self.put("dol_patch.py.refuse", "patches/2/dol.txt:4: word 80003104 was already written "
                                        "at patches/1/dol.txt:4\n", self.recomp)
        with self.assertRaises(mods.ModError) as cm:
            self.prepare()
        e = cm.exception
        self.assertEqual((e.mod, e.path, e.why), (
            "B Mod", "dol.txt:4", "word 80003104 was already written at A Mod/dol.txt:4"))
        self.assertEqual([c["tool"] for c in self.calls()], ["dol_patch.py"])

    def test_an_overlay_refusal_names_the_mod_with_a_file_at_or_under_its_path(self) -> None:
        self.put("A Mod/files/a.bin")
        self.put("B Mod/files/Data/b.bin")
        for n, (said, path, why) in enumerate((
                ("Data is a file on the disc, not a directory", "files/Data",
                 "is a file on the disc, not a directory"),
                ("data/B.BIN is a directory on the disc, not a file", "files/Data/b.bin",
                 "is a directory on the disc, not a file"))):
            with self.subTest(said=said):
                self.put("disc_overlay.py.refuse", f"error: {said}\n", self.recomp)
                with self.assertRaises(mods.ModError) as cm:
                    mods.prepare(self.scan(), self.disc, self.dol, self.tmp / f"out {n}",
                                 Path(sys.executable), self.recomp)
                e = cm.exception
                self.assertEqual((e.mod, e.path, e.why), ("B Mod", path, why))

    def test_an_overlay_refusal_names_the_mod_holding_the_whole_path_it_names(self) -> None:
        self.put("A Mod/files/Data/readme")
        self.put("B Mod/files/Data/readme text.txt/x.bin")
        self.put("disc_overlay.py.refuse",
                 "error: Data/readme text.txt is a file on the disc, not a directory\n", self.recomp)
        with self.assertRaises(mods.ModError) as cm:
            self.prepare()
        e = cm.exception
        self.assertEqual((e.mod, e.path, e.why), ("B Mod", "files/Data/readme text.txt",
                                                  "is a file on the disc, not a directory"))

    def test_an_overlay_refusal_of_case_twins_names_the_mod(self) -> None:
        self.put("Mod/files/Data/Readme.txt")
        twins = "matches 'README.TXT', 'readme.txt' on the disc by case alone"
        self.put("disc_overlay.py.refuse", f"error: Data/Readme.txt {twins}\n", self.recomp)
        with self.assertRaises(mods.ModError) as cm:
            self.prepare()
        e = cm.exception
        self.assertEqual((e.mod, e.path, e.why), ("Mod", "files/Data/Readme.txt", twins))

    def test_an_overlay_failure_that_only_starts_with_a_held_path_names_no_mod(self) -> None:
        self.put("A Mod/files/the")
        self.put("B Mod/files/big.bin")
        for n, said in enumerate(("the layout would end past 4 GiB, at big.bin",
                                  "the image's disc ID isn't printable ASCII",
                                  "big.bin is a file on the disc",
                                  "'the' and 'THE' in the files folder are one name on the disc")):
            with self.subTest(said=said):
                self.put("disc_overlay.py.refuse", f"error: {said}\n", self.recomp)
                with self.assertRaisesRegex(mods.PrepareError, "disc_overlay.py exited 1"):
                    mods.prepare(self.scan(), self.disc, self.dol, self.tmp / f"out {n}",
                                 Path(sys.executable), self.recomp)

    def test_a_patch_tool_failure_not_about_a_list_line_names_no_mod(self) -> None:
        self.put("Mod/dol.txt", DOL_TXT)
        self.put("dol_patch.py.refuse", "patches/1/hook code.bin: is not a regular file\n",
                 self.recomp)
        with self.assertRaisesRegex(mods.PrepareError, "dol_patch.py exited 1: patches/1/hook"):
            self.prepare()

    def test_a_failure_that_names_no_mod_is_a_prepare_error(self) -> None:
        self.put("Mod/dol.txt", DOL_TXT)
        self.put("dol_patch.py.refuse", f"{self.dol}: too short to be a DOL\n", self.recomp)
        with self.assertRaisesRegex(mods.PrepareError, "dol_patch.py exited 1: .*too short"):
            self.prepare()
        (self.recomp / "dol_patch.py.refuse").unlink()
        self.put("disc_overlay.py.refuse", "error: the layout would end past 4 GiB, at the FST\n",
                 self.recomp)
        with self.assertRaisesRegex(mods.PrepareError, "disc_overlay.py exited 1: error: the layout"):
            mods.prepare(self.scan(), self.disc, self.dol, self.tmp / "out 2",
                         Path(sys.executable), self.recomp)

    def test_a_missing_tool_is_a_prepare_error(self) -> None:
        self.put("Mod/files/a.bin")
        with self.assertRaisesRegex(mods.PrepareError, "disc_overlay.py exited 2"):
            mods.prepare(self.scan(), self.disc, self.dol, self.out, Path(sys.executable),
                         self.tmp / "no recomp")

    def test_out_has_to_be_new(self) -> None:
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(self.calls(), [])


# A DOL with one text and one data section. The text is mflr r0, li r3,1, mtlr r0, blr and four
# nops. Every address and value is made up.
TEXT = 0x80003100
TEXT_WORDS = (0x7C0802A6, 0x38600001, 0x7C0803A6, 0x4E800020) + (0x60000000,) * 4
DATA = 0x80003200
BSS = 0x80003300
HOOK = 0x80004000
HOOK_WORDS = (0x38600003, 0x4E800020)  # li r3,3 and blr


def make_dol() -> bytes:
    text = struct.pack(">8I", *TEXT_WORDS)
    data = bytes((k * 7 + 3) % 251 for k in range(0x20))
    offs, addrs, sizes = [0] * 18, [0] * 18, [0] * 18
    offs[0], addrs[0], sizes[0] = 0x100, TEXT, len(text)
    offs[7], addrs[7], sizes[7] = 0x100 + len(text), DATA, len(data)
    head = struct.pack(">18I18I18I3I", *offs, *addrs, *sizes, BSS, 0x100, TEXT)
    return head + bytes(0x100 - len(head)) + text + data


# An image whose FST holds Data/readme text.txt and zeta.bin. An entry is its type and name
# offset, then a file's offset and size or a folder's parent and the entry after it.
DISC_ID = b"TSTE01"
DOL_AT = 0x1000
FST_AT = 0x2000
FST_MAX = 0x60
FST = bytes.fromhex(
    "01000000 00000000 00000004"
    "01000000 00000000 00000003"
    "00000005 00003000 00000010"
    "00000015 00003020 00000008") + b"Data\0readme text.txt\0zeta.bin\0"


def make_image(dol: bytes) -> bytes:
    image = bytearray(0x3040)
    image[0:6] = DISC_ID
    struct.pack_into(">4I", image, 0x420, DOL_AT, FST_AT, len(FST), FST_MAX)
    image[DOL_AT:DOL_AT + len(dol)] = dol
    image[FST_AT:FST_AT + len(FST)] = FST
    image[0x3000:0x3010] = b"r" * 0x10
    image[0x3020:0x3028] = b"z" * 8
    return bytes(image)


def read_manifest(path: Path) -> tuple[dict[int, int], list[tuple[int, int, str]]]:
    """The header words and the ranges of a disc overlay manifest."""
    headers, ranges = {}, []
    for line in path.read_text().splitlines()[2:]:
        kind, rest = line.split(" ", 1)
        if kind == "header":
            word, value = rest.split(" ")
            headers[int(word, 16)] = int(value, 16)
        else:
            at, size, rel = rest.split(" ", 2)
            ranges.append((int(at, 16), int(size, 16), rel))
    return headers, ranges


@unittest.skipUnless((FORK / "disc_overlay.py").is_file() and (FORK / "dol_patch.py").is_file(),
                     "gcn-recomp isn't checked out: git submodule update --init")
class RealToolsTest(ModsCase):
    def setUp(self) -> None:
        super().setUp()
        self.dol_bytes = make_dol()
        self.sha = hashlib.sha1(self.dol_bytes).hexdigest()
        self.dol = self.put("cache dir/build/main.dol", self.dol_bytes, self.tmp)
        self.image = make_image(self.dol_bytes)
        self.disc = self.put("the disc.iso", self.image, self.tmp)
        self.out = self.tmp / "cache dir" / "build" / "disc-overlay"

    def prepare(self) -> mods.Prepared:
        return mods.prepare(mods.scan(self.mods, self.sha), self.disc, self.dol, self.out,
                            Path(sys.executable), FORK)

    def code_mod(self, name: str = "Code Mod", expect: int = TEXT_WORDS[1]) -> None:
        self.put(f"{name}/dol.txt", f"dol {self.sha}\n"
                                    f"word {TEXT + 4:08X} 38600002 {expect:08X}\n"
                                    f"section text {HOOK:08X} 8 hook code.bin\n"
                                    f"function {HOOK:08X} 8 hook\n")
        self.put(f"{name}/hook code.bin", struct.pack(">2I", *HOOK_WORDS))

    def test_the_dol_to_recompile_is_the_one_the_overlay_boots(self) -> None:
        self.code_mod()
        p = self.prepare()
        patched = p.dol.read_bytes()
        headers, ranges = read_manifest(p.manifest)
        (booted,) = [(size, rel) for at, size, rel in ranges if at == headers[0x420]]
        self.assertEqual(booted[0], len(patched))
        self.assertEqual((self.out / booted[1]).read_bytes(), patched)
        self.assertTrue(os.path.samefile(self.out / booted[1], p.dol))
        self.assertEqual(struct.unpack_from(">I", patched, 0x104)[0], 0x38600002)
        offset, addr, size = (struct.unpack_from(">I", patched, at + 4)[0] for at in (0, 0x48, 0x90))
        self.assertEqual((addr, size), (HOOK, 8))
        self.assertEqual(patched[offset:offset + 8], struct.pack(">2I", *HOOK_WORDS))
        self.assertIn(f"hook = .text:0x{HOOK:08X};", (self.out / "main.dol.syms").read_text())
        self.assertEqual(self.dol.read_bytes(), self.dol_bytes)

    def test_with_no_patch_list_the_disc_boots_the_dol_given(self) -> None:
        self.put("Big Mod/files/new file.bin", b"new")
        p = self.prepare()
        headers, _ = read_manifest(p.manifest)
        self.assertNotIn(0x420, headers)
        self.assertEqual(p.dol, self.dol)
        self.assertEqual(self.image[DOL_AT:DOL_AT + len(self.dol_bytes)], p.dol.read_bytes())

    def test_a_replacement_in_another_case_replaces_the_file(self) -> None:
        self.put("Big Mod/files/data/README TEXT.txt", b"a new readme")
        p = self.prepare()
        headers, ranges = read_manifest(p.manifest)
        self.assertNotIn(0x428, headers)
        self.assertEqual(len((self.out / "fst.bin").read_bytes()), len(FST))
        self.assertIn("files/data/README TEXT.txt", [rel for _, _, rel in ranges])

    def test_an_added_file_grows_the_fst_and_a_dotfile_never_reaches_the_disc(self) -> None:
        self.put("Big Mod/files/new file.bin", b"new")
        self.put("Big Mod/files/.DS_Store", b"finder")
        self.put("Big Mod/files/Data/._readme text.txt", b"resource fork")
        p = self.prepare()
        headers, ranges = read_manifest(p.manifest)
        self.assertGreater(headers[0x428], len(FST))
        self.assertEqual(sorted(rel for _, _, rel in ranges), ["files/new file.bin", "fst.bin"])

    def test_a_word_that_isnt_what_the_list_expects_names_the_mod_and_line(self) -> None:
        self.code_mod(expect=0x12345678)
        with self.assertRaises(mods.ModError) as cm:
            self.prepare()
        self.assertEqual((cm.exception.mod, cm.exception.path), ("Code Mod", "dol.txt:2"))
        self.assertIn("holds 38600001", cm.exception.why)

    def test_two_mods_writing_one_word_name_both(self) -> None:
        self.put("A Mod/dol.txt", f"dol {self.sha}\nword {TEXT + 4:08X} 38600002 38600001\n")
        self.put("B Mod/dol.txt", f"dol {self.sha}\nword {TEXT + 4:08X} 38600003 38600002\n")
        with self.assertRaises(mods.ModError) as cm:
            self.prepare()
        self.assertEqual(str(cm.exception), f"B Mod/dol.txt:2: word {TEXT + 4:08X} was already "
                                            "written at A Mod/dol.txt:2")

    def test_a_file_where_the_disc_has_a_folder_names_the_mod(self) -> None:
        self.put("Big Mod/files/Data", b"not a folder")
        with self.assertRaises(mods.ModError) as cm:
            self.prepare()
        self.assertEqual((cm.exception.mod, cm.exception.path), ("Big Mod", "files/Data"))
        self.assertIn("directory on the disc", cm.exception.why)

    def test_a_folder_where_the_disc_has_a_file_names_the_mod_that_needs_it(self) -> None:
        self.put("A Mod/files/Data/readme")
        self.put("B Mod/files/Data/readme text.txt/x.bin")
        with self.assertRaises(mods.ModError) as cm:
            self.prepare()
        e = cm.exception
        self.assertEqual((e.mod, e.path, e.why), ("B Mod", "files/Data/readme text.txt",
                                                  "is a file on the disc, not a directory"))

    def test_a_layout_past_4_gib_names_no_mod(self) -> None:
        self.put("A Mod/files/the")
        self.sparse("B Mod/files/big.bin", (1 << 32) - 1)
        with self.assertRaisesRegex(mods.PrepareError, "past 4 GiB, at big.bin"):
            self.prepare()

    def test_the_digest_of_the_clones_matches_the_mods_folders(self) -> None:
        self.code_mod()
        self.put("Big Mod/files/new file.bin", b"new")
        p = self.prepare()
        self.assertEqual(p.digest, mods.digest(mods.scan(self.mods, self.sha)))


if __name__ == "__main__":
    unittest.main()
