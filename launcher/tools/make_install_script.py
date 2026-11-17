#!/usr/bin/env python3
"""Write a release's install.sh from launcher/install.sh.in.

Usage: make_install_script.py --zip FILE --url URL --out FILE

Fills the template's @URL@ with URL, where the release serves the zip, and its @SHA256@ with
FILE's SHA-256, then writes the script to --out with mode 0755. The script downloads URL, checks
the hash and installs the app in ~/Applications, as the template's own comments say.

URL goes into the script inside single quotes, so it may hold no quote, backslash, whitespace or
control character, and it has to start with https:// or file://. The tests install from a
file:// URL.

Exits 0 when the script is written and prints its path, and 1 when writing it failed. Exits 2
with one line on stderr saying why and nothing written when FILE is missing or isn't a file, URL
can't go in the script, or the template doesn't hold each placeholder once.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import NoReturn, Optional

TEMPLATE = Path(__file__).resolve().parents[1] / "install.sh.in"
PLACEHOLDERS = ("@URL@", "@SHA256@")
URL = re.compile(r"(https|file)://[!-~]+")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(f"make_install_script.py: {message}", file=sys.stderr)
        sys.exit(2)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def url_problem(url: str) -> Optional[str]:
    """Why URL can't go between the script's single quotes, or None when it can."""
    if not URL.fullmatch(url) or any(c in url for c in "'\\"):
        return (f"--url {url!r} has to start with https:// or file:// and hold no quote, backslash,"
                " whitespace or control character")
    return None


def fill(template: str, url: str, digest: str) -> str:
    """TEMPLATE with its placeholders replaced. Raises ValueError unless each is there once."""
    for placeholder in PLACEHOLDERS:
        if template.count(placeholder) != 1:
            raise ValueError(f"{TEMPLATE.name} holds {placeholder} {template.count(placeholder)} times, not once")
    # One pass, so a URL that holds @SHA256@ keeps it.
    values = {"@URL@": url, "@SHA256@": digest}
    return re.sub("|".join(PLACEHOLDERS), lambda m: values[m.group(0)], template)


def main(argv: list[str]) -> int:
    ap = Parser(prog="make_install_script.py", description=__doc__,
                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", type=Path, required=True, help="the release's zipped app")
    ap.add_argument("--url", required=True, help="where the release serves the zip")
    ap.add_argument("--out", type=Path, required=True, help="the install.sh to write")
    a = ap.parse_args(argv)
    problem = None if a.zip.is_file() else f"--zip {a.zip} isn't a file"
    problem = problem or url_problem(a.url)
    if not problem:
        try:
            script = fill(TEMPLATE.read_text(encoding="utf-8"), a.url, sha256(a.zip))
        except (OSError, ValueError) as e:
            problem = str(e)
    if problem:
        print(f"make_install_script.py: {problem}", file=sys.stderr)
        return 2
    try:
        a.out.write_text(script, encoding="utf-8")
        a.out.chmod(0o755)
    except OSError as e:
        print(f"make_install_script.py: {e}", file=sys.stderr)
        return 1
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
