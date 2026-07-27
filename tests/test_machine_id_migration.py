from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import machine_id as machine_id_module
from core.feishu_license_client import _replace_legacy_device
from core.license_service import LicenseService
from core.machine_id import (
    MACHINE_ID_SALT,
    get_legacy_machine_id,
    get_machine_id,
    machine_id_candidates,
)


GUID = "9f8b2c1e-4d3a-4f5b-8e6c-1a2b3c4d5e6f"


def _expected(raw: str) -> str:
    return hashlib.sha256(f"{MACHINE_ID_SALT}|{raw}".encode("utf-8")).hexdigest()[:32]


class MachineIdTests(unittest.TestCase):
    def test_salt_must_not_change(self) -> None:
        # Changing the salt would invalidate every activation already sold.
        self.assertEqual(MACHINE_ID_SALT, "BBDown3.0")

    def test_windows_machine_uses_only_the_machine_guid(self) -> None:
        with patch.object(machine_id_module, "_read_windows_machine_guid", return_value=GUID):
            self.assertEqual(get_machine_id(), _expected(GUID))

    def test_the_id_survives_a_new_network_adapter_and_a_renamed_pc(self) -> None:
        with patch.object(machine_id_module, "_read_windows_machine_guid", return_value=GUID):
            with patch.object(machine_id_module.uuid, "getnode", return_value=1):
                with patch.dict(machine_id_module.os.environ, {"COMPUTERNAME": "OLD-PC"}, clear=False):
                    before = get_machine_id()
            with patch.object(machine_id_module.uuid, "getnode", return_value=2):
                with patch.dict(machine_id_module.os.environ, {"COMPUTERNAME": "NEW-PC"}, clear=False):
                    after = get_machine_id()

        self.assertEqual(before, after)

    def test_legacy_algorithm_is_untouched(self) -> None:
        with (
            patch.object(machine_id_module, "_read_windows_machine_guid", return_value=GUID),
            patch.object(machine_id_module.platform, "node", return_value="OLD-PC"),
            patch.object(machine_id_module.uuid, "getnode", return_value=0xAABBCCDDEEFF),
            patch.dict(
                machine_id_module.os.environ,
                {"COMPUTERNAME": "OLD-PC", "USERDOMAIN": "OLD-PC"},
                clear=False,
            ),
        ):
            legacy = get_legacy_machine_id()

        self.assertEqual(legacy, _expected(f"{GUID}|OLD-PC|OLD-PC|OLD-PC|{0xAABBCCDDEEFF}"))

    def test_candidates_offer_the_old_id_as_a_fallback(self) -> None:
        with patch.object(machine_id_module, "_read_windows_machine_guid", return_value=GUID):
            candidates = machine_id_candidates()
            current = get_machine_id()
            legacy = get_legacy_machine_id()

        self.assertEqual(candidates, [current, legacy])
        self.assertNotEqual(current, legacy)

    def test_without_a_machine_guid_there_is_nothing_to_migrate(self) -> None:
        with patch.object(machine_id_module, "_read_windows_machine_guid", return_value=""):
            candidates = machine_id_candidates()

        self.assertEqual(candidates, [get_legacy_machine_id()])


class LegacyDeviceReplacementTests(unittest.TestCase):
    """An upgrading user must keep the seat they already own, not take a second."""

    def test_old_id_is_swapped_for_the_new_one_in_place(self) -> None:
        devices = ["other-pc", "old-id"]

        upgraded = _replace_legacy_device(devices, "new-id", ["old-id"])

        self.assertEqual(upgraded, ["other-pc", "new-id"])
        self.assertEqual(len(upgraded), len(devices))

    def test_an_unknown_machine_is_not_migrated(self) -> None:
        self.assertIsNone(_replace_legacy_device(["other-pc"], "new-id", ["old-id"]))

    def test_no_legacy_ids_means_no_migration(self) -> None:
        self.assertIsNone(_replace_legacy_device(["old-id"], "new-id", []))

    def test_the_new_id_is_not_duplicated(self) -> None:
        upgraded = _replace_legacy_device(["new-id", "old-id"], "new-id", ["old-id"])

        self.assertEqual(upgraded, ["new-id"])


class _RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def activate(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"ok": True, "message": "激活成功", "plan": "标准版", "expire_at": "2999-12-31"}

    def verify(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"ok": True, "message": "校验成功", "plan": "标准版", "expire_at": "2999-12-31"}


class LicenseServiceMigrationTests(unittest.TestCase):
    def test_old_identifiers_are_sent_along(self) -> None:
        client = _RecordingClient()
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("core.license_service.build_direct_feishu_client", return_value=client),
                patch(
                    "core.license_service.machine_id_candidates",
                    return_value=["new-id", "old-id"],
                ),
            ):
                service = LicenseService(api_url="", cache_path=Path(directory) / "license.json")
                service.activate("DUYA9888")

        self.assertEqual(client.calls[0]["machine_id"], "new-id")
        self.assertEqual(client.calls[0]["legacy_machine_ids"], ["old-id"])

    def test_a_cache_written_under_the_old_id_is_still_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "license.json"
            cache_path.write_text(
                '{"card_key": "DUYA9888", "machine_id": "old-id", "expire_at": "2999-12-31"}',
                encoding="utf-8",
            )
            with (
                patch("core.license_service.build_direct_feishu_client", return_value=_RecordingClient()),
                patch(
                    "core.license_service.machine_id_candidates",
                    return_value=["new-id", "old-id"],
                ),
            ):
                service = LicenseService(api_url="", cache_path=cache_path)

                self.assertEqual(service.load_cache().get("card_key"), "DUYA9888")

    def test_a_cache_from_another_machine_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "license.json"
            cache_path.write_text(
                '{"card_key": "DUYA9888", "machine_id": "someone-else", "expire_at": "2999-12-31"}',
                encoding="utf-8",
            )
            with (
                patch("core.license_service.build_direct_feishu_client", return_value=_RecordingClient()),
                patch(
                    "core.license_service.machine_id_candidates",
                    return_value=["new-id", "old-id"],
                ),
            ):
                service = LicenseService(api_url="", cache_path=cache_path)

                self.assertEqual(service.load_cache(), {})
                self.assertFalse(service.verify().ok)


if __name__ == "__main__":
    unittest.main()
