---
name: d-image-director
version: 0.2.0
description: "选片后的产品细节修复质量门（产品外扩切图 + 局部高对比色块破惰性 + 外扩边羽化无损贴回）。先分诊 passed / blocked / reroll；只修局部漂移的把手、盖子、五金、品牌区、材质、接缝。默认只出诊断、色块预览与修复词，不直接调付费生图接口。"
---

# 产品细节修复（外扩切图 + 局部色块法）

## 核心原理

1. **产品外扩切图（最大化 AI 分辨率）**：以 `product_box` 向外扩展 `20%` 并吸附到标准比例池（`1:1 / 3:4 / 4:3 / 2:3 / 3:2 / 9:16 / 16:9`），让 AI 的 2K 像素全部集中在产品与细节上，且外扩边界落在背景平滑区，贴回无接缝。
2. **局部涂高对比色块（打破模型照抄惰性）**：在产品外扩图上，用实心高对比色块（默认荧光洋红 `#FF00FF`，避开产品固有色时可改 `#00FF00`）覆盖具体不对的局部 `defect_boxes`，抹除旧的错误结构先验，强迫模型严格对照 `@图2`（`设定集/白底图/`）重绘。
3. **外扩边羽化无损贴回（默认输出分层 `.psd`，也支持 `.tif` / `.png`）**：修好后按记录的 `crop_box` 自动输出**双图层可编辑蒙版 PSD**（底层「原图」100% 原像素 + 顶层「局部修复」自动对齐并附带可编辑羽化图层蒙版，进 Photoshop 直接微调蒙版或开关对比；也可指定 `--format tif` 输出无损 LZW TIFF 或 `.png`）。
4. **零项目垃圾**：切片、带色块待修图、联系表与任务 JSON 全部落在系统 `%TEMP%\dumik-runs\repair-*`，项目内不留任何 `.json` 队列。

## 只做三件事

1. 先分诊：`passed`（直接定稿）/ `blocked`（仅局部漂移，进修复）/ `reroll`（大轮廓/比例/SKU 错，回抽卡重出）
2. `blocked` 才修：标出 `product_box` 与 `defect_boxes` → 切外扩图 + 填色块 → 出预览/联系表确认 → 写极简修复词（≤250 字）
3. 授权出图并贴回复核：最多两轮

## 单张修复流程（`scripts/repair/mask_repair.py`）

1. **对照 `设定集/白底图/` 找差异**：列出可见细节偏差及像素坐标（`product_box` + 1~N 个 `defect_boxes`）。
2. **准备外扩色块图与预览**（不调付费接口）：
   ```powershell
   python scripts/repair/mask_repair.py prepare-single `
     --image "<待修原整图>" --white-ref "<设定集/白底图/基准图>" `
     --product-box X1 Y1 X2 Y2 --defect-box DX1 DY1 DX2 DY2 `
     --defect-desc "按白底图还原扁平 D 型一体焊把与倒角"
   ```
   将产出的 `*_preview.png`（左原切片 / 右涂色块切片）与精简修复词交用户确认。
3. **授权发包生图**：用户明确下令「开始修复 / 出图」后，交 `d-image-runner`（默认 DesignFlow MCP `2K · x2`，`@图1` 涂色块外扩图 + `@图2` 白底基准图，显式传入脚本返回的 `ratio`）；**产品修复模型优先级固定为：`即梦 5.5`（`seedream-5.5`）＞ `即梦 5.0 Pro`（`seedream-5-pro`）＞ `Banana 2.1`（`banana2.1`）**（首选不可用时按序降级）。
4. **无损贴回整图并清理 `%TEMP%`**：
   ```powershell
   python scripts/repair/mask_repair.py paste-single `
     --meta "<temp>/*_meta.json" --repaired "<AI修好的外扩图>" `
     --out "<项目>/制作/<编号_名称>/<原名>_repaired.png" --cleanup
   ```

## 批量修复流程（项目制多屏选片后）

1. **批量分诊**：扫完当前批次候选图，将 `blocked` 项与每张图的 `product_box`、`defect_boxes`、`defect_desc` 写入 `%TEMP%\dumik-runs\repair-manifest.json`（`passed` 与 `reroll` 自动跳过）。
2. **一键切图涂色块 + 生成联系表**：
   ```powershell
   python scripts/repair/mask_repair.py prepare-batch `
     --manifest "%TEMP%\dumik-runs\repair-manifest.json" --project-root "<项目根目录>"
   ```
   先将 `contact_sheet.png` 给用户 5 秒核对每张图的外扩范围与色块覆盖是否准确。
3. **一次并发出图**：用户确认并下令「开始修复」后，直接读取 `%TEMP%\...\designflow_items.json` 经 `d-image-runner` 走 DesignFlow MCP `items[]` 并发跑图（离线走直连并发）。
4. **一键批量无损贴回 + 清理**：
   ```powershell
   python scripts/repair/mask_repair.py paste-batch `
     --workdir "<temp>/repair-xxx" --repaired-dir "<AI修好图目录>" --cleanup
   ```
   完成后跑 `build_canvas_pipeline.py --status` 刷新 `project.md`，再交 `d-consistency-check` 做复核。
