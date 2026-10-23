"""The checks check_bundle.py runs on an app and on the DMG around it.

Each returns Findings and none stops at the first. Paths in a finding are relative to the app.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import NamedTuple

import bundle_tree
import export_source
from bundle_manifest import BundleManifest
from check_no_game_data import is_game_data

APP_NAME = "Dragoon.app"
APPLICATIONS = "Applications"
# The 32-bit, 64-bit and universal headers, in both byte orders.
MACHO_MAGICS = frozenset(bytes.fromhex(h) for h in (
    "feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca", "cafebabf", "bfbafeca"))
DISC_MAGIC = bytes.fromhex("c2339f3d")
DISC_MAGIC_AT = 0x1C
CISO = b"CISO"
HEAD = DISC_MAGIC_AT + len(DISC_MAGIC)
# What a build leaves behind, beside what check_no_game_data.is_game_data knows.
BUILD_DIRS = frozenset(("gen", "rels", "inputs"))
BUILD_FILES = frozenset(("main.dol", "CMakeCache.txt", "build.ninja", ".shader-warmup"))


class Finding(NamedTuple):
    kind: str
    path: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.kind}: {self.path}" + (f" ({self.detail})" if self.detail else "")


def is_build_output(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (bool(BUILD_DIRS.intersection(parts[:-1])) or parts[-1] in BUILD_FILES
            or parts[-1].startswith("memcard_"))


def contains(path: Path, needle: bytes, block: int = 1 << 20) -> bool:
    """Does the file at PATH hold NEEDLE anywhere? It reads BLOCK bytes at a time."""
    tail = b""
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            data = tail + chunk
            if needle in data:
                return True
            tail = data[max(len(data) - (len(needle) - 1), 0):]
    return False


def read_heads(app: Path, tree: bundle_tree.Tree) -> dict[str, bytes]:
    """The first bytes of each regular file, enough for every magic number."""
    heads = {}
    for path in tree.files:
        with open(app / path, "rb") as f:
            heads[path] = f.read(HEAD)
    return heads


def check_links(tree: bundle_tree.Tree, manifest: BundleManifest) -> list[Finding]:
    """Outside the snapshot, a symlink has to be listed and point where the manifest says."""
    found = []
    for path, target in sorted(tree.links.items()):
        if path.startswith(manifest.source + "/"):
            continue
        want = manifest.links.get(path)
        if want is None:
            found.append(Finding("symlink not on the manifest", path, f"-> {target}"))
        elif want != target:
            found.append(Finding("symlink target", path, f"-> {target}, the manifest has {want}"))
    return found


def check_paths(tree: bundle_tree.Tree, manifest: BundleManifest) -> list[Finding]:
    """Check 1. Game data and build output fail anywhere. Outside the snapshot a path also has
    to be on the manifest, and so does a directory with nothing in it."""
    found = []
    snap = manifest.source + "/"
    for path in sorted([*tree.files, *tree.links]):
        inside = path.startswith(snap)
        local = path[len(snap):] if inside else path
        if is_game_data(local) or is_build_output(local):
            found.append(Finding("game data", path))
        if not inside and path in tree.files and not manifest.allows_file(path):
            found.append(Finding("not on the manifest", path))
    for path in tree.empty_dirs:
        if not path.startswith(snap) and path != manifest.source and not manifest.under_dir(path + "/"):
            found.append(Finding("not on the manifest", path + "/"))
    found += [Finding("not a file or symlink", path) for path in tree.others]
    return found + check_links(tree, manifest)


def check_executables(heads: dict[str, bytes], manifest: BundleManifest) -> list[Finding]:
    """Check 2. A Mach-O, found by its magic, has to be at a path the manifest lists."""
    return [Finding("executable not on the manifest", path) for path in sorted(heads)
            if heads[path][:4] in MACHO_MAGICS and path not in manifest.machos]


def check_content(app: Path, heads: dict[str, bytes], manifest: BundleManifest,
                  disc_id: str) -> list[Finding]:
    """Check 3. No disc magic or CISO header in any file, and the disc ID only in the snapshot."""
    found = []
    needle = disc_id.encode()
    for path in sorted(heads):
        if heads[path][:len(CISO)] == CISO:
            found.append(Finding("disc image", path, "CISO header"))
        if heads[path][DISC_MAGIC_AT:HEAD] == DISC_MAGIC:
            found.append(Finding("disc image", path, f"GameCube magic at 0x{DISC_MAGIC_AT:X}"))
        if not path.startswith(manifest.source + "/") and contains(app / path, needle):
            found.append(Finding("disc ID", path, f"{disc_id} outside the source"))
    return found


def snapshot_entries(root: Path) -> dict[str, str]:
    """Every file's SHA-256 under ROOT, source-manifest.txt's included."""
    entries = dict(export_source.manifest(root))
    listing = root / export_source.MANIFEST
    if listing.is_file() and not listing.is_symlink():
        entries[export_source.MANIFEST] = export_source.sha256_file(listing)
    return entries


def check_source(app: Path, tree: bundle_tree.Tree, manifest: BundleManifest,
                 reference: Path) -> list[Finding]:
    """Check 4. The snapshot holds what REFERENCE, export_source.py's output, holds and nothing
    else, file by file by SHA-256 and directory by directory."""
    snap = manifest.source
    if any(path.startswith(snap + "/") for path in tree.others):
        return []  # manifest() can't read a pipe, and check 1 has named it
    root = app / snap
    have = snapshot_entries(root) if root.is_dir() else {}
    want = snapshot_entries(reference)
    found = []
    for path in sorted(set(have) | set(want)):
        if path not in want:
            found.append(Finding("extra in the source", f"{snap}/{path}"))
        elif path not in have:
            found.append(Finding("missing from the source", f"{snap}/{path}"))
        elif have[path] != want[path]:
            found.append(Finding("changed in the source", f"{snap}/{path}"))
    have_dirs = {d[len(snap) + 1:] for d in tree.empty_dirs if d.startswith(snap + "/")}
    want_dirs = set(bundle_tree.scan(reference).empty_dirs)
    found += [Finding("extra in the source", f"{snap}/{d}/") for d in sorted(have_dirs - want_dirs)]
    found += [Finding("missing from the source", f"{snap}/{d}/") for d in sorted(want_dirs - have_dirs)]
    return found


def check_size(name: str, tree: bundle_tree.Tree, manifest: BundleManifest) -> list[Finding]:
    """Check 5, for the app. NAME is what the finding calls it."""
    total, budget = sum(tree.files.values()), manifest.budgets["app"]
    return [Finding("over budget", name, f"{total} bytes, budget {budget}")] if total > budget else []


def check_app(app: Path, manifest: BundleManifest, reference: Path, disc_id: str) -> list[Finding]:
    """Checks 1 to 5 on the app at APP."""
    tree = bundle_tree.scan(app)
    heads = read_heads(app, tree)
    return (check_paths(tree, manifest) + check_executables(heads, manifest)
            + check_content(app, heads, manifest, disc_id)
            + check_source(app, tree, manifest, reference) + check_size(app.name, tree, manifest))


def check_dmg(mount: Path, dmg: Path, manifest: BundleManifest) -> list[Finding]:
    """Check 5, for the DMG, and check 6. The mounted DMG holds the app and an Applications
    link to /Applications and nothing else."""
    found = []
    size, budget = dmg.stat().st_size, manifest.budgets["dmg"]
    if size > budget:
        found.append(Finding("over budget", dmg.name, f"{size} bytes, budget {budget}"))
    found += [Finding("unexpected in the DMG", name) for name in sorted(os.listdir(mount))
              if name not in (APP_NAME, APPLICATIONS)]
    app, link = mount / APP_NAME, mount / APPLICATIONS
    if app.is_symlink() or not app.is_dir():
        found.append(Finding("missing from the DMG", APP_NAME))
    if not os.path.lexists(link):
        found.append(Finding("missing from the DMG", APPLICATIONS))
    elif not link.is_symlink():
        found.append(Finding("wrong Applications link", APPLICATIONS, "not a symlink"))
    elif os.readlink(link) != "/Applications":
        found.append(Finding("wrong Applications link", APPLICATIONS, f"-> {os.readlink(link)}"))
    return found
