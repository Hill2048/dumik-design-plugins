from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
