import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
import designflow_archive_outputs as mod


class DesignFlowArchiveOutputsTests(unittest.TestCase):
    def test_extract_dedupe_and_ratio_check(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img_vertical = root / "a.png"
            img_square = root / "b.png"
            Image.new("RGB", (90, 160), (200, 200, 200)).save(img_vertical)
            Image.new("RGB", (100, 100), (180, 180, 180)).save(img_square)

            # Nested JSON mimicking DesignFlow output log with duplicate path
            log_file = root / "output.txt"
            payload = {
                "assets": [
                    {"filePath": str(img_vertical)},
                    {"filePath": str(img_vertical)},
                    {"nested": json.dumps({"localPath": str(img_square)})},
                ]
            }
            log_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            sources = mod.extract_image_paths([str(log_file)])
            self.assertEqual(len(sources), 2)

            out_dir = root / "制作" / "S01_测试"
            summary = mod.archive_images(sources, out_dir, prefix="b21", expect_ratio="9:16")
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["count"], 2)
            self.assertTrue((out_dir / "b21_01.png").is_file())
            self.assertTrue((out_dir / "b21_02.png").is_file())
            self.assertTrue(summary["files"][0]["ratio_ok"])
            self.assertFalse(summary["files"][1]["ratio_ok"])
            self.assertEqual(len(summary["ratio_warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
