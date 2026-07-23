from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.output_paths import OutputPathAllocator


class OutputPathAllocatorTests(unittest.TestCase):
    def test_existing_path_can_be_kept_for_first_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.txt"
            target.write_text("existing", encoding="utf-8")
            allocator = OutputPathAllocator()

            first = allocator.reserve(target, allow_existing=True)
            second = allocator.reserve(target, allow_existing=True)

            self.assertEqual(first, target)
            self.assertEqual(second.name, "result (2).txt")

    def test_download_target_never_overwrites_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "audio.m4a"
            target.write_bytes(b"existing")

            reserved = OutputPathAllocator().reserve(target)

            self.assertEqual(reserved.name, "audio (2).m4a")

    def test_concurrent_reservations_are_unique(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "same.txt"
            allocator = OutputPathAllocator()
            with ThreadPoolExecutor(max_workers=8) as pool:
                paths = list(pool.map(lambda _index: allocator.reserve(target), range(20)))

            self.assertEqual(len({str(path) for path in paths}), 20)


if __name__ == "__main__":
    unittest.main()
