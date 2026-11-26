import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import build_canvas_pipeline as mod


class PromoteGuardTests(unittest.TestCase):
    def _make_project(self, root: Path) -> None:
        (root / "project.md").write_text(
            "# 项目总控\n\n## 详情页规划\n| 编号 | 名称 | 比例 | 状态 |\n| --- | --- | --- | --- |\n| S01 | 健康对比 | 9:16 | 候选已出(1张) |\n",
            encoding="utf-8",
        )

    def test_rejects_user_uploaded_and_low_res_unless_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_project(root)

            # 1. Chat upload (.user_uploaded/) must be rejected
            up_dir = root / ".user_uploaded"
            up_dir.mkdir()
            up_img = up_dir / "media_123.jpg"
            Image.new("RGB", (2048, 2048), (200, 200, 200)).save(up_img)
            with self.assertRaises(mod.PipelineError) as ctx1:
                mod.promote_candidate(root, item_id="S01", candidate_file=up_img)
            self.assertIn("user_uploaded", str(ctx1.exception))

            # 2. Low-res (<1500px) image must be rejected
            low_img = root / "low_1024.jpg"
            Image.new("RGB", (576, 1024), (200, 200, 200)).save(low_img)
            with self.assertRaises(mod.PipelineError) as ctx2:
                mod.promote_candidate(root, item_id="S01", candidate_file=low_img)
            self.assertIn("1500px", str(ctx2.exception))

            # 3. Escape hatch --allow-low-res works
            res_forced = mod.promote_candidate(root, item_id="S01", candidate_file=low_img, allow_low_res=True)
            self.assertTrue(res_forced["ok"])

            # 4. Real 2K image passes cleanly
            hi_img = root / "hi_2k.png"
            Image.new("RGB", (1536, 2752), (200, 200, 200)).save(hi_img)
            res_ok = mod.promote_candidate(root, item_id="S01", candidate_file=hi_img)
            self.assertTrue(res_ok["ok"])


if __name__ == "__main__":
    unittest.main()
