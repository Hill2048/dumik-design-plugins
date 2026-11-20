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

            # PreInvocation distinguishes forbidden vs authorized and deduplicates repeat step in same turn
            conv = f"test-{root.name}-{id(self)}"
            forbid_out = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "帮我改 S04 提示词，先不要生成",
                "cwd": str(root),
            })
            forbid_msg = forbid_out["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("禁止生图", forbid_msg)
            self.assertIn("S04（待写词）", forbid_msg)

            repeat_out = HOOKS.dispatch_hook({
                "hookEventName": "PreInvocation",
                "conversationId": conv,
                "lastUserInput": "帮我改 S04 提示词，先不要生成",
                "cwd": str(root),
            })
            self.assertEqual(repeat_out, {"injectSteps": []})

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
