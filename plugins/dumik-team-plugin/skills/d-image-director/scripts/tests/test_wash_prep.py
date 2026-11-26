import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import wash_prep as mod


class WashPrepTests(unittest.TestCase):
    def test_resolve_box_percentage_and_pixels(self):
        self.assertEqual(mod.resolve_box([0.2, 0.25, 0.8, 0.75], (1000, 800)), [200, 200, 800, 600])
        self.assertEqual(mod.resolve_box([100, 150, 400, 500], (1000, 800)), [100, 150, 400, 500])

    def test_single_wash_erases_product_text_and_pads_to_9_16(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref_path = root / "竞品参考.png"
            prod_path = root / "白底主品.png"
            # 1:1 square image with warm cream background, dark text bar on top, competitor block in center
            im = Image.new("RGB", (800, 800), (230, 220, 205))
            draw = ImageDraw.Draw(im)
            draw.rectangle([120, 40, 680, 120], fill=(30, 30, 30))  # text area
            draw.rectangle([240, 240, 560, 640], fill=(90, 110, 130))  # competitor product
            im.save(ref_path)
            Image.new("RGB", (512, 512), (255, 255, 255)).save(prod_path)

            workdir = root / "wash_tmp"
            rc = mod.main([
                "single",
                "--ref", str(ref_path),
                "--product-ref", str(prod_path),
                "--product-desc", "哑光钛灰色直身保温杯",
                "--erase-box", "0.3", "0.3", "0.7", "0.8",
                "--text-box", "0.15", "0.05", "0.85", "0.15",
                "--target-ratio", "9:16",
                "--name", "S02_场景洗图",
                "--workdir", str(workdir),
            ])
            self.assertEqual(rc, 0)
            washed_path = workdir / "S02_场景洗图_脱壳底图.png"
            preview_path = workdir / "S02_场景洗图_洗图预览.png"
            self.assertTrue(washed_path.is_file())
            self.assertTrue(preview_path.is_file())

            with Image.open(washed_path) as wim:
                # 800x800 padded to 9:16 -> 800x1422
                self.assertEqual(wim.width, 800)
                self.assertAlmostEqual(wim.width / wim.height, 9 / 16, delta=0.02)
                # Top padded area should match cream background
                self.assertEqual(wim.getpixel((400, 20)), (230, 220, 205))
                # Center of erased competitor product (shifted down by pad_top) must be magenta
                pad_top = int(round((wim.height - 800) * 0.72))
                self.assertEqual(wim.getpixel((400, pad_top + 440)), (255, 0, 255))
                # Text area should be filled with sampled cream background, not dark (30,30,30)
                self.assertEqual(wim.getpixel((400, pad_top + 80)), (230, 220, 205))

    def test_batch_wash_generates_chinese_outputs_and_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref1 = root / "r1.png"
            prod1 = root / "p1.png"
            Image.new("RGB", (600, 800), (200, 200, 195)).save(ref1)
            Image.new("RGB", (400, 400), (255, 255, 255)).save(prod1)

            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "name": "S03_咖啡桌",
                                "ref_image": "r1.png",
                                "product_ref": "p1.png",
                                "product_desc": "雪花钛直身杯",
                                "erase_boxes": [[0.25, 0.35, 0.75, 0.85]],
                                "target_ratio": "9:16",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            workdir = root / "batch_wash"
            rc = mod.main([
                "batch",
                "--manifest", str(manifest),
                "--project-root", str(root),
                "--workdir", str(workdir),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue((workdir / "S03_咖啡桌_脱壳底图.png").is_file())
            self.assertTrue((workdir / "洗图联系表.png").is_file())
            jobs = json.loads((workdir / "洗图并发任务.json").read_text(encoding="utf-8"))
            self.assertEqual(len(jobs["items"]), 1)
            self.assertLessEqual(len(jobs["items"][0]["prompt"]), 300)


if __name__ == "__main__":
    unittest.main()
