---
name: d-project-pipeline
description: "使用 build_canvas_pipeline.py 做 --status 状态校准、--prepare-batch 校验、%TEMP% 批量出图与 --promote 定稿归档。单图写词交 d-image-director。"
metadata:
  version: 0.2.1
---

# 项目流水线

所有任务行中的图片引用遵循 [图片引用格式](../../assets/image-reference-format.md)，统一为 `@图1` 等；每条任务单独核对图片顺序，不沿用另一任务的编号映射。

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。规则包会登记本 skill `references/` 下的全部文件，再追加当前项目状态和任务命中的导演/Runner 规则；只有命中文件进入当前正文，读取完整规则包后才能创建任务行、推进状态、提交执行或恢复断点。

进入流水线前先运行当前插件目录的 `scripts/compile_reference_pack.ps1 -Skill d-project-pipeline -Mode <image|canvas|video|mixed>`，再读取脚本返回的 `output_path`。导演和 Runner 的任务包仍需按各自 skill 重新编译，不能把流水线包当成执行包。

## 会话级自动更新

更新返回新安装目录时，重新定位并读取新目录的本技能、路由及适用参考；不继续使用旧缓存路径。同一会话已检查则不重复运行，恢复上下文不视为新会话。


每个会话首次触发任意 DUMIK skill 时，先运行当前 `SKILL.md` 所在目录向上两级的 `scripts/update_dumik_plugin.ps1`；无论成功或失败，本会话后续 DUMIK skill 都不重复运行。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<插件根目录>\scripts\update_dumik_plugin.ps1"
```

返回 `current` 或 `updated` 时静默继续；返回 `skipped` 表示保留了本地定制、未拉取远端或重装，不得称为已更新。同一会话只提示一次“已保留本地定制，本次跳过自动更新”，继续任务，不自动提交、暂存或回退改动。失败时只提示 `本次未能自动更新 DUMIK Team Plugin，将按当前本地版本继续。`，随后继续当前任务。此动作只维护本地插件，不代表用户授权图片或视频生成，也不改变费用确认与批量闸门。

本 skill 提供批量组织与断点恢复方法，不是项目总控。策略、确认节点、反馈范围和交付标准由项目 `AGENTS.md` 与当前任务给定。

## 编排方法（无状态调度 + 零本地 JSON 尾气）

1. **以根目录 `project.md` 与磁盘真实文件为唯一真相**：严禁在项目目录内生成 `run-state.json`、`wave*.json` 或 `运行记录.json/.md`。随时可用 `scripts/build_canvas_pipeline.py --project-root <项目> --status` 扫描 `制作/<编号_名称>/prompt.md`、候选图、`设定集/里程碑/` 与 `成品/`，自动校准 `project.md` 状态列。
2. **仅读取已写好的 `制作/<编号_名称>/prompt.md`**：禁止用草稿偷跑接口；若某批缺少 `prompt.md`，先交 `d-image-director` 编写最新完整纯无字底图提示词并就地覆盖写入 `prompt.md`。
3. **双模式无状态批量执行（禁止项目内落盘队列）**：仅当用户明确下令「开始生图 / 出图 / 批量跑图」时执行：
   - **DesignFlow 模式（默认，画布在线）**：先跑 `scripts/build_canvas_pipeline.py --project-root <项目> --prepare-batch --engine designflow --wave <N> --count <1-4>`（若同屏要多模型对比，传 `--image-models banana2.1,bananapro`）校验 `prompt.md` 与人物卡并生成 `designflowItems`（每屏仅生成 1 条 item，保留单节点 `count` 与 `models: [...]`；严禁把同词多模型拆成多行或多个节点），交 Agent 一次调 `designflow_generate_image({ items: [...] })` 并发跑图；完成后用 `designflow_export_image` 落盘，再跑 `--status` 刷新 `project.md`。
   - **API 直连模式（离线或指定直连）**：跑 `--execute --engine api` 经系统 `%TEMP%\dumik-runs\` 拆 `count: 1` 并发调 `d-image-runner`，结束后立即删除临时 JSON 并自动刷新 `project.md`。
4. **选片验收与外扩色块局部修复（单张/批量）**：候选图生成后先交 `d-consistency-check` 对照 `设定集/白底图/` 做三态验收；判定 `blocked`（整体构图光影已过关、仅局部产品细节漂移）时，交 `d-image-director` (`repair` 模式) 跑 `scripts/repair/mask_repair.py`（产品框外扩 20% 吸附比例池 + 偏差局部实心涂高对比色块，全部落 `%TEMP%\dumik-runs\`），向用户展示预览/联系表确认后，再由 `d-image-runner` 走 DesignFlow MCP 单张或 `items[]` 批量并发出图（**产品修复优先模型：`即梦 5.5` ＞ `即梦 5.0 Pro` ＞ `Banana 2.1`**），最后 `paste-single / paste-batch --cleanup` 默认输出分层可编辑蒙版 `.psd`（支持 `.tif`/`.png`）并 `--status` 刷新 `project.md`。
5. **定稿晋升归档**：候选图（或修复验收通过图）确认后，使用 `--promote <编号> --file <候选图>` 复制归档进 `设定集/里程碑/`（`MS*`）或 `成品/`（`S*`/`M*`/`E*`），同时刷新状态并在第 1 批详情定稿时提醒同步派生关联 `3:4` 主图。

按 [插件路由](../../assets/agent-skill-routing.md) 判断是否需要跨步骤执行编排，不凭“项目制、批量、Agent”单个词触发。单图追改就地覆盖 `制作/<编号_名称>/prompt.md`，详见 [任务状态合同](../../assets/task-state-contract.md)。

无状态流水线脚本与定稿晋升用法见 [references/canvas-auto-pipeline.md](references/canvas-auto-pipeline.md)（脚本 `scripts/build_canvas_pipeline.py`）；旧断点格式见 `references/legacy/D-detail-auto.md`（仅 `-Mode legacy` 按需读取）。实际调图时导演与 runner 规则继续按需读取。
