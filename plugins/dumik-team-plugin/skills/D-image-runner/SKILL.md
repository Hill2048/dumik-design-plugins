---
name: D-image-runner
description: "图片执行总入口。统一普通生图/改图、多候选并发、RunningHub 放大、超分、抠图和去背景；只在用户明确要求执行时调用接口。"
metadata:
  version: 0.1.1
---

# 图片执行器

统一原 `D-image-run` 与 `D-rh` 的执行入口。

## 模式

- `generate`：普通图片生成、改图、单图和独立多候选并发。上游提示词来自 `D-image-director`。
- `postprocess`：RunningHub 放大、超分、抠图、去背景和固定工作流后处理。

## 执行规则

- 用户只要提示词时不调用接口。
- 用户明确生图、改图、放大或后处理时才执行，并保存提交状态和结果。
- 多候选拆成独立 `count: 1` 任务，不把候选串联垫图。
- `generate` 资料见 `references/legacy/D-image-run.md`；脚本位于 `scripts/`。
- 使用 `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` 时，读取 `references/model-image2.5.md`；用户只说 `image2.5` 时路由到质量优先的 Sunburst。
- `postprocess` 资料见 `references/legacy/D-rh.md`；RunningHub 脚本位于 `scripts/`。
