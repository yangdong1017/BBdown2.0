from __future__ import annotations

import unittest

from core.feishu_license_client import (
    FIELD_BOUND_DEVICES,
    FIELD_CARD_KEY,
    FIELD_EXPIRE_AT,
    FIELD_MAX_DEVICES,
    FIELD_PLAN,
    FIELD_STATUS,
    FeishuLicenseClient,
    FeishuLicenseConfig,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_UNUSED,
)


class _FakeFeishuApi:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.updated: list[tuple[str, str, dict]] = []
        self.created: list[tuple[str, dict]] = []

    def list_fields(self, table_id: str) -> list[dict]:
        return [{"field_name": FIELD_BOUND_DEVICES, "type": 1}]

    def list_records(self, table_id: str) -> list[dict]:
        return self.records

    def update_record(self, table_id: str, record_id: str, fields: dict) -> None:
        self.updated.append((table_id, record_id, fields))

    def create_record(self, table_id: str, fields: dict) -> None:
        self.created.append((table_id, fields))


def _record(*, status: str = STATUS_UNUSED, devices: str = "", max_devices: int = 2, expire_at="2999-12-31") -> dict:
    return {
        "record_id": "record-1",
        "fields": {
            FIELD_CARD_KEY: "DUYA9888",
            FIELD_STATUS: status,
            FIELD_PLAN: "标准版",
            FIELD_MAX_DEVICES: max_devices,
            FIELD_BOUND_DEVICES: devices,
            FIELD_EXPIRE_AT: expire_at,
        },
    }


def _client(api: _FakeFeishuApi) -> FeishuLicenseClient:
    config = FeishuLicenseConfig(
        app_id="app-id",
        app_secret="app-secret",
        base_app_token="base-token",
        card_table_id="cards",
        log_table_id="logs",
    )
    return FeishuLicenseClient(config, api=api)


class FeishuLicenseClientTests(unittest.TestCase):
    def test_activate_binds_new_device(self) -> None:
        api = _FakeFeishuApi([_record()])

        result = _client(api).activate(card_key="duya9888", machine_id="machine-a", app_version="4.0")

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "激活成功")
        self.assertEqual(api.updated[0][2][FIELD_STATUS], STATUS_ACTIVE)
        self.assertEqual(api.updated[0][2][FIELD_BOUND_DEVICES], "machine-a")
        self.assertEqual(api.created[0][0], "logs")

    def test_verify_accepts_bound_device(self) -> None:
        api = _FakeFeishuApi([_record(status=STATUS_ACTIVE, devices="machine-a")])

        result = _client(api).verify(card_key="DUYA9888", machine_id="machine-a", app_version="4.0")

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "校验成功")
        self.assertEqual(len(api.updated), 1)

    def test_activate_rejects_device_limit(self) -> None:
        api = _FakeFeishuApi([_record(status=STATUS_ACTIVE, devices="machine-a,machine-b")])

        result = _client(api).activate(card_key="DUYA9888", machine_id="machine-c", app_version="4.0")

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "设备数量已满")
        self.assertEqual(api.updated, [])

    def test_expired_card_is_marked_and_rejected(self) -> None:
        api = _FakeFeishuApi([_record(expire_at="2000-01-01")])

        result = _client(api).verify(card_key="DUYA9888", machine_id="machine-a", app_version="4.0")

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "卡密已过期")
        self.assertEqual(api.updated[0][2][FIELD_STATUS], STATUS_EXPIRED)

    def test_unknown_card_is_rejected_and_logged(self) -> None:
        api = _FakeFeishuApi([])

        result = _client(api).activate(card_key="missing", machine_id="machine-a", app_version="4.0")

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "卡密无效")
        self.assertEqual(len(api.created), 1)


if __name__ == "__main__":
    unittest.main()
