"""Helpers the tools' tests share."""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
from pathlib import Path
from typing import Callable

# Fixture repositories ignore the user's and the system's git config, so no signing, hook
# or filter of theirs runs, and commit as a fixed name.
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


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


def git(repo: Path, *args: str) -> str:
    """Run git in REPO under GIT_ENV and return its output, stripped."""
    done = subprocess.run(["git", "-C", str(repo), *args], env={**os.environ, **GIT_ENV},
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def commit(repo: Path, files: dict[str, bytes | str]) -> str:
    """Write FILES (relative path: contents) into REPO, making it a repository first if it
    isn't one, commit them with anything already staged and return the commit."""
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q", "-b", "main")
    for name, data in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write_file(path.parent, path.name, data)
    git(repo, "add", "--", *files)
    git(repo, "commit", "-q", "-m", "commit")
    return git(repo, "rev-parse", "HEAD")
