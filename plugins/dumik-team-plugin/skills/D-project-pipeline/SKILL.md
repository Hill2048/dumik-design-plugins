---
name: D-project-pipeline
description: "项目制图片流水线。把视觉策划、方向抽卡、生图、选片、局部修复和终审串起来；只在用户明确要求批量或自动串跑时使用。"
metadata:
  version: 0.1.0
---

# 项目流水线

这是原 `D-detail-auto` 的项目编排入口，不再让用户直接记忆内部阶段 skill。

## 阶段

1. 用 `D-visual-plan` 固化视觉设定和卖点策略。
2. 用 `D-image-director direction` 运行 pilot 方向抽卡。
3. 用户确认方向后，回写产品级校准，再展开候选。
4. 用 `D-image-runner generate` 独立并发生成。
5. 选片、自检和局部偏差交给 `D-image-director repair`，需要时运行局部切贴脚本。
6. 终审通过后交付；三个闸门（方向、选片、终审）必须真实停等用户。

只在用户明确说项目制、批量、自动串跑或 Agent 模式时进入；普通单图任务回到 `D-image-director`。

完整 run-state、pilot、校准回写和批量规则保存在 [references/legacy/D-detail-auto.md](references/legacy/D-detail-auto.md)。
