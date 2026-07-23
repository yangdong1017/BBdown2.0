from __future__ import annotations

import unittest
from pathlib import Path

from core.config import APP_VERSION, WINDOW_TITLE


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class VersionConsistencyTests(unittest.TestCase):
    def test_release_metadata_uses_app_version(self) -> None:
        installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8-sig")
        development_guide = (PROJECT_ROOT / "#开发文档，AI禁止删除#.md").read_text(encoding="utf-8-sig")

        self.assertEqual(APP_VERSION, "4.0")
        self.assertEqual(WINDOW_TITLE, "BBDown 4.0")
        self.assertIn('#define MyAppVersion "4.0"', installer)
        self.assertIn("# BBDown4.0", readme)
        self.assertIn("BBDown-4.0.exe", readme)
        self.assertIn("BBDown-4.0.zip", readme)
        self.assertIn("release_assets\\v4.0", development_guide)


if __name__ == "__main__":
    unittest.main()
