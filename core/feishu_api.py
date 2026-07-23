from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import requests


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


@dataclass(slots=True)
class FeishuApiConfig:
    app_id: str
    app_secret: str
    base_app_token: str


class FeishuRecordApi(Protocol):
    def list_fields(self, table_id: str) -> list[dict[str, Any]]: ...

    def list_records(self, table_id: str) -> list[dict[str, Any]]: ...

    def update_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> None: ...

    def create_record(self, table_id: str, fields: dict[str, Any]) -> None: ...


class FeishuBaseClient:
    def __init__(self, config: FeishuApiConfig) -> None:
        self.config = config
        self._tenant_token = ""
        self._tenant_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)

    def list_fields(self, table_id: str) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            f"/bitable/v1/apps/{self.config.base_app_token}/tables/{table_id}/fields",
        )
        return list(data.get("items") or [])

    def list_records(self, table_id: str) -> list[dict[str, Any]]:
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

    def update_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
        self._request(
            "PUT",
            f"/bitable/v1/apps/{self.config.base_app_token}/tables/{table_id}/records/{record_id}",
            json={"fields": fields},
        )

    def create_record(self, table_id: str, fields: dict[str, Any]) -> None:
        self._request(
            "POST",
            f"/bitable/v1/apps/{self.config.base_app_token}/tables/{table_id}/records",
            json={"fields": fields},
        )

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
