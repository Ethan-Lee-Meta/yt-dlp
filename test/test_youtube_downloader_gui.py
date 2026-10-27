"""Offline tests for the YouTube desktop downloader backend."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "youtube_downloader"))
from backend import build_command, check_proxy, check_url, parse_output


class YouTubeDownloaderBackendTests(unittest.TestCase):
    VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    PLAYLIST = "https://www.youtube.com/playlist?list=PL1234567890"
    CHANNEL = "https://www.youtube.com/@examplechannel"

    def test_modes(self):
        self.assertEqual(check_url(self.VIDEO, "single"), self.VIDEO)
        self.assertEqual(check_url(self.PLAYLIST, "playlist"), self.PLAYLIST)
        self.assertEqual(check_url(self.CHANNEL, "channel"), self.CHANNEL)
        self.assertEqual(check_url("https://youtu.be/abc", "single"), "https://youtu.be/abc")

    def test_reject_other_hosts_and_wrong_modes(self):
        for url in (
            "https://youtube.com.evil.example/watch?v=abc",
            "file:///C:/Windows/system.ini",
            "http://localhost/watch?v=abc",
            "https://user:password@youtube.com/watch?v=abc",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                check_url(url, "single")
        with self.assertRaises(ValueError):
            check_url(self.VIDEO, "channel")
        with self.assertRaises(ValueError):
            check_url(self.CHANNEL, "single")

    def test_proxy_validation(self):
        self.assertEqual(check_proxy(""), "")
        self.assertEqual(check_proxy("http://127.0.0.1:7890"), "http://127.0.0.1:7890")
        with self.assertRaises(ValueError):
            check_proxy("http://user:password@localhost:7890")

    def test_archive_is_stable_and_scoped_to_source(self):
        with tempfile.TemporaryDirectory() as td:
            a = build_command(["yt-dlp"], self.PLAYLIST, "playlist", Path(td))
            b = build_command(["yt-dlp"], self.PLAYLIST, "playlist", Path(td))
            c = build_command(["yt-dlp"], self.CHANNEL, "channel", Path(td))
            archive_a = a[a.index("--download-archive") + 1]
            archive_b = b[b.index("--download-archive") + 1]
            archive_c = c[c.index("--download-archive") + 1]
            self.assertEqual(archive_a, archive_b)
            self.assertNotEqual(archive_a, archive_c)
            self.assertTrue(Path(archive_a).parent.is_dir())
            self.assertIn("--ignore-errors", a)
            self.assertIn("--no-playlist", build_command(["yt-dlp"], self.VIDEO, "single", Path(td)))

    def test_quality_subtitles_and_proxy_are_arguments(self):
        with tempfile.TemporaryDirectory() as td:
            cmd = build_command(
                ["yt-dlp"], self.VIDEO, "single", Path(td),
                "1080", True, "Edge", "http://127.0.0.1:7890",
            )
            self.assertEqual(cmd[0], "yt-dlp")
            self.assertEqual(cmd[-1], self.VIDEO)
            self.assertIn("bv*[height<=1080]+ba/b[height<=1080]", cmd)
            self.assertIn("--cookies-from-browser", cmd)
            self.assertIn("edge", cmd)
            self.assertIn("--write-auto-subs", cmd)
            self.assertIn("--proxy", cmd)
            self.assertIn("--continue", cmd)

    def test_progress_parser(self):
        self.assertEqual(
            parse_output("__YTDLP_PROGRESS__ 41.5%|1.2MiB/s|00:14\n"),
            ("progress", 41.5, "1.2MiB/s", "00:14"),
        )
        self.assertEqual(parse_output("__YTDLP_DONE__video123\n"), ("done", "video123"))
        self.assertEqual(parse_output("WARNING: skipped\n"), ("log", "WARNING: skipped"))


if __name__ == "__main__":
    unittest.main()
