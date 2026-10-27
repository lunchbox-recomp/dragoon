"""What environment does a tool that the build runs get?

tool_env() is the whole of it. PATH holds only the system's folders, so nothing Homebrew or
MacPorts installed is found, and Python writes no bytecode and leaves the user's site-packages
out. launcher_build.py runs the recipe's tools with it, and mods.py runs gcn-recomp's. It has no
command line.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

TOOL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def tool_env() -> dict[str, str]:
    return {"PATH": TOOL_PATH, "HOME": str(Path.home()), "TMPDIR": tempfile.gettempdir(),
            "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
