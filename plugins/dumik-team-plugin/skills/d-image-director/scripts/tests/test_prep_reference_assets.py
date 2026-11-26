import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import prep_reference_assets as mod


class PrepReferenceAssetsTests(unittest.TestCase):
    def test_stitch_white_identity_card(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            imgs = []
            for idx, col in enumerate([(180, 120, 100), (100, 160, 180), (120, 180, 110)], start=1):
                p = root / f"view_{idx}.png"
                im = Image.new("RGB", (600, 600), (255, 255, 255))
                ImageDraw.Draw(im).rectangle([200, 150, 400, 450], fill=col)
                im.save(p)
                imgs.append(p)

            out_card = root / "00_水杯_多视图白底身份卡.jpg"
            res = mod.stitch_white_identity_card(imgs, out_card, labels=["正视", "侧视", "顶视"])
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["count"], 3)
            self.assertTrue(out_card.is_file())
            with Image.open(out_card) as card:
                self.assertLessEqual(card.width, 2560)
                self.assertGreater(card.width, card.height)

    def test_compress_oversized_refs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            big = root / "超大实拍.png"
            small = root / "正常小图.jpg"
            Image.new("RGB", (3200, 2400), (140, 150, 160)).save(big)
            Image.new("RGB", (800, 800), (120, 120, 120)).save(small)

            res = mod.compress_oversized_refs(root, max_mb=4.0, max_edge=2048)
            self.assertEqual(res["compressed_count"], 1)
            self.assertEqual(res["skipped_count"], 1)
            out_lite = root / "超大实拍_轻量2K.jpg"
            self.assertTrue(out_lite.is_file())
            with Image.open(out_lite) as im:
                self.assertLessEqual(max(im.size), 2048)

    def test_detect_white_bg_slots_three_views(self):
        sheet = Image.new("RGB", (1800, 600), (255, 255, 255))
        draw = ImageDraw.Draw(sheet)
        draw.rectangle([100, 100, 450, 500], fill=(160, 160, 165))
        draw.rectangle([700, 120, 1050, 480], fill=(130, 150, 170))
        draw.rectangle([1300, 100, 1650, 500], fill=(180, 140, 120))

        slots = mod.detect_white_bg_slots(sheet)
        self.assertEqual(len(slots), 3)
        # Left-to-right ordering
        self.assertLess(slots[0][0], slots[1][0])
        self.assertLess(slots[1][0], slots[2][0])
        self.assertAlmostEqual(slots[1][0], 700, delta=15)
        self.assertAlmostEqual(slots[1][2], 1050, delta=15)

    def test_grid_overlay_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "scene.png"
            out = root / "scene_坐标网格.jpg"
            Image.new("RGB", (900, 1600), (60, 70, 80)).save(src)

            rc = mod.main(["grid-overlay", "--image", str(src), "--out", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.is_file())
            with Image.open(out) as im:
                self.assertEqual(im.size, (900, 1600))


if __name__ == "__main__":
    unittest.main()
