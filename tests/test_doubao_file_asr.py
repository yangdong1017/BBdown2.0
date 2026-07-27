from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.asr_task import process_file_asr_task
from core.doubao_file_asr import MEDIA_CONTENT_TYPES, DoubaoFileASRResult, transcribe_doubao_file
from core.media import MEDIA_EXTENSIONS
from core.tos_public_storage import PublicTOSObject


class FakeStorage:
    def __init__(self, output_path: Path | None = None, *, delete_result: bool = True) -> None:
        self.output_path = output_path
        self.delete_result = delete_result
        self.upload_calls: list[dict[str, object]] = []
        self.deleted: list[PublicTOSObject] = []
        self.output_existed_when_deleted = False

    def upload(self, path, *, suffix, content_type, stopped):
        self.upload_calls.append(
            {"path": Path(path), "suffix": suffix, "content_type": content_type, "stopped": stopped}
        )
        return PublicTOSObject(f"asr-temp/file{suffix}", f"https://example.com/asr-temp/file{suffix}")

    def delete(self, uploaded):
        self.deleted.append(uploaded)
        if self.output_path is not None:
            self.output_existed_when_deleted = self.output_path.exists()
        return self.delete_result


class DoubaoFileASRTests(unittest.TestCase):
    def test_every_selectable_media_format_has_an_upload_content_type(self) -> None:
        self.assertEqual(set(MEDIA_CONTENT_TYPES), MEDIA_EXTENSIONS)

    @patch("core.doubao_file_asr.transcribe_doubao_url", return_value="识别结果")
    def test_supported_media_uploads_original_bytes_without_conversion(self, transcribe) -> None:
        for suffix, content_type in MEDIA_CONTENT_TYPES.items():
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / f"source{suffix}"
                output = root / "source.txt"
                source.write_bytes(f"original-{suffix}".encode())
                storage = FakeStorage(output)
                statuses: list[str] = []

                result = transcribe_doubao_file(
                    source,
                    output,
                    stopped=lambda: False,
                    status_callback=statuses.append,
                    storage=storage,
                )

                self.assertEqual(result.output_path, str(output))
                self.assertTrue(result.cleanup_ok)
                self.assertEqual(output.read_text(encoding="utf-8"), "识别结果")
                self.assertEqual(statuses, ["上传中", "识别中"])
                self.assertEqual(storage.upload_calls[0]["path"], source)
                self.assertEqual(storage.upload_calls[0]["suffix"], suffix)
                self.assertEqual(storage.upload_calls[0]["content_type"], content_type)
                self.assertEqual(source.read_bytes(), f"original-{suffix}".encode())
                self.assertTrue(storage.output_existed_when_deleted)
                transcribe.assert_called_with(
                    f"https://example.com/asr-temp/file{suffix}",
                    "txt",
                    stopped=unittest.mock.ANY,
                    infer_format=False,
                )

    @patch("core.doubao_file_asr.transcribe_doubao_url", return_value="识别结果")
    def test_cleanup_failure_keeps_completed_transcript(self, _transcribe) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "speech.mp3"
            output = root / "speech.txt"
            source.write_bytes(b"audio")

            result = transcribe_doubao_file(
                source,
                output,
                stopped=lambda: False,
                storage=FakeStorage(output, delete_result=False),
            )

            self.assertTrue(output.exists())
            self.assertFalse(result.cleanup_ok)

    @patch("core.doubao_file_asr.transcribe_doubao_url", side_effect=RuntimeError("识别失败"))
    def test_recognition_failure_still_deletes_cloud_object(self, _transcribe) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "speech.wav"
            output = root / "speech.txt"
            source.write_bytes(b"audio")
            storage = FakeStorage(output)

            with self.assertRaisesRegex(RuntimeError, "识别失败"):
                transcribe_doubao_file(
                    source,
                    output,
                    stopped=lambda: False,
                    storage=storage,
                )

            self.assertEqual(len(storage.deleted), 1)
            self.assertFalse(output.exists())

    @patch(
        "core.asr_task.transcribe_doubao_file",
        return_value=DoubaoFileASRResult("output.txt", cleanup_ok=False),
    )
    def test_task_reports_cleanup_warning_without_failing(self, _transcribe) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "speech.mp3"
            source.write_bytes(b"audio")

            result = process_file_asr_task(
                index=0,
                path=str(source),
                engine_name="豆包",
                export_format="txt",
                output_path=root / "speech.txt",
                ffmpeg_path=None,
                stopped=lambda: False,
            )

        self.assertEqual(result.status, "ok")
        self.assertIn("转写成功，但云端临时文件清理失败", result.message)


if __name__ == "__main__":
    unittest.main()
