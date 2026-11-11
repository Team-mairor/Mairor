"""유튜브 받기: 403 거절은 다시 받고, 다른 실패는 바로 올린다."""

import unittest
from pathlib import Path
from unittest import mock

import yt_dlp

from processor.clients import youtube

FORBIDDEN = yt_dlp.utils.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
DONE = {"requested_downloads": [{"filepath": "v.mp4"}]}


def fake_ydl(*results):
    client = mock.MagicMock()
    client.__enter__.return_value.extract_info.side_effect = list(results)
    return mock.patch("yt_dlp.YoutubeDL", return_value=client), client.__enter__.return_value


class DownloadTests(unittest.TestCase):
    def test_forbidden_is_downloaded_again(self):
        patcher, ydl = fake_ydl(FORBIDDEN, DONE)
        with patcher, mock.patch.object(youtube.time, "sleep") as sleep:
            path, _ = youtube.download("u", "f", Path("."), "v")
        self.assertEqual(path, Path("v.mp4"))
        self.assertEqual(ydl.extract_info.call_count, 2)
        sleep.assert_called_once_with(youtube.RETRY_WAIT)

    def test_gives_up_after_the_last_attempt(self):
        patcher, ydl = fake_ydl(*[FORBIDDEN] * youtube.DOWNLOAD_ATTEMPTS)
        with patcher, mock.patch.object(youtube.time, "sleep"), self.assertRaises(yt_dlp.utils.DownloadError):
            youtube.download("u", "f", Path("."), "v")
        self.assertEqual(ydl.extract_info.call_count, youtube.DOWNLOAD_ATTEMPTS)

    def test_other_failures_are_not_retried(self):
        patcher, ydl = fake_ydl(yt_dlp.utils.DownloadError("ERROR: Video unavailable"), DONE)
        with patcher, mock.patch.object(youtube.time, "sleep") as sleep, \
                self.assertRaises(yt_dlp.utils.DownloadError):
            youtube.download("u", "f", Path("."), "v")
        self.assertEqual(ydl.extract_info.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
