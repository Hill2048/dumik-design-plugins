---
name: d-image-runner
description: "图片执行总入口。统一普通生图/改图、多候选并发、RunningHub 放大、超分、抠图和去背景；只在用户明确要求执行时调用接口。"
metadata:
  version: 0.1.1
---

# 图片执行器

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

成功时静默继续。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一原 `D-image-run` 与 `D-rh` 的执行入口。

## 模式

- `generate`：普通图片生成、改图、单图和独立多候选并发。上游提示词来自 `d-image-director`。
- `postprocess`：RunningHub 放大、超分、抠图、去背景和固定工作流后处理。

## 执行规则

- 用户只要提示词时不调用接口。
- 用户明确生图、改图、放大或后处理时才执行，并保存提交状态和结果。
- 多候选拆成独立 `count: 1` 任务，不把候选串联垫图。
- `generate` 资料见 `references/legacy/D-image-run.md`；脚本位于 `scripts/`。
- 使用 `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` 时，读取 `references/model-image2.5.md`；用户只说 `image2.5` 时路由到质量优先的 Sunburst。
- `postprocess` 资料见 `references/legacy/D-rh.md`；RunningHub 脚本位于 `scripts/`。
