from __future__ import annotations

import unittest
from unittest.mock import patch

from core.feishu_api import FeishuApiConfig, FeishuBaseClient


class _Response:
    def __init__(self, payload: dict, *, ok: bool = True, status_code: int = 200) -> None:
        self.payload = payload
        self.ok = ok
        self.status_code = status_code

    def json(self) -> dict:
        return self.payload


class FeishuBaseClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FeishuBaseClient(
            FeishuApiConfig(
                app_id="app-id",
                app_secret="app-secret",
                base_app_token="base-token",
            )
        )

    def test_list_records_collects_all_pages(self) -> None:
        pages = [
            {"items": [{"record_id": "one"}], "has_more": True, "page_token": "next"},
            {"items": [{"record_id": "two"}], "has_more": False},
        ]
        with patch.object(self.client, "_request", side_effect=pages) as request:
            records = self.client.list_records("cards")

        self.assertEqual([item["record_id"] for item in records], ["one", "two"])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].kwargs["params"]["page_token"], "next")

    def test_tenant_token_is_reused(self) -> None:
        token_response = _Response(
            {
                "code": 0,
                "tenant_access_token": "tenant-token",
                "expire": 7200,
            }
        )
        fields_response = _Response({"code": 0, "data": {"items": []}})
        with (
            patch("core.feishu_api.requests.post", return_value=token_response) as token_request,
            patch("core.feishu_api.requests.request", return_value=fields_response) as api_request,
        ):
            self.client.list_fields("cards")
            self.client.list_fields("cards")

        self.assertEqual(token_request.call_count, 1)
        self.assertEqual(api_request.call_count, 2)
        self.assertEqual(
            api_request.call_args.kwargs["headers"]["Authorization"],
            "Bearer tenant-token",
        )


if __name__ == "__main__":
    unittest.main()
