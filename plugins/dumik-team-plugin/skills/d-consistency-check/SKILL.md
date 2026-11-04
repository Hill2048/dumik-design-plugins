---
name: d-consistency-check
description: "对比原产品图与 AI 生成图，按项输出一致/不一致/无法判断三态；用于电商产品结构验收与出图审稿。不写提示词、不调用生图接口；策略交 d-visual-plan，写修复指令交 d-image-director，实际出图交 d-image-runner。"
metadata:
  version: 0.1.0
---

# 产品一致性验收

本 skill 只做「原图 vs 生成图」的结构与外观核对，输出可执行的三态结论。不承担写词、策划或调接口。

## 参考文件硬门槛

本 skill 必须遵守 [参考文件读取硬门槛](../../assets/reference-loading-protocol.md)。进入本 skill 后读取 `references/checklist.md`；有 PowerShell 时可编译规则包，**Grok Bot / Linux** 若无 `compile_reference_pack.ps1`，直接 `Read` 本目录命中参考即可，不得跳过 checklist。

## 会话级自动更新

每个会话首次触发任意 DUMIK skill 时，Windows 环境可先运行插件根目录 `scripts/update_dumik_plugin.ps1`（同会话不重复）。**Grok Bot / Linux** 跳过该脚本，按宿主方式更新插件。更新不代表授权生图。

## 输入

- **原图**：产品白底、结构确认图或用户指定的结构真源；统一 `@图N`（见 [图片引用格式](../../assets/image-reference-format.md)）。
- **生成图**：待验收的 AI 结果，同样用 `@图N` 标明。
- 可附：用户关心的部件名单；未指定则按下方清单全检。

缺少原图或生成图时停止，说明缺什么，不凭记忆验收。

## 检查清单

对每一项给出且仅给出三态之一：**一致** / **不一致** / **无法判断**。

1. 外形比例与外轮廓
2. 接口数量与相对位置
3. 按键 / 旋钮 / 开关
4. 材质倾向（金属/塑料/木材等，非风格形容词）
5. Logo / 丝印占位（不要求认清未成像文字的具体字形）
6. 颜色固有色（相对原图，允许曝光差异但不得换色相家族）

细则与输出表见 `references/checklist.md`。

## 硬规则

- 角度、遮挡、分辨率导致看不清 → **无法判断**，禁止猜成「一致」或「不一致」。
- 「差不多」「感觉对」禁止；不一致须指出可见差异（哪一部位、怎样不同）。
- 不写 Prompt、不改策略、不调用 `d-image-runner`。
- 审美好坏、文案排版、氛围是否高级：**不在本 skill 范围**，除非用户明确要求并另说标准。

## 输出

1. **分项表**：检查项 | 状态 | 一句话证据（不一致/无法判断必填）
2. **总判**：通过（无「不一致」）/ 不通过（任一「不一致」）/ 受限通过（无「不一致」但有关键项「无法判断」）
3. **交接建议**（仅建议，不自动执行）：
   - 有「不一致」→ `d-image-director` 的 `repair` 或 `edit` 写修复指令
   - 通过且用户还要继续出图 → 再交 `d-image-runner`（须用户明确要求）
   - 策略/卖点问题 → `d-visual-plan`

## 模式资料

- 必读：`references/checklist.md`
- 路由：`../../assets/agent-skill-routing.md` 中 `image.review`
