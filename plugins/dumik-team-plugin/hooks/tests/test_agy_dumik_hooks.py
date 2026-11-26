import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR))
import agy_dumik_hooks as hooks


class AgyDumikHooksRoutingTests(unittest.TestCase):
    def test_model_plus_concurrency_authorizes_execution(self):
        text = "重新构图两个杯子的距离不要太远，不然不好排版，banana2.1、pro并发x2，桌面放一个小摆件不然太空了"
        res = hooks.classify_user_intent(text, Path("."))
        self.assertEqual(res["auth"], "authorized")
        self.assertIn("d-image-runner", res["skill"])

    def test_typo_re_generate_authorizes_execution(self):
        res = hooks.classify_user_intent("不用扩，重新升成，并且统一证书的朝向", Path("."))
        self.assertEqual(res["auth"], "authorized")

    def test_explicit_forbid_overrides_model_mentions(self):
        res = hooks.classify_user_intent("banana2.1 并发x2 先不生成，只写提示词", Path("."))
        self.assertEqual(res["auth"], "forbidden")

    def test_pre_invocation_injects_anti_drift_and_compact_nudge(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "design.md").write_text("# Design\n", encoding="utf-8")
            (root / "project.md").write_text("# Project\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")

            fake_state = {
                "conv-long": {
                    "turn_sig": "old",
                    "last_route_key": "",
                    "seen_rows": {},
                    "warned_bytes": False,
                    "turn_count": 24,
                }
            }
            with mock.patch.object(hooks, "_load_hook_state", return_value=fake_state), mock.patch.object(
                hooks, "_save_hook_state"
            ):
                out = hooks.handle_pre_invocation(
                    {
                        "cwd": str(root),
                        "conversationId": "conv-long",
                        "lastUserInput": "S15 氛围丢了，重新生成",
                    }
                )
            msgs = [s["systemMessage"]["systemMessage"] for s in out.get("injectSteps", [])]
            combined = "\n".join(msgs)
            self.assertIn("/compact", combined)
            self.assertIn("防漂移底线", combined)


if __name__ == "__main__":
    unittest.main()
