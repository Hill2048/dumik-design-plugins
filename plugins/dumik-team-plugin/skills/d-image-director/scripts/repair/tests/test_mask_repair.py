import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

REPAIR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPAIR_DIR))
import mask_repair as mod


class MaskRepairTests(unittest.TestCase):
    def test_single_prepare_and_paste_preserves_untouched_pixels(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Create a 900x1600 vertical image with distinct background color
            img_path = root / "full.png"
            white_path = root / "white.png"
            base = Image.new("RGB", (900, 1600), (40, 60, 80))
            # Draw a "product" block at [250, 500, 650, 1000]
            for x in range(250, 650):
                for y in range(500, 1000):
                    base.putpixel((x, y), (180, 180, 185))
            base.save(img_path)
            Image.new("RGB", (512, 512), (255, 255, 255)).save(white_path)

            workdir = root / "tmp_work"
            rc = mod.main([
                "prepare-single",
                "--image", str(img_path),
                "--white-ref", str(white_path),
                "--product-box", "250", "500", "650", "1000",
                "--defect-box", "550", "600", "640", "760",
                "--defect-desc", "按白底图还原扁平 D 型焊把",
                "--workdir", str(workdir),
            ])
            self.assertEqual(rc, 0)
            meta_path = workdir / "full_meta.json"
            self.assertTrue(meta_path.is_file())
            self.assertTrue((workdir / "full_预览图.png").is_file())

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertIn(meta["ratio"], {"1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9"})
            # Verify magenta mask pixel exists inside masked crop
            with Image.open(meta["masked_crop"]) as masked_im:
                lx1, ly1, lx2, ly2 = meta["defect_boxes_local"][0]
                cx, cy = (lx1 + lx2) // 2, (ly1 + ly2) // 2
                r, g, b = masked_im.convert("RGB").getpixel((cx, cy))
                self.assertEqual((r, g, b), (255, 0, 255))

            # Simulate AI returning a repaired crop (greenish tint in product center)
            repaired_crop_path = workdir / "ai_repaired.png"
            repaired_im = Image.new("RGB", tuple(meta["crop_size"]), (120, 190, 140))
            repaired_im.save(repaired_crop_path)

            out_final = root / "final_repaired.png"
            rc2 = mod.main([
                "paste-single",
                "--meta", str(meta_path),
                "--repaired", str(repaired_crop_path),
                "--out", str(out_final),
                "--feather", "20",
                "--cleanup",
            ])
            self.assertEqual(rc2, 0)
            self.assertTrue(out_final.is_file())
            self.assertFalse(workdir.exists())  # cleanup removed temp dir

            with Image.open(out_final) as fin:
                self.assertEqual(fin.size, (900, 1600))
                # Corner background pixel outside crop_box must be 100% untouched
                self.assertEqual(fin.convert("RGB").getpixel((10, 10)), (40, 60, 80))
                # Center of product should reflect repaired image
                self.assertEqual(fin.convert("RGB").getpixel((450, 750)), (120, 190, 140))

    def test_batch_prepare_and_paste(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img1 = root / "s01.png"
            img2 = root / "s02.png"
            white = root / "white.png"
            Image.new("RGB", (600, 1000), (50, 50, 50)).save(img1)
            Image.new("RGB", (600, 1000), (70, 70, 70)).save(img2)
            Image.new("RGB", (400, 400), (255, 255, 255)).save(white)

            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "image_id": "S01_健康对比",
                                "image_path": "s01.png",
                                "white_ref": "white.png",
                                "verdict": "blocked",
                                "product_box": [150, 300, 450, 700],
                                "defect_boxes": [[380, 360, 440, 500]],
                                "defect_desc": "修复把手弧度",
                                "out_path": "out/s01_fixed.png",
                            },
                            {
                                "image_id": "S02_已通过",
                                "image_path": "s02.png",
                                "white_ref": "white.png",
                                "verdict": "passed",
                                "product_box": [150, 300, 450, 700],
                                "defect_boxes": [[380, 360, 440, 500]],
                                "defect_desc": "跳过",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            workdir = root / "batch_tmp"
            rc = mod.main([
                "prepare-batch",
                "--manifest", str(manifest_path),
                "--project-root", str(root),
                "--workdir", str(workdir),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue((workdir / "色块联系表.png").is_file())
            df_items = json.loads((workdir / "designflow_items.json").read_text(encoding="utf-8"))
            self.assertEqual(len(df_items["items"]), 1)  # passed item skipped
            self.assertEqual(df_items["items"][0]["models"], ["seedream-5.5"])
            self.assertEqual(df_items["items"][0]["modelPriority"], ["seedream-5.5", "seedream-5-pro", "banana2.1"])

            repaired_dir = root / "repaired_in"
            repaired_dir.mkdir()
            Image.new("RGB", (512, 512), (200, 160, 120)).save(repaired_dir / "S01_健康对比_01.png")

            rc2 = mod.main([
                "paste-batch",
                "--workdir", str(workdir),
                "--repaired-dir", str(repaired_dir),
                "--cleanup",
            ])
            self.assertEqual(rc2, 0)
            self.assertTrue((root / "out" / "s01_fixed.png").is_file())
            self.assertFalse(workdir.exists())

    def test_layered_psd_and_tiff_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = Image.new("RGB", (400, 600), (30, 50, 70))
            repaired = Image.new("RGB", (200, 200), (210, 150, 90))
            crop_box = [100, 200, 300, 400]

            psd_path = root / "result.psd"
            tif_path = root / "result.tif"
            mod.save_pasted_output(base, repaired, crop_box, psd_path, feather=20)
            mod.save_pasted_output(base, repaired, crop_box, tif_path, feather=20)

            self.assertTrue(psd_path.is_file())
            self.assertTrue(tif_path.is_file())

            raw = psd_path.read_bytes()
            self.assertTrue(raw.startswith(b"8BPS"))
            self.assertIn(b"8BIMluni", raw)
            # Multi-candidate layered PSD (Base + 2 candidate layers)
            repaired2 = Image.new("RGB", (200, 200), (90, 210, 150))
            multi_psd = root / "multi.psd"
            mod.save_pasted_output(base, [repaired, repaired2], crop_box, multi_psd, feather=20)
            mraw = multi_psd.read_bytes()
            self.assertIn("修复候选_01".encode("utf-16-be"), mraw)
            self.assertIn("修复候选_02".encode("utf-16-be"), mraw)
            with Image.open(multi_psd) as m_im:
                self.assertEqual(m_im.size, (400, 600))
                # Composite uses first candidate
                self.assertEqual(m_im.convert("RGB").getpixel((200, 300)), (210, 150, 90))
            # Pillow must be able to open the PSD composite preview and read exact pixels
            with Image.open(psd_path) as psd_im:
                self.assertEqual(psd_im.size, (400, 600))
                self.assertEqual(psd_im.convert("RGB").getpixel((5, 5)), (30, 50, 70))
                self.assertEqual(psd_im.convert("RGB").getpixel((200, 300)), (210, 150, 90))

            with Image.open(tif_path) as tif_im:
                self.assertEqual(tif_im.size, (400, 600))
                self.assertEqual(tif_im.convert("RGB").getpixel((5, 5)), (30, 50, 70))
                self.assertEqual(tif_im.convert("RGB").getpixel((200, 300)), (210, 150, 90))

    def test_white_ref_angle_crop_aligns_ratio(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img_path = root / "scene.png"
            sheet_white = root / "five_views.png"
            Image.new("RGB", (900, 1600), (40, 50, 60)).save(img_path)
            # Simulate a wide 5-view white-bg sheet (2500x600) with target view at [500, 100, 900, 500]
            w_im = Image.new("RGB", (2500, 600), (255, 255, 255))
            for x in range(500, 900):
                for y in range(100, 500):
                    w_im.putpixel((x, y), (190, 195, 200))
            w_im.save(sheet_white)

            workdir = root / "w_tmp"
            rc = mod.main([
                "prepare-single",
                "--image", str(img_path),
                "--white-ref", str(sheet_white),
                "--white-box", "500", "100", "900", "500",
                "--product-box", "250", "500", "650", "900",
                "--defect-box", "400", "550", "550", "700",
                "--defect-desc", "对齐角度修复",
                "--workdir", str(workdir),
            ])
            self.assertEqual(rc, 0)
            meta = json.loads((workdir / "scene_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(len(meta["white_ref_crops"]), 1)
            ref_crop_path = Path(meta["white_ref_crops"][0])
            self.assertTrue(ref_crop_path.is_file())
            with Image.open(ref_crop_path) as ref_im:
                # Cropped from 2500x600 sheet down to matched 1:1 square
                self.assertLess(ref_im.width, 800)
                self.assertAlmostEqual(ref_im.width / ref_im.height, 1.0, delta=0.12)


if __name__ == "__main__":
    unittest.main()
