from __future__ import annotations

import os
import tempfile
import unittest

from src.projectx_api import ProjectXConfig, _read_env_file


class TestProjectXEnvParsing(unittest.TestCase):
    def test_read_env_file_ignores_comments_and_blank_lines(self) -> None:
        content = """
# comment
PROJECTX_USERNAME=alice
PROJECTX_API_KEY=abc123

PROJECTX_LIVE=true
""".strip()
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(content)
            path = f.name

        values = _read_env_file(path)
        self.assertEqual(values["PROJECTX_USERNAME"], "alice")
        self.assertEqual(values["PROJECTX_API_KEY"], "abc123")
        self.assertEqual(values["PROJECTX_LIVE"], "true")

        os.unlink(path)

    def test_read_env_file_supports_export_prefix_and_inline_comment(self) -> None:
        content = """
export PROJECTX_USERNAME = bob
export PROJECTX_API_KEY = xyz789 # inline comment
""".strip()
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(content)
            path = f.name

        values = _read_env_file(path)
        self.assertEqual(values["PROJECTX_USERNAME"], "bob")
        self.assertEqual(values["PROJECTX_API_KEY"], "xyz789")
        os.unlink(path)

    def test_from_env_prefers_os_env_over_file(self) -> None:
        content = """
PROJECTX_USERNAME=file_user
PROJECTX_API_KEY=file_key
PROJECTX_LIVE=false
""".strip()
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(content)
            path = f.name

        old_user = os.environ.get("PROJECTX_USERNAME")
        old_key = os.environ.get("PROJECTX_API_KEY")
        old_live = os.environ.get("PROJECTX_LIVE")
        os.environ["PROJECTX_USERNAME"] = "env_user"
        os.environ["PROJECTX_API_KEY"] = "env_key"
        os.environ["PROJECTX_LIVE"] = "true"

        config = ProjectXConfig.from_env(path)
        self.assertEqual(config.username, "env_user")
        self.assertEqual(config.api_key, "env_key")
        self.assertTrue(config.live)

        if old_user is None:
            os.environ.pop("PROJECTX_USERNAME", None)
        else:
            os.environ["PROJECTX_USERNAME"] = old_user
        if old_key is None:
            os.environ.pop("PROJECTX_API_KEY", None)
        else:
            os.environ["PROJECTX_API_KEY"] = old_key
        if old_live is None:
            os.environ.pop("PROJECTX_LIVE", None)
        else:
            os.environ["PROJECTX_LIVE"] = old_live

        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
