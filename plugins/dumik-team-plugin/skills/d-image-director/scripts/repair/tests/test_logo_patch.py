import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPAIR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPAIR_DIR))
import logo_patch as mod


class LogoPatchTests(unittest.TestCase):
    def _make_sample_logo(self, path: Path) -> None:
        im = Image.new("RGBA", (240, 80), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        # Bold horizontal bar + vertical strokes simulating crisp logo letters
        draw.rectangle([16, 14, 70, 66], fill=(220, 220, 220, 255))
        draw.rectangle([90, 14, 144, 66], fill=(220, 220, 220, 255))
        draw.rectangle([164, 14, 218, 66], fill=(220, 220, 220, 255))
        # Tiny ® block in top-right corner
        draw.ellipse([224, 4, 236, 16], fill=(220, 220, 220, 255))
        im.save(path)

    def test_perspective_patch_erase_blend_and_multilayer_psd(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base_path = root / "base.png"
            logo_path = root / "logo.png"
            psd_path = root / "out.psd"
            png_path = root / "out.png"

            # Textured metallic background with a dark garbled smudge inside quad
            rng = np.random.default_rng(7)
            bg = np.clip(195 + rng.normal(0, 8, size=(400, 500, 3)), 0, 255).astype(np.uint8)
            bg[180:220, 230:270] = (30, 30, 30)  # garbled smudge to erase
            Image.fromarray(bg, mode="RGB").save(base_path)
            self._make_sample_logo(logo_path)

            rc = mod.main([
                "patch-logo",
                "--image", str(base_path),
                "--logo", str(logo_path),
                "--quad", "180", "160", "320", "165", "315", "235", "175", "230",
                "--mode", "perspective",
                "--blend", "multiply",
                "--opacity", "0.85",
                "--tint", "#70747A",
                "--displace", "0.6",
                "--drop-reg",
                "--erase-quad",
                "--erase-engine", "opencv",
                "--out", str(psd_path),
                "--preview-png", str(png_path),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(psd_path.is_file())
            self.assertTrue(png_path.is_file())

            raw = psd_path.read_bytes()
            self.assertTrue(raw.startswith(b"8BPS"))
            self.assertIn(b"8BIMmul ", raw)
            self.assertIn("原图".encode("utf-16-be"), raw)
            self.assertIn("擦除旧字层".encode("utf-16-be"), raw)
            self.assertIn("LOGO精修层".encode("utf-16-be"), raw)

            with Image.open(psd_path) as psd_im, Image.open(png_path) as png_im:
                self.assertEqual(psd_im.size, (500, 400))
                self.assertEqual(png_im.size, (500, 400))
                # Corner pixels untouched
                self.assertEqual(psd_im.convert("RGB").getpixel((5, 5)), tuple(int(v) for v in bg[5, 5]))
                self.assertEqual(png_im.convert("RGB").getpixel((5, 5)), tuple(int(v) for v in bg[5, 5]))
                # Inside logo stroke, Multiply with #70747A darkened the ~195 background clearly
                center_px = png_im.convert("RGB").getpixel((250, 198))
                self.assertLess(sum(center_px) / 3.0, 145.0)
                self.assertGreater(sum(center_px) / 3.0, 45.0)

    def test_cylindrical_warp_and_all_blend_modes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base_path = root / "mug.png"
            logo_path = root / "logo.png"
            out_psd = root / "cyl.psd"

            bg = np.full((360, 360, 3), 200, dtype=np.uint8)
            Image.fromarray(bg, mode="RGB").save(base_path)
            self._make_sample_logo(logo_path)

            rc = mod.main([
                "patch-logo",
                "--image", str(base_path),
                "--logo", str(logo_path),
                "--quad", "0.2", "0.3", "0.8", "0.3", "0.8", "0.65", "0.2", "0.65",
                "--mode", "cylinder",
                "--cylinder-curve", "0.48",
                "--cylinder-axis", "vertical",
                "--cylinder-bow", "0.10",
                "--blend", "soft_light",
                "--opacity", "0.9",
                "--tint", "#505050",
                "--out", str(out_psd),
            ])
            self.assertEqual(rc, 0)
            raw = out_psd.read_bytes()
            self.assertIn(b"8BIMsLit", raw)
            with Image.open(out_psd) as im:
                self.assertEqual(im.size, (360, 360))

        # Smoke test every supported PS blend mode numerically
        bg_tile = np.full((16, 16, 3), 150, dtype=np.uint8)
        fg_tile = np.full((16, 16, 4), (100, 120, 140, 200), dtype=np.uint8)
        for blend_name in mod.PS_BLEND_KEYS:
            res = mod.apply_ps_blend(bg_tile, fg_tile, blend=blend_name, opacity=0.8)
            self.assertEqual(res.shape, (16, 16, 3))
            self.assertEqual(res.dtype, np.uint8)

    def test_recolor_led_keeps_outside_pixels_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "scale.png"
            out_psd = root / "scale_orange.psd"
            out_png = root / "scale_orange.png"

            # Beige scale body with black rectangular screen and white glowing digit block
            img = np.full((300, 400, 3), (220, 212, 202), dtype=np.uint8)
            img[80:220, 60:340] = (14, 13, 12)
            img[120:180, 150:250] = (250, 248, 245)
            Image.fromarray(img, mode="RGB").save(src)

            rc = mod.main([
                "recolor-led",
                "--image", str(src),
                "--screen-box", "40", "60", "360", "240",
                "--color", "#FF5E00",
                "--out", str(out_psd),
                "--preview-png", str(out_png),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(out_psd.is_file())
            with Image.open(out_png) as res:
                # Outside beige body strictly untouched
                self.assertEqual(res.getpixel((10, 10)), (220, 212, 202))
                # Digit center turned vivid orange (high R, medium G, very low B)
                r, g, b = res.getpixel((200, 150))
                self.assertGreater(r, 230)
                self.assertLess(g, 160)
                self.assertLess(b, 60)


if __name__ == "__main__":
    unittest.main()
