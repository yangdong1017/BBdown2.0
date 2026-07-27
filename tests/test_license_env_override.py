from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest import mock

from core import config


class LicenseEnvOverrideTests(unittest.TestCase):
    """The packaged EXE must ignore license overrides from the environment."""

    def tearDown(self) -> None:
        # Other tests import core.config at module level, so restore the real one.
        importlib.reload(config)

    def _reload_with(self, frozen: bool, env: dict[str, str]):
        environ = {key: value for key, value in os.environ.items() if not key.startswith("BBDOWN_LICENSE_")}
        environ.update(env)
        with mock.patch.dict(os.environ, environ, clear=True):
            if frozen:
                with mock.patch.object(sys, "frozen", True, create=True):
                    return importlib.reload(config)
            saved = getattr(sys, "frozen", None)
            if saved is not None:
                del sys.frozen
            try:
                return importlib.reload(config)
            finally:
                if saved is not None:
                    sys.frozen = saved

    def test_frozen_build_ignores_required_override(self) -> None:
        reloaded = self._reload_with(True, {"BBDOWN_LICENSE_REQUIRED": "0"})
        self.assertTrue(reloaded.IS_FROZEN)
        self.assertTrue(reloaded.LICENSE_REQUIRED)

    def test_frozen_build_ignores_api_url_override(self) -> None:
        reloaded = self._reload_with(True, {"BBDOWN_LICENSE_API_URL": "http://attacker.example.com"})
        self.assertEqual(reloaded.LICENSE_API_URL, reloaded.DEFAULT_LICENSE_API_URL)

    def test_development_build_still_allows_overrides(self) -> None:
        reloaded = self._reload_with(
            False,
            {"BBDOWN_LICENSE_REQUIRED": "0", "BBDOWN_LICENSE_API_URL": "http://localhost:8000/"},
        )
        self.assertFalse(reloaded.IS_FROZEN)
        self.assertFalse(reloaded.LICENSE_REQUIRED)
        self.assertEqual(reloaded.LICENSE_API_URL, "http://localhost:8000")

    def test_license_required_defaults_to_true(self) -> None:
        reloaded = self._reload_with(False, {})
        self.assertTrue(reloaded.LICENSE_REQUIRED)


if __name__ == "__main__":
    unittest.main()
