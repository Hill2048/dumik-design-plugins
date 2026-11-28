import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    path = PLUGIN_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


INIT_MOD = _load("e2e_init", "skills/d-init/scripts/init_dumik_project.py")
PIPE_MOD = _load("e2e_pipe", "skills/d-project-pipeline/scripts/build_canvas_pipeline.py")
PREP_MOD = _load("e2e_prep", "skills/d-image-director/scripts/prep_reference_assets.py")
WASH_MOD = _load("e2e_wash", "skills/d-image-director/scripts/wash_prep.py")
REPAIR_MOD = _load("e2e_repair", "skills/d-image-director/scripts/repair/mask_repair.py")
HOOKS_MOD = _load("e2e_hooks", "hooks/agy_dumik_hooks.py")
TELEM_MOD = _load("e2e_telem", "scripts/dumik_telemetry.py")


class FullWorkflowE2ETests(unittest.TestCase):
    def test_full_7_stage_dumik_production_line(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            proj = base / "测试纯钛杯"
            proj.mkdir()

            # Stage 1: Prepare 3 raw white-bg views + oversized ref, then run d-init & prep_reference_assets
            wb_views = []
            for idx, col in enumerate([(170, 170, 175), (120, 160, 200), (190, 150, 130)], start=1):
                vp = base / f"视角_{idx}.png"
                im = Image.new("RGB", (600, 600), (255, 255, 255))
                ImageDraw.Draw(im).rectangle([160, 120, 440, 480], fill=col)
                im.save(vp)
                wb_views.append(vp)

            raw_big = proj / "超大实拍原图.png"
            Image.new("RGB", (2600, 1800), (210, 200, 190)).save(raw_big)

            init_res = INIT_MOD.init_project(project_root=proj, white_bg_inputs=[str(wb_views[0])])
            self.assertTrue(init_res["ok"])
            self.assertEqual(
                sorted(p.name for p in proj.iterdir() if p.is_file()),
                ["AGENTS.md", "assets.md", "design.md", "project.md"],
            )
            self.assertEqual(list(proj.rglob("*.json")), [])

            stitched_card = proj / "设定集" / "白底图" / "00_测试纯钛杯_多视图白底身份卡.jpg"
            st_res = PREP_MOD.stitch_white_identity_card(wb_views, stitched_card, labels=["正视", "侧视", "顶视"])
            self.assertEqual(st_res["count"], 3)
            with Image.open(stitched_card) as card_im:
                slots = PREP_MOD.detect_white_bg_slots(card_im)
            self.assertEqual(len(slots), 3)

            # Compress oversized ref in 设定集
            big_ref = proj / "设定集" / "超大母版.png"
            Image.new("RGB", (2800, 2100), (180, 170, 160)).save(big_ref)
            comp_res = PREP_MOD.compress_oversized_refs(proj / "设定集", max_mb=4.0, max_edge=2048)
            self.assertGreaterEqual(comp_res["compressed_count"], 1)
            self.assertTrue((proj / "设定集" / "超大母版_轻量2K.jpg").is_file())

            # Stage 2: Promote 2K MS02 milestone -> verify prop-bible reminder & hook gate
            ms02_cand = proj / "制作" / "MS02_首屏KV视觉定调" / "候选_01.png"
            ms02_cand.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1536, 2752), (235, 225, 210)).save(ms02_cand)

            # Append S01 row into project.md so we can test detail production + promote
            pm_path = proj / "project.md"
            pm_txt = pm_path.read_text(encoding="utf-8")
            pm_txt = pm_txt.replace(
                "| — | — | — | 待补充详情分屏规划（纯报告/参数屏将标为无需生图） | — | — | — | — |",
                "| S01 | ★第1批 | — | 测试主卖点 | 纯无字底图 | 微俯35° | — | 待写词 |",
            )
            pm_path.write_text(pm_txt, encoding="utf-8")

            ms_promo = PIPE_MOD.promote_candidate(proj, item_id="MS02", candidate_file=ms02_cand)
            self.assertTrue(ms_promo["ok"])
            self.assertIn("置景摆件库", ms_promo["reminder"])

            # Hook must warn about unfilled prop bible in assets.md
            self.assertTrue(HOOKS_MOD.has_unfilled_prop_bible(proj))
            fake_state = {}
            with mock.patch.object(HOOKS_MOD, "_load_hook_state", return_value=fake_state), mock.patch.object(
                HOOKS_MOD, "_save_hook_state"
            ):
                hook_out = HOOKS_MOD.handle_pre_invocation(
                    {"cwd": str(proj), "conversationId": "e2e-conv", "lastUserInput": "写 S01 提示词"}
                )
            injected = "\n".join(s["systemMessage"]["systemMessage"] for s in hook_out["injectSteps"])
            self.assertIn("前置置景提醒", injected)
            self.assertIn("防漂移底线", injected)

            # Stage 3: Fill assets.md Prop Bible -> hook reminder clears
            assets_path = proj / "assets.md"
            assets_txt = assets_path.read_text(encoding="utf-8").replace(
                "| 01 | 待规划（如桌面托盘/杯垫） | 待填 | — | 未用 |",
                "| 01 | 拉丝冷银椭圆托盘 | 哑光拉丝不锈钢 | 设定集/摆件身份卡/01_托盘.png | S01 |",
            )
            assets_path.write_text(assets_txt, encoding="utf-8")
            self.assertFalse(HOOKS_MOD.has_unfilled_prop_bible(proj))

            # Stage 4: Write S01 prompt.md, prepare DesignFlow multi-model batch, and test wash_prep
            s01_dir = proj / "制作" / "S01_测试主卖点"
            s01_dir.mkdir(parents=True, exist_ok=True)
            (s01_dir / "prompt.md").write_text(
                "比例：9:16\n\n"
                "- `@图1`: `设定集/白底图/00_测试纯钛杯_多视图白底身份卡.jpg`\n"
                f"- `@图2`: `{ms_promo['promotedTo']}`\n\n"
                "```text\n比例：9:16\n@图1为产品结构真源，@图2为静奢阳光光影母版。画面中下段放纯钛杯与拉丝冷银椭圆托盘，顶部留白。\n```\n",
                encoding="utf-8",
            )
            batch_res = PIPE_MOD.prepare_or_execute_batch(
                project_root=proj,
                ids=["S01"],
                engine="designflow",
                count=2,
                image_models="banana2.1,bananapro",
                execute=False,
            )
            self.assertTrue(batch_res["ok"])
            self.assertEqual(len(batch_res["designflowItems"]), 1)
            self.assertEqual(batch_res["designflowItems"][0]["count"], 2)
            self.assertEqual(batch_res["designflowItems"][0]["models"], ["banana2.1", "bananapro"])

            # Wash prep test
            comp_ref = base / "竞品图.png"
            Image.new("RGB", (800, 800), (230, 220, 205)).save(comp_ref)
            wash_dir = base / "wash_tmp"
            rc_w = WASH_MOD.main([
                "single",
                "--ref", str(comp_ref),
                "--product-ref", str(stitched_card),
                "--product-desc", "纯钛直筒杯",
                "--erase-box", "0.3", "0.3", "0.7", "0.8",
                "--target-ratio", "9:16",
                "--name", "S01_洗图测试",
                "--workdir", str(wash_dir),
            ])
            self.assertEqual(rc_w, 0)
            self.assertTrue((wash_dir / "S01_洗图测试_脱壳底图.png").is_file())

            # Stage 5: Local repair with 0~1 pct coords + --white-slot 2 + --match-border-color
            s01_cand = s01_dir / "候选_01.png"
            Image.new("RGB", (1536, 2752), (235, 225, 210)).save(s01_cand)
            rep_work = base / "rep_work"
            rc_rp = REPAIR_MOD.main([
                "prepare-single",
                "--image", str(s01_cand),
                "--white-ref", str(stitched_card),
                "--white-slot", "2",
                "--product-box", "0.25", "0.40", "0.75", "0.75",
                "--defect-box", "0.55", "0.45", "0.70", "0.60",
                "--defect-desc", "还原手柄倒角",
                "--workdir", str(rep_work),
            ])
            self.assertEqual(rc_rp, 0)
            meta_p = rep_work / "候选_01_meta.json"
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            ai_rep = rep_work / "ai_fixed.png"
            # Color-shifted crop (darker by 15) to test --match-border-color
            Image.new("RGB", tuple(meta["crop_size"]), (220, 210, 195)).save(ai_rep)
            psd_out = s01_dir / "候选_01_已修复.psd"
            rc_ps = REPAIR_MOD.main([
                "paste-single",
                "--meta", str(meta_p),
                "--repaired", str(ai_rep),
                "--out", str(psd_out),
                "--match-border-color",
                "--cleanup",
            ])
            self.assertEqual(rc_ps, 0)
            self.assertTrue(psd_out.is_file())
            self.assertFalse(rep_work.exists())
            with Image.open(psd_out) as psd_im:
                self.assertEqual(psd_im.convert("RGB").getpixel((768, 1500)), (235, 225, 210))

            # Stage 6: Promote guard blocks compressed .user_uploaded, allows 2K, then variant-sku runs
            up_dir = base / ".user_uploaded"
            up_dir.mkdir()
            up_low = up_dir / "media_low.jpg"
            Image.new("RGB", (576, 1024), (200, 200, 200)).save(up_low)
            with self.assertRaises(PIPE_MOD.PipelineError):
                PIPE_MOD.promote_candidate(proj, item_id="S01", candidate_file=up_low)

            s01_promo = PIPE_MOD.promote_candidate(proj, item_id="S01", candidate_file=s01_cand)
            self.assertTrue(s01_promo["ok"])
            self.assertEqual(s01_promo["newStatus"], "已定稿")

            var_res = PIPE_MOD.prepare_variant_batch(
                proj,
                variant_sku="星空灰",
                variant_ref=stitched_card,
                variant_desc="改为深空灰磨砂钛面",
            )
            self.assertTrue(var_res["ok"])
            self.assertEqual(var_res["count"], 1)

            # Stage 7: Stop hook passes on clean project, blocks on stray JSON clutter; telemetry suppressed in pytest
            stop_clean = HOOKS_MOD.handle_stop({"cwd": str(proj), "terminationReason": "NO_TOOL_CALL"})
            self.assertEqual(stop_clean["decision"], "stop")

            (proj / "run-state.json").write_text("{}", encoding="utf-8")
            stop_dirty = HOOKS_MOD.handle_stop({"cwd": str(proj), "terminationReason": "NO_TOOL_CALL"})
            self.assertEqual(stop_dirty["decision"], "continue")
            (proj / "run-state.json").unlink()

            with mock.patch.dict("os.environ", {"PYTEST_CURRENT_TEST": "e2e_stage7"}):
                self.assertFalse(TELEM_MOD.report_event_async(event="invoke", skill="d-project-pipeline"))

    def test_audit_assets_md_flags_missing_paths(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "巡检测试"
            proj.mkdir()
            (proj / "设定集" / "场景身份卡").mkdir(parents=True)
            (proj / "设定集" / "场景身份卡" / "01_有效母版.png").write_bytes(b"ok")
            (proj / "assets.md").write_text(
                "- 有效：`设定集/场景身份卡/01_有效母版.png`\n"
                "- 失效：`设定集/场景身份卡/01_旧失效卡.png`\n"
                "- 旧版已废弃：`设定集/场景身份卡/00_废弃卡.png`\n",
                encoding="utf-8",
            )
            broken = PIPE_MOD.audit_assets_md(proj)
            self.assertEqual(broken, ["设定集/场景身份卡/01_旧失效卡.png"])


if __name__ == "__main__":
    unittest.main()
