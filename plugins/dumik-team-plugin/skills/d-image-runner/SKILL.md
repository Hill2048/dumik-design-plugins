---
name: d-image-runner
description: "图片执行总入口。统一普通生图/改图、多候选并发、RunningHub 放大、超分、抠图和去背景；只在用户明确要求执行时调用接口。"
metadata:
  version: 0.1.2
---

# 图片执行器

本 skill 负责准确传图、调用模型、保存结果与返回执行状态。协作、参考授权范围和结果审阅由项目 `AGENTS.md` 统筹，不在执行器里另设设计判断或展示规则。

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一原 `D-image-run` 与 `D-rh` 的执行入口。

## 模式

- `generate`：普通图片生成、改图、单图和独立多候选并发。上游提示词来自 `d-image-director`。
- `postprocess`：RunningHub 放大、超分、抠图、去背景和固定工作流后处理。

## 执行规则

- 提示词图片引用遵循 [图片引用格式](../../assets/image-reference-format.md)。核对 `@图1` 对应主图、后续编号对应实际参考图顺序；模型名与 API 字段不改名。

- 用户只要提示词时不调用接口。
- 用户明确生图、改图、放大或后处理时才执行，并保存提交状态和结果。
- 多候选拆成独立 `count: 1` 任务，不把候选串联垫图。
- `generate` 资料见 `references/legacy/D-image-run.md`；脚本位于 `scripts/`。
- 使用 `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` 时，读取 `references/model-image2.5.md`；用户只说 `image2.5` 时路由到质量优先的 Sunburst。
- `postprocess` 资料见 `references/legacy/D-rh.md`；RunningHub 脚本位于 `scripts/`。
