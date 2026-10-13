import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import archive
from stage5_publish import QCResult


class ArchiveQCTest(unittest.TestCase):
    def test_qc_path_is_serialized_and_other_fields_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "2026-10-13"
            run.mkdir()
            item = run / "001210.json"
            item.write_text(json.dumps({"ticker": "001210", "name": "금호전기"}))
            qc = QCResult(Path("output/001210.mp4"), True, 75, 3840, 2160, 133.7, "OK")
            with patch.object(archive, "ARCHIVE_DIR", root), patch.object(archive, "INDEX_FILE", root / "index.json"):
                self.assertTrue(archive.set_item_field("2026-10-13", "001210", "qc", vars(qc)))
            saved = json.loads(item.read_text())
            self.assertEqual(saved["name"], "금호전기")
            self.assertEqual(saved["qc"]["path"], "output/001210.mp4")
            self.assertTrue(saved["qc"]["ok"])


if __name__ == "__main__":
    unittest.main()
