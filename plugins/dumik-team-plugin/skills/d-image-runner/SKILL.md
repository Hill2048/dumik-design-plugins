---
name: d-image-runner
description: "仅在用户明确下令生图/出图/重抽/放大/抠图时调用接口或 DesignFlow 执行并保存结果。只写词或改材质不触发执行。"
metadata:
  version: 0.2.0
---

# 图片执行器

本 skill 负责准确传图、调用模型、保存结果与返回执行状态。协作、参考授权范围和结果审阅由项目 `AGENTS.md` 统筹，不在执行器里另设设计判断或展示规则。

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。规则包会登记本 skill `references/` 下的全部文件，再追加本次模型和后处理命中的条件文件；只有命中文件进入当前正文，读取完整规则包后才能提交。缺文件或未读完时不得调用接口。

执行前先运行当前插件目录的 `scripts/compile_reference_pack.ps1 -Skill d-image-runner -Mode <generate|postprocess> -Model <模型名>`，再读取脚本返回的 `output_path`。规则包没有成功生成或没有读完时，不发送请求。

## 会话级自动更新

更新返回新安装目录时，重新定位并读取新目录的本技能、路由及适用参考；不继续使用旧缓存路径。同一会话已检查则不重复运行，恢复上下文不视为新会话。


每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

统一原 `D-image-run` 与 `D-rh` 的执行入口。

## 模式

- `generate`：普通图片生成、改图、单图和独立多候选并发（默认 `banana2.1`，`2K`，`thinkingLevel: high`，超 `6MB` 大图脚本内自动在内存压缩不落项目垃圾）。
- `postprocess`：RunningHub 放大、超分、抠图、去背景和固定工作流后处理。

## 执行规则

- 按 [插件路由](../../assets/agent-skill-routing.md) 区分文字修改与真实执行；项目制多图执行优先通过 `d-project-pipeline` 在 `%TEMP%` 组批次并从 `制作/<编号_名称>/prompt.md` 读取正文；单图追改核对授权后不重做已完成提交。

- 提示词图片引用遵循 [图片引用格式](../../assets/image-reference-format.md)。`@图1` 对应第一张实际输入，具体职责由角色说明决定，不强制是目标图；模型名与 API 字段不改名。

- 用户只要提示词时不调用接口。
- 用户明确生图、改图、放大或后处理时才执行，图片直接落入对应 `制作/<编号_名称>/`（或指定目录）。**默认不写出 `运行记录.json` 与 `运行记录.md`**（零本地运行垃圾），仅基准测试或显式排错时才传 `--write-run-record`。
- **执行模式分流（严禁混用规则）**：
  - **1) DesignFlow 模式（默认，画布在线且未指定直连 API 时）**：
    1. **同提示词多张与跨模型单节点并发**：`x2`/`x4` 必须在单次 `designflow_generate_image` 传 `count: 2..4`（**严禁拆成多个 `count: 1` 节点**）；同提示词跨模型或跨渠道对比直接传 `models: [...]`（1–12 个，支持云端与即梦/LibTV/Flowith 混选并发）。
    2. **多屏批量一次并发**：多组不同提示词直接走一次 `designflow_generate_image({ items: [...] })`（最多 24 组），支持传 `requestId` 幂等防重与 `maxCredits`/`dryRun`；工具默认 `wait: true` 直接返回终态，无需每次手动追加 `designflow_wait_command`（仅返回 `WAIT_TIMEOUT` 时才用 `designflow_wait_command` 续等或 `designflow_query_request` 查原 `requestId`）。多屏预校验可先跑 `build_canvas_pipeline.py --prepare-batch --engine designflow`。
    3. **原图导出落盘**：严禁拿 `designflow_view_image` 预览图当成片；落盘直接调 `designflow_export_image`（传 `assetId` 或 `nodeId` + `outputPath: "<项目>/制作/<编号_名称>/候选_01.png"`）导出无损原图，并用 PIL 核验宽高后再送检；若画布离线或无法走通，再切换 **API 直连模式**。
  - **2) API 直连模式（画布离线或用户明确指定直连 API 时）**：
    1. 优先走 `build_canvas_pipeline.py --engine api --execute` 或 `python scripts/generate_batch_images.py --batch`（经 `%TEMP%\dumik-runs\` 跑完即焚，`Banana2.1` 直连规范见 `references/model-banana2.md`）。
    2. **仅 API 直连模式下**将多候选拆成独立 `count: 1` 任务行并发提交（不串联垫图），因直连 Gemini `:generateContent` 单请求只稳定出 1 张图。
- 使用 `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` 时，必须读取 `references/model-image2.5.md`；用户只说 `image2.5` 时路由到质量优先的 Sunburst。
- 使用 Banana2 / Banana2.1 / Banana Pro 时必须读取 `references/model-banana2.md`。
- `postprocess` 必须完整读取 `references/legacy/D-rh.md`；RunningHub 脚本位于 `scripts/`。
- 没有完成本次 `reference_set` 的读取，停在执行前，不发送请求。
