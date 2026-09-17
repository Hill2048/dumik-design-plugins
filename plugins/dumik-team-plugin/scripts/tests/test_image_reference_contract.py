from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
HD_PATH = ROOT / "skills/d-image-director/scripts/hd/run_image_repair_hd_workflow.py"
SPEC = importlib.util.spec_from_file_location("hd_reference_contract", HD_PATH)
assert SPEC and SPEC.loader
HD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HD)
OLD_REFERENCE = re.compile(r"image[1-9]\d*\b|(?<!@)图片?[1-9]\d*|@图片[1-9]\d*")


class ImageReferenceContractTests(unittest.TestCase):
    def test_hd_workflow_keeps_input_order_and_model_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            output = root / "result"
            Image.new("RGB", (64, 64), "white").save(source)
            argv = [
                str(HD_PATH), "--image", str(source),
                "--output-dir", str(output), "--scene-prompt", "A metal badge.",
            ]
            with patch.object(sys, "argv", argv), patch.object(HD, "call_image_batch") as call:
                HD.main()
            self.assertEqual(call.call_count, 3)
            first, second, final = [item.kwargs for item in call.call_args_list]
            self.assertEqual(first["image"], source)
            self.assertEqual(second["image"], source)
            self.assertEqual(final["image"], output / "01-lineart.png")
            self.assertEqual(final["references"], [output / "02-color-draft.png"])
            for item in (first, second, final):
                self.assertEqual(item["image_model"], "image2")
            prompt = final["prompt"]
            self.assertEqual(set(re.findall(r"@图(\d+)", prompt)), {"1", "2"})
            self.assertIsNone(OLD_REFERENCE.search(prompt))
            self.assertIn("A metal badge.", prompt)
            self.assertEqual((output / "04-final-prompt.txt").read_text(encoding="utf-8"), prompt)

    def test_hd_command_preserves_api_argument_order(self):
        with patch.object(HD, "run_command") as run:
            HD.call_image_batch(
                image=Path("lineart.png"), references=[Path("color.png")],
                prompt="@图1 structure; @图2 colors.", image_model="image2",
                output_size="2048x2048", out_path=Path("final.png"),
            )
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--image") + 1], "lineart.png")
        self.assertEqual(command[command.index("--reference") + 1], "color.png")
        self.assertEqual(command[command.index("--image-model") + 1], "image2")

    def test_benchmark_document_matches_generated_prompt(self):
        script = ROOT / "skills/d-api-test/scripts/run_image_benchmark.py"
        tree = ast.parse(script.read_text(encoding="utf-8"))
        prompt = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "PROMPT_BODY" for target in node.targets)
        )
        reference = (ROOT / "skills/d-api-test/references/image-benchmark.md").read_text(encoding="utf-8")
        self.assertIn(prompt, reference)
        self.assertIsNone(OLD_REFERENCE.search(prompt))
        self.assertIn('FIXTURE_DIR / "image1-target.png"', script.read_text(encoding="utf-8"))

    def test_runner_examples_have_matching_reference_counts(self):
        path = ROOT / "skills/d-image-runner/references/results-input-example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data["items"]:
            prompt = item["final_instruction"]
            labels = {int(number) for number in re.findall(r"@图(\d+)", prompt)}
            self.assertEqual(labels, set(range(1, len(item["reference_files"]) + 2)))
            self.assertIsNone(OLD_REFERENCE.search(prompt))
            self.assertEqual(prompt.splitlines()[0], "比例：1:1")


if __name__ == "__main__":
    unittest.main()
