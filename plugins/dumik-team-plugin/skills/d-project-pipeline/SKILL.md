---
name: d-project-pipeline
description: "项目制图片流水线。把视觉策划、方向抽卡、生图、选片、局部修复和终审串起来；只在用户明确要求批量或自动串跑时使用。"
metadata:
  version: 0.1.0
---

# 项目流水线

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

成功时静默继续。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

这是原 `D-detail-auto` 的项目编排入口，不再让用户直接记忆内部阶段 skill。

## 阶段

1. 用 `d-visual-plan` 固化视觉设定和卖点策略。
2. 用 `d-image-director direction` 运行 pilot 方向抽卡。
3. 用户确认方向后，回写产品级校准，再展开候选。
4. 用 `d-image-runner generate` 独立并发生成。
5. 选片、自检和局部偏差交给 `d-image-director repair`，需要时运行局部切贴脚本。
6. 终审通过后交付；三个闸门（方向、选片、终审）必须真实停等用户。

只在用户明确说项目制、批量、自动串跑或 Agent 模式时进入；普通单图任务回到 `d-image-director`。

完整 run-state、pilot、校准回写和批量规则保存在 [references/legacy/D-detail-auto.md](references/legacy/D-detail-auto.md)。
