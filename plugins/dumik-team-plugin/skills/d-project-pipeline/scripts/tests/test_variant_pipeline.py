import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import build_canvas_pipeline as mod


class VariantSkuPipelineTests(unittest.TestCase):
    def test_prepare_variant_batch_scans_finished_and_writes_temp_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "成品" / "详情_790xn").mkdir(parents=True)
            (root / "成品" / "主图_3x4").mkdir(parents=True)
            (root / "设定集" / "白底图").mkdir(parents=True)

            Image.new("RGB", (90, 160), (200, 200, 200)).save(root / "成品" / "详情_790xn" / "S01_健康对比.png")
            Image.new("RGB", (90, 120), (200, 200, 200)).save(root / "成品" / "主图_3x4" / "M01_门面主图.png")
            ref_black = root / "设定集" / "白底图" / "磨砂黑_白底.png"
            Image.new("RGB", (100, 100), (30, 30, 30)).save(ref_black)

            res = mod.prepare_variant_batch(
                root,
                variant_sku="磨砂黑",
                variant_ref=ref_black,
                variant_desc="替换为磨砂黑纯钛哑光涂层",
                count=2,
            )
            self.assertTrue(res["ok"])
            self.assertEqual(res["count"], 2)
            self.assertEqual(res["modelPriority"], ["seedream-5.5", "seedream-5-pro", "banana2.1"])
            # No JSON written inside project root
            self.assertEqual(list(root.rglob("*.json")), [])
            temp_json = Path(res["designflowItemsFile"])
            self.assertTrue(temp_json.is_file())
            ratios = {it["ratio"] for it in res["items"]}
            self.assertEqual(ratios, {"9:16", "3:4"})
            temp_json.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
