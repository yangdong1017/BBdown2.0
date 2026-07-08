from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import requests


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

STATUS_UNUSED = "未使用"
STATUS_ACTIVE = "已激活"
STATUS_DISABLED = "禁用"
STATUS_EXPIRED = "过期"

FIELD_CARD_KEY = "卡密"
FIELD_STATUS = "状态"
FIELD_PLAN = "套餐"
FIELD_MAX_DEVICES = "最大设备数"
FIELD_BOUND_DEVICES = "已绑定设备"
FIELD_BOUND_DEVICES_FALLBACK = "文本"
FIELD_ACTIVATED_AT = "激活时间"
FIELD_EXPIRE_AT = "到期时间"
FIELD_LAST_VERIFIED_AT = "最后校验时间"

LOG_FIELD_TIME = "时间"
LOG_FIELD_CARD_KEY = "卡密"
LOG_FIELD_MACHINE_ID = "设备ID"
LOG_FIELD_APP_VERSION = "软件版本"
LOG_FIELD_ACTION = "动作"
LOG_FIELD_RESULT = "结果"
LOG_FIELD_REASON = "原因"


class FeishuLicenseConfigError(RuntimeError):
    pass


@dataclass(slots=True)
class FeishuLicenseConfig:
    app_id: str
    app_secret: str
    base_app_token: str
    card_table_id: str
    log_table_id: str


class FeishuLicenseClient:
    def __init__(self, config: FeishuLicenseConfig) -> None:
        self.config = config
        self._tenant_token = ""
        self._tenant_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._field_type_cache: dict[str, int] = {}

    def activate(self, *, card_key: str, machine_id: str, app_version: str) -> dict[str, Any]:
        return self._handle(card_key=card_key, machine_id=machine_id, app_version=app_version, action="激活")

    def verify(self, *, card_key: str, machine_id: str, app_version: str) -> dict[str, Any]:
        return self._handle(card_key=card_key, machine_id=machine_id, app_version=app_version, action="校验")

    def _handle(self, *, card_key: str, machine_id: str, app_version: str, action: str) -> dict[str, Any]:
        self._ensure_card_field_types()
        record = self._find_card_record(card_key)
        if not record:
            result = _fail("卡密无效")
            self._write_log_safe(card_key, machine_id, app_version, action, "拒绝", result["message"])
            return result

        license_data = _normalize_license_record(record)
        expired = _is_expired(license_data["expire_at"])
        if expired and license_data["status"] != STATUS_EXPIRED:
            self._update_card_record(
                license_data["record_id"],
                {
                    FIELD_STATUS: STATUS_EXPIRED,
                    FIELD_LAST_VERIFIED_AT: _now_millis(),
                },
            )

        blocked = _blocked_reason(license_data, expired)
        if blocked:
            result = _fail(blocked)
            self._write_log_safe(card_key, machine_id, app_version, action, "拒绝", result["message"])
            return result

        if action == "激活":
            result = self._activate_record(license_data, machine_id)
        else:
            result = self._verify_record(license_data, machine_id)

        self._write_log_safe(card_key, machine_id, app_version, action, "通过" if result["ok"] else "拒绝", result["message"])
        return result

    def _activate_record(self, license_data: dict[str, Any], machine_id: str) -> dict[str, Any]:
        devices = _normalize_device_list(license_data["bound_devices"])
        has_device = machine_id in devices
        max_devices = _normalize_max_devices(license_data["max_devices"])
        if not has_device and len(devices) >= max_devices:
            return _fail("设备数量已满")

        now = _now_millis()
        next_devices = devices if has_device else [*devices, machine_id]
        patch: dict[str, Any] = {
            FIELD_STATUS: STATUS_ACTIVE,
            self._bound_devices_field_name(): ",".join(next_devices),
            FIELD_LAST_VERIFIED_AT: now,
        }
        if not license_data["activated_at"]:
            patch[FIELD_ACTIVATED_AT] = now
        self._update_card_record(license_data["record_id"], patch)
        return _success("已激活" if has_device else "激活成功", license_data)

    def _verify_record(self, license_data: dict[str, Any], machine_id: str) -> dict[str, Any]:
        devices = _normalize_device_list(license_data["bound_devices"])
        if machine_id not in devices:
            return _fail("当前设备未激活")
        self._update_card_record(license_data["record_id"], {FIELD_LAST_VERIFIED_AT: _now_millis()})
        return _success("校验成功", license_data)

    def _find_card_record(self, card_key: str) -> dict[str, Any] | None:
        target = _normalize_card_key(card_key)
        for record in self._list_records(self.config.card_table_id):
            fields = record.get("fields") or {}
            if _normalize_card_key(_string_value(fields.get(FIELD_CARD_KEY))) == target:
                return record
        return None

    def _bound_devices_field_name(self) -> str:
        field_type = self._field_type_cache.get(FIELD_BOUND_DEVICES)
        if field_type == 1:
            return FIELD_BOUND_DEVICES
        if self._field_type_cache.get(FIELD_BOUND_DEVICES_FALLBACK) == 1:
            return FIELD_BOUND_DEVICES_FALLBACK
        return FIELD_BOUND_DEVICES

    def _ensure_card_field_types(self) -> None:
        if self._field_type_cache:
            return
        data = self._request(
            "GET",
            f"/bitable/v1/apps/{self.config.base_app_token}/tables/{self.config.card_table_id}/fields",
        )
        self._field_type_cache = {
            str(field.get("field_name") or ""): int(field.get("type") or 0)
            for field in data.get("items", [])
        }

    def _list_records(self, table_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params = {
                "page_size": "500",
                "text_field_as_array": "false",
            }
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.config.base_app_token}/tables/{table_id}/records",
                params=params,
            )
            records.extend(data.get("items") or data.get("records") or [])
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or data.get("next_page_token") or "")
            if not page_token:
                break
        return records

    def _update_card_record(self, record_id: str, fields: dict[str, Any]) -> None:
        self._request(
            "PUT",
            f"/bitable/v1/apps/{self.config.base_app_token}/tables/{self.config.card_table_id}/records/{record_id}",
            json={"fields": fields},
        )

    def _write_log_safe(
        self,
        card_key: str,
        machine_id: str,
        app_version: str,
        action: str,
        result: str,
        reason: str,
    ) -> None:
        if not self.config.log_table_id:
            return
        fields = {
            LOG_FIELD_TIME: _now_text(),
            LOG_FIELD_CARD_KEY: card_key,
            LOG_FIELD_MACHINE_ID: machine_id,
            LOG_FIELD_APP_VERSION: app_version,
            LOG_FIELD_ACTION: action,
            LOG_FIELD_RESULT: result,
            LOG_FIELD_REASON: reason,
        }
        try:
            self._request(
                "POST",
                f"/bitable/v1/apps/{self.config.base_app_token}/tables/{self.config.log_table_id}/records",
                json={"fields": fields},
            )
        except Exception:
            pass

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{FEISHU_API_BASE}{path}",
            headers={
                "Authorization": f"Bearer {self._tenant_access_token()}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=15,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"飞书接口返回异常: HTTP {response.status_code}") from exc
        if not response.ok or payload.get("code") != 0:
            code = payload.get("code", response.status_code)
            message = payload.get("msg") or payload.get("message") or "未知错误"
            raise RuntimeError(f"飞书接口调用失败: {code} {message}")
        return payload.get("data") or {}

    def _tenant_access_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._tenant_token and self._tenant_token_expires_at - timedelta(minutes=2) > now:
            return self._tenant_token

        response = requests.post(
            f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret,
            },
            timeout=15,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"飞书授权返回异常: HTTP {response.status_code}") from exc
        if not response.ok or payload.get("code") != 0 or not payload.get("tenant_access_token"):
            code = payload.get("code", response.status_code)
            message = payload.get("msg") or payload.get("message") or "未知错误"
            raise RuntimeError(f"飞书授权失败: {code} {message}")
        self._tenant_token = str(payload["tenant_access_token"])
        self._tenant_token_expires_at = now + timedelta(seconds=int(payload.get("expire") or 7200))
        return self._tenant_token


def build_direct_feishu_client() -> FeishuLicenseClient | None:
    try:
        from core import license_private
    except Exception:
        return None

    if not bool(getattr(license_private, "ENABLE_DIRECT_FEISHU_LICENSE", False)):
        return None

    config = FeishuLicenseConfig(
        app_id=str(getattr(license_private, "FEISHU_APP_ID", "")).strip(),
        app_secret=str(getattr(license_private, "FEISHU_APP_SECRET", "")).strip(),
        base_app_token=str(getattr(license_private, "BASE_APP_TOKEN", "")).strip(),
        card_table_id=str(getattr(license_private, "CARD_TABLE_ID", "")).strip(),
        log_table_id=str(getattr(license_private, "LOG_TABLE_ID", "")).strip(),
    )
    missing = [
        name
        for name, value in (
            ("FEISHU_APP_ID", config.app_id),
            ("FEISHU_APP_SECRET", config.app_secret),
            ("BASE_APP_TOKEN", config.base_app_token),
            ("CARD_TABLE_ID", config.card_table_id),
            ("LOG_TABLE_ID", config.log_table_id),
        )
        if not value
    ]
    if missing:
        raise FeishuLicenseConfigError(f"卡密配置缺失: {', '.join(missing)}")
    return FeishuLicenseClient(config)


def _normalize_license_record(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields") or {}
    return {
        "record_id": str(record.get("record_id") or record.get("id") or ""),
        "card_key": _string_value(fields.get(FIELD_CARD_KEY)).strip(),
        "status": _string_value(fields.get(FIELD_STATUS)).strip() or STATUS_UNUSED,
        "plan": _string_value(fields.get(FIELD_PLAN)).strip(),
        "max_devices": fields.get(FIELD_MAX_DEVICES),
        "bound_devices": fields.get(FIELD_BOUND_DEVICES) or fields.get(FIELD_BOUND_DEVICES_FALLBACK),
        "activated_at": _string_value(fields.get(FIELD_ACTIVATED_AT)).strip(),
        "expire_at": fields.get(FIELD_EXPIRE_AT),
        "last_verified_at": _string_value(fields.get(FIELD_LAST_VERIFIED_AT)).strip(),
    }


def _success(message: str, license_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "message": message,
        "plan": str(license_data.get("plan") or ""),
        "expire_at": _normalize_expire_output(license_data.get("expire_at")),
    }


def _fail(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}


def _blocked_reason(license_data: dict[str, Any], expired: bool) -> str:
    if license_data["status"] == STATUS_DISABLED:
        return "卡密已禁用"
    if license_data["status"] == STATUS_EXPIRED or expired:
        return "卡密已过期"
    return ""


def _normalize_card_key(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_max_devices(value: Any) -> int:
    try:
        normalized = int(float(_string_value(value) or value or 1))
    except Exception:
        return 1
    return max(1, normalized)


def _normalize_device_list(value: Any) -> list[str]:
    text = _string_value(value).strip()
    if not text:
        return []
    parts = [item.strip() for item in text.replace("，", ",").replace("\n", ",").split(",")]
    return list(dict.fromkeys(item for item in parts if item))


def _is_expired(value: Any) -> bool:
    timestamp = _parse_expire_timestamp(value)
    return bool(timestamp and datetime.now().timestamp() * 1000 > timestamp)


def _parse_expire_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 100000000000 else number * 1000

    text = _string_value(value).strip()
    if not text:
        return 0
    if text.isdigit():
        number = float(text)
        return number if number > 100000000000 else number * 1000
    if len(text) == 10 and text.count("-") == 2:
        text = f"{text} 23:59:59"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).timestamp() * 1000
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return 0


def _normalize_expire_output(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp < 100000000000:
            timestamp *= 1000
        return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
    return _string_value(value).strip()


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return ",".join(item for item in (_string_value(item) for item in value) if item)
    if isinstance(value, dict):
        for key in ("text", "name", "value", "link"):
            if key in value:
                return _string_value(value[key])
    return ""


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_millis() -> int:
    return int(datetime.now().timestamp() * 1000)
