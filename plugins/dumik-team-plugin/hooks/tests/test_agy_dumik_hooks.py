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

    def test_prop_bible_hook_reminds_only_when_unfilled_after_milestone(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.md").write_text(
                "| 编号 | 名称 | 画幅 | 状态 |\n| --- | --- | --- | --- |\n| MS02 | 首屏KV | 9:16 | 已锁定 |\n",
                encoding="utf-8",
            )
            (root / "design.md").write_text(
                "## 四、置景摆件库与饮品/食材排期\n### 1. 风格摆件库\n| 序号 | 摆件名称与分组 | 材质 |\n| --- | --- | --- |\n| 01 | 待规划（杯垫） | 待填 |\n",
                encoding="utf-8",
            )
            self.assertTrue(hooks.has_unfilled_prop_bible(root))

            # Once filled with real prop, reminder clears
            (root / "design.md").write_text(
                "## 四、置景摆件库与饮品/食材排期\n### 1. 风格摆件库\n| 序号 | 摆件名称与分组 | 材质 |\n| --- | --- | --- |\n| 01 | 焦糖真皮杯垫 | 焦糖粒面真皮 |\n",
                encoding="utf-8",
            )
            self.assertFalse(hooks.has_unfilled_prop_bible(root))

    def test_food_drink_stylist_route_matches(self):
        res = hooks.classify_user_intent("帮我做几款高写实的饮品设计和食材造型", Path("."))
        self.assertEqual(res["skill"], "d-food-drink-stylist")
        self.assertEqual(res["auth"], "unconfirmed")

    def test_brand_badge_route_matches(self):
        res = hooks.classify_user_intent("帮我重新设计一个我们品牌六边形的3D徽章", Path("."))
        self.assertEqual(res["skill"], "d-brand-badge")
        self.assertEqual(res["auth"], "unconfirmed")

        res_exec = hooks.classify_user_intent("开始生图，生成品牌扁六边形徽章", Path("."))
        self.assertEqual(res_exec["skill"], "d-brand-badge -> d-image-runner")
        self.assertEqual(res_exec["auth"], "authorized")


if __name__ == "__main__":
    unittest.main()
