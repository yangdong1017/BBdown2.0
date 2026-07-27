from __future__ import annotations

import unittest

from core.douyin_audio_urls import extract_douyin_audio_links


STANDARD_AUDIO_LINK = (
    "https://lf9-music-east.douyinstatic.com/obj/ies-music-hj/"
    "7546439142222302011.mp3"
)


class DouyinAudioUrlTests(unittest.TestCase):
    def test_extracts_douyin_audio_links_and_deduplicates(self) -> None:
        text = f"""
        音频：{STANDARD_AUDIO_LINK}
        重复：{STANDARD_AUDIO_LINK}
        https://example.com/not-douyin.mp3
        """

        links = extract_douyin_audio_links(text)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].audio_id, "7546439142222302011")
        self.assertEqual(links[0].task_id, "7546439142222302011")
        self.assertEqual(links[0].file_suffix, ".mp3")
        self.assertEqual(links[0].url, STANDARD_AUDIO_LINK)

    def test_ignores_video_and_share_links(self) -> None:
        text = """
        https://aweme.snssdk.com/aweme/v1/play/?video_id=video_a
        https://www.douyin.com/video/123456
        """

        self.assertEqual(extract_douyin_audio_links(text), [])


if __name__ == "__main__":
    unittest.main()
