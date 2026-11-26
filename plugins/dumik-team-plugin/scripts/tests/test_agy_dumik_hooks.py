from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = PLUGIN_ROOT / "hooks.json"
HOOK_SCRIPT = PLUGIN_ROOT / "hooks" / "agy_dumik_hooks.py"

SPEC = importlib.util.spec_from_file_location("agy_dumik_hooks_test_mod", HOOK_SCRIPT)
assert SPEC and SPEC.loader
HOOKS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HOOKS
SPEC.loader.exec_module(HOOKS)


class AgyDumikHooksTests(unittest.TestCase):
    def test_hooks_json_registers_expected_events(self):
        data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        cfg = data["dumik-project-harness"]
        self.assertEqual(set(cfg.keys()), {"SessionStart", "PreInvocation", "Stop"})
        self.assertIn("agy_dumik_hooks.py", cfg["SessionStart"][0]["command"])
        self.assertIn("agy_dumik_hooks.py", cfg["PreInvocation"][0]["command"])
        self.assertIn("agy_dumik_hooks.py", cfg["Stop"][0]["command"])

    def test_non_dumik_workspace_is_neutral_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            res_start = HOOKS.dispatch_hook({"hookEventName": "SessionStart", "cwd": tmp, "workspacePaths": [tmp]})
            self.assertEqual(res_start, {"injectSteps": []})
            res_pre = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": "c1",
                "lastUserInput": "S04 开始生图",
                "cwd": tmp,
            })
            self.assertEqual(res_pre, {"injectSteps": []})
            res_stop = HOOKS.dispatch_hook({
                "hookEventName": "Stop",
                "terminationReason": "NO_TOOL_CALL",
                "continuationActive": False,
                "cwd": tmp,
            })
            self.assertEqual(res_stop, {"decision": "stop"})

    def test_dumik_project_session_preinvocation_and_stop_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "钛壶项目"
            for d in ("设定集/人物身份卡", "制作/S04_首屏", "成品", "素材"):
                (root / d).mkdir(parents=True, exist_ok=True)
            (root / "设定集" / "人物身份卡" / "01_主角.png").write_bytes(b"img")
            (root / "design.md").write_text("# 视觉宪法\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("@[design.md](design.md)\n", encoding="utf-8")
            (root / "project.md").write_text(
                "| 编号 | 批次 | 画面意图 | 状态 |\n"
                "| --- | --- | --- | --- |\n"
                "| S04 | 第1批 | 满壶倒茶 | 待写词 |\n",
                encoding="utf-8",
            )

            # SessionStart summarizes state & byte count
            start_out = HOOKS.dispatch_hook({"hookEventName": "SessionStart", "cwd": str(root)})
            msg = start_out["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("钛壶项目", msg)
            self.assertIn("待写词:1", msg)
            self.assertIn("上限 24000B", msg)

            # PreInvocation: general chatter / archiving / git push is completely silent (0 tokens)
            conv = f"test-{root.name}-{id(self)}"
            for general_input in (
                "推送github",
                "开始",
                "> 方案 C：女儿身份卡_方案C_奶白开衫.jpg\n这个作为女孩设定",
                "女儿身份卡_方案C 这个作为女孩设定",
            ):
                silent_out = HOOKS.dispatch_hook({
                    "hookEventName": "PreInvocation",
                    "conversationId": conv,
                    "lastUserInput": general_input,
                    "cwd": str(root),
                })
                self.assertEqual(silent_out, {"injectSteps": []}, msg=f"Expected silence on: {general_input}")

            # Entering prompt mode with S04 injects compact route + S04 row, without static boilerplate
            forbid_out = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "帮我改 S04 提示词，先不要生成",
                "cwd": str(root),
            })
            forbid_msg = forbid_out["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("禁止生图", forbid_msg)
            self.assertIn("S04（待写词）", forbid_msg)
            self.assertNotIn("人物身份卡", forbid_msg)

            # Same-turn repeat is silent
            repeat_out = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "帮我改 S04 提示词，先不要生成",
                "cwd": str(root),
            })
            self.assertEqual(repeat_out, {"injectSteps": []})

            # Consecutive turn in same route+auth and unchanged S04 row is ALSO silent
            follow_up_same = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "把 S04 提示词里的光影再调柔一点，先不要生成",
                "cwd": str(root),
            })
            self.assertEqual(follow_up_same, {"injectSteps": []})

            # Authorizing execution emits ONLY the changed route/auth, without re-dumping unchanged S04 row
            auth_out = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "S04 开始生图",
                "cwd": str(root),
            })
            auth_msg = auth_out["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("已授权可执行", auth_msg)
            self.assertNotIn("S04（待写词）", auth_msg)

            # Once S04 status updates in project.md, mentioning S04 again injects the updated row delta
            (root / "project.md").write_text(
                "| 编号 | 批次 | 画面意图 | 状态 |\n"
                "| --- | --- | --- | --- |\n"
                "| S04 | 第1批 | 满壶倒茶 | 候选已出(2张) |\n",
                encoding="utf-8",
            )
            updated_row_out = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "看看 S04 改图提示词",
                "cwd": str(root),
            })
            updated_msg = updated_row_out["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("S04（候选已出(2张)）", updated_msg)

            # Badge/emblem material wash routes to d-badge-wash (and chains runner only when authorized)
            badge_plan = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "帮我清洗一下这个徽章，先转纯色平面图再重构材质",
                "cwd": str(root),
            })
            badge_plan_msg = badge_plan["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("d-badge-wash", badge_plan_msg)
            self.assertIn("仅文本/禁调接口", badge_plan_msg)

            badge_run = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "徽章按A案开始生图",
                "cwd": str(root),
            })
            badge_run_msg = badge_run["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("d-badge-wash -> d-image-runner", badge_run_msg)
            self.assertIn("已授权可执行", badge_run_msg)

            # Stop blocks when unsynced candidate or .pytest_cache exists, stops cleanly after cleanup
            (root / "制作" / "S04_首屏" / "候选_01.png").write_bytes(b"cand")
            (root / ".pytest_cache").mkdir()
            stop_block = HOOKS.dispatch_hook({
                "hookEventName": "Stop",
                "terminationReason": "NO_TOOL_CALL",
                "continuationActive": False,
                "cwd": str(root),
            })
            self.assertEqual(stop_block["decision"], "continue")
            self.assertIn(".pytest_cache", stop_block["reason"])
            self.assertIn("S04", stop_block["reason"])

            # continuationActive=True never loops
            stop_cont = HOOKS.dispatch_hook({
                "hookEventName": "Stop",
                "terminationReason": "NO_TOOL_CALL",
                "continuationActive": True,
                "cwd": str(root),
            })
            self.assertEqual(stop_cont, {"decision": "stop"})


if __name__ == "__main__":
    unittest.main()
