from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


INIT_SCRIPT = Path(__file__).resolve().parents[1] / "init_dumik_project.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


INIT_MOD = _load("init_dumik_project", INIT_SCRIPT)


class InitDumikProjectTests(unittest.TestCase):
    def test_empty_folder_init_organizes_root_images_and_white_bg_with_zero_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "纯钛勺子"
            root.mkdir()
            # Loose raw photos dropped directly in folder root
            (root / "实拍正拍.png").write_bytes(b"png-raw")
            (root / "实拍侧面.jpg").write_bytes(b"jpg-raw")
            wb_src = Path(tmp) / "external-white-bg.png"
            wb_src.write_bytes(b"white-bg-bytes")

            res = INIT_MOD.init_project(
                project_root=root,
                white_bg_inputs=[str(wb_src)],
            )
            self.assertTrue(res["ok"])
            self.assertEqual(sorted(res["movedRootImages"]), ["素材/实拍原图/实拍侧面.jpg", "素材/实拍原图/实拍正拍.png"])
            self.assertEqual(res["whiteBgRefs"], ["设定集/白底图/external-white-bg.png"])

            # Verify root contains strictly the 4 markdown files + 4 asset dirs
            top_files = sorted(p.name for p in root.iterdir() if p.is_file())
            top_dirs = sorted(p.name for p in root.iterdir() if p.is_dir())
            self.assertEqual(top_files, ["AGENTS.md", "assets.md", "design.md", "project.md"])
            self.assertEqual(top_dirs, ["制作", "成品", "素材", "设定集"])
            self.assertEqual(list((root / "制作").iterdir()), [])
            self.assertEqual(list(root.rglob("*.json")), [])

            agents_txt = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertNotIn("@[project.md](project.md)", agents_txt)
            self.assertNotIn("@[assets.md](assets.md)", agents_txt)
            self.assertIn("@[design.md](design.md)", agents_txt)
            self.assertIn("纯无字画面底图", agents_txt)
            self.assertLess(len(agents_txt.encode("utf-8")), 1500)

            design_txt = (root / "design.md").read_text(encoding="utf-8")
            self.assertIn("纯审美与工艺规范", design_txt)
            self.assertLess(len((agents_txt + design_txt).encode("utf-8")), 24000)

            assets_txt = (root / "assets.md").read_text(encoding="utf-8")
            self.assertIn("`设定集/白底图/external-white-bg.png`", assets_txt)
            self.assertIn("风格摆件库", assets_txt)
            self.assertIn("饮品 / 食材错峰排期表", assets_txt)

            project_txt = (root / "project.md").read_text(encoding="utf-8")
            self.assertIn("设定集/白底图/external-white-bg.png", project_txt)
            self.assertIn("MS05", project_txt)
            self.assertIn("已锁定", project_txt)

            for txt in (agents_txt, design_txt, project_txt):
                for forbidden in ("P0", "P1", "P2"):
                    self.assertNotIn(forbidden, txt)

    def test_feishu_init_and_incremental_sync_preserves_locked_rows_and_design(self):
        mock_nodes = [
            {"id": "m1", "type": "image", "x": -3000, "y": 1000, "width": 1500, "height": 2000, "image": {"token": "MainTok123456789012"}},
            {"id": "mt1", "type": "composite_shape", "x": -2900, "y": 1200, "width": 500, "height": 120, "text": {"text": "加宽加深勺头 一勺兜大馄饨"}},
            {"id": "m2", "type": "image", "x": -1200, "y": 1000, "width": 1500, "height": 2000, "image": {"token": "MainTok223456789012"}},
            {"id": "mt2", "type": "composite_shape", "x": -1100, "y": 1200, "width": 500, "height": 120, "text": {"text": "耐腐蚀不变色"}},
            {"id": "d1", "type": "image", "x": -2000, "y": 5000, "width": 790, "height": 1100, "image": {"token": "DetTok1234567890123"}},
            {"id": "dt1", "type": "composite_shape", "x": -1950, "y": 5100, "width": 400, "height": 90, "text": {"text": "加宽加深勺头 一勺兜大馄饨"}},
            {"id": "d2", "type": "image", "x": -2000, "y": 6300, "width": 790, "height": 1000, "image": {"token": "DetTok2234567890123"}},
            {"id": "dt2", "type": "composite_shape", "x": -1950, "y": 6400, "width": 400, "height": 90, "text": {"text": "权威检测报告 产品参数"}},
            {"id": "d3", "type": "image", "x": -2000, "y": 7500, "width": 790, "height": 1050, "image": {"token": "DetTok3234567890123"}},
            {"id": "dt3", "type": "composite_shape", "x": -1950, "y": 7600, "width": 400, "height": 90, "text": {"text": "一体成型无焊接"}},
            {"id": "d4", "type": "image", "x": -2000, "y": 8700, "width": 790, "height": 1050, "image": {"token": "DetTok4234567890123"}},
            {"id": "dt4", "type": "composite_shape", "x": -1950, "y": 8800, "width": 400, "height": 90, "text": {"text": "加厚勺柄握感舒适"}},
        ]

        parser_mod = INIT_MOD._load_parser_module()

        def fake_call(args, identities):
            if args[:2] == ["wiki", "+node-get"]:
                return {"data": {"title": "纯钛勺测试", "obj_type": "docx", "obj_token": "DocMock123456789012"}}, "user"
            if args[:2] == ["docs", "+fetch"]:
                return {"data": {"document": {"content": '<title>纯钛勺测试</title><whiteboard token="WbMock1234567890123"></whiteboard>'}}}, "user"
            if args[:2] == ["whiteboard", "+export"]:
                return {"data": {"nodes": mock_nodes}}, "user"
            raise AssertionError(f"Unexpected call: {args}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "纯钛勺测试"
            with patch.object(parser_mod, "detect_lark_identities", return_value=["user"]), patch.object(
                parser_mod, "call_with_identity_fallback", side_effect=fake_call
            ):
                res = INIT_MOD.init_project(
                    project_root=root,
                    feishu_url="https://example.feishu.cn/wiki/MockWiki987654321",
                )
                self.assertTrue(res["ok"])
                self.assertEqual(res["feishuSummary"]["layoutOnlyScreens"], 1)
                self.assertEqual(list(root.rglob("*.json")), [])

                # Customize design.md and mark MS02/S01 status in project.md
                design_path = root / "design.md"
                design_path.write_text(design_path.read_text(encoding="utf-8") + "\n- 自定义光影锁：清晨冷窗光\n", encoding="utf-8")
                pm_path = root / "project.md"
                updated_lines = []
                for ln in pm_path.read_text(encoding="utf-8").splitlines():
                    if ln.startswith("| MS02 |"):
                        parts = ln.split("|")
                        parts[4] = " 已锁定 "
                        parts[5] = " 设定集/里程碑/MS02_首屏KV.png "
                        ln = "|".join(parts)
                    elif ln.startswith("| S01 |"):
                        parts = ln.split("|")
                        parts[-2] = " 已定稿 "
                        ln = "|".join(parts)
                    updated_lines.append(ln)
                pm_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

                # Sync WITHOUT passing --feishu-url; must extract URL from project.md and preserve locks & design.md
                sync_res = INIT_MOD.init_project(project_root=root, sync=True)
                self.assertTrue(sync_res["ok"])
                self.assertIn("- 自定义光影锁：清晨冷窗光", design_path.read_text(encoding="utf-8"))
                synced_pm = pm_path.read_text(encoding="utf-8")
                self.assertIn("| 已锁定 | 设定集/里程碑/MS02_首屏KV.png |", synced_pm)
                self.assertIn("| 已定稿 |", synced_pm)
                self.assertIn("无需生图（后期排版）", synced_pm)


if __name__ == "__main__":
    unittest.main()
