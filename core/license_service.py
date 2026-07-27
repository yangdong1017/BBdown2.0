from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from core.config import (
    APP_VERSION,
    LICENSE_API_URL,
    LICENSE_OFFLINE_GRACE_HOURS,
    LICENSE_PATH,
    LICENSE_VERIFY_INTERVAL_HOURS,
)
from core.config_store import atomic_write_json, read_json
from core.feishu_license_client import FeishuLicenseConfigError, build_direct_feishu_client
from core.machine_id import machine_id_candidates


@dataclass(slots=True)
class LicenseResult:
    ok: bool
    message: str
    plan: str = ""
    expire_at: str = ""
    offline: bool = False


class LicenseService:
    def __init__(self, api_url: str = LICENSE_API_URL, cache_path: Path = LICENSE_PATH) -> None:
        self.api_url = api_url.strip().rstrip("/")
        self.cache_path = cache_path
        candidates = machine_id_candidates()
        self.machine_id = candidates[0]
        # Identifiers this machine may already be registered under, from before
        # the machine id stopped depending on network adapters and the PC name.
        self.legacy_machine_ids = candidates[1:]
        self._direct_client = None
        self._direct_client_error = ""
        if not self.api_url:
            try:
                self._direct_client = build_direct_feishu_client()
            except FeishuLicenseConfigError as exc:
                self._direct_client_error = str(exc)

    def activate(self, card_key: str) -> LicenseResult:
        card_key = card_key.strip()
        if not card_key:
            return LicenseResult(False, "请输入卡密")
        return self._request("activate", card_key=card_key)

    def verify(self, *, force: bool = False) -> LicenseResult:
        cache = self.load_cache()
        if not cache:
            return LicenseResult(False, "请先激活卡密")
        if self._is_expired(str(cache.get("expire_at", ""))):
            return LicenseResult(False, "卡密已过期")
        if not force and not self._needs_remote_verify(cache):
            return LicenseResult(
                True,
                "已激活",
                plan=str(cache.get("plan", "")),
                expire_at=str(cache.get("expire_at", "")),
            )
        card_key = str(cache.get("card_key", "")).strip()
        if not card_key:
            return LicenseResult(False, "本地授权信息不完整，请重新激活")
        return self._request("verify", card_key=card_key, existing_cache=cache)

    def load_cache(self) -> dict[str, Any]:
        data = read_json(self.cache_path)
        known = {self.machine_id, *self.legacy_machine_ids}
        if data.get("machine_id") not in known:
            return {}
        return data

    def clear_cache(self) -> None:
        try:
            self.cache_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _request(
        self,
        endpoint: str,
        *,
        card_key: str,
        existing_cache: dict[str, Any] | None = None,
    ) -> LicenseResult:
        if not self.api_url:
            return self._direct_request(endpoint, card_key=card_key, existing_cache=existing_cache)

        payload = {
            "card_key": card_key,
            "machine_id": self.machine_id,
            "legacy_machine_ids": self.legacy_machine_ids,
            "app_version": APP_VERSION,
        }

        try:
            response = requests.post(
                f"{self.api_url}/{endpoint}",
                json=payload,
                timeout=12,
                headers={"User-Agent": f"BBDown/{APP_VERSION}"},
            )
            data = response.json()
        except requests.RequestException:
            return self._offline_or_fail(existing_cache, "网络异常，无法校验卡密")
        except ValueError:
            return self._offline_or_fail(existing_cache, "卡密接口返回异常")

        if not isinstance(data, dict):
            return self._offline_or_fail(existing_cache, "卡密接口返回异常")

        ok = bool(data.get("ok"))
        message = str(data.get("message") or ("成功" if ok else "卡密校验失败"))
        if not response.ok:
            return self._offline_or_fail(existing_cache, message)
        if not ok:
            self._clear_cache_for_remote_rejection(message)
            return LicenseResult(False, message)

        cache = self._build_cache(card_key, data, existing_cache)
        self._save_cache(cache)
        return LicenseResult(
            True,
            message,
            plan=str(cache.get("plan", "")),
            expire_at=str(cache.get("expire_at", "")),
        )

    def _direct_request(
        self,
        endpoint: str,
        *,
        card_key: str,
        existing_cache: dict[str, Any] | None = None,
    ) -> LicenseResult:
        if self._direct_client_error:
            return self._offline_or_fail(existing_cache, self._direct_client_error)
        if not self._direct_client:
            return self._offline_or_fail(existing_cache, "本地飞书卡密配置未启用")
        try:
            if endpoint == "activate":
                data = self._direct_client.activate(
                    card_key=card_key,
                    machine_id=self.machine_id,
                    app_version=APP_VERSION,
                    legacy_machine_ids=self.legacy_machine_ids,
                )
            else:
                data = self._direct_client.verify(
                    card_key=card_key,
                    machine_id=self.machine_id,
                    app_version=APP_VERSION,
                    legacy_machine_ids=self.legacy_machine_ids,
                )
        except requests.RequestException:
            return self._offline_or_fail(existing_cache, "网络异常，无法校验卡密")
        except Exception as exc:
            return self._offline_or_fail(existing_cache, str(exc) or "飞书卡密校验失败")

        ok = bool(data.get("ok"))
        message = str(data.get("message") or ("成功" if ok else "卡密校验失败"))
        if not ok:
            self._clear_cache_for_remote_rejection(message)
            return LicenseResult(False, message)

        cache = self._build_cache(card_key, data, existing_cache)
        self._save_cache(cache)
        return LicenseResult(
            True,
            message,
            plan=str(cache.get("plan", "")),
            expire_at=str(cache.get("expire_at", "")),
        )

    def _build_cache(
        self,
        card_key: str,
        data: dict[str, Any],
        existing_cache: dict[str, Any] | None,
    ) -> dict[str, Any]:
        existing_cache = existing_cache or {}
        now = _now_iso()
        return {
            "card_key": card_key,
            "machine_id": self.machine_id,
            "plan": str(data.get("plan") or existing_cache.get("plan") or ""),
            "expire_at": str(data.get("expire_at") or existing_cache.get("expire_at") or ""),
            "activated_at": str(existing_cache.get("activated_at") or now),
            "last_verified_at": now,
            "app_version": APP_VERSION,
        }

    def _save_cache(self, data: dict[str, Any]) -> None:
        atomic_write_json(self.cache_path, data)

    def _offline_or_fail(self, cache: dict[str, Any] | None, message: str) -> LicenseResult:
        if not cache:
            return LicenseResult(False, message)
        if self._is_expired(str(cache.get("expire_at", ""))):
            return LicenseResult(False, "卡密已过期")
        if self._within_offline_grace(cache):
            return LicenseResult(
                True,
                "离线授权可用",
                plan=str(cache.get("plan", "")),
                expire_at=str(cache.get("expire_at", "")),
                offline=True,
            )
        return LicenseResult(False, message)

    def _needs_remote_verify(self, cache: dict[str, Any]) -> bool:
        verified_at = _parse_datetime(str(cache.get("last_verified_at", "")))
        if not verified_at:
            return True
        return datetime.now().astimezone() - verified_at >= timedelta(hours=LICENSE_VERIFY_INTERVAL_HOURS)

    def _within_offline_grace(self, cache: dict[str, Any]) -> bool:
        verified_at = _parse_datetime(str(cache.get("last_verified_at", "")))
        if not verified_at:
            return False
        return datetime.now().astimezone() - verified_at <= timedelta(hours=LICENSE_OFFLINE_GRACE_HOURS)

    def _is_expired(self, expire_at: str) -> bool:
        expiry = _parse_expiry(expire_at)
        if not expiry:
            return False
        return datetime.now().astimezone() > expiry

    def _clear_cache_for_remote_rejection(self, message: str) -> None:
        terminal_messages = ("卡密无效", "卡密已禁用", "卡密已过期", "当前设备未激活")
        if any(text in message for text in terminal_messages):
            self.clear_cache()


def _now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _parse_expiry(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        if len(value) == 10:
            local_tz = datetime.now().astimezone().tzinfo
            return datetime.strptime(value, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=local_tz)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None
