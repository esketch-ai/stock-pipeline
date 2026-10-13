import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from video_files import latest_video, video_filename, video_ticker
import stage5_publish


class VideoFilesTest(unittest.TestCase):
    def test_name_and_legacy_codes(self):
        self.assertEqual(video_filename("0220W0", "한화머시너리앤서비스홀딩스", datetime(2026, 10, 13)),
                         "0220W0_한화머시너리앤서비스홀딩스_20261013.mp4")
        for name in ["001210.mp4", "001210_001.mp4", "001210_금호전기_20261013.mp4"]:
            self.assertEqual(video_ticker(Path(name)), "001210")

    def test_latest_includes_new_and_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "001210.mp4"
            new = root / "001210_금호전기_20261013.mp4"
            old.touch()
            new.touch()
            os.utime(old, (1, 1))
            self.assertEqual(latest_video(root, "001210"), new)

    def test_publish_uses_ticker_metadata(self):
        qc = stage5_publish.QCResult(Path("001210_금호전기_20261013.mp4"), True, 420, 3840, 2160, 500, "OK")
        with patch.object(stage5_publish, "publish", return_value=None) as publish:
            stage5_publish.publish_all([qc], {"001210": {"name": "금호전기"}})
            self.assertIn("금호전기", publish.call_args.args[1])
