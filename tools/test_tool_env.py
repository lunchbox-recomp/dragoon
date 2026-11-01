from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import launcher_build
import mods
import tool_env


class ToolEnvTest(unittest.TestCase):
    def test_it_holds_the_system_path_and_the_python_flags_and_nothing_else(self) -> None:
        self.assertEqual(tool_env.tool_env(), {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()),
            "TMPDIR": tempfile.gettempdir(), "LANG": "en_US.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})

    def test_the_recipe_and_mods_py_share_it(self) -> None:
        self.assertIs(launcher_build.tool_env, tool_env.tool_env)
        self.assertIs(mods.tool_env, tool_env.tool_env)


if __name__ == "__main__":
    unittest.main()
