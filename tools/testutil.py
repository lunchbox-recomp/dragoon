"""Helpers the tools' tests share."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Callable


def run_main(main: Callable[[list[str]], int], *argv: str) -> tuple[int, str, str]:
    """Run a tool's main with its output captured: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def write_file(directory: Path, name: str, data: bytes | str) -> Path:
    path = Path(directory, name)
    if isinstance(data, str):
        path.write_text(data)
    else:
        path.write_bytes(data)
    return path
