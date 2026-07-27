from __future__ import annotations

import errno
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.asr_file_worker import ASRWorkerThread
from core.asr_service import GENERIC_MESSAGE, format_task_error
from core.errors import UserFacingError
from core.url_asr_worker import UrlASRWorkerThread


def _http_error(status: int) -> requests.HTTPError:
    response = Mock()
    response.status_code = status
    return requests.HTTPError(f"{status} Server Error", response=response)


class FormatTaskErrorTests(unittest.TestCase):
    """Users must never see a raw exception string."""

    def test_our_own_messages_pass_through(self) -> None:
        self.assertEqual(
            format_task_error(UserFacingError("豆包识别失败：余额不足或服务未开通。")),
            "豆包识别失败：余额不足或服务未开通。",
        )

    def test_stop_is_still_recognisable(self) -> None:
        self.assertEqual(format_task_error(UserFacingError("已停止")), "已停止")
        self.assertEqual(format_task_error(RuntimeError("已停止")), "已停止")

    def test_unknown_exceptions_become_one_plain_sentence(self) -> None:
        for exc in (
            KeyError("segments"),
            ValueError("invalid literal for int() with base 10: 'abc'"),
            AttributeError("'NoneType' object has no attribute 'text'"),
            TypeError("unsupported operand"),
        ):
            with self.subTest(exc=type(exc).__name__):
                self.assertEqual(format_task_error(exc), GENERIC_MESSAGE)

    def test_unknown_exceptions_are_written_to_the_log(self) -> None:
        with patch("core.asr_service.logging.getLogger") as get_logger:
            format_task_error(KeyError("segments"))
        get_logger.return_value.error.assert_called_once()

    def test_http_errors_get_a_reason_the_user_can_act_on(self) -> None:
        cases = {
            412: "识别服务结果暂未就绪",
            401: "API Key",
            403: "API Key",
            429: "请求过于频繁",
            500: "暂时不可用",
            503: "暂时不可用",
            418: "HTTP 418",
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                self.assertIn(expected, format_task_error(_http_error(status)))

    def test_network_problems_are_named_plainly(self) -> None:
        self.assertIn("超时", format_task_error(requests.Timeout()))
        self.assertIn("网络连接失败", format_task_error(requests.ConnectionError()))
        self.assertIn("网络请求失败", format_task_error(requests.RequestException()))

    def test_disk_problems_are_named_plainly(self) -> None:
        no_space = OSError(errno.ENOSPC, "No space left on device")
        self.assertIn("磁盘空间不足", format_task_error(no_space))
        self.assertIn("权限", format_task_error(PermissionError("denied")))
        self.assertIn("找不到", format_task_error(FileNotFoundError("gone.mp3")))


class StoppedCountTests(unittest.TestCase):
    """A stopped batch must still add up to the total."""

    def test_url_batch_summary_accounts_for_every_link(self) -> None:
        urls = [f"https://example.com/{index}.mp3" for index in range(5)]
        worker = UrlASRWorkerThread(
            urls=urls,
            engine_name="必剪",
            export_format="txt",
            concurrency=5,
            out_dir=tempfile.gettempdir(),
        )
        worker.stop_flag.set()

        result = worker._run_batch()

        self.assertTrue(result.stopped)
        self.assertEqual(result.ok + result.skip + result.fail + result.stopped_count, result.total)
        self.assertEqual(result.stopped_count, 5)
        self.assertIn("已停止 5", result.summary)

    def test_finished_url_batch_summary_is_unchanged(self) -> None:
        worker = UrlASRWorkerThread(
            urls=[],
            engine_name="必剪",
            export_format="txt",
            concurrency=5,
            out_dir=tempfile.gettempdir(),
        )

        summary = worker._run_batch().summary

        self.assertTrue(summary.startswith("完成: 成功 0 跳过 0 失败 0 |"))
        self.assertNotIn("已停止", summary)

    def test_file_batch_summary_accounts_for_every_file(self) -> None:
        worker = ASRWorkerThread(
            files=[f"/tmp/clip{index}.mp3" for index in range(3)],
            engine_name="必剪",
            export_format="txt",
            concurrency=5,
            out_dir=tempfile.gettempdir(),
            ffmpeg_path=None,
        )
        worker.stop_flag.set()

        summary = worker._run_batch()

        self.assertIn("未处理 3", summary)


if __name__ == "__main__":
    unittest.main()
