from __future__ import annotations

import argparse
import base64
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "generate_batch_images.py"
SPEC = importlib.util.spec_from_file_location("generate_batch_images", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


ONE_PIXEL_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z9p8AAAAASUVORK5CYII="
    )
).decode("ascii")


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": ONE_PIXEL_PNG,
                                }
                            }
                        ]
                    }
                }
            ]
        }


class FakeImageResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"data": [{"b64_json": ONE_PIXEL_PNG}]}


class GenerateChatImagesTests(unittest.TestCase):
    def test_multiple_candidates_are_requested_concurrently(self):
        original_post = MODULE.requests.post

        def fake_post(*args, **kwargs):
            time.sleep(0.15)
            return FakeResponse()

        MODULE.requests.post = fake_post
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_paths = [Path(temp_dir) / f"candidate-{index}.png" for index in range(3)]
                started = time.perf_counter()
                saved = MODULE.generate_chat_images(
                    base_url="https://example.invalid",
                    api_key="test-key",
                    image_model=MODULE.BANANA2_IMAGE_MODEL,
                    source_file=None,
                    reference_files=[],
                    prompt="test",
                    count=3,
                    size="2048x2048",
                    output_paths=output_paths,
                )
                elapsed = time.perf_counter() - started

                self.assertLess(elapsed, 0.4)
                self.assertEqual(saved, [str(path) for path in output_paths])
                self.assertTrue(all(path.exists() for path in output_paths))
        finally:
            MODULE.requests.post = original_post


class GptImage25Tests(unittest.TestCase):
    def test_aliases_route_image25_to_sunburst(self):
        self.assertEqual(MODULE.normalize_image_model("image2.5"), MODULE.IMAGE25_SUNBURST_MODEL)
        self.assertEqual(MODULE.normalize_image_model("flare"), MODULE.IMAGE25_FLARE_MODEL)
        self.assertEqual(MODULE.normalize_image_model("sunburst"), MODULE.IMAGE25_SUNBURST_MODEL)

    def test_payload_uses_official_image25_fields(self):
        payload = MODULE.image_model_payload_options(MODULE.IMAGE25_FLARE_MODEL, "2048x2048")
        self.assertEqual(
            payload,
            {"size": "2048x2048", "quality": "high", "output_format": "png"},
        )

    def test_edit_uses_official_multi_image_field(self):
        original_post = MODULE.requests.post
        captured = {}

        def fake_post(*args, **kwargs):
            captured.update(kwargs)
            return FakeImageResponse()

        MODULE.requests.post = fake_post
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source = root / "image1.png"
                reference = root / "image2.png"
                source.write_bytes(base64.b64decode(ONE_PIXEL_PNG))
                reference.write_bytes(base64.b64decode(ONE_PIXEL_PNG))
                output = root / "result.png"
                MODULE.generate_images(
                    base_url="https://example.invalid/v1",
                    api_key="test-key",
                    image_model=MODULE.IMAGE25_SUNBURST_MODEL,
                    source_file=str(source),
                    reference_files=[str(reference)],
                    prompt="test",
                    count=1,
                    size="1024x1024",
                    output_paths=[output],
                )
                self.assertEqual([field for field, _ in captured["files"]], ["image[]", "image[]"])
                self.assertEqual(captured["data"]["output_format"], "png")
                self.assertNotIn("response_format", captured["data"])
                self.assertTrue(output.exists())
        finally:
            MODULE.requests.post = original_post


class AspectRatioSizePresetTests(unittest.TestCase):
    def test_standard_ratio_presets_for_bananapro_and_image25(self):
        cases = {
            "9:16": "1152x2048",
            "9:16-2k": "1152x2048",
            "9:16-4k": "2160x3840",
            "3:4": "1536x2048",
            "3:4-4k": "2400x3200",
            "1:1": "2048x2048",
            "1:1-4k": "2880x2880",
        }
        for preset, expected in cases.items():
            for model in ("bananapro", "gpt-image-2.5-sunburst"):
                item = MODULE.PromptItem(
                    id="size-check",
                    file=None,
                    reference_files=[],
                    task="size preset check",
                    count=1,
                    output_name="out.png",
                    final_instruction="test",
                    output_size=preset,
                )
                self.assertEqual(
                    MODULE.api_size_for_item(item, image_model=model),
                    expected,
                    msg=f"{preset} on {model}",
                )


class RunRecordLoggingTests(unittest.TestCase):
    def test_run_single_skips_run_record_by_default_and_writes_when_enabled(self):
        original_post = MODULE.requests.post
        MODULE.requests.post = lambda *args, **kwargs: FakeResponse()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                out_dir = Path(temp_dir) / "默认无日志"
                args_default = argparse.Namespace(
                    prompt="clean titanium spoon photo",
                    prompt_file=None,
                    output_dir=str(out_dir),
                    out=str(out_dir / "candidate.png"),
                    image=None,
                    reference=[],
                    count=1,
                    id="s04",
                    task="test",
                    output_size="1:1",
                    image_model=MODULE.BANANA2_IMAGE_MODEL,
                    write_run_record=False,
                )
                MODULE.run_single(args_default, "https://example.invalid", "test-key")
                self.assertTrue((out_dir / "candidate.png").exists())
                self.assertFalse((out_dir / "运行记录.json").exists())
                self.assertFalse((out_dir / "运行记录.md").exists())

                out_dir_rec = Path(temp_dir) / "开启日志"
                args_rec = argparse.Namespace(**{**vars(args_default), "output_dir": str(out_dir_rec), "out": str(out_dir_rec / "candidate.png"), "write_run_record": True})
                MODULE.run_single(args_rec, "https://example.invalid", "test-key")
                self.assertTrue((out_dir_rec / "candidate.png").exists())
                self.assertTrue((out_dir_rec / "运行记录.json").exists())
                self.assertTrue((out_dir_rec / "运行记录.md").exists())
        finally:
            MODULE.requests.post = original_post


class Banana21Tests(unittest.TestCase):
    def test_aliases_route_to_banana21(self):
        for alias in ("banana2.1", "banana-2.1", "banana21", "nano-banana-2.1", "gemini-nano-banana-2.1"):
            self.assertEqual(MODULE.normalize_image_model(alias), MODULE.BANANA21_IMAGE_MODEL)
        self.assertIn(MODULE.BANANA21_IMAGE_MODEL, MODULE.CHAT_IMAGE_MODELS)

    def test_thinking_level_validation_and_payload(self):
        for level in ("minimal", "medium", "high"):
            cfg = MODULE.build_chat_generation_config(
                size="1152x2048",
                image_model=MODULE.BANANA21_IMAGE_MODEL,
                thinking_level=level,
            )
            self.assertEqual(cfg["thinkingConfig"], {"thinkingLevel": level})

        cfg_b2 = MODULE.build_chat_generation_config(
            size="1152x2048",
            image_model=MODULE.BANANA2_IMAGE_MODEL,
            thinking_level="high",
        )
        self.assertEqual(cfg_b2["thinkingConfig"], {"thinkingLevel": "high"})

        with self.assertRaises(MODULE.BatchImageError):
            MODULE.normalize_thinking_level("medium", image_model=MODULE.BANANA2_IMAGE_MODEL)

        self.assertEqual(
            MODULE.normalize_image_model(MODULE.DEFAULT_IMAGE_MODEL),
            MODULE.BANANA21_IMAGE_MODEL,
        )
        cfg_default = MODULE.build_chat_generation_config(
            size="1152x2048",
            image_model=MODULE.BANANA21_IMAGE_MODEL,
        )
        self.assertEqual(cfg_default["thinkingConfig"], {"thinkingLevel": "high"})

        cfg_off = MODULE.build_chat_generation_config(
            size="1152x2048",
            image_model=MODULE.BANANA21_IMAGE_MODEL,
            thinking_level="off",
        )
        self.assertNotIn("thinkingConfig", cfg_off)

        with self.assertRaises(MODULE.BatchImageError):
            MODULE.normalize_thinking_level("high", image_model="gpt-image-2.5-sunburst")


if __name__ == "__main__":
    unittest.main()
