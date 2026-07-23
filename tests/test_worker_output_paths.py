from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.asr_file_worker import ASRWorkerThread
from core.bilibili_workers import DownloadWorkerThread
from core.models import Toolchain
from core.url_asr_worker import UrlASRWorkerThread


class WorkerOutputPathTests(unittest.TestCase):
    def test_local_files_with_same_stem_get_distinct_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = ASRWorkerThread(
                [str(root / "one" / "same.mp3"), str(root / "two" / "same.mp3")],
                "必剪",
                "txt",
                5,
                str(root / "output"),
                None,
            )

            self.assertEqual([path.name for path in worker.output_paths], ["same.txt", "same (2).txt"])

    def test_urls_with_same_filename_get_distinct_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worker = UrlASRWorkerThread(
                ["https://one.example/audio.mp3", "https://two.example/audio.mp3"],
                "必剪",
                "txt",
                5,
                directory,
            )

            self.assertEqual([path.name for path in worker.output_paths], ["audio.txt", "audio (2).txt"])

    def test_bilibili_parallel_moves_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_dir = root / "output"
            worker = DownloadWorkerThread(
                [],
                str(save_dir),
                5,
                Toolchain(),
                root,
                "utf-8",
            )
            jobs = []
            for index in range(2):
                job = root / f"job-{index}"
                job.mkdir()
                (job / "same.m4a").write_bytes(f"file-{index}".encode())
                jobs.append(job)

            with ThreadPoolExecutor(max_workers=2) as pool:
                moved = list(pool.map(worker._move_job_outputs, jobs))

            output_files = sorted(save_dir.glob("*.m4a"))
            self.assertEqual(len(output_files), 2)
            self.assertEqual(len({path.read_bytes() for path in output_files}), 2)
            self.assertEqual(sum(len(paths) for paths in moved), 2)


if __name__ == "__main__":
    unittest.main()
