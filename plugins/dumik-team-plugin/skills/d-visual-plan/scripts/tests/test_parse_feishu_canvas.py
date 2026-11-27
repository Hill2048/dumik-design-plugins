from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


VISUAL_SCRIPT = Path(__file__).resolve().parents[1] / "parse_feishu_canvas.py"
PLUGIN_ROOT = Path(__file__).resolve().parents[4]
PIPELINE_SCRIPT = PLUGIN_ROOT / "skills/d-project-pipeline/scripts/build_canvas_pipeline.py"
RUNNER_SCRIPT = PLUGIN_ROOT / "skills/d-image-runner/scripts/generate_batch_images.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PARSER_MOD = _load("parse_feishu_canvas", VISUAL_SCRIPT)
PIPELINE_MOD = _load("build_canvas_pipeline", PIPELINE_SCRIPT)
RUNNER_MOD = _load("generate_batch_images_check", RUNNER_SCRIPT)


def _sample_planning_nodes() -> list[dict]:
    nodes: list[dict] = []
    # 1. Pure competitor reference row at top (y = -15000, no text overlays or notes)
    for i in range(4):
        nodes.append(
            {
                "id": f"comp:{i}",
                "type": "image",
                "x": -4000 + i * 1600,
                "y": -15000,
                "width": 1440,
                "height": 1920,
                "image": {"token": f"CompTok{i}123456789012345"},
            }
        )

    # 2. Active 3:4 main-image row at y = 7000
    nodes.extend(
        [
            {
                "id": "main:1",
                "type": "image",
                "x": -5000,
                "y": 7000,
                "width": 1500,
                "height": 2000,
                "image": {"token": "MainTok123456789012345"},
            },
            {
                "id": "main_txt:1",
                "type": "composite_shape",
                "x": -4900,
                "y": 7300,
                "width": 600,
                "height": 140,
                "text": {"text": "加大加深勺头\n喝汤舀粥一勺顶三勺"},
            },
            {
                "id": "main:2",
                "type": "image",
                "x": -3200,
                "y": 7000,
                "width": 1500,
                "height": 2000,
                "image": {"token": "MainTok223456789012345"},
            },
            {
                "id": "main_txt:2",
                "type": "composite_shape",
                "x": -3100,
                "y": 7300,
                "width": 600,
                "height": 140,
                "text": {"text": "耐腐蚀抗酸碱"},
            },
            {
                "id": "main_stk:1",
                "type": "sticky_note",
                "x": -3250,
                "y": 8700,
                "width": 250,
                "height": 250,
                "text": {"text": "加个弧度"},
            },
        ]
    )

    # 3. Active 790xn vertical detail stack at x = -3650
    detail_specs = [
        ("det:1", 12000, 790, 1000, "首屏KV纯钛抗菌勺", "DetTok123456789012345"),
        ("det:2", 13100, 790, 1050, "加大加深勺头 喝汤舀粥一勺顶三勺", "DetTok223456789012345"),
        ("det:3", 14250, 790, 1100, "细长手柄 握持舒适不烫手", "DetTok323456789012345"),
        ("det:4", 15450, 790, 980, "0重金属析出", "DetTok423456789012345"),
    ]
    for nid, y, w, h, label, tok in detail_specs:
        nodes.append(
            {
                "id": nid,
                "type": "image",
                "x": -3650,
                "y": y,
                "width": w,
                "height": h,
                "image": {"token": tok},
            }
        )
        nodes.append(
            {
                "id": f"txt_{nid}",
                "type": "composite_shape",
                "x": -3600,
                "y": y + 120,
                "width": 450,
                "height": 100,
                "text": {"text": label},
            }
        )

    # Embedded small image inside det:2 (must NOT become a separate screen)
    nodes.append(
        {
            "id": "det:2_sub",
            "type": "image",
            "x": -3450,
            "y": 13500,
            "width": 320,
            "height": 300,
            "image": {"token": "SubTok223456789012345"},
        }
    )
    # Sticky note on det:4
    nodes.append(
        {
            "id": "det_stk:4",
            "type": "sticky_note",
            "x": -3950,
            "y": 15700,
            "width": 220,
            "height": 220,
            "text": {"text": "换成粥"},
        }
    )

    # 4. 1:1 SKU card + sticky note
    nodes.extend(
        [
            {
                "id": "sku_stk",
                "type": "sticky_note",
                "x": -800,
                "y": 12000,
                "width": 300,
                "height": 300,
                "text": {"text": "sku"},
            },
            {
                "id": "sku:1",
                "type": "image",
                "x": 250,
                "y": 12000,
                "width": 800,
                "height": 800,
                "image": {"token": "SkuTok123456789012345"},
            },
            {
                "id": "sku_txt:1",
                "type": "composite_shape",
                "x": 300,
                "y": 12600,
                "width": 250,
                "height": 90,
                "text": {"text": "大号1支 长度18.8cm"},
            },
        ]
    )
    return nodes


class ParseFeishuCanvasTests(unittest.TestCase):
    def test_spatial_clustering_and_main_shared_wave1(self):
        board = PARSER_MOD.analyze_whiteboard_nodes(
            _sample_planning_nodes(),
            board_token="TestWbToken123456789",
            default_ratio="9:16",
        )
        self.assertEqual(board["competitor_reference_count"], 4)
        self.assertEqual(len(board["main_cards"]), 2)
        self.assertEqual(len(board["detail_screens"]), 4)
        self.assertEqual(len(board["entry_cards"]), 1)

        # Embedded small image stays inside S02, not promoted as 5th detail screen
        s02 = board["detail_screens"][1]
        self.assertEqual(len(s02["embedded_images"]), 1)
        self.assertTrue(s02["is_main_shared"])
        self.assertEqual(s02["linked_main_ids"], ["M01"])
        self.assertEqual(s02["priority_wave"], 1)
        self.assertEqual(s02["target_gen_ratio"], "9:16")

        # S04 keeps its sticky note and stays in wave 2
        s04 = board["detail_screens"][3]
        self.assertFalse(s04["is_main_shared"])
        self.assertEqual(s04["priority_wave"], 2)
        self.assertIn("换成粥", s04["sticky_notes"])

    def test_milestone_extraction_and_checklist_has_no_p_tiers(self):
        ms_nodes = [
            {"id": "ms_title", "type": "composite_shape", "x": 10, "y": 10, "width": 800, "height": 60, "text": {"text": "里程碑一"}},
            {"id": "ms_img1", "type": "image", "x": 500, "y": 150, "width": 160, "height": 300, "image": {"token": "MsTok123456789012345"}},
            {"id": "ms_s1", "type": "composite_shape", "x": 20, "y": 480, "width": 300, "height": 50, "text": {"text": "产品身份卡"}},
            {"id": "ms_s2", "type": "composite_shape", "x": 480, "y": 480, "width": 200, "height": 50, "text": {"text": "首屏KV"}},
        ]
        ms_board = PARSER_MOD.analyze_whiteboard_nodes(
            ms_nodes,
            board_token="MsToken1234567890123",
            board_heading="里程碑一",
            is_milestone_heading=True,
            default_ratio="9:16",
        )
        plan_board = PARSER_MOD.analyze_whiteboard_nodes(
            _sample_planning_nodes(),
            board_token="PlanToken12345678901",
            default_ratio="9:16",
        )
        doc_info = PARSER_MOD.parse_doc_markup(
            "<title>测试纯钛勺子</title><table><tr><td>这是什么</td><td>纯钛抗菌勺</td></tr></table>"
        )
        manifest = PARSER_MOD.build_manifest(
            doc_info=doc_info,
            boards=[ms_board, plan_board],
            source_url="https://example.feishu.cn/wiki/TestNode",
            identities_used=["bot"],
            default_ratio="9:16",
        )
        md = PARSER_MOD.render_checklist_markdown(manifest)
        self.assertIn("第一批优先", md)
        self.assertIn("9:16", md)
        for forbidden in ("P0", "P1", "P2"):
            self.assertNotIn(forbidden, md)

        pm = PARSER_MOD.render_project_markdown(manifest)
        self.assertIn("第 1 批（最优先）", pm)
        self.assertIn("9:16", pm)
        for forbidden in ("P0", "P1", "P2"):
            self.assertNotIn(forbidden, pm)

        # Verify resolved 9:16 output size works cleanly in generate_batch_images.py
        out_size = PIPELINE_MOD.resolve_output_size(manifest["defaultGenRatio"], "2k")
        self.assertEqual(out_size, "9:16-2k")
        item = RUNNER_MOD.PromptItem(
            id="s02",
            file=None,
            reference_files=[],
            task="test",
            count=1,
            output_name="s02.png",
            final_instruction="比例：9:16\n\n测试主指令",
            output_size=out_size,
        )
        self.assertEqual(RUNNER_MOD.api_size_for_item(item, image_model="banana2"), "1152x2048")

    def test_doc_multi_board_classification_skips_video_and_marks_revision(self):
        xml = (
            '<title>测试锅具策划</title>'
            '<h1><a href="https://example.com/item/123">商品链接</a></h1>'
            '<h1>11.6日</h1><h3>「运营目的」</h3><p>修改</p>'
            '<whiteboard token="RevWbToken1234567890"></whiteboard>'
            '<h1>主图视频策划</h1><whiteboard token="VidWbToken1234567890"></whiteboard>'
            '<h1>8.24日</h1><h3>「运营目的」</h3><p>主图详情策划</p>'
            '<whiteboard token="PlanWbToken123456789"></whiteboard>'
            '<h1>10.27日 里程碑一</h1><whiteboard token="MsWbToken12345678901"></whiteboard>'
        )
        doc = PARSER_MOD.parse_doc_markup(xml)
        self.assertEqual(len(doc["links"]), 1)
        wbs = {w["token"]: w for w in doc["whiteboards"]}
        self.assertTrue(wbs["RevWbToken1234567890"]["is_revision_heading"])
        self.assertTrue(wbs["VidWbToken1234567890"]["is_video_only"])
        self.assertTrue(wbs["PlanWbToken123456789"]["is_main_detail_heading"])
        self.assertTrue(wbs["MsWbToken12345678901"]["is_milestone_heading"])

    def test_section_wireframes_must_render_and_dual_detail_isolation(self):
        nodes = [
            {"id": "lbl_m", "type": "text_shape", "x": -4500, "y": -2500, "width": 300, "height": 200, "text": {"text": "750主图"}},
            {"id": "m_sec1", "type": "section", "x": -3500, "y": -2450, "width": 764, "height": 1065, "text": {"text": ""}},
            {"id": "m_txt1", "type": "composite_shape", "x": -3400, "y": -2200, "width": 500, "height": 120, "text": {"text": "必渲① 锅内纯钛+logo"}},
            {"id": "m_sec2", "type": "section", "x": -2500, "y": -2450, "width": 764, "height": 1065, "text": {"text": ""}},
            {"id": "m_txt2", "type": "composite_shape", "x": -2400, "y": -2200, "width": 500, "height": 120, "text": {"text": "必渲③ 钛铝钢截面"}},
            {"id": "m_sec3", "type": "composite_shape", "x": -1500, "y": -2450, "width": 764, "height": 1065, "text": {"text": ""}},
            {"id": "m_txt3", "type": "text_shape", "x": -1400, "y": -2200, "width": 400, "height": 100, "text": {"text": "轻巧顺手"}},
            {"id": "lbl_e", "type": "composite_shape", "x": 4500, "y": -2500, "width": 300, "height": 120, "text": {"text": "800主图"}},
            {"id": "e_frm", "type": "composite_shape", "x": 5000, "y": -2450, "width": 608, "height": 608, "text": {"text": ""}},
            {"id": "e_txt", "type": "text_shape", "x": 5050, "y": -2200, "width": 400, "height": 80, "text": {"text": "入口规格1"}},
            # Giant wrapper section that must NOT become a detail screen
            {"id": "wrap_sec", "type": "section", "x": -4000, "y": 5000, "width": 12000, "height": 30000, "text": {"text": ""}},
        ]
        # Primary detail stack at x=1700 (5 screens, first references 必渲① even with short text)
        for i in range(5):
            y = 6000 + i * 1300
            nodes.append({"id": f"d_p_{i}", "type": "composite_shape", "x": 1700, "y": y, "width": 920, "height": 1200, "text": {"text": ""}})
            label = "必渲① 内胆特写" if i == 0 else f"常规分屏 {i}"
            nodes.append({"id": f"d_pt_{i}", "type": "composite_shape", "x": 1750, "y": y + 100, "width": 400, "height": 90, "text": {"text": label}})
        # Secondary parallel detail stack at x=6000 (4 screens)
        for i in range(4):
            y = 6000 + i * 1300
            nodes.append({"id": f"d_s_{i}", "type": "image", "x": 6000, "y": y, "width": 790, "height": 1100, "image": {"token": f"AltDetTok{i}1234567890"}})
            nodes.append({"id": f"d_st_{i}", "type": "text_shape", "x": 6050, "y": y + 100, "width": 350, "height": 80, "text": {"text": f"备选列 {i}"}})

        board = PARSER_MOD.analyze_whiteboard_nodes(nodes, board_token="PanWbToken1234567890")
        self.assertEqual(len(board["main_cards"]), 3)
        self.assertEqual(len(board["entry_cards"]), 1)
        self.assertEqual(len(board["detail_screens"]), 5)
        self.assertEqual(len(board["alt_detail_stacks"]), 1)
        self.assertEqual(len(board["must_render_assets"]), 2)
        self.assertTrue(board["detail_screens"][0]["is_main_shared"])
        self.assertEqual(board["detail_screens"][0]["priority_wave"], 1)
        self.assertIn("共用必渲(必渲①)", board["detail_screens"][0]["match_reasons"][0])
        self.assertTrue(any("并排存在多套详情列" in c for c in board["fact_conflicts"]))

    def test_visual_mode_classification_project_md_sync_and_zero_json(self):
        nodes = _sample_planning_nodes()
        # Add a pure layout-only screen (质检报告 + 产品参数, no cooking/eating action)
        nodes.extend(
            [
                {"id": "det:5", "type": "image", "x": -3650, "y": 16650, "width": 790, "height": 1000, "image": {"token": "DetTok523456789012345"}},
                {"id": "txt_det:5", "type": "composite_shape", "x": -3600, "y": 16750, "width": 450, "height": 100, "text": {"text": "权威检测报告 产品规格参数"}},
            ]
        )
        board = PARSER_MOD.analyze_whiteboard_nodes(nodes, board_token="PlanWb123456789012", default_ratio="9:16")
        doc_info = PARSER_MOD.parse_doc_markup("<title>测试纯钛勺子</title>")
        manifest = PARSER_MOD.build_manifest(
            doc_info=doc_info,
            boards=[board],
            source_url="https://example.feishu.cn/wiki/TestNode",
            identities_used=["user"],
            default_ratio="9:16",
        )
        self.assertEqual(manifest["summaryCounts"]["layoutOnlyScreens"], 1)
        w2_items = manifest["waves"]["wave2_detail_rest"]
        layout_items = [x for x in w2_items if x["visual_mode"] == "layout_only"]
        self.assertEqual(len(layout_items), 1)
        self.assertEqual(layout_items[0]["default_status"], "无需生图（后期排版）")

        project_md = PARSER_MOD.render_project_markdown(manifest)
        self.assertIn("纯无字底图", project_md)
        self.assertIn("PS", project_md)
        self.assertIn("无需生图（后期排版）", project_md)
        for forbidden in ("P0", "P1", "P2"):
            self.assertNotIn(forbidden, project_md)
        self.assertEqual(PARSER_MOD.extract_feishu_url_from_project_md(project_md), "https://example.feishu.cn/wiki/TestNode")

        # Simulate user manually marking MS01 as 已锁定 (with white-bg path) and S02 as 已定稿, then syncing
        edited_lines = []
        for ln in project_md.splitlines():
            if ln.startswith("| MS01 |"):
                parts = ln.split("|")
                parts[4] = " 已锁定 "
                parts[5] = " 设定集/白底图/white.png "
                ln = "|".join(parts)
            elif ln.startswith("| S02 |"):
                parts = ln.split("|")
                parts[-2] = " 已定稿 "
                ln = "|".join(parts)
            edited_lines.append(ln)
        edited_md = "\n".join(edited_lines) + "\n"

        preserved = PARSER_MOD.parse_existing_project_statuses(edited_md)
        self.assertEqual(preserved["MS01"]["status"], "已锁定")
        self.assertEqual(preserved["MS01"]["asset_path"], "设定集/白底图/white.png")
        self.assertEqual(preserved["S02"]["status"], "已定稿")

        resynced_md = PARSER_MOD.render_project_markdown(manifest, existing_statuses=preserved)
        self.assertIn("| 已锁定 | 设定集/白底图/white.png |", resynced_md)
        self.assertIn("| 已定稿 |", resynced_md)

        # Verify fetch_and_parse writes ONLY project.md by default (zero .json files in project_root)
        def fake_call(args, identities):
            if args[:2] == ["wiki", "+node-get"]:
                return {"data": {"title": "纯钛测试", "obj_type": "docx", "obj_token": "DocxMockToken123456"}}, "user"
            if args[:2] == ["docs", "+fetch"]:
                return {"data": {"document": {"content": '<title>纯钛测试</title><whiteboard token="PlanWb123456789012"></whiteboard>'}}}, "user"
            if args[:2] == ["whiteboard", "+export"]:
                return {"data": {"nodes": nodes}}, "user"
            raise AssertionError(f"Unexpected CLI call: {args}")

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            with patch.object(PARSER_MOD, "detect_lark_identities", return_value=["user"]), patch.object(
                PARSER_MOD, "call_with_identity_fallback", side_effect=fake_call
            ):
                _m, pm_path, m_out, c_out = PARSER_MOD.fetch_and_parse(
                    url="https://example.feishu.cn/wiki/MockWiki12345",
                    whiteboard_tokens=[],
                    project_root=proj,
                )
            self.assertEqual(pm_path, proj / "project.md")
            self.assertIsNone(m_out)
            self.assertIsNone(c_out)
            all_files = [p for p in proj.rglob("*") if p.is_file()]
            self.assertEqual(all_files, [proj / "project.md"])
            self.assertEqual(list(proj.rglob("*.json")), [])

    def test_alternating_camera_shots_prevents_three_consecutive_repeats(self):
        screens = [
            {"id": "S01", "title": "一锅煎炒1", "texts": ["一锅煎炒"], "evidence_family": "场景与动作证明", "visual_mode": "pure_visual"},
            {"id": "S02", "title": "一锅煎炒2", "texts": ["一锅煎炒"], "evidence_family": "场景与动作证明", "visual_mode": "pure_visual"},
            {"id": "S03", "title": "一锅煎炒3", "texts": ["一锅煎炒"], "evidence_family": "场景与动作证明", "visual_mode": "pure_visual"},
            {"id": "S04", "title": "一锅煎炒4", "texts": ["一锅煎炒"], "evidence_family": "场景与动作证明", "visual_mode": "pure_visual"},
            {"id": "S05", "title": "权威检测报告", "texts": ["权威检测报告"], "evidence_family": "纯后期排版", "visual_mode": "layout_only"},
        ]
        PARSER_MOD.assign_alternating_camera_shots(screens)
        shots = [s["camera_shot"] for s in screens[:4]]
        for idx in range(1, len(shots)):
            self.assertNotEqual(shots[idx], shots[idx - 1])
        self.assertEqual(screens[4]["camera_shot"], "—")

        manifest = PARSER_MOD.build_manifest(
            doc_info=PARSER_MOD.parse_doc_markup("<title>景别轮转测试</title>"),
            boards=[{"milestone_slots": [], "detail_screens": screens, "main_cards": [], "entry_cards": [], "must_render_assets": [], "competitor_reference_count": 0, "board_facts": {}, "fact_conflicts": []}],
            source_url="https://example.feishu.cn/wiki/ShotTest",
            identities_used=["user"],
        )
        pm = PARSER_MOD.render_project_markdown(manifest)
        self.assertIn("| 机位景别 |", pm)
        self.assertIn("微俯3/4·中景瞬态", pm)

    def test_vertical_main_side_refs_video_exclusion_and_container_absorption(self):
        nodes = [
            # Entry 1:1 wireframe + right-side reference image (must attach as side ref, NOT duplicate E02)
            {"id": "e_frm", "type": "composite_shape", "x": 505, "y": 6662, "width": 1010, "height": 990, "text": {"text": ""}},
            {"id": "e_txt", "type": "text_shape", "x": 580, "y": 6700, "width": 600, "height": 180, "text": {"text": "100%纯钛 TA1级假一罚万"}},
            {"id": "e_stk", "type": "sticky_note", "x": -200, "y": 7000, "width": 500, "height": 180, "text": {"text": "展示2个杯子（一个开盖、一个盖盖）"}},
            {"id": "e_side", "type": "image", "x": 1623, "y": 6681, "width": 990, "height": 990, "image": {"token": "EntrySideTok1234567890"}},
            # Video frame (must be excluded from static main_cards)
            {"id": "vid_lbl", "type": "composite_shape", "x": -1203, "y": 7621, "width": 420, "height": 194, "text": {"text": "卖点合集视频"}},
            {"id": "vid_frm", "type": "composite_shape", "x": -1203, "y": 7868, "width": 1086, "height": 1271, "text": {"text": ""}},
            # Vertical main wireframes at x=462 + right-side bare reference + repeated small logo
            {"id": "m_frm1", "type": "composite_shape", "x": 462, "y": 7814, "width": 1086, "height": 1302, "text": {"text": ""}},
            {"id": "m_txt1", "type": "text_shape", "x": 600, "y": 7900, "width": 600, "height": 180, "text": {"text": "不易变色 久用如新 钛结晶工艺"}},
            {"id": "m_logo1", "type": "image", "x": 484, "y": 8000, "width": 302, "height": 207, "image": {"token": "SmallBrandLogo12345678"}},
            {"id": "m_side1", "type": "image", "x": 1659, "y": 7850, "width": 957, "height": 1253, "image": {"token": "MainSideRef12345678901"}},
            {"id": "m_frm2", "type": "composite_shape", "x": 462, "y": 9281, "width": 1086, "height": 1302, "text": {"text": ""}},
            {"id": "m_txt2", "type": "text_shape", "x": 600, "y": 9350, "width": 600, "height": 180, "text": {"text": "保冷保热更持久 双重锁温"}},
            {"id": "m_logo2", "type": "image", "x": 484, "y": 9450, "width": 302, "height": 207, "image": {"token": "SmallBrandLogo12345678"}},
            # Detail stack at x=802 (outer containers absorb inner images; 食卫报告 stays layout_only)
            {"id": "s_rep", "type": "composite_shape", "x": 802, "y": 17000, "width": 1086, "height": 479, "text": {"text": "食卫报告"}},
            {"id": "s_kb", "type": "composite_shape", "x": 802, "y": 17520, "width": 1086, "height": 2081, "text": {"text": ""}},
            {"id": "s_kb_t", "type": "text_shape", "x": 860, "y": 17620, "width": 600, "height": 180, "text": {"text": "钛抗菌 抗菌率99.9% 不锈钢材质对比"}},
            {"id": "s_kb_sub", "type": "image", "x": 810, "y": 18000, "width": 1065, "height": 442, "image": {"token": "KbSubImg12345678901234"}},
            {"id": "s_kb_logo", "type": "image", "x": 870, "y": 17560, "width": 302, "height": 207, "image": {"token": "SmallBrandLogo12345678"}},
            {"id": "s_cr", "type": "composite_shape", "x": 802, "y": 19700, "width": 1086, "height": 4067, "text": {"text": ""}},
            {"id": "s_cr_t", "type": "text_shape", "x": 860, "y": 19820, "width": 700, "height": 180, "text": {"text": "不易变色 久用如新 钛结晶工艺 茶水浸泡24小时"}},
            {"id": "s_cr_side", "type": "image", "x": 1993, "y": 20000, "width": 790, "height": 1400, "image": {"token": "DetSideRef12345678901"}},
            {"id": "s_lk", "type": "composite_shape", "x": 802, "y": 23900, "width": 1086, "height": 3715, "text": {"text": ""}},
            {"id": "s_lk_t", "type": "text_shape", "x": 860, "y": 24020, "width": 700, "height": 180, "text": {"text": "保冷保热更持久 纯钛搭配真空 双重锁温"}},
            {"id": "s_sz", "type": "image", "x": 799, "y": 27800, "width": 940, "height": 901, "image": {"token": "DetEndSize12345678901"}},
            {"id": "s_sz_t", "type": "composite_shape", "x": 820, "y": 28400, "width": 300, "height": 80, "text": {"text": "杯身高 94mm"}},
        ]
        board = PARSER_MOD.analyze_whiteboard_nodes(nodes, board_token="MugTestWb1234567890", default_ratio="9:16")
        self.assertEqual(len(board["entry_cards"]), 1)
        self.assertEqual(board["entry_cards"][0]["primary_ref_token"], "EntrySideTok1234567890")
        self.assertEqual(len(board["main_cards"]), 2)
        self.assertEqual(board["main_cards"][0]["primary_ref_token"], "MainSideRef12345678901")
        self.assertEqual(len(board["detail_screens"]), 5)
        self.assertEqual(board["detail_screens"][1]["primary_ref_token"], "KbSubImg12345678901234")
        self.assertEqual(board["detail_screens"][2]["primary_ref_token"], "DetSideRef12345678901")
        self.assertEqual(board["detail_screens"][2]["linked_main_ids"], ["M01"])
        self.assertEqual(board["detail_screens"][3]["linked_main_ids"], ["M02"])

        manifest = PARSER_MOD.build_manifest(
            doc_info=PARSER_MOD.parse_doc_markup("<title>纯钛马克杯测试</title>"),
            boards=[board],
            source_url="https://example.feishu.cn/wiki/MugTest",
            identities_used=["user"],
            downloaded_assets={
                "EntrySideTok1234567890": "素材/飞书画布/E01_参考.png",
                "MainSideRef12345678901": "素材/飞书画布/M01_参考.png",
                "KbSubImg12345678901234": "素材/飞书画布/S02_参考.png",
                "DetSideRef12345678901": "素材/飞书画布/S03_参考.png",
            },
        )
        pm = PARSER_MOD.render_project_markdown(manifest)
        self.assertIn('<img src="素材/飞书画布/S03_参考.png" width="110">', pm)
        self.assertIn('<img src="素材/飞书画布/M01_参考.png" width="110">', pm)
        self.assertIn("无需生图（后期排版）", pm)
        self.assertNotIn("对比证明", pm.split("| S02 |")[1].split("\n")[0].split("|")[-1])

    def test_section_relative_coords_car_angle_isolation_and_composite_snapshots(self) -> None:
        """Section children use section-relative coords; 车图角度 never leaks into E01..En; multi-refs & composite snapshots export cleanly."""
        nodes = [
            # Entry section at (4000, -1000), child coords relative to section
            {"id": "sec_entry", "type": "section", "x": 4000, "y": -1000, "width": 2400, "height": 1400, "section": {"title": "入口图"}},
            {"id": "e1_bg", "type": "image", "parent_id": "sec_entry", "x": 100, "y": 150, "width": 800, "height": 800, "image": {"token": "EntryBaseTok123456789"}},
            {"id": "e1_ov", "type": "composite_shape", "parent_id": "sec_entry", "x": 180, "y": 200, "width": 500, "height": 120, "text": {"text": "入口直通文案"}},
            {"id": "e1_ref1", "type": "image", "parent_id": "sec_entry", "x": 960, "y": 150, "width": 700, "height": 700, "image": {"token": "EntryRef1Tok123456789"}},
            # Main section at (-600, 1000) with wireframe on left + 2 side refs
            {"id": "sec_main", "type": "section", "x": -600, "y": 1000, "width": 3200, "height": 1600, "section": {"title": "主图"}},
            {"id": "m1_box", "type": "composite_shape", "parent_id": "sec_main", "x": 120, "y": 120, "width": 800, "height": 1067, "text": {"text": ""}},
            {"id": "m1_title", "type": "composite_shape", "parent_id": "sec_main", "x": 150, "y": 150, "width": 600, "height": 100, "text": {"text": "100%纯钛对比"}},
            {"id": "m1_tbl", "type": "table", "parent_id": "sec_main", "x": 150, "y": 400, "width": 700, "height": 420, "table": {"cells": [
                {"row_index": 0, "col_index": 0, "text": {"text": "100%纯钛"}},
                {"row_index": 0, "col_index": 1, "text": {"text": "不锈钢"}},
                {"row_index": 1, "col_index": 0, "text": {"text": "0异味"}},
                {"row_index": 1, "col_index": 1, "text": {"text": "金属味"}},
            ]}},
            {"id": "m1_r1", "type": "image", "parent_id": "sec_main", "x": 980, "y": 130, "width": 760, "height": 1000, "image": {"token": "MainRef1Tok1234567890"}},
            {"id": "m1_r2", "type": "image", "parent_id": "sec_main", "x": 1800, "y": 130, "width": 760, "height": 1000, "image": {"token": "MainRef2Tok1234567890"}},
            # Car angle section should NOT become active SKU entry cards
            {"id": "sec_car", "type": "section", "x": 4000, "y": 2000, "width": 2000, "height": 1200, "section": {"title": "车图角度"}},
            {"id": "car_bg", "type": "image", "parent_id": "sec_car", "x": 100, "y": 100, "width": 800, "height": 800, "image": {"token": "CarAngleTok1234567890"}},
            # Detail stack (4+ aligned screens) + thin flush bottom strip (<=250px) that should merge into S01
            {"id": "s1_top", "type": "image", "x": 500, "y": 4000, "width": 790, "height": 1100, "image": {"token": "DetMainBaseTok1234567"}},
            {"id": "s1_strip", "type": "image", "x": 500, "y": 5100, "width": 790, "height": 220, "image": {"token": "DetStripTok1234567890"}},
            {"id": "s1_ov", "type": "composite_shape", "x": 560, "y": 4060, "width": 460, "height": 90, "text": {"text": "顶部叠加钛标"}},
            {"id": "s2_det", "type": "image", "x": 500, "y": 5400, "width": 790, "height": 1100, "image": {"token": "DetTwoBaseTok12345678"}},
            {"id": "s3_det", "type": "image", "x": 500, "y": 6600, "width": 790, "height": 1100, "image": {"token": "DetThreeBaseTok123456"}},
            {"id": "s4_det", "type": "image", "x": 500, "y": 7800, "width": 790, "height": 1100, "image": {"token": "DetFourBaseTok1234567"}},
            # Distant sticky should NOT dock onto distant S01 even if accidentally matched
            {"id": "stk_far", "type": "sticky_note", "x": 9000, "y": 9000, "width": 220, "height": 120, "sticky_note": {"text": "遥远便签"}},
        ]
        board = PARSER_MOD.analyze_whiteboard_nodes(nodes, board_token="SecTestWb123456789012", default_ratio="9:16")
        self.assertEqual(len(board["entry_cards"]), 1)
        self.assertEqual(board["entry_cards"][0]["title"], "入口直通文案")
        self.assertEqual([r["token"] for r in board["entry_cards"][0]["side_reference_images"]], ["EntryRef1Tok123456789"])
        self.assertEqual(len(board["main_cards"]), 1)
        self.assertEqual([r["token"] for r in board["main_cards"][0]["side_reference_images"]], ["MainRef1Tok1234567890", "MainRef2Tok1234567890"])
        self.assertEqual(len(board["detail_screens"]), 4)
        self.assertGreaterEqual(board["detail_screens"][0]["rect"]["h"], 1300)

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            from PIL import Image as PilImage

            def _fake_call(args, identities):
                return {"data": {"nodes": nodes}}, "user"

            def _fake_download(token, out_dir, name_stem, identities, blocked_download_identities=None):
                out_dir.mkdir(parents=True, exist_ok=True)
                p = out_dir / f"{name_stem}.png"
                PilImage.new("RGB", (600, 600), (210, 195, 175)).save(p, format="PNG")
                return p, None

            with patch.object(PARSER_MOD, "detect_lark_identities", return_value=["user"]), \
                 patch.object(PARSER_MOD, "call_with_identity_fallback", side_effect=_fake_call), \
                 patch.object(PARSER_MOD, "download_whiteboard_media", side_effect=_fake_download):
                manifest, pm_path, _, _ = PARSER_MOD.fetch_and_parse(
                    url=None,
                    whiteboard_tokens=["SecTestWb123456789012"],
                    project_root=proj,
                    download_assets=True,
                    write_project_md=True,
                )

            self.assertIsNotNone(pm_path)
            pm_text = pm_path.read_text(encoding="utf-8")
            self.assertIn("画布原图与参考", pm_text)
            self.assertIn("素材/飞书画布/M01_整行.png", pm_text)
            self.assertIn("素材/飞书画布/S01_画布原图.png", pm_text)
            self.assertIn("素材/飞书画布/E01_整行.png", pm_text)
            self.assertTrue((proj / "素材/飞书画布/M01_画布原图.png").is_file())
            self.assertTrue((proj / "素材/飞书画布/M01_参考1.png").is_file())
            self.assertTrue((proj / "素材/飞书画布/M01_整行.png").is_file())
            self.assertTrue((proj / "素材/飞书画布/E01_整行.png").is_file())
            self.assertTrue((proj / "素材/飞书画布/主图区总览.png").is_file())
            self.assertTrue((proj / "素材/飞书画布/入口区总览.png").is_file())
            self.assertTrue((proj / "素材/飞书画布/详情区总览.png").is_file())
            self.assertTrue((proj / "素材/飞书画布/M01_参考2.png").is_file())
            self.assertFalse((proj / "素材/飞书画布/_tmp").exists())
            self.assertEqual(manifest["summaryCounts"]["wave3EntrySkuCards"], 1)

    def test_flush_slice_seam_refinement_avoids_mid_object_cut(self) -> None:
        """When two flush detail images slice right through a high-detail scene, snap crop to the quiet divider band."""
        RFB_MOD = _load("render_feishu_board", VISUAL_SCRIPT.parent / "render_feishu_board.py")
        from PIL import Image as PilImage, ImageDraw as PilDraw

        # Create one single 800x1600 canvas with a jagged high-contrast striped box crossing y=800,
        # followed by a quiet dark separator band at y=1100..1160, then another stripe band below y=1200.
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            full_img = PilImage.new("RGB", (800, 1600), (242, 240, 236))
            d = PilDraw.Draw(full_img)
            for y in range(200, 1080, 14):
                for x in range(80, 720, 22):
                    d.rectangle([x, y, x + 10, y + 10], fill=(40, 35, 30))
            d.rectangle([0, 1090, 800, 1180], fill=(35, 28, 24))
            for y in range(1220, 1520, 16):
                for x in range(100, 700, 24):
                    d.rectangle([x, y, x + 12, y + 12], fill=(160, 70, 50))

            tok_a = tdir / "SliceATok1234567890.png"
            tok_b = tdir / "SliceBTok1234567890.png"
            full_img.crop((0, 0, 800, 800)).save(tok_a)
            full_img.crop((0, 800, 800, 1600)).save(tok_b)

            nodes = [
                {"id": "sa", "type": "image", "x": 500, "y": 1000, "width": 800, "height": 800, "image": {"token": "SliceATok1234567890"}},
                {"id": "sb", "type": "image", "x": 500, "y": 1800, "width": 800, "height": 800, "image": {"token": "SliceBTok1234567890"}},
                {"id": "sa_t", "type": "composite_shape", "x": 520, "y": 1020, "width": 400, "height": 80, "text": {"text": "上半场景标题"}},
                {"id": "sb_t", "type": "composite_shape", "x": 520, "y": 2250, "width": 400, "height": 80, "text": {"text": "下半奖项标题"}},
            ]
            parsed = PARSER_MOD._normalize_nodes(nodes)
            fake_analyzed = {
                "detail_screens": [
                    {"id": "S01", "source_kind": "image", "rect": {"x": 500, "y": 1000, "w": 800, "h": 800, "node_id": "sa"}, "sticky_notes": [], "side_reference_images": []},
                    {"id": "S02", "source_kind": "image", "rect": {"x": 500, "y": 1800, "w": 800, "h": 800, "node_id": "sb"}, "sticky_notes": [], "side_reference_images": []},
                ],
                "main_cards": [],
                "entry_cards": [],
            }
            out_dir = tdir / "out"
            res = RFB_MOD.reconstruct_and_crop_board(
                analyzed_board=fake_analyzed,
                parsed=parsed,
                raw_token_files={"SliceATok1234567890": tok_a, "SliceBTok1234567890": tok_b},
                dest_dir=out_dir,
                zones={"detail"},
                write_overviews=False,
            )
            with PilImage.open(res["snapshots"]["S01"]) as s1_im:
                s1_w, s1_h = s1_im.size
            with PilImage.open(res["snapshots"]["S02"]) as s2_im:
                s2_w, s2_h = s2_im.size
            # S01 must have expanded downward past 800 (aspect ratio taller than square 1:1!)
            self.assertGreater(s1_h, s1_w * 1.25)
            # S02 must correspondingly start below the quiet band (much shorter than 1:1!)
            self.assertLess(s2_h, s2_w * 0.75)

    def test_sharp_banner_step_seam_refinement_and_blank_guard(self) -> None:
        """Sharp color-step banner seams (without wide blank gaps) must snap cleanly, and blank crops must raise."""
        RFB_MOD = _load("render_feishu_board", VISUAL_SCRIPT.parent / "render_feishu_board.py")
        from PIL import Image as PilImage, ImageDraw as PilDraw

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            # Reject effectively blank crop when check_blank=True
            blank = PilImage.new("RGB", (200, 200), (247, 248, 250))
            with self.assertRaises(ValueError):
                RFB_MOD._save_png_atomic(blank, tdir / "blank.png", check_blank=True)

            # Build 600x1400 strip:
            # y=0..460 light beige card (low horizontal texture near bottom of y=450..460)
            # y=460..1400 dark banner & textured pot crossing raw slice seam y=700!
            full_img = PilImage.new("RGB", (600, 1400), (240, 234, 224))
            d = PilDraw.Draw(full_img)
            for y in range(60, 420, 18):
                for x in range(40, 560, 24):
                    d.rectangle([x, y, x + 10, y + 10], fill=(120, 95, 70))
            # Sharp color transition at y=460 into dark background + textured subject across y=700
            d.rectangle([0, 460, 600, 1400], fill=(28, 30, 26))
            for y in range(510, 1280, 14):
                for x in range(40, 560, 20):
                    d.rectangle([x, y, x + 10, y + 10], fill=(230, 195, 95))

            tok_a = tdir / "BannerATok1234567890.png"
            tok_b = tdir / "BannerBTok1234567890.png"
            full_img.crop((0, 0, 600, 700)).save(tok_a)
            full_img.crop((0, 700, 600, 1400)).save(tok_b)

            nodes = [
                {"id": "ba", "type": "image", "x": 100, "y": 1000, "width": 600, "height": 700, "image": {"token": "BannerATok1234567890"}},
                {"id": "bb", "type": "image", "x": 100, "y": 1700, "width": 600, "height": 700, "image": {"token": "BannerBTok1234567890"}},
            ]
            parsed = PARSER_MOD._normalize_nodes(nodes)
            fake_analyzed = {
                "detail_screens": [
                    {"id": "S16", "source_kind": "image", "rect": {"x": 100, "y": 1000, "w": 600, "h": 700, "node_id": "ba"}, "sticky_notes": [], "side_reference_images": []},
                    {"id": "S17", "source_kind": "image", "rect": {"x": 100, "y": 1700, "w": 600, "h": 700, "node_id": "bb"}, "sticky_notes": [], "side_reference_images": []},
                ],
                "main_cards": [],
                "entry_cards": [],
            }
            res = RFB_MOD.reconstruct_and_crop_board(
                analyzed_board=fake_analyzed,
                parsed=parsed,
                raw_token_files={"BannerATok1234567890": tok_a, "BannerBTok1234567890": tok_b},
                dest_dir=tdir / "out",
                zones={"detail"},
                write_overviews=False,
            )
            with PilImage.open(res["snapshots"]["S16"]) as im16, PilImage.open(res["snapshots"]["S17"]) as im17:
                # S16 should shrink upward to ~460 (< 600), and S17 should expand upward to ~940 (> 760)
                self.assertLess(im16.height, im16.width * 0.95)
                self.assertGreater(im17.height, im17.width * 1.25)

    def test_medium_scale_board_and_side_by_side_main_thumbnails(self) -> None:
        """Medium-scale boards (455x607 main, 580-wide detail, 302x303 SKU) parse cleanly and embed main thumbs beside Wave 1 rows."""
        nodes = [
            # 3 horizontal 455x607 main cards
            {"id": "m1", "type": "image", "x": 100, "y": 100, "width": 455, "height": 607, "image": {"token": "Main1Tok1234567890"}},
            {"id": "m2", "type": "image", "x": 620, "y": 100, "width": 455, "height": 607, "image": {"token": "Main2Tok1234567890"}},
            {"id": "m3", "type": "image", "x": 1140, "y": 100, "width": 455, "height": 607, "image": {"token": "Main3Tok1234567890"}},
            {"id": "mt1", "type": "composite_shape", "x": 110, "y": 120, "width": 320, "height": 60, "text": {"text": "0涂层 爆炒不粘"}},
            # 4 vertical 580-wide detail cards
            {"id": "d1", "type": "image", "x": 100, "y": 1000, "width": 580, "height": 720, "image": {"token": "Det1Tok1234567890"}},
            {"id": "dt1", "type": "composite_shape", "x": 120, "y": 1040, "width": 320, "height": 60, "text": {"text": "0涂层 爆炒不粘 详情首屏"}},
            {"id": "d2", "type": "image", "x": 100, "y": 1720, "width": 580, "height": 720, "image": {"token": "Det2Tok1234567890"}},
            {"id": "d3", "type": "image", "x": 100, "y": 2440, "width": 580, "height": 720, "image": {"token": "Det3Tok1234567890"}},
            {"id": "d4", "type": "image", "x": 100, "y": 3160, "width": 580, "height": 720, "image": {"token": "Det4Tok1234567890"}},
            # 2 302x303 SKU cards with sku header
            {"id": "skh", "type": "composite_shape", "x": 2000, "y": 60, "width": 100, "height": 40, "text": {"text": "sku"}},
            {"id": "e1", "type": "image", "x": 2000, "y": 120, "width": 302, "height": 303, "image": {"token": "Sku1Tok1234567890"}},
            {"id": "et1", "type": "composite_shape", "x": 2010, "y": 360, "width": 180, "height": 40, "text": {"text": "炒锅+煎锅两件套"}},
            {"id": "e2", "type": "image", "x": 2360, "y": 120, "width": 302, "height": 303, "image": {"token": "Sku2Tok1234567890"}},
            {"id": "et2", "type": "composite_shape", "x": 2370, "y": 360, "width": 180, "height": 40, "text": {"text": "四件套全家福"}},
        ]
        analyzed = PARSER_MOD.analyze_whiteboard_nodes(nodes, board_token="MedBoard")
        self.assertEqual(len(analyzed["main_cards"]), 3)
        self.assertEqual(len(analyzed["detail_screens"]), 4)
        self.assertEqual(len(analyzed["entry_cards"]), 2)

        # Simulate asset paths & render project.md -> verify side-by-side main thumb in Wave 1 row
        analyzed["main_cards"][0]["local_asset_path"] = "素材/飞书画布/M01_画布原图.png"
        manifest = PARSER_MOD.build_manifest(
            doc_info={"title": "中尺度套装测试", "headings": [], "tables": [], "whiteboards": [], "paragraphs": [], "links": []},
            boards=[analyzed],
            source_url="https://example.feishu.cn/wiki/test",
            identities_used=["user"],
            default_ratio="9:16",
        )
        md = PARSER_MOD.render_project_markdown(manifest)
        self.assertIn("批次与同源主图对照", md)
        self.assertIn('<img src="素材/飞书画布/M01_画布原图.png" width="90">', md)


if __name__ == "__main__":
    unittest.main()
