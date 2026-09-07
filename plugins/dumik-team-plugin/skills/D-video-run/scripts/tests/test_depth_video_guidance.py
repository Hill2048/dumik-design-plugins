import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "generate_batch_videos.py"
SPEC = importlib.util.spec_from_file_location("generate_batch_videos", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DepthVideoGuidanceTests(unittest.TestCase):
    def load(self, row):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.json"
            path.write_text(json.dumps({"items": [row]}, ensure_ascii=False), encoding="utf-8")
            return MODULE.load_prompt_items(path)[0]

    def base_row(self):
        return {
            "id": "depth-001",
            "provider": "dreamina",
            "mode": "multimodal2video",
            "guidance_mode": "depth_video",
            "reference_videos": ["F:/refs/depth.mp4"],
            "final_instruction": "以 depth_video 作为空间和动作引导，转化为真实实景视频。",
        }

    def test_depth_video_uses_seedance_multimodal_video_reference(self):
        item = self.load(self.base_row())
        command = MODULE.build_command(item, poll=5)
        self.assertEqual(item.guidance_mode, "depth_video")
        self.assertEqual(command[1], "multimodal2video")
        self.assertIn("--video", command)
        self.assertIn("F:/refs/depth.mp4", command)

    def test_depth_video_requires_reference_video(self):
        row = self.base_row()
        row["reference_videos"] = []
        with self.assertRaisesRegex(MODULE.BatchVideoError, "requires a video"):
            self.load(row)

    def test_depth_video_rejects_veo(self):
        row = self.base_row()
        row["provider"] = "veo"
        with self.assertRaisesRegex(MODULE.BatchVideoError, "requires Dreamina/Seedance"):
            self.load(row)


if __name__ == "__main__":
    unittest.main()
