from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from core.doubao_asr import (
    DoubaoASRError,
    HTTP_TIMEOUT,
    _format_api_error,
    _post_with_retry,
    _submit_task,
    _wait_or_stop,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        headers: dict[str, str] | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._data = data or {}
        self.content = b"{}"

    def json(self) -> dict[str, object]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class DoubaoASRTests(unittest.TestCase):
    def test_silence_error_is_readable_and_hides_raw_response(self) -> None:
        message = _format_api_error(
            "20000003",
            "[Normal silence audio] Handle response: no valid speech in audio",
            {},
        )

        self.assertEqual(message, "没有检测到有效人声，请确认音频内容后重试。")
        self.assertNotIn("Normal silence", message)

    @patch("core.doubao_asr.requests.post")
    def test_submit_can_omit_format_for_model_auto_detection(self, post) -> None:
        post.return_value = FakeResponse(
            headers={"X-Api-Status-Code": "20000000", "X-Tt-Logid": "log-auto"}
        )

        _submit_task("key", "request", "https://example.com/video.mp4", "")

        self.assertEqual(post.call_args.kwargs["json"]["audio"], {"url": "https://example.com/video.mp4"})

    @patch("core.doubao_asr._wait_or_stop")
    @patch("core.doubao_asr.requests.post")
    def test_submit_retries_transient_network_error(self, post, wait) -> None:
        post.side_effect = [
            requests.ConnectionError("reset"),
            FakeResponse(headers={"X-Api-Status-Code": "20000000", "X-Tt-Logid": "log-1"}),
        ]

        log_id = _submit_task("key", "request", "https://example.com/audio.mp3", "mp3")

        self.assertEqual(log_id, "log-1")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["timeout"], HTTP_TIMEOUT)
        wait.assert_called_once()

    @patch("core.doubao_asr._wait_or_stop")
    @patch("core.doubao_asr.requests.post")
    def test_retries_busy_http_response(self, post, wait) -> None:
        post.side_effect = [FakeResponse(502), FakeResponse(200)]

        response = _post_with_retry(
            "https://example.com/query",
            headers={},
            payload={},
            stopped=None,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_count, 2)
        wait.assert_called_once()

    @patch("core.doubao_asr._wait_or_stop")
    @patch("core.doubao_asr.requests.post")
    def test_network_failure_has_readable_error(self, post, _wait) -> None:
        post.side_effect = requests.ConnectionError("reset")

        with self.assertRaisesRegex(DoubaoASRError, "网络连接异常"):
            _post_with_retry(
                "https://example.com/query",
                headers={},
                payload={},
                stopped=None,
            )

        self.assertEqual(post.call_count, 3)

    def test_wait_stops_without_sleeping(self) -> None:
        with self.assertRaisesRegex(DoubaoASRError, "已停止"):
            _wait_or_stop(30, lambda: True)


if __name__ == "__main__":
    unittest.main()
