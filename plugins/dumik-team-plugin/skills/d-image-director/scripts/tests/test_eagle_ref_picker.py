import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import eagle_ref_picker as mod


class EagleRefPickerTests(unittest.TestCase):
    def test_filters_used_ids_and_builds_preview(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / "proj"
            proj.mkdir()
            (proj / "design.md").write_text("已使用参考：#55 MWKGD3MFY8Q3B", encoding="utf-8")

            img_new = root / "new_ref.png"
            Image.new("RGB", (400, 600), (180, 170, 160)).save(img_new)

            def fake_get(url, timeout=3.0):
                if url.endswith("/library/info"):
                    return {
                        "status": "success",
                        "data": {
                            "folders": [{"id": "FLD001", "name": "纯钛杯子", "children": []}],
                        },
                    }
                return {
                    "status": "success",
                    "data": [
                        {"id": "MWKGD3MFY8Q3B", "name": "已用过的客厅图", "ext": "jpg", "filePath": str(img_new)},
                        {"id": "MW9999AAA111B", "name": "晨间餐桌新图", "ext": "png", "width": 400, "height": 600, "filePath": str(img_new)},
                    ],
                }

            with patch.object(mod, "_http_get_json", side_effect=fake_get):
                res = mod.query_eagle_candidates(folder="纯钛杯子", query="餐桌", project_root=proj, top=3)

            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["skipped_used_count"], 1)
            self.assertEqual(len(res["candidates"]), 1)
            self.assertEqual(res["candidates"][0]["id"], "MW9999AAA111B")
            self.assertTrue(Path(res["preview_sheet"]).is_file())
            Path(res["preview_sheet"]).unlink(missing_ok=True)

    def test_offline_graceful_fallback(self):
        with patch.object(mod, "_http_get_json", side_effect=OSError("connection refused")):
            res = mod.query_eagle_candidates(folder="纯钛杯子")
        self.assertEqual(res["status"], "eagle_offline")
        self.assertEqual(res["candidates"], [])


if __name__ == "__main__":
    unittest.main()
