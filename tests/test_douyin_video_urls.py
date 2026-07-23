from __future__ import annotations

import unittest

from core.douyin_video_urls import extract_douyin_video_links


class DouyinVideoUrlTests(unittest.TestCase):
    def test_extracts_links_from_arbitrary_text_and_deduplicates(self) -> None:
        text = """
        文本 https://aweme.snssdk.com/aweme/v1/play/?video_id=video_a
        [重复](https://aweme.snssdk.com/aweme/v1/play/?video_id=video_a)
        https://aweme.snssdk.com/aweme/v1/play/?video_id=video_b
        """

        links = extract_douyin_video_links(text)

        self.assertEqual([link.video_id for link in links], ["video_a", "video_b"])
        self.assertEqual(
            links[0].url,
            "https://aweme.snssdk.com/aweme/v1/play/?video_id=video_a",
        )

    def test_ignores_unsupported_douyin_pages(self) -> None:
        text = """
        https://www.douyin.com/video/7661131131446292115
        https://www.douyin.com/note/7649818152348447579
        https://v.douyin.com/example/
        """

        self.assertEqual(extract_douyin_video_links(text), [])


if __name__ == "__main__":
    unittest.main()
