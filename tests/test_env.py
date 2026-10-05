""".env 加载器单元测试。"""

import os
import tempfile
import unittest
from pathlib import Path

from src import env


class TestLoadDotenv(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / ".env"
        self._cleanup_keys = {"A", "B", "C", "EXISTING_KEY"}

    def tearDown(self):
        for k in self._cleanup_keys:
            os.environ.pop(k, None)

    def test_parse_basic(self):
        self.tmp.write_text(
            'A=1\nB=hello\n# 注释\nC="quoted value"\n', encoding="utf-8"
        )
        self.assertTrue(env.load_dotenv(self.tmp))
        self.assertEqual(os.environ.get("A"), "1")
        self.assertEqual(os.environ.get("B"), "hello")
        self.assertEqual(os.environ.get("C"), "quoted value")

    def test_does_not_override_existing(self):
        os.environ["EXISTING_KEY"] = "keep"
        self.tmp.write_text("EXISTING_KEY=new\n", encoding="utf-8")
        env.load_dotenv(self.tmp)
        self.assertEqual(os.environ["EXISTING_KEY"], "keep")

    def test_missing_file(self):
        self.assertFalse(env.load_dotenv(Path(tempfile.mkdtemp()) / "nope.env"))


if __name__ == "__main__":
    unittest.main()
