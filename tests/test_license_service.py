from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.license_service import LicenseService


class _DirectLicenseClient:
    def __init__(self) -> None:
        self.verify_result = {
            "ok": True,
            "message": "校验成功",
            "plan": "标准版",
            "expire_at": "2999-12-31",
        }
        self.verify_calls = 0

    def activate(self, **kwargs) -> dict:
        return {
            "ok": True,
            "message": "激活成功",
            "plan": "标准版",
            "expire_at": "2999-12-31",
        }

    def verify(self, **kwargs) -> dict:
        self.verify_calls += 1
        return self.verify_result


class LicenseServiceTests(unittest.TestCase):
    def test_direct_client_activation_and_forced_verification(self) -> None:
        direct_client = _DirectLicenseClient()
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "license.json"
            with (
                patch("core.license_service.build_direct_feishu_client", return_value=direct_client),
                patch("core.license_service.get_machine_id", return_value="machine-a"),
            ):
                service = LicenseService(api_url="", cache_path=cache_path)
                activated = service.activate("DUYA9888")
                verified = service.verify(force=True)

            self.assertTrue(activated.ok)
            self.assertTrue(verified.ok)
            self.assertEqual(direct_client.verify_calls, 1)
            self.assertTrue(cache_path.exists())

    def test_terminal_remote_rejection_clears_local_cache(self) -> None:
        direct_client = _DirectLicenseClient()
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "license.json"
            with (
                patch("core.license_service.build_direct_feishu_client", return_value=direct_client),
                patch("core.license_service.get_machine_id", return_value="machine-a"),
            ):
                service = LicenseService(api_url="", cache_path=cache_path)
                self.assertTrue(service.activate("DUYA9888").ok)
                direct_client.verify_result = {"ok": False, "message": "卡密无效"}
                verified = service.verify(force=True)

            self.assertFalse(verified.ok)
            self.assertFalse(cache_path.exists())


if __name__ == "__main__":
    unittest.main()
