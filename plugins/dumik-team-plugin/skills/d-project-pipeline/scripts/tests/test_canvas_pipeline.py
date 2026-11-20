from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PIPELINE_SCRIPT = Path(__file__).resolve().parents[1] / "build_canvas_pipeline.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PIPELINE_MOD = _load("build_canvas_pipeline_test_mod", PIPELINE_SCRIPT)


def _write_sample_project(root: Path) -> None:
    for rel in (
        "素材/实拍原图",
        "设定集/白底图",
        "设定集/里程碑",
        "设定集/必渲特写",
        "制作",
        "成品/详情_790xn",
        "成品/主图_3x4",
        "成品/入口与SKU_1x1",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "设定集" / "白底图" / "spoon-white.png").write_bytes(b"white-bg")
    (root / "设定集" / "里程碑" / "MS02_kv.png").write_bytes(b"kv-ref")

    project_md = """# 纯钛勺子 — 项目总账本

- 飞书源：https://example.feishu.cn/wiki/MockWiki
- 默认生图画幅：**9:16 竖版**（纯无字底图，人工后期 PS 排版）

## 二、第 0 批：视觉里程碑设定（定调后锁入 design.md）

| 编号 | 里程碑项 | 画幅 | 状态 | 定稿/参考路径 | 定调重点 |
| --- | --- | --- | --- | --- | --- |
| MS01 | 产品白底身份卡 | 9:16 | 已锁定 | 设定集/白底图/spoon-white.png | 锁产品结构 |
| MS02 | 首屏 KV 视觉定调 | 9:16 | 待生成定调 | 无 | 锁光影母体 |

## 三、第 1 批（最优先）：主图×详情共用核心画面（9:16 无字同源母版）

| 编号 | 关联主图 | 核心卖点意图 | 纯画面物理证据 & PS留白要求 | 证据类型 | 状态 |
| --- | --- | --- | --- | --- | --- |
| S04 | M01、M08 | **钛好舀**：加宽加深 | 勺兜大云吞，顶部留 25% 净底 | 场景与动作证明 | 待写词 |

## 四、第 2 批：详情其余分屏（默认 9:16 无字底图）

| 编号 | 画面主题 | 纯画面物理证据 & PS留白要求 | 证据类型 | 状态 |
| --- | --- | --- | --- | --- |
| S09 | **材质参数**：权威检测 | 纯后期排版屏（不生图） | 纯后期排版 | 无需生图（后期排版） |

## 五、第 3 批与主图派生对照（3:4 主图 & 独立 1:1 入口/SKU）

| 编号 | 交付规格 | 画面意图与批注 | 来源方式 | 状态 |
| --- | --- | --- | --- | --- |
| M01 | 3:4 主图 | 加宽加深 | 由第1批 9:16 母片裁切派生（关联 S04） | 待派生 |
"""
    (root / "project.md").write_text(project_md, encoding="utf-8")


class CanvasPipelineTests(unittest.TestCase):
    def test_status_sync_and_missing_prompt_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            _write_sample_project(root)

            # MS02 already has 设定集/里程碑/MS02_kv.png on disk -> sync must set MS02 to 已锁定
            sync1 = PIPELINE_MOD.sync_project_status(root)
            self.assertTrue(sync1["ok"])
            pm1 = (root / "project.md").read_text(encoding="utf-8")
            self.assertIn("| MS02 | 首屏 KV 视觉定调 | 9:16 | 已锁定 | 设定集/里程碑/MS02_kv.png |", pm1)

            # Running wave 1 without 制作/S04_*/prompt.md must fail loudly
            with self.assertRaises(PIPELINE_MOD.PipelineError) as ctx:
                PIPELINE_MOD.prepare_or_execute_batch(project_root=root, wave=1, execute=False)
            self.assertIn("S04", str(ctx.exception))

            # Add S04 prompt.md -> status syncs to 提示词就绪, dry-run prepares in %TEMP% and leaves zero JSON in project
            s04_dir = root / "制作" / "S04_钛好舀"
            s04_dir.mkdir(parents=True)
            prompt_md = """# S04_钛好舀

- @图1：设定集/白底图/spoon-white.png（产品结构真源）
- @图2：设定集/里程碑/MS02_kv.png（光影风格母体）

```text
比例：9:16

@图1：纯钛勺结构真源；@图2：清晨自然窗光基调。
纯无字实拍微距俯斜画面，勺头盛起完整鲜虾大云吞与清亮汤汁，勺身中段稳占画幅55%，顶部25%保留干净低反差浅灰石台虚化留白。
禁止：任何标题文字、数字标尺、引导线或角标。
```
"""
            (s04_dir / "prompt.md").write_text(prompt_md, encoding="utf-8")
            PIPELINE_MOD.sync_project_status(root)
            pm2 = (root / "project.md").read_text(encoding="utf-8")
            self.assertIn("| 提示词就绪 |", pm2)

            prep = PIPELINE_MOD.prepare_or_execute_batch(project_root=root, wave=1, execute=False)
            self.assertTrue(prep["ok"])
            self.assertTrue(prep["tempFileCleaned"])
            self.assertEqual(prep["itemsCount"], 1)
            self.assertEqual(prep["items"][0]["outputSize"], "9:16-2k")
            self.assertEqual(prep["items"][0]["outputName"], "S04_钛好舀/候选_01.png")
            self.assertEqual(prep["items"][0]["referenceCount"], 2)
            self.assertEqual(list(root.rglob("*.json")), [])

            # Mock execution creating 候选_01.png, then verify status & promote to 成品
            def fake_subproc(cmd, **kwargs):
                res_idx = cmd.index("--results-input") + 1
                batch_data = json.loads(Path(cmd[res_idx]).read_text(encoding="utf-8"))
                out_dir = Path(cmd[cmd.index("--output-dir") + 1])
                for item in batch_data["items"]:
                    out_p = out_dir / item["output_name"]
                    out_p.parent.mkdir(parents=True, exist_ok=True)
                    out_p.write_bytes(b"fake-png-data")

                class R:
                    returncode = 0

                return R()

            with patch.object(PIPELINE_MOD.subprocess, "run", side_effect=fake_subproc):
                exec_res = PIPELINE_MOD.prepare_or_execute_batch(project_root=root, wave=1, execute=True)
            self.assertTrue(exec_res["ok"])
            self.assertTrue(exec_res["tempFileCleaned"])
            self.assertEqual(list(root.rglob("*.json")), [])
            self.assertIn("| 候选已出(1张) |", (root / "project.md").read_text(encoding="utf-8"))

            # Promote S04 candidate into 成品/详情_790xn/ and check M01/M08 derivation reminder
            prom = PIPELINE_MOD.promote_candidate(root, item_id="S04", candidate_file=s04_dir / "候选_01.png")
            self.assertTrue(prom["ok"])
            self.assertEqual(prom["newStatus"], "已定稿")
            self.assertEqual(prom["linkedMainToDerive"], ["M01", "M08"])
            self.assertTrue((root / prom["promotedTo"]).is_file())
            self.assertIn("| 已定稿 |", (root / "project.md").read_text(encoding="utf-8"))

            # If user manually deletes prompt + candidates and keeps final, status stays 已定稿; if user deletes final too, reverts to 待写词
            (root / prom["promotedTo"]).unlink()
            (s04_dir / "候选_01.png").unlink()
            (s04_dir / "prompt.md").unlink()
            PIPELINE_MOD.sync_project_status(root)
            self.assertIn("| 待写词 |", (root / "project.md").read_text(encoding="utf-8"))

    def test_five_section_image_embedded_table_sync_and_ref_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mug"
            _write_sample_project(root)
            (root / "素材" / "飞书画布").mkdir(parents=True, exist_ok=True)
            (root / "素材" / "飞书画布" / "S03_参考.png").write_bytes(b"comp-ref")

            pm_v2 = """# 纯钛马克杯 — 项目总账本

- 飞书源：https://example.feishu.cn/wiki/MockMug
- 默认生图画幅：**9:16 竖版**（纯无字底图，人工后期 PS 排版）

## 二、第 0 批：视觉里程碑设定（定调后锁入 design.md）

| 编号 | 里程碑项 | 画幅 | 状态 | 定稿/参考路径 | 定调重点 |
| --- | --- | --- | --- | --- | --- |
| MS01 | 产品白底身份卡 | 9:16 | 已锁定 | 设定集/白底图/spoon-white.png | 锁产品结构 |

## 三、3:4 主图转化序列（门面点击逻辑与同源裁切对照）

| 编号 | 画布原参考 | 运营原主副标题 & 批注（PS排字直接复制） | 纯无字画面与来源方式 | 当前出图 | 状态 |
| --- | --- | --- | --- | --- | --- |
| M04 | <img src="素材/飞书画布/M04_参考.png" width="110"> | 不易变色 久用如新 | ★由第1批 9:16 母片裁切派生（关联 S03） | — | 待派生 |

## 四、详情页纵向叙事全表（第 1 批（最优先）★主图同源屏 + 第 2 批其余分屏，按阅读顺序顺排）

| 编号 | 批次与关联 | 画布原参考 | 运营原主副标题 & 批注（PS排字直接复制） | 纯无字底图拍法 & PS留白 | 机位景别 | 当前出图 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S02 | 后期排版 | — | 食卫报告 | 纯后期排版 | — | — | 无需生图（后期排版） |
| S03 | **★第1批**（同源 M04） | <img src="素材/飞书画布/S03_参考.png" width="110"> | 不易变色 久用如新 / 钛结晶工艺 | 微距晶体表面 | 掠射平视·微距特写 | — | 待写词 |
"""
            (root / "project.md").write_text(pm_v2, encoding="utf-8")
            _, parsed_rows = PIPELINE_MOD.parse_project_md(root / "project.md")
            by_id = {r.id: r for r in parsed_rows}
            self.assertEqual(by_id["S03"].wave, 1)
            self.assertEqual(by_id["S03"].linked_main, ["M04"])
            self.assertEqual(by_id["S02"].wave, 2)
            self.assertEqual(by_id["M04"].wave, 3)

            # Binding 素材/飞书画布/* as @图N must be blocked loudly
            s03_dir = root / "制作" / "S03_钛耐用"
            s03_dir.mkdir(parents=True)
            bad_prompt = """# S03_钛耐用
- @图1：设定集/白底图/spoon-white.png
- @图2：素材/飞书画布/S03_参考.png

```text
比例：9:16
测试拦截
```
"""
            (s03_dir / "prompt.md").write_text(bad_prompt, encoding="utf-8")
            with self.assertRaises(PIPELINE_MOD.PipelineError) as exc_ctx:
                PIPELINE_MOD.prepare_or_execute_batch(project_root=root, wave=1, execute=False)
            self.assertIn("素材/飞书画布/", str(exc_ctx.exception))

            # Clean prompt + generated candidate image auto-populates 当前出图 <img ... width="110">
            good_prompt = """# S03_钛耐用
- @图1：设定集/白底图/spoon-white.png
- @图2：设定集/里程碑/MS02_kv.png

```text
比例：9:16
@图1：[结构锁死]；@图2：[属性迁移]
微距结晶特写，顶部留白 25%。
```
"""
            (s03_dir / "prompt.md").write_text(good_prompt, encoding="utf-8")
            cand = s03_dir / "候选_01.png"
            cand.write_bytes(b"cand-png")
            PIPELINE_MOD.sync_project_status(root)
            pm_synced = (root / "project.md").read_text(encoding="utf-8")
            self.assertIn('<img src="制作/S03_钛耐用/候选_01.png" width="110">', pm_synced)
            self.assertIn("| 候选已出(1张) |", pm_synced)

    def test_backtick_spaced_paths_person_card_gate_subshot_and_count_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mug_pro"
            _write_sample_project(root)
            (root / "设定集" / "人物身份卡").mkdir(parents=True, exist_ok=True)
            (root / "设定集" / "人物身份卡" / "01_主角模特.png").write_bytes(b"person-card")
            eagle_file = root / "素材" / "实拍原图" / "Eagle Shot With Space 01.jpg"
            eagle_file.write_bytes(b"eagle-jpg")

            # Add S03 row to project.md
            pm = root / "project.md"
            pm.write_text(
                pm.read_text(encoding="utf-8") + "| S03 | **★第1批**（同源 M01） | — | 防烫 | 手握杯 | 平视 | — | 待写词 |\n",
                encoding="utf-8",
            )

            s04_dir = root / "制作" / "S04_钛好舀"
            s04_dir.mkdir(parents=True)
            # Negative mention of 人物正脸 only -> should NOT trigger person card error; backticks & spaced path MUST parse
            neg_only_prompt = """# S04_钛好舀
- `@图1`：`设定集/白底图/spoon-white.png`（[结构锁]）
- `@图2`：`素材/实拍原图/Eagle Shot With Space 01.jpg`（[实拍基底]）

```text
比例：9:16

桌面静物微距，绝无多余物体。
禁止：人物正脸、文字水印。
```
"""
            (s04_dir / "prompt.md").write_text(neg_only_prompt, encoding="utf-8")
            prep_split = PIPELINE_MOD.prepare_or_execute_batch(project_root=root, ids=["S04"], count=2, execute=False)
            self.assertEqual(prep_split["itemsCount"], 2)
            self.assertEqual(prep_split["items"][0]["referenceCount"], 2)
            self.assertEqual([it["outputName"] for it in prep_split["items"]], ["S04_钛好舀/候选_01.png", "S04_钛好舀/候选_02.png"])

            # Positive hand/sleeve description WITHOUT person card -> MUST raise PipelineError
            s03_dir = root / "制作" / "S03_握把"
            s03_dir.mkdir(parents=True)
            missing_person_prompt = """# S03_握把
- @图1：设定集/白底图/spoon-white.png

```text
比例：9:16

右手四指穿握把手，露出真丝袖口。
```
"""
            (s03_dir / "prompt.md").write_text(missing_person_prompt, encoding="utf-8")
            with self.assertRaises(PIPELINE_MOD.PipelineError) as p_err:
                PIPELINE_MOD.prepare_or_execute_batch(project_root=root, ids=["S03"], execute=False)
            self.assertIn("人物身份卡", str(p_err.exception))

            # Sub-shot directory S04-1 should resolve cleanly when --ids S04-1 is passed, without breaking S04 exact match
            sub_dir = root / "制作" / "S04-1_子镜"
            sub_dir.mkdir(parents=True)
            (sub_dir / "prompt.md").write_text(neg_only_prompt, encoding="utf-8")
            self.assertEqual(PIPELINE_MOD._find_matching_work_dir(root, "S04").name, "S04_钛好舀")
            prep_sub = PIPELINE_MOD.prepare_or_execute_batch(project_root=root, ids=["S04-1"], execute=False)
            self.assertEqual(prep_sub["items"][0]["outputName"], "S04-1_子镜/候选_01.png")


if __name__ == "__main__":
    unittest.main()
