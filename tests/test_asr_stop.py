from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bk_asr.BcutASR import BcutASR
from core.media import convert_to_mp3


class ASRStopTests(unittest.TestCase):
    def test_bcut_stops_before_network_request(self) -> None:
        engine = BcutASR(b"audio", stopped=lambda: True)
        engine.session.post = Mock()

        with self.assertRaisesRegex(RuntimeError, "已停止"):
            engine.upload()

        engine.session.post.assert_not_called()

    @patch("core.media.time.sleep")
    @patch("core.media.subprocess.Popen")
    def test_ffmpeg_process_is_killed_when_stopped(self, popen, _sleep) -> None:
        process = Mock()
        process.poll.return_value = None
        popen.return_value = process

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.mp3"
            output.write_bytes(b"partial")

            result = convert_to_mp3(
                "input.wav",
                output,
                "ffmpeg.exe",
                stopped=lambda: True,
            )

            self.assertFalse(result)
            self.assertFalse(output.exists())
            process.kill.assert_called_once()
            process.wait.assert_called_once()


if __name__ == "__main__":
    unittest.main()
